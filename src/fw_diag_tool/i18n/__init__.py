from __future__ import annotations

from fw_diag_tool.i18n.compat import bridge_i2c_localization
from fw_diag_tool.i18n.registry import (
    TranslationRegistry,
    create_default_registry,
    get_global_registry,
    set_global_registry,
    t,
)

__all__ = [
    "TranslationRegistry",
    "bridge_i2c_localization",
    "create_default_registry",
    "get_global_registry",
    "set_global_registry",
    "t",
]
