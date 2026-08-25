"""config — declarative wiring loaded from ams.json.

Secrets (serial / access_code) live only in ams.local.json (gitignored); never commit real
values. See SECURITY.md.
"""

from amsx.config.loader import load_config
from amsx.config.schema import (
    BusConfig,
    ClusterConfig,
    Config,
    ModuleConfig,
    PrinterConfig,
    SpoolmanConfig,
)

__all__ = [
    "BusConfig",
    "ClusterConfig",
    "Config",
    "ModuleConfig",
    "PrinterConfig",
    "SpoolmanConfig",
    "load_config",
]
