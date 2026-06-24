"""API smoke tests — the Brain behind FastAPI, in simulate mode (no printer/hardware)."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from amsx.api import create_app
from amsx.brain import Brain
from amsx.config import Config, ModuleConfig, PrinterConfig


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
