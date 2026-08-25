"""PrinterLink implementations — one per printer, real and simulated.

Out on ``device/{serial}/request``; in on ``device/{serial}/report``. Both satisfy the
``PrinterLink`` protocol from ``amsx.types``, which is what makes ``Printer``
transport-agnostic and lets every test run with no broker.
"""

from __future__ import annotations

import json
import logging

from amsx.system.infra.mqtt.bus import MqttBus
from amsx.types import PrinterId, Report, ReportHandler

log = logging.getLogger("amsx.system.infra.mqtt")

__all__ = ["MqttPrinterLink", "SimulatedPrinterLink"]


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
