"""infra.mqtt — the printer's MQTT endpoint and our own broker. Dumb pipe, no decisions.

Moves bytes between paho-mqtt and the rest of the Brain. `PrinterLink` (the seam) and
`Report` / `ReportHandler` (the wire shapes) are defined in `amsx.types` and re-exported here
so they read beside the MqttPrinterLink / SimulatedPrinterLink that implement them.

⚠️ PHASE-0: the printer read path is verified live against an A1; the *request* payloads the
drivers build on top of it are not. See docs/09 "Still UNVERIFIED".
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
from collections.abc import Awaitable, Callable

from amsx.types import PrinterId, PrinterLink, Report, ReportHandler

log = logging.getLogger("amsx.system.infra.mqtt")

__all__ = [
    "MqttBus",
    "MqttPrinterLink",
    "PrinterLink",
    "Report",
    "ReportHandler",
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
