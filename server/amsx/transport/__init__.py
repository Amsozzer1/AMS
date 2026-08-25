"""transport — MqttBus, PrinterLink, ClusterLink, FtpClient (non-sentient plumbing).

The transport layer is dumb pipe: it moves bytes between our Mosquitto broker / the printer's
local MQTT endpoint and the rest of the Brain. It makes **no decisions** (single-brain rule).

⚠️ PHASE-0 status: we do NOT have a real printer on the LAN yet, so every *real* network path
here is a stub that raises ``NotImplementedError`` with a pointer at the v0.2 keystone spike
(docs/09-filament-change-protocol.md → "Still UNVERIFIED"). The **shape** is real, and a
simulator path (``SimulatedPrinterLink``) lets the rest of v0 develop and be tested without
hardware. When the v0.2 spike confirms a topic/payload, the finding replaces the matching
``# PHASE-0: verify`` comment — we never fabricate a "confirmed" payload here.
"""

from __future__ import annotations

import asyncio
import ftplib
import json
import logging
import ssl
import threading
from collections.abc import Awaitable, Callable

from amsx.types import FtpClient, PrinterId, PrinterLink, Report, ReportHandler

log = logging.getLogger("amsx.transport")

# PrinterLink / FtpClient (the seams) and Report / ReportHandler (the wire shapes) are defined
# in amsx.types and re-exported here, so callers can keep importing them alongside the concrete
# MqttPrinterLink / FtpsClient that implement them.
__all__ = [
    "FtpClient",
    "FtpsClient",
    "MqttBus",
    "MqttPrinterLink",
    "PrinterLink",
    "Report",
    "ReportHandler",
    "SimulatedFtpClient",
    "SimulatedPrinterLink",
]

TopicHandler = Callable[[str, bytes], Awaitable[None]]


# --------------------------------------------------------------------------------------------
# MqttBus — thin wrapper over paho-mqtt (our broker AND the printer's local endpoint)
# --------------------------------------------------------------------------------------------
class MqttBus:
    """Thin async-shaped wrapper over paho-mqtt.

    Shape mirrors docs/10 (``publish(topic, payload)`` / ``subscribe(topic, handler)``).
    The real ``connect()`` is a PHASE-0 stub: TLS-on-8883 + access-code auth to a Bambu
    printer is exactly the thing the v0.2 spike exists to confirm. Tests use the simulator
    paths (``SimulatedPrinterLink``) instead of standing up a broker.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8883) -> None:
        self.host = host
        self.port = port
        self._connected = False
        # Local-only subscription table so the simulator can route without a broker.
        self._subs: dict[str, list[TopicHandler]] = {}
        self._client: object | None = None  # paho Client once connected (real path)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connect_rc: object | None = None

    def connect(self, *, access_code: str | None = None) -> None:
        """Connect to a Bambu printer's local MQTT endpoint over TLS.

        v0.2 spike (read path verified live against an A1): the printer runs its own broker on
        TLS:8883 with username ``bblp`` and the LAN access code as the password. The cert is
        self-signed, so verification is disabled (LAN-only, access-code-gated). paho's network
        loop runs on its own thread; ``on_message`` hands each payload back to the asyncio loop
        via ``run_coroutine_threadsafe``. Blocks until CONNACK (or raises on auth/timeout).
        """
        import paho.mqtt.client as mqtt

        self._loop = asyncio.get_running_loop()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set("bblp", access_code or "")
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

        connected = threading.Event()

        def on_connect(_c, _u, _flags, reason_code, _props) -> None:
            self._connect_rc = reason_code
            if not reason_code.is_failure:
                self._connected = True
                for topic in self._subs:  # (re)subscribe after a connect/reconnect
                    client.subscribe(topic)
            connected.set()

        def on_message(_c, _u, msg) -> None:
            handlers = self._subs.get(msg.topic, [])
            loop = self._loop
            if loop is None:
                return
            for handler in handlers:
                asyncio.run_coroutine_threadsafe(handler(msg.topic, msg.payload), loop)

        def on_disconnect(_c, _u, _flags, reason_code, _props) -> None:
            self._connected = False
            log.warning("MQTT %s:%d disconnected (%s)", self.host, self.port, reason_code)

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        client.connect(self.host, self.port, keepalive=60)
        client.loop_start()
        self._client = client

        if not connected.wait(timeout=10.0):
            client.loop_stop()
            raise TimeoutError(f"MQTT connect to {self.host}:{self.port} timed out (no CONNACK)")
        rc = self._connect_rc
        if rc is not None and getattr(rc, "is_failure", False):
            client.loop_stop()
            raise ConnectionError(
                f"MQTT connect to {self.host}:{self.port} refused: {rc} "
                "(check access code / LAN-mode enabled)"
            )
        log.info("MQTT connected to %s:%d", self.host, self.port)

    def disconnect(self) -> None:
        client = self._client
        if client is None:
            return
        client.loop_stop()  # type: ignore[attr-defined]
        client.disconnect()  # type: ignore[attr-defined]
        self._connected = False

    async def publish(self, topic: str, payload: bytes) -> None:
        """Publish a raw payload to a topic.

        Real path: hand off to paho. Falls back to in-process delivery when no client is
        connected (keeps the bus usable without a broker, e.g. in unit tests).
        """
        client = self._client
        if client is not None:
            client.publish(topic, payload)  # type: ignore[attr-defined]
            return
        for handler in self._subs.get(topic, []):
            await handler(topic, payload)

    def subscribe(self, topic: str, handler: TopicHandler) -> None:
        """Register a handler for a topic, and subscribe on the broker if already connected."""
        self._subs.setdefault(topic, []).append(handler)
        client = self._client
        if client is not None and self._connected:
            client.subscribe(topic)  # type: ignore[attr-defined]

    @property
    def connected(self) -> bool:
        return self._connected


# --------------------------------------------------------------------------------------------
# PrinterLink — one per printer; the request/report seam
# --------------------------------------------------------------------------------------------
class MqttPrinterLink:
    """Real PrinterLink over MQTT. PHASE-0 stub — shape only, no live transport yet."""

    def __init__(self, bus: MqttBus, printer_id: PrinterId, serial: str) -> None:
        self.bus = bus
        self.printer_id = printer_id
        self.serial = serial
        self._handlers: list[ReportHandler] = []

    @property
    def request_topic(self) -> str:
        return f"device/{self.serial}/request"

    @property
    def report_topic(self) -> str:
        return f"device/{self.serial}/report"

    async def request(self, payload: Report) -> None:
        """Send a command on ``device/{serial}/request`` as a JSON object.

        PHASE-0: verify — that an unload / extrude / confirm-resume sent this way is honoured
        (docs/09 UNVERIFIED item #3). The transport/JSON envelope is confirmed; the *command
        verbs* inside the payload (built by the driver) are still the open spike item.
        """
        await self.bus.publish(self.request_topic, json.dumps(payload).encode())

    def on_report(self, handler: ReportHandler) -> None:
        """Subscribe to ``device/{serial}/report`` and decode each payload to a report dict.

        paho delivers raw bytes on its network thread; we JSON-decode and forward to the
        Printer's async handler. PHASE-0: verify — that this live stream actually surfaces a
        pause and the filament-present sensor (docs/09 UNVERIFIED items #1 and #2).
        """
        self._handlers.append(handler)

        async def _route(_topic: str, payload: bytes) -> None:
            try:
                report = json.loads(payload)
            except (ValueError, TypeError):
                log.warning("dropping non-JSON report on %s", self.report_topic)
                return
            if isinstance(report, dict):
                await handler(report)

        self.bus.subscribe(self.report_topic, _route)


class SimulatedPrinterLink:
    """In-memory PrinterLink fed scripted report dicts — no network, no real printer.

    Lets the Printer state model, delta application, and event emission be developed and tested
    before the v0.2 hardware spike. ``feed_report`` pushes a (full or delta) report dict to
    every registered handler exactly as a real report would arrive; ``sent`` records outgoing
    requests so tests can assert what the driver tried to send.
    """

    def __init__(self, printer_id: PrinterId, serial: str = "SIM0000000000000") -> None:
        self.printer_id = printer_id
        self.serial = serial
        self._handlers: list[ReportHandler] = []
        self.sent: list[Report] = []

    async def request(self, payload: Report) -> None:
        self.sent.append(payload)

    def on_report(self, handler: ReportHandler) -> None:
        self._handlers.append(handler)

    async def feed_report(self, report: Report) -> None:
        """Deliver one scripted report dict to all handlers (full or incremental delta)."""
        for handler in self._handlers:
            await handler(report)


# --------------------------------------------------------------------------------------------
# FtpClient — LAN file upload (FTPS) of the sliced job
# --------------------------------------------------------------------------------------------
class _ImplicitFTPTLS(ftplib.FTP_TLS):
    """``ftplib`` speaks *explicit* FTPS (plaintext greeting, then ``AUTH TLS``); Bambu speaks
    *implicit* FTPS — the control channel is TLS from the first byte on port 990. We wrap the
    control socket in TLS the moment ``ftplib`` assigns it, which turns the explicit client
    into an implicit one without touching the rest of the state machine.

    Bambu's FTPS ALSO requires **TLS session resumption on the data channel**: each PASV data
    connection must reuse the control connection's TLS session, or the encrypted transfer stalls
    and reads time out (the file may still arrive, but ftplib raises). ``ntransfercmd`` below
    wraps every data socket reusing ``self.sock.session`` to satisfy that.

    Finally, Bambu never answers the data-channel **close_notify**, so the TLS shutdown that
    ftplib's stock ``storbinary`` performs after an upload blocks until the socket timeout and
    raises ``TimeoutError`` — though the file already committed and the server already sent 226.
    Our ``storbinary`` override skips that shutdown (plain close); verified live (ftps_diag.py).
    """

    @property
    def sock(self) -> object:
        return self._sock

    @sock.setter
    def sock(self, value: object) -> None:
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd: str, rest: object = None):
        # Open the data connection, then (when PROT P is active) TLS-wrap it REUSING the control
        # channel's session — the resumption Bambu's server demands. Without `session=...` the
        # data transfer hangs -> "read operation timed out".
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=self.sock.session
            )
        return conn, size

    def storbinary(  # type: ignore[override]
        self,
        cmd: str,
        fp: object,
        blocksize: int = 8192,
        callback: Callable[[bytes], object] | None = None,
        rest: object = None,
    ) -> str:
        # Run the STOR ourselves and SKIP the post-transfer ``conn.unwrap()``. Both
        # ``ftplib.FTP.storbinary`` AND ``FTP_TLS.storbinary`` perform that TLS shutdown
        # handshake on the data socket — and Bambu's FTPS server never answers the close_notify,
        # so ``unwrap()`` blocks until the socket timeout and raises ``TimeoutError`` ("read
        # operation timed out") EVEN THOUGH the file already committed and the server already
        # sent 226. Verified live on the A1 mini (see scripts/check_ftps_integrity.py): a
        # plain socket close commits the upload and returns 226 in ~0.1s. The data channel is
        # still TLS (via our session-reusing ``ntransfercmd``) — we only drop the redundant
        # TLS *shutdown*.
        self.voidcmd("TYPE I")
        with self.transfercmd(cmd, rest) as conn:
            while True:
                buf = fp.read(blocksize)  # type: ignore[attr-defined]
                if not buf:
                    break
                conn.sendall(buf)
                if callback is not None:
                    callback(buf)
        return self.voidresp()


class FtpsClient:
    """Real implicit-FTPS upload of the sliced job to a Bambu printer over the LAN.

    How Bambu's file transfer works (confirmed pattern, Doridian/OpenBambuAPI + community):
    the printer runs an **implicit**-FTPS server on port 990 — TLS from the first byte — with
    user ``bblp`` and the LAN access code as the password; the cert is self-signed (we don't
    verify it — the link is LAN-local and access-code-gated). Sliced ``.3mf`` files go in the
    printer's ``/cache`` directory, and the print is then started over MQTT with
    ``project_file`` referencing ``ftp:///cache/<name>`` (the empty-host triple slash is just
    ``ftp://`` + the absolute ``/cache/...`` path). So ``upload`` returns ``/cache/<name>`` and
    the driver wraps it ``ftp://`` → ``ftp:///cache/<name>``.

    ``ftplib`` is blocking, so the transfer runs in a worker thread.

    PHASE-0 (v0.4) — implemented to the documented convention but **not yet run against our
    A1**: the remaining hardware item is simply confirming the A1 accepts this upload +
    ``project_file`` start. The dir (``/cache``) and url form are the documented norm.
    """

    PORT = 990
    USER = "bblp"
    CACHE_DIR = "/cache"  # Bambu stores sliced jobs here; start_print references ftp:///cache/...

    def __init__(self, host: str, access_code: str, *, timeout: float = 30.0) -> None:
        self.host = host
        self._access_code = access_code  # secret: never log
        self._timeout = timeout

    async def upload(self, printer: PrinterId, file: str) -> str:
        """Upload ``file`` into the printer's ``/cache`` and return the path start_print uses."""
        name = file.rsplit("/", 1)[-1]
        await asyncio.to_thread(self._upload_blocking, file, name)
        remote = f"{self.CACHE_DIR}/{name}"
        # Log the path only — never the access code.
        log.info("FtpsClient: uploaded %s to printer %s", remote, printer)
        return remote

    def _upload_blocking(self, file: str, name: str) -> None:
        # Self-signed cert -> unverified context. Bambu's FTPS stack is old, so relax the
        # OpenSSL security level enough for its cert/ciphers to negotiate.
        ctx = ssl._create_unverified_context()
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except ssl.SSLError:  # pragma: no cover - depends on the local OpenSSL build
            pass

        ftp = _ImplicitFTPTLS(context=ctx, timeout=self._timeout)
        # Log every phase so a hang points at the exact step (the last line before it stalls),
        # rather than a bare "read operation timed out" with no context. No secrets are logged.
        try:
            log.info("FTPS %s:%d — connecting (implicit TLS)…", self.host, self.PORT)
            ftp.connect(self.host, self.PORT)
            log.info("FTPS %s — connected; authenticating as %r…", self.host, self.USER)
            ftp.login(self.USER, self._access_code)
            ftp.prot_p()  # encrypt the data channel too (Bambu requires it)
            log.info("FTPS %s — authenticated; entering %s…", self.host, self.CACHE_DIR)
            # Drop the file in /cache (where Bambu keeps sliced jobs). The dir exists on stock
            # firmware; create it defensively in case a wipe removed it.
            try:
                ftp.cwd(self.CACHE_DIR)
            except ftplib.error_perm:  # pragma: no cover - depends on the live printer
                ftp.mkd(self.CACHE_DIR)
                ftp.cwd(self.CACHE_DIR)
            log.info("FTPS %s — storing %r…", self.host, name)
            with open(file, "rb") as fh:
                ftp.storbinary(f"STOR {name}", fh)
            log.info("FTPS %s — stored %s/%s ✓", self.host, self.CACHE_DIR, name)
        finally:
            try:
                ftp.quit()
            except ftplib.all_errors:  # quit can fail if the link is already gone
                ftp.close()


class SimulatedFtpClient:
    """In-memory FtpClient for tests: records uploads, returns a deterministic remote path."""

    def __init__(self) -> None:
        self.uploaded: list[tuple[PrinterId, str]] = []

    async def upload(self, printer: PrinterId, file: str) -> str:
        self.uploaded.append((printer, file))
        name = file.rsplit("/", 1)[-1]
        return f"/cache/{name}"


__all__ = [
    "FtpClient",
    "FtpsClient",
    "MqttBus",
    "MqttPrinterLink",
    "PrinterLink",
    "Report",
    "ReportHandler",
    "SimulatedFtpClient",
    "SimulatedPrinterLink",
]
