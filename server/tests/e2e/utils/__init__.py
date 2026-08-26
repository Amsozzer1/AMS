from amsx.system.brain import build_brain
from tests.e2e.utils.constants import A1_CONFIG, P1_CONFIG, PRINTER_ID

a1_brain = build_brain(A1_CONFIG, simulate=False)
p1_brain = build_brain(P1_CONFIG, simulate=False)

__all__ = ["A1_CONFIG", "P1_CONFIG", "PRINTER_ID", "a1_brain", "p1_brain"]
