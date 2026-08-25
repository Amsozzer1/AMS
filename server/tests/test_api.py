"""API smoke tests — the Brain behind FastAPI, in simulate mode (no printer/hardware)."""

from __future__ import annotations

import io
import time
import zipfile

from fastapi.testclient import TestClient

from amsx.api import create_app
from amsx.config import Config, ModuleConfig, PrinterConfig
from amsx.system.brain import Brain


def _sim_brain() -> Brain:
    config = Config(
        printers=[
            PrinterConfig(id="x1c-1", model="x1", serial="SIM123", access_code="x", ip="1.2.3.4")
        ],
        modules=[
            ModuleConfig(id="m1", cluster_id="c", filament_index=0),
            ModuleConfig(id="m2", cluster_id="c", filament_index=1),
        ],
    )
    return Brain(config, simulate=True)


def _sliced_3mf(*changes: int) -> bytes:
    """Build a minimal sliced .gcode.3mf: one `M1020 S<n>` + `M400 U1` per change."""
    lines = ["; header", "G28", "M104 S210"]
    for n in changes:
        lines += [f"M1020 S{n}", "M400 U1", "G1 X10 Y10"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Metadata/plate_1.gcode", "\n".join(lines) + "\n")
    return buf.getvalue()


def test_health_and_printers():
    with TestClient(create_app(_sim_brain())) as client:
        health = client.get("/health").json()
        assert health["ok"] is True and health["simulate"] is True
        assert health["printers"] == ["x1c-1"]

        printers = client.get("/api/printers").json()
        assert [p["id"] for p in printers] == ["x1c-1"]
        assert client.get("/api/printers/nope").status_code == 404


def test_job_upload_returns_plan():
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("two-color.gcode.3mf", _sliced_3mf(0, 1), "application/octet-stream")}
        resp = client.post("/api/printers/x1c-1/job", files=files)
        assert resp.status_code == 200, resp.text
        plan = resp.json()["planned_swaps"]
        assert [s["filament_index"] for s in plan] == [0, 1]
        assert all(s["tag"] for s in plan)


def test_job_upload_unknown_printer_404():
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("x.gcode.3mf", _sliced_3mf(0), "application/octet-stream")}
        assert client.post("/api/printers/ghost/job", files=files).status_code == 404


def test_bad_3mf_is_400():
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("bad.gcode.3mf", b"not a zip", "application/octet-stream")}
        assert client.post("/api/printers/x1c-1/job", files=files).status_code == 400


def test_printer_detail_exposes_everything_without_secrets():
    with TestClient(create_app(_sim_brain())) as client:
        resp = client.get("/api/printers/x1c-1/detail")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # identity + status
        assert body["id"] == "x1c-1"
        assert body["serial"] == "SIM123"
        assert body["model"] == "x1"
        assert body["ip"] == "1.2.3.4"
        assert body["connected"] is True  # simulator link is always "connected"
        assert "raw" in body  # the full report blob is exposed
        # the access code must NEVER be serialised
        assert "access_code" not in resp.text
        assert "access_code" not in body
        # unknown printer -> 404
        assert client.get("/api/printers/nope/detail").status_code == 404


def test_answer_unknown_prompt_404():
    with TestClient(create_app(_sim_brain())) as client:
        assert client.post("/api/prompts/nope/answer").status_code == 404
        assert client.get("/api/prompts").json() == []


# --- orchestrator status + simulate-only swap-loop hooks -------------------------------------
def _submit(client: TestClient, *changes: int):
    files = {"file": ("t.gcode.3mf", _sliced_3mf(*changes), "application/octet-stream")}
    resp = client.post("/api/printers/x1c-1/job", files=files)
    assert resp.status_code == 200, resp.text
    return resp


def _drive_until(client: TestClient, target_cursor: int, *, budget: int = 400) -> dict:
    """Answer every pending human prompt and trip the sensor in SENSING until the cursor
    reaches ``target_cursor`` (or the loop safe-holds). Mirrors scripts/test_v0_api.py."""
    for _ in range(budget):
        for p in client.get("/api/prompts").json():
            client.post(f"/api/prompts/{p['id']}/answer")
        st = client.get("/api/printers/x1c-1/orchestrator").json()
        if st.get("swap_state") == "SENSING":
            client.post("/api/printers/x1c-1/sim/sensor", params={"present": True})
        if st.get("cursor") == target_cursor or st.get("held"):
            return st
        time.sleep(0.01)
    return client.get("/api/printers/x1c-1/orchestrator").json()


def test_arm_only_does_not_start():
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("t.gcode.3mf", _sliced_3mf(0, 1), "application/octet-stream")}
        resp = client.post("/api/printers/x1c-1/job", params={"start": "false"}, files=files)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["started"] is False
        # The plan is armed even though the print was not started (FTPS-free path).
        st = client.get("/api/printers/x1c-1/orchestrator").json()
        assert st["armed"] is True and st["total"] == 2 and st["cursor"] == 0


def test_orchestrator_unarmed_then_armed():
    with TestClient(create_app(_sim_brain())) as client:
        assert client.get("/api/printers/nope/orchestrator").status_code == 404
        assert client.get("/api/printers/x1c-1/orchestrator").json() == {
            "armed": False,
            "printer_id": "x1c-1",
        }
        _submit(client, 0, 1)
        st = client.get("/api/printers/x1c-1/orchestrator").json()
        assert st["armed"] is True
        assert st["cursor"] == 0 and st["total"] == 2 and st["done"] is False
        assert [s["filament_index"] for s in st["swaps"]] == [0, 1]


def test_sim_hooks_require_armed_job():
    with TestClient(create_app(_sim_brain())) as client:
        # No job yet -> 409 (nothing to pause).
        assert client.post("/api/printers/x1c-1/sim/pause").status_code == 409
        assert client.post("/api/printers/ghost/sim/pause").status_code == 404


def test_sim_hooks_blocked_when_not_simulating():
    # Start in simulate mode (no real connection), then flip the live brain to non-simulate:
    # the hooks must refuse even with a job armed.
    with TestClient(create_app(_sim_brain())) as client:
        _submit(client, 0)
        client.app.state.brain.simulate = False
        assert client.post("/api/printers/x1c-1/sim/pause").status_code == 409
        assert client.post("/api/printers/x1c-1/sim/sensor").status_code == 409


def test_mismatched_tag_pause_safe_holds():
    with TestClient(create_app(_sim_brain())) as client:
        _submit(client, 0, 1)
        resp = client.post("/api/printers/x1c-1/sim/pause", params={"tag": "WRONG-TAG"})
        assert resp.status_code == 200
        st = _drive_until(client, target_cursor=99)  # never reached; we expect a hold
        assert st["held"] is True
        assert st["cursor"] == 0
        assert any("does not match" in a for a in st["alerts"])


def test_far_line_pause_safe_holds():
    # An untagged pause whose reported line is nowhere near a planned swap = stray → safe-hold.
    with TestClient(create_app(_sim_brain())) as client:
        _submit(client, 0, 1)
        resp = client.post("/api/printers/x1c-1/sim/pause", params={"line": 999999})
        assert resp.status_code == 200 and resp.json()["line"] == 999999
        st = _drive_until(client, target_cursor=99, budget=120)
        assert st["held"] is True and st["cursor"] == 0


def test_money_shot_two_color_loop_over_http():
    """The v0 money shot, end to end over HTTP in simulate mode: submit -> pause -> human
    prompt -> sensor trip -> resume -> cursor advances, for both color changes."""
    with TestClient(create_app(_sim_brain())) as client:
        _submit(client, 0, 1)
        for expected_cursor in (1, 2):
            pause = client.post("/api/printers/x1c-1/sim/pause")
            assert pause.status_code == 200, pause.text
            st = _drive_until(client, target_cursor=expected_cursor)
            assert st["held"] is False, st["alerts"]
            assert st["cursor"] == expected_cursor
        final = client.get("/api/printers/x1c-1/orchestrator").json()
        assert final["done"] is True and final["held"] is False


def test_job_start_after_arm_starts_held_job():
    """Two-step flow: arm (start=false) then POST /job/start pushes+starts without re-arming."""
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("t.gcode.3mf", _sliced_3mf(0, 1), "application/octet-stream")}
        armed = client.post("/api/printers/x1c-1/job", params={"start": "false"}, files=files)
        assert armed.status_code == 200 and armed.json()["started"] is False
        started = client.post("/api/printers/x1c-1/job/start")
        assert started.status_code == 200 and started.json()["started"] is True


def test_job_start_without_arm_is_409():
    with TestClient(create_app(_sim_brain())) as client:
        assert client.post("/api/printers/x1c-1/job/start").status_code == 409


def test_job_start_unknown_printer_404():
    with TestClient(create_app(_sim_brain())) as client:
        assert client.post("/api/printers/ghost/job/start").status_code == 404


# ---- regressions from the typed-response-model change --------------------------------------


def test_odd_progress_values_do_not_break_printer_state():
    """A firmware-specific `layer_num` must never 500 the whole dashboard.

    `Printer._apply_fields` copies `layer_num` / `mc_percent` straight off the report without
    validating them, so a non-integral or non-numeric value really can reach `state.progress`.
    Before the response models existed the route returned that dict verbatim; a bare
    `int | None` on the model would instead raise and take out /api/printers, /{id} and
    /{id}/detail at once. Odd values are reported as absent, never as an error.
    """
    brain = _sim_brain()
    with TestClient(create_app(brain)) as client:
        printer = brain.printers["x1c-1"]
        printer.state.progress = {"layer": 12.5, "percent": "not-a-number", "line": "abc"}

        for path in ("/api/printers", "/api/printers/x1c-1", "/api/printers/x1c-1/detail"):
            res = client.get(path)
            assert res.status_code == 200, f"{path} -> {res.status_code} {res.text}"

        state = client.get("/api/printers/x1c-1").json()
        assert state["progress"]["layer"] is None
        assert state["progress"]["percent"] is None
        assert state["progress"]["line"] is None

        # Clean values still survive, including the string ints Bambu actually sends.
        printer.state.progress = {"layer": "37", "percent": 50.5, "line": 900}
        state = client.get("/api/printers/x1c-1").json()
        assert state["progress"] == {"layer": 37, "percent": 50.5, "line": 900}


def test_sim_pause_returns_only_the_injected_form():
    """A tagged pause returns `tag` and NO `line` key, and vice versa.

    The response model carries both fields, so without `response_model_exclude_unset` each
    reply gained the other key as null — a wire change for any client that tests for key
    presence rather than value.
    """
    with TestClient(create_app(_sim_brain())) as client:
        files = {"file": ("t.gcode.3mf", _sliced_3mf(0, 1), "application/octet-stream")}
        client.post("/api/printers/x1c-1/job", params={"start": "false"}, files=files)

        tagged = client.post("/api/printers/x1c-1/sim/pause", params={"tag": "T1"}).json()
        assert tagged["injected"] == "pause" and tagged["tag"] == "T1"
        assert "line" not in tagged

        lined = client.post("/api/printers/x1c-1/sim/pause", params={"line": 4242}).json()
        assert lined["injected"] == "pause" and lined["line"] == 4242
        assert "tag" not in lined
