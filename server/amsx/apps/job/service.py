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
swap. A pause with no preceding ``M1020`` defaults to slot ``0`` — the manual
external-spool change flow ("Add pause" / a No-AMS preset) emits a bare
``M400 U1`` and the single external spool is always slot 0; which physical module
feeds is resolved later by the loadout/identity layer, not this index.

``tag`` is derived deterministically from ``seq`` (``"swap-001"``, ...) so the
Orchestrator can validate a live pause against the plan and, later, inject the
same marker when it authors the change-gcode.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from defusedxml.ElementTree import fromstring as _xml_fromstring  # XXE / billion-laughs safe

from amsx.errors import JobParseError
from amsx.types import FilamentColor, PlannedSwap, PrinterId, SwapPlan

__all__ = ["PLATE_GCODE_PATH", "Job", "JobParseError", "JobParser"]

#: The member inside the .gcode.3mf zip that holds the gcode the printer runs.
PLATE_GCODE_PATH = "Metadata/plate_1.gcode"

# 3MF metadata paths for colour-plan enrichment (confirmed real file layout).
CUSTOM_GCODE_PATH = "Metadata/custom_gcode_per_layer.xml"
FILAMENT_SEQ_PATH = "Metadata/filament_sequence.json"
SLICE_INFO_PATH = "Metadata/slice_info.config"

_HEX_RE = re.compile(r"#?([0-9A-Fa-f]{6})")

# Line-anchored matchers. Real gcode is huge and full of comments/whitespace, so we
# anchor on the whole (stripped) line and ignore anything after a ``;`` comment.
#
#   M400 U1   -> pause for manual change
#   M1020 S<n> -> which project filament is next (S0 = filament 1)
_PAUSE_RE = re.compile(r"^M400(?:\s+U1)\b")
_M1020_RE = re.compile(r"^M1020\s+S(\d+)\b")

# Bambu/Orca layer marker — a COMMENT: "; layer num/total_layer_count: 75/250". We track it so
# each swap records the LAYER it happens on. The orchestrator binds a live pause by layer because
# the A1 reports mc_print_line_number as 0 at the pause (so the gcode line can't guard), while
# layer_num IS reported correctly (confirmed live 2026-06-25: M400 U1 at line 133871 = layer 75,
# and the printer reported layer 75 at the pause).
_LAYER_RE = re.compile(r"^;\s*layer num/total_layer_count:\s*(\d+)")


def _hex6(s: str | None) -> str | None:
    """Extract and normalise a 6-hex colour string to UPPERCASE, or None."""
    m = _HEX_RE.search(s or "")
    return m.group(1).upper() if m else None


def _slice_info_map(zf: zipfile.ZipFile) -> dict[int, tuple[str | None, str | None, float | None]]:
    """Parse ``Metadata/slice_info.config`` -> ``{index: (material, color_hex, grams)}``.

    Best-effort: any missing/malformed/hostile XML degrades to ``{}``.
    """
    try:
        root = _xml_fromstring(zf.read(SLICE_INFO_PATH).decode("utf-8", "replace"))
    except Exception:
        return {}
    out: dict[int, tuple[str | None, str | None, float | None]] = {}
    for fil in root.iter("filament"):
        try:
            idx = int(fil.get("id", ""))
        except ValueError:
            continue
        grams = fil.get("used_g")
        out[idx] = (fil.get("type"), _hex6(fil.get("color")), float(grams) if grams else None)
    return out


def _changes(zf: zipfile.ZipFile) -> list[tuple[int, str | None]]:
    """Parse ``Metadata/custom_gcode_per_layer.xml`` -> ordered ``[(extruder_index, color_hex)]``.

    Only ``gcode="tool_change"`` entries are returned, in document order.
    Best-effort: any missing/malformed/hostile XML degrades to ``[]``.
    """
    try:
        root = _xml_fromstring(zf.read(CUSTOM_GCODE_PATH).decode("utf-8", "replace"))
    except Exception:
        return []
    out: list[tuple[int, str | None]] = []
    for layer in root.iter("layer"):
        if layer.get("gcode") == "tool_change":
            try:
                out.append((int(layer.get("extruder", "")), _hex6(layer.get("color"))))
            except ValueError:
                continue
    return out


def _base_index(zf: zipfile.ZipFile) -> int | None:
    """Return the first filament index from ``Metadata/filament_sequence.json``.

    This is the base (starting) filament for the job. Best-effort: any missing/
    malformed JSON degrades to ``None``.
    """
    try:
        seq = json.loads(zf.read(FILAMENT_SEQ_PATH).decode("utf-8", "replace"))
        plate = next(iter(seq.values()))
        return int(plate["sequence"][0])
    except (KeyError, ValueError, StopIteration, IndexError, TypeError):
        return None


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
        current_layer: int | None = None
        seq = 0

        # 1-based line index over the RAW file (comments/blanks included). `line` is kept for
        # printers that report a usable mc_print_line_number; `layer` is the binding the A1 needs
        # (it reports line 0 at the pause). See the #17 ordinal + layer/line guard.
        for line_no, raw_line in enumerate(gcode.splitlines(), start=1):
            stripped = raw_line.strip()
            # Layer markers are COMMENTS, so read them off the raw line BEFORE comments are dropped.
            layer_m = _LAYER_RE.match(stripped)
            if layer_m is not None:
                current_layer = int(layer_m.group(1))
                continue

            # Drop trailing comments and surrounding whitespace before matching gcode.
            line = raw_line.split(";", 1)[0].strip()
            if not line:
                continue

            m1020 = _M1020_RE.match(line)
            if m1020 is not None:
                current_index = int(m1020.group(1))
                continue

            if _PAUSE_RE.match(line) is not None:
                # M1020 S<n> selects the filament slot, but the manual external-spool change flow
                # (Bambu Studio "Add pause" / a No-AMS change-gcode preset) emits a BARE M400 U1
                # with no M1020 — and on a single external spool the slot is always 0 anyway. A
                # missing M1020 therefore defaults to slot 0; *which physical module* feeds is
                # resolved later by the loadout/identity layer, not this index. When M1020 IS
                # present (AMS / multi-extruder, X1/P1) we honour the value it selected.
                seq += 1
                swaps.append(
                    PlannedSwap(
                        seq=seq,
                        filament_index=current_index if current_index is not None else 0,
                        tag=f"swap-{seq:03d}",
                        layer=current_layer,
                        line=line_no,
                    )
                )

        if not swaps:
            raise JobParseError(
                f"{source}: no filament changes (M400 U1) found in {PLATE_GCODE_PATH}"
            )
        return SwapPlan(swaps=swaps)

    def parse(self, job: Job) -> SwapPlan:
        """Parse ``job``'s sliced 3MF into an ordered :class:`SwapPlan`.

        Opens the zip once to read the plate gcode (required) then the colour
        metadata (best-effort: missing/hostile files degrade gracefully).
        Colour fields are only populated when the tool_change count in
        ``custom_gcode_per_layer.xml`` exactly matches the ``M400 U1`` pause
        count — any mismatch leaves ``material``/``color_hex`` as ``None``.
        """
        path = Path(job.file)
        gcode = self._read_plate_gcode(path)
        plan = self._plan_from_gcode(gcode, source=str(path))
        try:
            with zipfile.ZipFile(path) as zf:
                info = _slice_info_map(zf)
                changes = _changes(zf)
                base_idx = _base_index(zf)
        except zipfile.BadZipFile:
            return plan
        # Bind colours to pauses by ORDERED POSITION; only if counts line up.
        swaps = plan.swaps
        if changes and len(changes) == len(swaps):
            swaps = [
                PlannedSwap(
                    seq=s.seq,
                    filament_index=idx,
                    tag=s.tag,
                    layer=s.layer,
                    line=s.line,
                    material=(info.get(idx) or (None, None, None))[0],
                    color_hex=color or (info.get(idx) or (None, None, None))[1],
                )
                for s, (idx, color) in zip(swaps, changes, strict=True)
            ]
        base = None
        if base_idx is not None and base_idx in info:
            mat, col, grams = info[base_idx]
            base = FilamentColor(base_idx, mat, col, grams)
        colors = [FilamentColor(i, m, c, g) for i, (m, c, g) in info.items()]
        return SwapPlan(swaps=swaps, base=base, colors=colors)
