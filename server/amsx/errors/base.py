"""The root of every error we raise deliberately."""

from __future__ import annotations

__all__ = ["AmsxError"]


class AmsxError(Exception):
    """Root of every error we raise deliberately. Lets a caller catch ours and nothing else."""
