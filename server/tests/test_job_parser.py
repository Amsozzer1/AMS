"""Tests for amsx.job.JobParser — sliced .gcode.3mf -> ordered SwapPlan.

Fixtures: ``tests/fixtures/plate_1.gcode`` is a small synthetic multi-change
gcode. ``_make_3mf`` zips arbitrary plate gcode into a ``.gcode.3mf`` so each
test can build the exact 3MF it needs (valid, sliceless, or non-zip).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from amsx.job import PLATE_GCODE_PATH, Job, JobParseError, JobParser

FIXTURES = Path(__file__).parent / "fixtures"


def _make_3mf(tmp_path: Path, *, plate_gcode: str | None, name: str = "job.gcode.3mf") -> Path:
    """Zip ``plate_gcode`` into a ``.gcode.3mf`` (omit it for a sliceless 3MF)."""
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Members a real sliced 3MF carries alongside the gcode.
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("Metadata/plate_1.json", "{}")
        if plate_gcode is not None:
            zf.writestr(PLATE_GCODE_PATH, plate_gcode)
    return path


@pytest.fixture
def sliced_3mf(tmp_path: Path) -> Path:
    gcode = (FIXTURES / "plate_1.gcode").read_text()
    return _make_3mf(tmp_path, plate_gcode=gcode)


def test_ordered_plan_from_multi_change_gcode(sliced_3mf: Path) -> None:
    plan = JobParser().parse(Job(file=sliced_3mf, printer_id="p1"))

    # Three M400 U1 pauses -> three swaps, seq strictly 1..3 in file order.
    assert len(plan) == 3
    assert [s.seq for s in plan.swaps] == [1, 2, 3]


def test_filament_index_per_change(sliced_3mf: Path) -> None:
    plan = JobParser().parse(Job(file=sliced_3mf, printer_id="p1"))

    # Governing M1020 = last S value at/above each pause.
    # change#1: M1020 S1 ; change#2: M1020 S4 ; change#3: S2 then S0 -> 0 wins.
    assert [s.filament_index for s in plan.swaps] == [1, 4, 0]


def test_tags_are_deterministic_and_seq_based(sliced_3mf: Path) -> None:
    plan = JobParser().parse(Job(file=sliced_3mf, printer_id="p1"))
    assert [s.tag for s in plan.swaps] == ["swap-001", "swap-002", "swap-003"]


def test_bare_m400_without_u1_is_not_a_change(tmp_path: Path) -> None:
    gcode = "M1020 S3\nM400\nG1 X1 Y1\n"  # bare M400 = not a swap, and no U1 pause at all
    path = _make_3mf(tmp_path, plate_gcode=gcode)
    with pytest.raises(JobParseError):
        JobParser().parse(Job(file=path, printer_id="p1"))


def test_comments_and_whitespace_are_ignored(tmp_path: Path) -> None:
    gcode = "   M1020 S2   ; pick filament 3\n\n;just a comment line\n  M400 U1 ; swap now\n"
    path = _make_3mf(tmp_path, plate_gcode=gcode)
    plan = JobParser().parse(Job(file=path, printer_id="p1"))
    assert len(plan) == 1
    assert plan.swaps[0].filament_index == 2


def test_error_on_sliceless_3mf(tmp_path: Path) -> None:
    """A 3MF with no Metadata/plate_1.gcode (e.g. an unsliced project) fails loudly."""
    path = _make_3mf(tmp_path, plate_gcode=None)
    with pytest.raises(JobParseError, match=r"plate_1\.gcode"):
        JobParser().parse(Job(file=path, printer_id="p1"))


def test_error_on_non_zip(tmp_path: Path) -> None:
    path = tmp_path / "broken.gcode.3mf"
    path.write_bytes(b"this is not a zip file")
    with pytest.raises(JobParseError, match="not a valid 3MF"):
        JobParser().parse(Job(file=path, printer_id="p1"))


def test_error_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(JobParseError, match="file not found"):
        JobParser().parse(Job(file=tmp_path / "nope.gcode.3mf", printer_id="p1"))


def test_error_when_no_changes(tmp_path: Path) -> None:
    path = _make_3mf(tmp_path, plate_gcode="G28\nG1 X1 Y1 E1\nM104 S0\n")
    with pytest.raises(JobParseError, match="no filament changes"):
        JobParser().parse(Job(file=path, printer_id="p1"))


def test_error_on_pause_with_no_governing_m1020(tmp_path: Path) -> None:
    path = _make_3mf(tmp_path, plate_gcode="G28\nM400 U1\nG1 X1 Y1\n")
    with pytest.raises(JobParseError, match="no preceding"):
        JobParser().parse(Job(file=path, printer_id="p1"))
