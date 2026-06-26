"""Tests for vt_tray external-filament read/write (A1Driver, Task 5)."""

from amsx.printer.drivers import A1Driver


def test_parse_external_filament():
    rpt = {"print": {"vt_tray": {"tray_type": "PLA", "tray_color": "FF0000FF"}}}
    assert A1Driver().parse_external_filament(rpt) == ("PLA", "FF0000")


def test_set_external_filament_payload():
    pr = A1Driver().request_set_external_filament("PLA", "ff0000")["print"]
    assert pr["command"] == "ams_filament_setting"
    assert pr["ams_id"] == 255 and pr["tray_id"] == 254 and pr["slot_id"] == 0
    assert pr["tray_color"] == "FF0000FF"  # RRGGBBAA uppercase
    assert pr["tray_type"] == "PLA"
