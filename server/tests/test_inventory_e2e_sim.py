"""Inventory e2e sim test — arm->assignment->confirm, no hardware.

Exercises the full chain:
    POST /job?start=false (arm_job -> resolver.propose -> brain.assignment)
    GET  /job/assignment  (proposal: one loaded row + one gap row)
    POST /job/assignment  (operator confirms/overrides gap row)
    GET  /job/assignment  (confirmed=True, overridden row now loaded)

Uses a sliced 3MF with embedded colour metadata so the Resolver can distinguish
the two filament indices and produce a meaningful loaded/gap split — unlike the
bare-gcode 3MFs in test_api.py (which carry no colour info and can't produce a gap
row from the resolver without a matching spool for every index).
"""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from amsx.apps.inventory import FakeSpoolStore
from amsx.config import Config, ModuleConfig, PrinterConfig
from amsx.system.brain import Brain
from amsx.system.infra.http.app import create_app
from amsx.types import Spool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_WHITE_SPOOL = Spool(
    id="s1",
    filament_id="f1",
    material="PLA",
    color_hex="FFFFFF",
    name="White PLA",
    remaining_g=900.0,
    module="m1",  # already loaded in module m1
)

# No red spool: index 1 will be a gap in the resolver proposal.


def _sim_brain() -> Brain:
    """Brain with two modules and a FakeSpoolStore containing one white spool in m1."""
    config = Config(
        printers=[
            PrinterConfig(id="x1c-1", model="x1", serial="SIM123", access_code="x", ip="1.2.3.4")
        ],
        modules=[
            ModuleConfig(id="m1", cluster_id="c", filament_index=0),
            ModuleConfig(id="m2", cluster_id="c", filament_index=1),
        ],
    )
    brain = Brain(config, simulate=True)
    brain.store = FakeSpoolStore([_WHITE_SPOOL])
    return brain


def _two_color_3mf() -> bytes:
    """Build a sliced .gcode.3mf with full colour metadata.

    Plate gcode: two M400 U1 pauses — swap 1 to PLA white (index 0) and swap 2
    to PLA red (index 1).  The colour metadata files let the Resolver match the
    white spool already loaded in m1 for index 0 and report a gap for index 1
    (no red spool in the store).
    """
    gcode = (
        "; header\n"
        "G28\n"
        "M104 S210\n"
        "; layer num/total_layer_count: 1/20\n"
        "M1020 S0\n"
        "M400 U1\n"
        "G1 X10 Y10\n"
        "; layer num/total_layer_count: 10/20\n"
        "M1020 S1\n"
        "M400 U1\n"
        "G1 X20 Y20\n"
    )
    custom_gcode = (
        "<custom_gcodes_per_layer>"
        '<layer gcode="tool_change" extruder="0" color="#FFFFFF"/>'
        '<layer gcode="tool_change" extruder="1" color="#FF0000"/>'
        "</custom_gcodes_per_layer>"
    )
    slice_info = (
        "<config>"
        '<filament id="0" type="PLA" color="#FFFFFF" used_g="50.0"/>'
        '<filament id="1" type="PLA" color="#FF0000" used_g="40.0"/>'
        "</config>"
    )
    filament_seq = '{"1": {"sequence": [0, 1]}}'

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Metadata/plate_1.gcode", gcode)
        zf.writestr("Metadata/custom_gcode_per_layer.xml", custom_gcode)
        zf.writestr("Metadata/slice_info.config", slice_info)
        zf.writestr("Metadata/filament_sequence.json", filament_seq)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_arm_job_produces_assignment_proposal():
    """POST /job?start=false arms the plan and resolver builds the assignment proposal."""
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("two-color.gcode.3mf", _two_color_3mf(), "application/octet-stream")}
        resp = client.post("/api/printers/x1c-1/job", params={"start": "false"}, files=files)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["started"] is False
        assert len(body["planned_swaps"]) == 2

        # Orchestrator must be armed after arm_job.
        orch = client.get("/api/printers/x1c-1/orchestrator").json()
        assert orch["armed"] is True
        assert orch["total"] == 2 and orch["cursor"] == 0


def test_assignment_proposal_after_arm():
    """GET /job/assignment returns one loaded row (index 0, m1) and one gap row (index 1)."""
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("two-color.gcode.3mf", _two_color_3mf(), "application/octet-stream")}
        resp = client.post("/api/printers/x1c-1/job", params={"start": "false"}, files=files)
        assert resp.status_code == 200, resp.text

        r = client.get("/api/printers/x1c-1/job/assignment")
        assert r.status_code == 200, r.text
        body = r.json()

        # Two rows: one per filament index.
        assert len(body["rows"]) == 2
        # Not yet confirmed — no POST has happened.
        assert body["confirmed"] is False

        rows = {row["index"]: row for row in body["rows"]}

        # Index 0: white spool is loaded in m1 → resolver finds it.
        assert rows[0]["status"] == "loaded"
        assert rows[0]["module"] == "m1"
        assert rows[0]["spool_id"] == "s1"

        # Index 1: no red spool in store → gap.
        assert rows[1]["status"] == "gap"
        assert rows[1]["module"] is None
        assert rows[1]["spool_id"] is None


def test_confirm_assignment_overrides_gap_row():
    """POST /job/assignment with {1: m2} binds the gap row; GET shows confirmed=True."""
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("two-color.gcode.3mf", _two_color_3mf(), "application/octet-stream")}
        resp = client.post("/api/printers/x1c-1/job", params={"start": "false"}, files=files)
        assert resp.status_code == 200, resp.text

        # (a) Confirm: operator assigns the gap row (index 1) to module m2.
        r_post = client.post(
            "/api/printers/x1c-1/job/assignment",
            json={"1": "m2"},
        )
        assert r_post.status_code == 200, r_post.text
        assert r_post.json()["ok"] is True

        # (b) GET after confirm: confirmed flag flipped, gap row now loaded.
        r_after = client.get("/api/printers/x1c-1/job/assignment")
        assert r_after.status_code == 200, r_after.text
        body = r_after.json()
        assert body["confirmed"] is True

        rows = {row["index"]: row for row in body["rows"]}

        # Index 0 (loaded from the start) must be unchanged.
        assert rows[0]["status"] == "loaded"
        assert rows[0]["module"] == "m1"

        # Index 1: operator chose m2 → status promoted to loaded, module bound.
        assert rows[1]["status"] == "loaded"
        assert rows[1]["module"] == "m2"


def test_rearm_clears_confirmation():
    """Re-arming a new job clears the confirmed state so the operator must confirm again."""
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("two-color.gcode.3mf", _two_color_3mf(), "application/octet-stream")}

        # First arm + confirm.
        client.post("/api/printers/x1c-1/job", params={"start": "false"}, files=files)
        client.post("/api/printers/x1c-1/job/assignment", json={"1": "m2"})
        assert client.get("/api/printers/x1c-1/job/assignment").json()["confirmed"] is True

        # Re-arm: new job upload must reset confirmed.
        client.post("/api/printers/x1c-1/job", params={"start": "false"}, files=files)
        body = client.get("/api/printers/x1c-1/job/assignment").json()
        assert body["confirmed"] is False, "re-arm should clear the confirmed flag"
