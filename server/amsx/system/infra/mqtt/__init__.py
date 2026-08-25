"""infra.mqtt — the printer's MQTT endpoint and our own broker. Dumb pipe, no decisions.

``PrinterLink`` (the seam) and ``Report`` / ``ReportHandler`` (the wire shapes) are defined in
``amsx.types`` and re-exported here so they read beside the implementations.

⚠️ PHASE-0: the printer read path is verified live against an A1; the *request* payloads the
drivers build on top of it are not. See docs/09 "Still UNVERIFIED".
"""

from amsx.system.infra.mqtt.bus import MqttBus, TopicHandler
from amsx.system.infra.mqtt.link import MqttPrinterLink, SimulatedPrinterLink
from amsx.types import PrinterLink, Report, ReportHandler

__all__ = [
    "MqttBus",
    "MqttPrinterLink",
    "PrinterLink",
    "Report",
    "ReportHandler",
    "SimulatedPrinterLink",
    "TopicHandler",
]
