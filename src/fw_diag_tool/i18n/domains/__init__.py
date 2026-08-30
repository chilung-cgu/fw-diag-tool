from __future__ import annotations

from typing import TYPE_CHECKING

from fw_diag_tool.i18n.domains.common import register_common_domain
from fw_diag_tool.i18n.domains.gui import register_gui_domain

if TYPE_CHECKING:
    from fw_diag_tool.i18n.registry import TranslationRegistry


def register_all_domains(registry: TranslationRegistry) -> None:
    """註冊所有內建 domain 詞條。"""
    register_common_domain(registry)
    register_gui_domain(registry)


__all__ = [
    "register_all_domains",
    "register_common_domain",
    "register_gui_domain",
]
