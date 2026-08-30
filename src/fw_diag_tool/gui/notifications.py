from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

import streamlit as st


def show_toast(message: str, icon: str = "ℹ️") -> None:
    st.toast(message, icon=icon)


def show_success_toast(message: str) -> None:
    show_toast(message, icon="✅")


def show_error_toast(message: str) -> None:
    show_toast(message, icon="❌")


@contextmanager
def analysis_progress(protocol: str, stages: Iterable[str]) -> Iterator[Any]:
    stage_names = [str(stage) for stage in stages]
    sequence = " → ".join(stage_names)
    label = f"{protocol}：{sequence}" if sequence else f"{protocol}：分析進度"

    with st.status(label, expanded=True) as status:
        try:
            yield status
        except Exception:
            status.update(label=f"{protocol}：分析失敗", state="error")
            raise
        else:
            status.update(label=f"{protocol}：分析完成", state="complete")
