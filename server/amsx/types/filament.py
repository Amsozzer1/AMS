"""Filament identity — what is (or should be) loaded, and what a job asks for."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FilamentColor", "FilamentRef"]


@dataclass(frozen=True)
class FilamentRef:
    """What the Brain believes is (or should be) loaded. `index` is the M1020 S<n> value."""

    index: int
    material: str | None = None
    color: str | None = None
    spool_id: str | None = None


@dataclass(frozen=True)
class FilamentColor:
    """One filament used by a job: the slicer index + its colour/material + grams used."""

    index: int
    material: str | None = None
    color_hex: str | None = None
    grams: float | None = None
