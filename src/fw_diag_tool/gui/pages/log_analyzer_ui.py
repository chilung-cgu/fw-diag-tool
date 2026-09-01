"""Linux Kernel (dmesg) and OpenBMC (journalctl) system log correlation and diagnostic UI."""

from __future__ import annotations

from typing import Any

import streamlit as st

from fw_diag_tool.board_profile import BoardProfile, load_board_profile
from fw_diag_tool.gui.charts.stats_charts import distribution_bar, distribution_pie
from fw_diag_tool.gui.page_index import render_breadcrumb
from fw_diag_tool.gui.route_registry import resolve_page
from fw_diag_tool.gui.shared import (
    _localize_gui_error,
    render_guide_expander,
    render_page_footer,
)
from fw_diag_tool.gui.uploads import MAX_TEXT_BYTES, decode_uploaded_text, validate_pasted_text
from fw_diag_tool.i18n import t
from fw_diag_tool.log.diff import LogDiffEngine
from fw_diag_tool.log.models import LogReport
from fw_diag_tool.log.parser import LogParser

_SAMPLE_I2C = """[   10.123456] i2c_designware 0000:00:15.0: i2c_dw_handle_tx_abort: lost arbitration
[   10.123500] i2c i2c-1: controller timed out waiting for bus
[   10.123600] i2c-1: client at 0x50: No such device or address (-ENXIO)
[   10.123700] tmp421 1-004c: probe of 1-004c failed with error -121
"""

_SAMPLE_PCIE = """[   20.100100] pcieport 0000:00:01.0: AER: Uncorrectable error received: 0000:01:00.0
[   20.100200] pcieport 0000:00:01.0: PCIe Bus Error: severity=Uncorrected
[   20.100300] pcieport 0000:00:01.0: Data Link Layer Link Degraded
"""

_SAMPLE_BMC = """Sep 01 12:00:00 bmc-yv4 psusensor[1024]: Sensor /xyz/openbmc_project/sensors/power/PSU0_Power not available: -110
Sep 01 12:00:01 bmc-yv4 entity-manager[512]: Probe failed for /xyz/openbmc_project/inventory/system/chassis: Configuration not found
Sep 01 12:00:02 bmc-yv4 phosphor-state-manager[768]: Chassis power state changed to xyz.openbmc_project.State.Chassis.PowerState.Off
"""


def format_log_markdown(report: LogReport, title: str = "System Log Diagnostic Report") -> str:
    """Format structured LogReport into standard Markdown diagnostic report."""
    lines = [
        f"# {title}",
        "",
        f"- **Source Type**: `{report.source_type.value}`",
        f"- **Total Lines**: {report.summary.total_lines}",
        f"- **Detected Events**: {report.summary.total_events}",
        f"- **Correlated Incidents**: {report.summary.total_incidents}",
    ]
    if report.summary.time_span_seconds is not None:
        lines.append(f"- **Time Span**: {report.summary.time_span_seconds:.3f} s")
    else:
        lines.append("- **Time Span**: N/A")

    lines.extend(["", "## Summary Breakdown", ""])
    if report.summary.subsystem_counts:
        lines.append("### Subsystems")
        for sub, count in sorted(report.summary.subsystem_counts.items()):
            lines.append(f"- **{sub}**: {count}")
        lines.append("")

    if report.summary.severity_counts:
        lines.append("### Severities")
        for sev, count in sorted(report.summary.severity_counts.items()):
            lines.append(f"- **{sev}**: {count}")
        lines.append("")

    lines.extend(["## Incidents", ""])
    if not report.incidents:
        lines.append("No incidents detected.")
    else:
        for inc in report.incidents:
            lines.append(f"### [{inc.severity.value}] {inc.id}: {inc.title}")
            lines.append(f"- **Subsystem**: {inc.subsystem.value}")
            lines.append(f"- **Events Count**: {len(inc.events)}")
            if inc.root_cause_hypothesis:
                lines.append(f"- **Root Cause Hypothesis**: {inc.root_cause_hypothesis}")
            if inc.board_context:
                lines.append(f"- **Board Context**: {inc.board_context}")
            if inc.recommended_actions:
                lines.append("- **Recommended Actions**:")
                for act in inc.recommended_actions:
                    lines.append(f"  - {act}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def render() -> None:
    """Render the System Log Correlation and Diagnostics GUI page."""
    cat_title = t("nav_category_system_log", domain="gui")
    page_title = t("title_log_analyzer", domain="gui")
    render_breadcrumb(
        cat_title if cat_title != "nav_category_system_log" else "System Logs",
        page_title if page_title != "title_log_analyzer" else "系統日誌關聯分析",
    )

    st.header("Linux Kernel（dmesg）與 OpenBMC（journalctl）日誌關聯診斷")
    render_guide_expander(
        "chapters/ch24_log_analyzer.md",
        "📖 點擊展開：系統日誌關聯分析教學",
        fallback_title="📖 點擊展開：系統日誌關聯分析教學",
        fallback_body=(
            "系統日誌關聯分析可自動解析 Linux 核心 dmesg 與 OpenBMC journalctl 日誌，"
            "並將分散的硬體與韌體錯誤依時間與拓撲關聯為 Incident 進行根因排查。"
        ),
    )

    col_s1, col_s2, col_s3 = st.columns(3)
    if col_s1.button("🚀 載入 I2C 仲裁遺失與逾時範例", key="log_btn_sample_i2c"):
        st.session_state["log_analyzer_raw_text"] = _SAMPLE_I2C
    if col_s2.button("🚀 載入 PCIe AER 錯誤範例", key="log_btn_sample_pcie"):
        st.session_state["log_analyzer_raw_text"] = _SAMPLE_PCIE
    if col_s3.button("🚀 載入 OpenBMC 感測器遺失範例", key="log_btn_sample_bmc"):
        st.session_state["log_analyzer_raw_text"] = _SAMPLE_BMC

    with st.expander("板級拓撲設定檔（選填，用於硬體對照）", expanded=False):
        board_file = st.file_uploader(
            "上傳 Board Profile (YAML/JSON)",
            type=["yaml", "yml", "json"],
            key="log_board_profile_file",
        )
        board_text = st.text_area(
            "或直接貼上 Board Profile YAML/JSON：",
            height=100,
            key="log_board_profile_text",
        )

    board_profile: BoardProfile | None = None
    profile_raw = ""
    if board_file is not None:
        try:
            profile_raw = decode_uploaded_text(
                board_file, allowed_extensions={".yaml", ".yml", ".json"}
            )
        except Exception as exc:
            st.warning(f"Board Profile 讀取失敗：{exc}")
    elif board_text and board_text.strip():
        profile_raw = board_text.strip()

    if profile_raw:
        try:
            board_profile = load_board_profile(profile_raw)
        except Exception as exc:
            st.warning(f"Board Profile 解析失敗：{exc}")

    uploaded_log = st.file_uploader(
        "上傳日誌檔案（.log, .txt, .dmesg, .journal）",
        type=["log", "txt", "dmesg", "journal"],
        key="log_file_uploader",
    )
    if uploaded_log is not None:
        try:
            st.session_state["log_analyzer_raw_text"] = decode_uploaded_text(
                uploaded_log, allowed_extensions={".log", ".txt", ".dmesg", ".journal"}
            )
        except ValueError as exc:
            st.error(f"日誌檔案讀取錯誤：{exc}")

    log_text = st.text_area(
        "或直接貼上日誌內容（dmesg / journalctl）：",
        height=180,
        max_chars=MAX_TEXT_BYTES,
        key="log_analyzer_raw_text",
    )

    if not log_text or not log_text.strip():
        st.info(
            "請上傳日誌檔案（.log / .txt / .dmesg）或在上方文字框貼上 dmesg / journalctl 內容，亦可點擊上方按鈕載入示範日誌。"
        )
        render_page_footer()
        return

    try:
        validated_text = validate_pasted_text(log_text, label="系統日誌（System Log）")
    except Exception as exc:
        st.error(f"日誌驗證失敗：{_localize_gui_error(exc, domain='general')}")
        render_page_footer()
        return

    report = LogParser.parse_log_text(validated_text, board_profile=board_profile)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總事件數 (Total Events)", report.summary.total_events)
    c2.metric("關聯異常群組 (Incidents)", report.summary.total_incidents)
    c3.metric("涉及子系統數 (Subsystems)", len(report.summary.subsystem_counts))
    time_span_str = (
        f"{report.summary.time_span_seconds:.3f} s"
        if report.summary.time_span_seconds is not None
        else "N/A"
    )
    c4.metric("涵蓋時間跨度 (Time Span)", time_span_str)

    tab_incidents, tab_timeline, tab_dist = st.tabs(
        [
            "🚨 異常事件群組 (Incidents)",
            "⏱️ 事件時間軸 (Timeline)",
            "📊 子系統分佈 (Distribution)",
        ]
    )

    with tab_incidents:
        if not report.incidents:
            st.success("✅ 未偵測到明確異常事件群組 (No correlated incidents detected)")
        else:
            for inc in report.incidents:
                with st.expander(
                    f"[{inc.severity.value}] {inc.id}: {inc.title}",
                    expanded=True,
                ):
                    st.markdown(
                        f"**嚴重度 (Severity)**: `{inc.severity.value}` | "
                        f"**子系統 (Subsystem)**: `{inc.subsystem.value}` | "
                        f"**事件數量**: `{len(inc.events)}`"
                    )
                    if inc.root_cause_hypothesis:
                        st.markdown(
                            f"**💡 根因假設 (Root Cause Hypothesis)**: {inc.root_cause_hypothesis}"
                        )
                    if inc.board_context:
                        st.info(
                            f"**📋 板級拓撲對照 (Board Profile Context)**:\n\n{inc.board_context}"
                        )
                    if inc.recommended_actions:
                        st.markdown("**🛠️ 建議排查步驟 (Actionable Checklist)**:")
                        for act in inc.recommended_actions:
                            st.markdown(f"- [ ] {act}")
                    if inc.related_tool_page:
                        target_url = inc.related_tool_page
                        resolved = resolve_page(target_url)
                        if resolved is not None:
                            try:
                                st.page_link(
                                    resolved, label=f"🔗 前往 {target_url} 診斷工具", icon="🔍"
                                )
                            except Exception:
                                st.markdown(f"👉 **相關工具頁面**：[{target_url}](/{target_url})")
                        else:
                            st.markdown(f"👉 **相關工具頁面**：`{target_url}`")

    with tab_timeline:
        if report.events:
            event_rows: list[dict[str, Any]] = []
            for ev in report.events:
                event_rows.append(
                    {
                        "時間戳記 (Timestamp)": f"{ev.timestamp:.6f}"
                        if ev.timestamp is not None
                        else "N/A",
                        "子系統 (Subsystem)": ev.subsystem.value,
                        "嚴重度 (Severity)": ev.severity.value,
                        "訊息內容 (Message)": ev.message,
                        "規則 ID (Pattern ID)": ev.pattern_id,
                        "Bus": str(ev.bus) if ev.bus is not None else "",
                        "Address": f"0x{ev.address:02X}" if ev.address is not None else "",
                        "BDF": ev.bdf or "",
                        "驅動 (Driver)": ev.driver or "",
                        "錯誤代碼 (Errno)": ev.errno_code or "",
                    }
                )
            st.dataframe(event_rows)
        else:
            st.info("日誌中無符合規則的事件。")

    with tab_dist:
        if report.summary.subsystem_counts:
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.plotly_chart(
                    distribution_pie(
                        report.summary.subsystem_counts,
                        "子系統事件分佈 (Subsystem Distribution)",
                    ),
                )
            with col_c2:
                st.plotly_chart(
                    distribution_bar(
                        report.summary.subsystem_counts,
                        "子系統事件數量 (Subsystem Event Counts)",
                    ),
                )
        else:
            st.info("無子系統分佈資料。")

    with st.expander("日誌 A/B 對比分析 (Baseline vs Candidate)", expanded=False):
        st.markdown("比對目前日誌（Candidate）與基準日誌（Baseline）的事件與異常差異。")
        baseline_file = st.file_uploader(
            "上傳 Baseline 日誌檔案",
            type=["log", "txt", "dmesg", "journal"],
            key="log_diff_baseline_uploader",
        )
        baseline_text = st.text_area(
            "或直接貼上 Baseline 日誌內容：",
            height=120,
            key="log_diff_baseline_text",
        )

        baseline_raw = ""
        if baseline_file is not None:
            try:
                baseline_raw = decode_uploaded_text(
                    baseline_file, allowed_extensions={".log", ".txt", ".dmesg", ".journal"}
                )
            except ValueError as exc:
                st.error(f"Baseline 檔案讀取失敗：{exc}")
        elif baseline_text and baseline_text.strip():
            baseline_raw = baseline_text.strip()

        if baseline_raw:
            try:
                validated_base = validate_pasted_text(baseline_raw, label="Baseline 日誌")
                base_report = LogParser.parse_log_text(validated_base, board_profile=board_profile)
                diff_res = LogDiffEngine.compare(base_report, report)

                st.markdown("### 對比摘要 (Diff Summary)")
                st.info(diff_res.summary)

                d_c1, d_c2, d_c3, d_c4 = st.columns(4)
                d_c1.metric("Baseline 事件數", diff_res.baseline_event_count)
                d_c2.metric("Candidate 事件數", diff_res.candidate_event_count)
                delta_str = (
                    f"+{diff_res.event_count_delta}"
                    if diff_res.event_count_delta > 0
                    else f"{diff_res.event_count_delta}"
                )
                d_c3.metric("事件數變化", delta_str)
                d_c4.metric(
                    "對比結果", "相同 (Identical)" if diff_res.is_identical else "有差異 (Changed)"
                )

                diff_col1, diff_col2 = st.columns(2)
                with diff_col1:
                    st.markdown("**🚨 新增異常 (New Incidents)**")
                    if diff_res.new_incidents:
                        for inc_name in diff_res.new_incidents:
                            st.markdown(f"- 🔴 {inc_name}")
                    else:
                        st.caption("無新增異常")
                with diff_col2:
                    st.markdown("**✅ 已解決異常 (Resolved Incidents)**")
                    if diff_res.resolved_incidents:
                        for inc_name in diff_res.resolved_incidents:
                            st.markdown(f"- 🟢 {inc_name}")
                    else:
                        st.caption("無已解決異常")

                if diff_res.common_incidents:
                    with st.expander("共同異常 (Common Incidents)"):
                        for inc_name in diff_res.common_incidents:
                            st.markdown(f"- ⚪ {inc_name}")
            except Exception as exc:
                st.error(f"Baseline 解析失敗：{exc}")
        else:
            st.caption("請上傳或貼上 Baseline 日誌以進行 A/B 差異比對。")

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        md_report = format_log_markdown(report)
        st.download_button(
            "⬇️ 下載 Markdown 診斷報告",
            data=md_report,
            file_name="system_log_diagnostic_report.md",
            mime="text/markdown",
            key="log_download_md_report",
        )
    with col_d2:
        st.download_button(
            "⬇️ 下載 JSON 診斷報告",
            data=report.to_json(),
            file_name="system_log_diagnostic_report.json",
            mime="application/json",
            key="log_download_json_report",
        )

    render_page_footer()


__all__ = ["format_log_markdown", "render"]
