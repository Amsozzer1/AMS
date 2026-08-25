"""Reading ams.json off disk and validating it into a typed ``Config``."""

from __future__ import annotations

import json
from pathlib import Path

from amsx.config.schema import Config

__all__ = ["load_config"]


def load_config(path: str | Path) -> Config:
    """Load and validate an ams.json into a typed Config."""
    text = Path(path).read_text()
    data = json.loads(text) if text.strip() else {}
    return Config.model_validate(data)
