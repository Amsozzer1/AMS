"""API tests for spool-inventory endpoints (GET /api/spools, loadout, job/assignment)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from amsx.api import create_app
from amsx.config import Config, ModuleConfig, PrinterConfig
from amsx.inventory import FakeSpoolStore
from amsx.types import Spool


def _brain_with_store(spools: list[Spool] | None = None):
    """Build a simulate Brain with an injected FakeSpoolStore and known printer/module ids."""
    config = Config(
        printers=[
            PrinterConfig(id="x1c-1", model="x1", serial="SIM123", access_code="x", ip="1.2.3.4")
        ],
        modules=[
            ModuleConfig(id="m1", cluster_id="c", filament_index=0),
            ModuleConfig(id="m2", cluster_id="c", filament_index=1),
        ],
    )
    from amsx.brain import Brain

    brain = Brain(config, simulate=True)
    brain.store = FakeSpoolStore(spools or [])
    return brain


def _client(spools: list[Spool] | None = None):
    brain = _brain_with_store(spools)
    app = create_app(brain)
    return TestClient(app)


_SPOOL = Spool(
    id="1",
    filament_id="10",
    material="PLA",
    color_hex="FFFFFF",
    name="White",
    remaining_g=900,
    module="m1",
)


def test_list_spools_endpoint():
    with _client([_SPOOL]) as c:
        r = c.get("/api/spools")
        assert r.status_code == 200
        assert r.json()[0]["color_hex"] == "FFFFFF"


def test_list_spools_fields():
    with _client([_SPOOL]) as c:
        row = c.get("/api/spools").json()[0]
        assert row["id"] == "1"
        assert row["filament_id"] == "10"
        assert row["material"] == "PLA"
        assert row["name"] == "White"
        assert row["remaining_g"] == 900
        assert row["module"] == "m1"
        assert row["archived"] is False


def test_set_loadout_endpoint():
    with _client([_SPOOL]) as c:
        r = c.put("/api/printers/x1c-1/loadout", params={"module": "m2", "spool_id": "1"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        lo = {row["module"]: row for row in c.get("/api/printers/x1c-1/loadout").json()}
        assert lo["m2"]["spool"]["id"] == "1"


def test_get_loadout_returns_all_modules():
    with _client([_SPOOL]) as c:
        rows = c.get("/api/printers/x1c-1/loadout").json()
        modules = {row["module"] for row in rows}
        assert "m1" in modules and "m2" in modules


def test_loadout_unknown_printer_404():
    with _client([_SPOOL]) as c:
        assert c.get("/api/printers/ghost/loadout").status_code == 404
        assert (
            c.put(
                "/api/printers/ghost/loadout", params={"module": "m1", "spool_id": "1"}
            ).status_code
            == 404
        )


def test_get_job_assignment_no_job():
    with _client() as c:
        r = c.get("/api/printers/x1c-1/job/assignment")
        assert r.status_code == 200
        body = r.json()
        assert body["rows"] == []
        assert body["confirmed"] is False


def test_get_job_assignment_unknown_printer_404():
    with _client() as c:
        assert c.get("/api/printers/ghost/job/assignment").status_code == 404


def test_post_job_assignment_unknown_printer_404():
    with _client() as c:
        assert c.post("/api/printers/ghost/job/assignment", json={"0": "m1"}).status_code == 404
