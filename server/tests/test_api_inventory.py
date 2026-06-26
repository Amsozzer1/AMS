"""API tests for spool-inventory endpoints (GET /api/spools, loadout, job/assignment)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from amsx.api import create_app
from amsx.config import Config, ModuleConfig, PrinterConfig
from amsx.inventory import FakeSpoolStore
from amsx.inventory.resolver import ProposedRow
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


def test_job_assignment_get_post_get_round_trip():
    """GET→POST→GET round-trip: POST persists the override and flips confirmed False→True."""
    brain = _brain_with_store([_SPOOL])
    # Inject a pre-built proposal with one gap row (index=1) and one loaded row (index=0).
    brain.assignment["x1c-1"] = {
        0: ProposedRow(
            index=0,
            material="PLA",
            color_hex="FFFFFF",
            grams=100.0,
            module="m1",
            spool_id="1",
            status="loaded",
        ),
        1: ProposedRow(
            index=1,
            material="PLA",
            color_hex="FF0000",
            grams=80.0,
            module=None,
            spool_id=None,
            status="gap",
        ),
    }
    app = create_app(brain)
    with TestClient(app) as c:
        # (a) Initial GET: confirmed must be False.
        r_before = c.get("/api/printers/x1c-1/job/assignment")
        assert r_before.status_code == 200
        body_before = r_before.json()
        assert body_before["confirmed"] is False

        # POST: operator confirms index 1 → module "m2".
        r_post = c.post("/api/printers/x1c-1/job/assignment", json={"1": "m2"})
        assert r_post.status_code == 200
        assert r_post.json()["ok"] is True

        # (b) Final GET: index 1 row must now have module="m2", status="loaded"; confirmed=True.
        r_after = c.get("/api/printers/x1c-1/job/assignment")
        assert r_after.status_code == 200
        body_after = r_after.json()
        assert body_after["confirmed"] is True
        rows_by_index = {row["index"]: row for row in body_after["rows"]}
        assert rows_by_index[1]["module"] == "m2"
        assert rows_by_index[1]["status"] == "loaded"
        # index 0 (loaded from start) must be unchanged.
        assert rows_by_index[0]["module"] == "m1"
        assert rows_by_index[0]["status"] == "loaded"


async def test_brain_module_resolver_prefers_confirmed_assignment():
    """The orchestrator's module resolver prefers the confirmed assignment over the config map."""
    brain = _brain_with_store()
    await brain.start()
    # config maps index 0 -> m1, index 1 -> m2. Confirm index 0 -> m2 (override of m1).
    brain.assignment["x1c-1"] = {
        0: ProposedRow(
            index=0,
            material="PLA",
            color_hex="FFFFFF",
            grams=None,
            module="m2",
            spool_id=None,
            status="loaded",
        )
    }
    resolve = brain._module_resolver_for("x1c-1")
    assert resolve(0).id == "m2"  # confirmed assignment wins (config would give m1)
    assert resolve(1).id == "m2"  # no assignment for index 1 -> config fallback (m2)
    await brain.stop()


async def test_brain_module_resolver_falls_back_to_config():
    """With no assignment, the resolver uses the static config registry map."""
    brain = _brain_with_store()
    await brain.start()
    resolve = brain._module_resolver_for("x1c-1")
    assert resolve(0).id == "m1"  # config: index 0 -> m1
    assert resolve(1).id == "m2"  # config: index 1 -> m2
    await brain.stop()
