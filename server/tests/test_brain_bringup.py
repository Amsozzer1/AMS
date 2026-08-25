"""Live-mode bring-up resilience: an offline/unreachable printer must not abort the Brain."""

from __future__ import annotations

import pytest

from amsx.config import Config, PrinterConfig
from amsx.system import brain as brain_mod
from amsx.system.brain import Brain

pytestmark = pytest.mark.asyncio


class _DeadBus:
    """Stand-in for MqttBus whose connect() fails like an offline printer (No route to host)."""

    def __init__(self, *_a, **_k) -> None:
        self._connected = False

    def connect(self, *, access_code: str | None = None) -> None:
        raise OSError("[Errno 113] No route to host")

    def disconnect(self) -> None:  # called on Brain.stop()
        pass

    @property
    def connected(self) -> bool:
        return self._connected


def _live_brain() -> Brain:
    config = Config(
        printers=[
            PrinterConfig(
                id="Bedroom", model="a1-mini", serial="S", access_code="x", ip="192.168.1.88"
            )
        ]
    )
    return Brain(config, simulate=False)


async def test_unreachable_printer_does_not_abort_bringup(monkeypatch):
    monkeypatch.setattr(brain_mod, "MqttBus", _DeadBus)
    b = _live_brain()
    # The whole point: this used to raise and kill startup. It must now return cleanly.
    await b._bring_up_printers()
    # The printer is still registered (so the dashboard shows it), but DISCONNECTED.
    assert "Bedroom" in b.printers
    assert b._printer_buses["Bedroom"].connected is False


async def test_reachable_printer_still_connects(monkeypatch):
    """A printer whose bus connects fine is brought up and seeded as before."""
    connected_calls: list = []

    class _LiveBus(_DeadBus):
        def connect(self, *, access_code: str | None = None) -> None:
            connected_calls.append(access_code)
            self._connected = True

    monkeypatch.setattr(brain_mod, "MqttBus", _LiveBus)
    # request({pushall}) over the (fake) link runs through MqttPrinterLink → bus.publish; stub it.
    monkeypatch.setattr(brain_mod.MqttPrinterLink, "request", _async_noop)
    monkeypatch.setattr(brain_mod.MqttPrinterLink, "on_report", lambda *_a, **_k: None)
    b = _live_brain()
    await b._bring_up_printers()
    assert b._printer_buses["Bedroom"].connected is True
    assert connected_calls == ["x"]


async def _async_noop(*_a, **_k) -> None:
    return None
