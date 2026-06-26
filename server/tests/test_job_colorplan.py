# server/tests/test_job_colorplan.py
import json
import zipfile
from pathlib import Path

from amsx.job import Job, JobParser

PLATE = (
    "; layer num/total_layer_count: 1/3\n"
    "M1020 S0\n"
    "G1 Z0.2\n"
    "; layer num/total_layer_count: 2/3\n"
    "M400 U1\n"  # one change @ layer 2
    "G1 Z0.4\n"
)
CUSTOM_GCODE = (
    '<?xml version="1.0"?><custom_gcodes_per_layer><plate><plate_info id="1"/>'
    '<layer top_z="0.4" type="2" extruder="5" color="#FF0000" gcode="tool_change"/>'
    '<mode value="MultiAsSingle"/></plate></custom_gcodes_per_layer>'
)
SLICE_INFO = (
    '<plate><metadata key="index" value="1"/>'
    '<filament id="1" type="PLA" color="#FFFFFF" used_g="0.36"/>'
    '<filament id="5" type="PLA" color="#FF0000" used_g="1.14"/></plate>'
)


def _mk(tmp_path: Path) -> Path:
    p = tmp_path / "two.gcode.3mf"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("Metadata/plate_1.gcode", PLATE)
        zf.writestr("Metadata/custom_gcode_per_layer.xml", CUSTOM_GCODE)
        zf.writestr(
            "Metadata/filament_sequence.json", json.dumps({"plate_1": {"sequence": [1, 5]}})
        )
        zf.writestr("Metadata/slice_info.config", SLICE_INFO)
    return p


def test_colorplan_base_and_change(tmp_path):
    plan = JobParser().parse(Job(file=_mk(tmp_path), printer_id="p1"))
    assert len(plan) == 1
    assert plan.base.index == 1 and plan.base.color_hex == "FFFFFF" and plan.base.grams == 0.36
    assert plan.swaps[0].color_hex == "FF0000" and plan.swaps[0].material == "PLA"
    assert plan.swaps[0].filament_index == 5
    assert {c.color_hex for c in plan.colors} == {"FFFFFF", "FF0000"}


def test_colorplan_absent_degrades(tmp_path):
    # No custom_gcode/slice_info -> colours None, plan still parses by M400 U1.
    p = tmp_path / "bare.gcode.3mf"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("Metadata/plate_1.gcode", "M1020 S0\nM400 U1\n")
    plan = JobParser().parse(Job(file=p, printer_id="p1"))
    assert plan.swaps[0].color_hex is None and plan.base is None
