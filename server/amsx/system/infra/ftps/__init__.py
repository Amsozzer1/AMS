"""infra.ftps — uploading the sliced .gcode.3mf to the printer over implicit FTPS.

Bambu's FTPS is non-standard in two ways that took a spike each to pin down: the control
channel is TLS from the first byte (implicit, port 990) rather than after an AUTH TLS, and the
data channel must reuse the control connection's TLS session. Both findings are encoded below
and explained where they bite. See scripts/check_ftps_integrity.py for the live round-trip check.

`FtpClient` (the seam) is defined in `amsx.types` and re-exported here.
"""

from __future__ import annotations

import asyncio
import ftplib
import logging
import ssl
from collections.abc import Callable

from amsx.types import FtpClient, PrinterId

log = logging.getLogger("amsx.system.infra.ftps")

__all__ = ["FtpClient", "FtpsClient", "SimulatedFtpClient"]


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
