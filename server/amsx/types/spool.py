"""Physical spools — the inventory's view of what's on the shelf and in the modules."""

from __future__ import annotations

from dataclasses import dataclass

from amsx.types.ids import ModuleId

__all__ = ["Spool", "SpoolSpec"]


@dataclass(frozen=True)
class Spool:
    """One physical spool from the inventory (Spoolman), flattened for the Brain.

    `color_hex` is 6-hex RRGGBB UPPERCASE (no alpha). `module` is which AMS module it's loaded
    in (from Spoolman's `extra.ams_module`), or None if not loaded.
    """

    id: str
    filament_id: str
    material: str | None = None
    color_hex: str | None = None
    name: str | None = None
    remaining_g: float | None = None
    module: ModuleId | None = None
    archived: bool = False


@dataclass(frozen=True)
class SpoolSpec:
    """Operator's request to create one spool (AMS resolves/creates the Spoolman filament)."""

    material: str
    color_hex: str | None = None  # bare 6-hex RRGGBB (no '#'); upper/lower accepted
    name: str | None = None
    vendor: str | None = None  # vendor display name; created-or-reused
    initial_g: float = 1000.0
    module: ModuleId | None = None
    location: str | None = None
