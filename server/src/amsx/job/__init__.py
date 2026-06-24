"""job — Job, JobParser (sliced-3MF -> plan), SwapPlan, PlannedSwap.

Turns an uploaded **sliced** ``.gcode.3mf`` into the ordered material-change
``SwapPlan`` the Orchestrator rides. A sliced 3MF is just a zip; "parsing" is
``unzip + read Metadata/plate_1.gcode`` (docs/09-filament-change-protocol.md).
This module is a leaf: pure parsing, stdlib only, no MQTT/FastAPI/printer/module
imports. It produces the *shared* contracts from ``amsx.types`` and never
redefines them.

The gcode facts (docs/09):

* ``M400 U1``        -> **pause** and wait for a manual filament change. The k-th
  such pause is change #k and maps to ``PlannedSwap.seq == k`` (1-based).
* ``M1020 S<n>``     -> **which** project filament is next (``S0`` = filament 1).
  This sets ``PlannedSwap.filament_index`` and is recorded verbatim: index ``n``
  is the literal ``S`` value, matching ``FilamentRef.index``.

M1020 -> pause binding rule (THE CONTRACT)
------------------------------------------
The governing ``M1020 S<n>`` is the **last ``M1020`` seen at or before** its
``M400 U1`` pause, top-to-bottom. Slicers emit ``M1020 S<n>`` to select the next
filament *just before* the pause that swaps to it, so "most recent S value above
the pause" is the value in effect when that pause fires. Concretely we scan the
gcode once, top-to-bottom, holding a ``current_index`` that every ``M1020 S<n>``
overwrites; when we hit an ``M400 U1`` we snapshot ``current_index`` for that
swap. A pause with no preceding ``M1020`` is a malformed plan and raises.

``tag`` is derived deterministically from ``seq`` (``"swap-001"``, ...) so the
Orchestrator can validate a live pause against the plan and, later, inject the
same marker when it authors the change-gcode.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from amsx.types import PlannedSwap, PrinterId, SwapPlan

__all__ = ["PLATE_GCODE_PATH", "Job", "JobParseError", "JobParser"]

#: The member inside the .gcode.3mf zip that holds the gcode the printer runs.
PLATE_GCODE_PATH = "Metadata/plate_1.gcode"

# Line-anchored matchers. Real gcode is huge and full of comments/whitespace, so we
# anchor on the whole (stripped) line and ignore anything after a ``;`` comment.
#
#   M400 U1   -> pause for manual change
#   M1020 S<n> -> which project filament is next (S0 = filament 1)
_PAUSE_RE = re.compile(r"^M400(?:\s+U1)\b")
_M1020_RE = re.compile(r"^M1020\s+S(\d+)\b")


class JobParseError(Exception):
    """Raised when a 3MF cannot be turned into a SwapPlan.

    Covers: not a zip, missing ``Metadata/plate_1.gcode`` (likely an *unsliced*
    project 3MF — out of scope), no changes found, or a pause with no governing
    ``M1020 S<n>``.
    """


@dataclass(frozen=True)
class Job:
    """An uploaded sliced ``.gcode.3mf`` bound to the printer that will run it."""

    file: str | Path
    printer_id: PrinterId


class JobParser:
    """Sliced ``.gcode.3mf`` -> ordered :class:`SwapPlan`.

    ``parse`` opens the 3MF as a zip, reads ``Metadata/plate_1.gcode``, scans it
    top-to-bottom and emits one :class:`PlannedSwap` per ``M400 U1`` pause, in
    order. See the module docstring for the M1020 -> pause binding rule.
    """

    @staticmethod
    def _read_plate_gcode(file: str | Path) -> str:
        path = Path(file)
        try:
            with zipfile.ZipFile(path) as zf:
                try:
                    raw = zf.read(PLATE_GCODE_PATH)
                except KeyError as exc:
                    raise JobParseError(
                        f"{path}: no {PLATE_GCODE_PATH!r} in 3MF — is this a *sliced* "
                        "3MF? (an unsliced project 3MF carries no gcode and is out of scope)"
                    ) from exc
        except FileNotFoundError as exc:
            raise JobParseError(f"{path}: file not found") from exc
        except zipfile.BadZipFile as exc:
            raise JobParseError(f"{path}: not a valid 3MF (not a zip)") from exc
        # gcode is ASCII/latin-1 safe; tolerate any stray bytes rather than crash.
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _plan_from_gcode(gcode: str, source: str) -> SwapPlan:
        swaps: list[PlannedSwap] = []
        current_index: int | None = None
        seq = 0

        for raw_line in gcode.splitlines():
            # Drop trailing comments and surrounding whitespace before matching.
            line = raw_line.split(";", 1)[0].strip()
            if not line:
                continue

            m1020 = _M1020_RE.match(line)
            if m1020 is not None:
                current_index = int(m1020.group(1))
                continue

            if _PAUSE_RE.match(line) is not None:
                if current_index is None:
                    raise JobParseError(
                        f"{source}: M400 U1 pause #{seq + 1} has no preceding "
                        "M1020 S<n> — cannot tell which filament is next"
                    )
                seq += 1
                swaps.append(
                    PlannedSwap(
                        seq=seq,
                        filament_index=current_index,
                        tag=f"swap-{seq:03d}",
                    )
                )

        if not swaps:
            raise JobParseError(
                f"{source}: no filament changes (M400 U1) found in {PLATE_GCODE_PATH}"
            )
        return SwapPlan(swaps=swaps)

    def parse(self, job: Job) -> SwapPlan:
        """Parse ``job``'s sliced 3MF into an ordered :class:`SwapPlan`."""
        gcode = self._read_plate_gcode(job.file)
        return self._plan_from_gcode(gcode, source=str(job.file))
