"""Stable string ids for the things the system addresses.

Aliases, not ``NewType``, on purpose: they stay friendly to YAML/JSON round-trips and to
dict keys without a wrapper at every boundary.
"""

from __future__ import annotations

__all__ = ["ClusterId", "ModuleId", "PrinterId"]

PrinterId = str
ClusterId = str
ModuleId = str
