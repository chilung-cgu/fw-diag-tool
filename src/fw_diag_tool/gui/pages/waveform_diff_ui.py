from __future__ import annotations

import streamlit as st

from fw_diag_tool.gui.shared import render_guide_expander
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES, decode_uploaded_text
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine
from fw_diag_tool.i2c.waveform_diff_report import (
    format_waveform_diff_markdown,
    localize_diff_description,
    localize_diff_hint,
    localize_diff_summary,
    localize_diff_type,
)
from fw_diag_tool.resources import load_waveform_diff_samples

MAX_UPLOAD_MIB = MAX_UPLOAD_BYTES // (1024 * 1024)


def render() -> None:
    st.header("Golden（正常板卡）與 Failing（故障板卡）雙波形差分對比（Waveform Diff）")
    render_guide_expander(
        "chapters/ch03_waveform_diff.md", "📖 點擊展開：Golden 與 Failing 雙波形差分比對教學"
    )
    use_diff_sample = st.button(
        "載入內建 Golden/Failing 範例",
        key="waveform_diff_load_sample",
        help="載入套件內建的最小 decoded CSV pair，可立即重現文件中的 NACK_MISMATCH。",
    )
    if use_diff_sample:
        golden_sample, failing_sample = load_waveform_diff_samples()
        st.session_state["waveform_diff_sample_active"] = True
        st.session_state["waveform_diff_golden_sample"] = golden_sample
        st.session_state["waveform_diff_failing_sample"] = failing_sample
        # A built-in pair is an explicit replacement for previously uploaded
        # files.  Clear the uploader state before recreating those widgets.
        st.session_state.pop("waveform_diff_golden_file", None)
        st.session_state.pop("waveform_diff_failing_file", None)

    sample_golden = st.session_state.get("waveform_diff_golden_sample")
    sample_failing = st.session_state.get("waveform_diff_failing_sample")
    sample_active = (
        st.session_state.get("waveform_diff_sample_active") is True
        and isinstance(sample_golden, str)
        and isinstance(sample_failing, str)
    )
    if sample_active:
        st.info(
            "已載入內建 Golden/Failing 範例；可直接查看差分，或下載 CSV 後替換成自己的 capture。"
        )
        sample_download_col1, sample_download_col2 = st.columns(2)
        with sample_download_col1:
            st.download_button(
                "下載 Golden 範例 CSV",
                data=sample_golden,
                file_name="i2c_golden.csv",
                mime="text/csv",
                key="waveform_diff_download_golden",
            )
        with sample_download_col2:
            st.download_button(
                "下載 Failing 範例 CSV",
                data=sample_failing,
                file_name="i2c_failing_nack.csv",
                mime="text/csv",
                key="waveform_diff_download_failing",
            )
    d_col1, d_col2 = st.columns(2)
    with d_col1:
        golden_file = st.file_uploader(
            "上傳 Golden (正常) Trace CSV",
            type=["csv", "txt"],
            max_upload_size=MAX_UPLOAD_MIB,
            key="waveform_diff_golden_file",
        )
    with d_col2:
        failing_file = st.file_uploader(
            "上傳 Failing (故障) Trace CSV",
            type=["csv", "txt"],
            max_upload_size=MAX_UPLOAD_MIB,
            key="waveform_diff_failing_file",
        )
    g_text = None
    f_text = None
    if use_diff_sample or (sample_active and not golden_file and not failing_file):
        g_text = sample_golden
        f_text = sample_failing
    elif golden_file or failing_file:
        # Any user upload supersedes the built-in pair, even when only one
        # side has been selected so the next run cannot mix two sources.
        st.session_state["waveform_diff_sample_active"] = False
        st.session_state.pop("waveform_diff_golden_sample", None)
        st.session_state.pop("waveform_diff_failing_sample", None)
        if not golden_file or not failing_file:
            st.info("請同時提供 Golden 與 Failing 兩份 trace，才能執行差分。")
    if golden_file and failing_file and not use_diff_sample:
        try:
            g_text = decode_uploaded_text(golden_file, allowed_extensions={".csv", ".txt"})
            f_text = decode_uploaded_text(failing_file, allowed_extensions={".csv", ".txt"})
        except ValueError as exc:
            st.error(f"無法讀取比較 trace：{exc}")
            st.stop()
    if g_text is not None and f_text is not None:
        try:
            eng = I2CDiagnosticEngine()
            g_rep = eng.analyze_csv_content(g_text)
            f_rep = eng.analyze_csv_content(f_text)
            diff_res = WaveformDiffEngine.compare_reports(g_rep, f_rep)
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            st.error(f"無法分析比較 trace：{exc}")
            st.stop()
        golden_name = (
            "i2c_golden.csv"
            if sample_active
            else (golden_file.name if golden_file is not None else "Golden trace")
        )
        failing_name = (
            "i2c_failing_nack.csv"
            if sample_active
            else (failing_file.name if failing_file is not None else "Failing trace")
        )
        st.caption(
            "證據範圍：此處比較解碼後 transaction；若要確認實際 SCL/SDA edge、電壓或雜訊，"
            "請改用原始數位 capture 與示波器／邏輯分析儀。"
        )
        if diff_res.is_identical:
            st.success("🎉 Golden 與 Failing 兩份波形在協定層完全一致！")
        else:
            st.error(f"🚨 {localize_diff_summary(diff_res.summary)}")
            for dp in diff_res.divergence_points:
                with st.expander(
                    f"分歧點：交易 #{dp.tx_index}（{localize_diff_type(dp.mismatch_type)}）",
                    expanded=True,
                ):
                    st.markdown(f"**現象描述**：{localize_diff_description(dp.description)}")
                    st.markdown(f"**排查建議**：{localize_diff_hint(dp.root_cause_hint)}")
            st.plotly_chart(
                WaveformDiffEngine.create_comparison_figure(
                    diff_res,
                    title="Golden（正常）與 Failing（故障）波形比較（Waveform Comparison）",
                ),
                width="stretch",
            )
        diff_md = format_waveform_diff_markdown(
            diff_res, golden_name=golden_name, failing_name=failing_name
        )
        st.download_button(
            "下載差分 Markdown 報告",
            data=diff_md,
            file_name="i2c_waveform_diff_report.md",
            mime="text/markdown",
            key="waveform_diff_download_report",
        )


__all__ = ["render"]
