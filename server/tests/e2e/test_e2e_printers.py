import pytest

from tests.e2e.utils import PRINTER_ID, a1_brain, p1_brain

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_printer_connection():
    a1 = a1_brain.printers[PRINTER_ID]
    p1 = p1_brain.printers[PRINTER_ID]
    assert p1.state.raw, f"P1S {p1.id!r} sent no report"
    assert a1.state.raw, f"A1 {a1.id!r} sent no report"
