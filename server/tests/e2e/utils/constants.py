from pathlib import Path

PRINTER_ID = "Bedroom"
A1_CONFIG = Path(__file__).resolve().parents[3] / "config" / "ams.test.aSeries.json"
P1_CONFIG = Path(__file__).resolve().parents[3] / "config" / "ams.test.pSeries.json"

__all__ = ["A1_CONFIG", "P1_CONFIG", "PRINTER_ID"]
