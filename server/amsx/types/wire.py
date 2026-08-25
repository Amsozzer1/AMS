"""Raw wire shapes for the printer's MQTT report stream.

These are deliberately loose: the schema is Bambu's, not ours, and the specific fields we
trust are named in the drivers rather than modelled here. Lives in ``types`` (not the mqtt
adapter) so drivers can name a report without importing the transport.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

__all__ = ["Report", "ReportHandler"]

# A raw MQTT report payload, already JSON-decoded into a dict.
Report = dict[str, object]
ReportHandler = Callable[[Report], Awaitable[None]]
