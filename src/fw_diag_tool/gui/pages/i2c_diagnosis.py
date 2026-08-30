from __future__ import annotations

import hashlib
import math

import pandas as pd
import streamlit as st

from fw_diag_tool import __version__
from fw_diag_tool.board_profile import load_board_profile
from fw_diag_tool.errors import ResourceLimitError
from fw_diag_tool.gui.session_io import (
    capture_matches,
    restore_i2c_board_profile,
    serialize_i2c_session,
)
from fw_diag_tool.gui.shared import (
    DEFAULT_I2C_TIMEOUT_MS,
    GUI_ANALYSIS_LIMITS,
    _localize_gui_error,
    _reset_i2c_session_state,
    analyze_i2c_input,
    render_guide_expander,
)
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES, decode_uploaded_text
from fw_diag_tool.i2c.input import I2CInputFormat, normalize_i2c_input_format
from fw_diag_tool.i2c.localization import (
    localize_ack,
    localize_category,
    localize_device_name,
    localize_direction,
    localize_evidence,
    localize_explanatory_text,
    localize_health_grade,
    localize_input_format,
    localize_issue_advice,
    localize_issue_description,
    localize_issue_root_cause,
    localize_issue_title,
    localize_quality_message,
    localize_semantic_summary,
    localize_severity,
    localize_status,
)
from fw_diag_tool.i2c.models import I2CDirection
from fw_diag_tool.i2c.raw_adapter import raw_decode_to_waveform
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.i2c.status import get_transaction_status
from fw_diag_tool.i2c.timing import frequency_samples_khz
from fw_diag_tool.i2c.timing_charts import I2CTimingCharts
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor
from fw_diag_tool.resources import load_i2c_sample
from fw_diag_tool.session.session_manager import SessionManager

MAX_UPLOAD_MIB = MAX_UPLOAD_BYTES // (1024 * 1024)


def render() -> None:
    st.header("I2C / SMBus / PMBus 協定分析與數位波形檢視")
    render_guide_expander("chapters/ch01_i2c_pmbus.md", "📖 點擊展開：I2C/PMBus 波形診斷手冊")
    render_guide_expander(
        "chapters/appendix_chart_guide.md", "📊 點擊展開：附錄 A 圖表與數據判讀指南"
    )
    session_upload = st.file_uploader(
        "載入可重現 Session（需另行提供原始 capture 才能重播）",
        type=["json"],
        max_upload_size=SessionManager.MAX_SESSION_BYTES // (1024 * 1024),
        key="i2c_session_upload",
    )
    session_upload_bytes = session_upload.getvalue() if session_upload is not None else None
    session_upload_digest = (
        hashlib.sha256(session_upload_bytes).hexdigest()
        if session_upload_bytes is not None
        else None
    )
    previous_session_upload_digest = st.session_state.get("i2c_session_upload_digest")
    if "i2c_session_upload_digest" not in st.session_state:
        st.session_state["i2c_session_upload_digest"] = session_upload_digest
    elif previous_session_upload_digest != session_upload_digest:
        _reset_i2c_session_state()
        st.session_state["i2c_session_upload_digest"] = session_upload_digest

    loaded_session = None
    if session_upload is not None:
        try:
            loaded_session = SessionManager.deserialize_session(session_upload_bytes or b"")
        except (TypeError, ValueError) as exc:
            st.error(f"無法載入 Session：{_localize_gui_error(exc, domain='session')}")
        else:
            try:
                # Validate embedded board-profile identity/hash before putting
                # its YAML into widget state.  A session is provenance data,
                # not a trusted configuration blob.
                restore_i2c_board_profile(loaded_session)
                timeout_present = "smbus_timeout_ms" in loaded_session.config
                saved_timeout = loaded_session.config.get(
                    "smbus_timeout_ms", DEFAULT_I2C_TIMEOUT_MS
                )
                if timeout_present and (
                    isinstance(saved_timeout, bool)
                    or not isinstance(saved_timeout, (int, float))
                    or not math.isfinite(float(saved_timeout))
                    or not 1.0 <= float(saved_timeout) <= 100.0
                ):
                    raise ValueError(
                        "session smbus_timeout_ms must be a finite value between 1 and 100"
                    )
                saved_mode = loaded_session.config.get("input_mode")
                saved_format = loaded_session.config.get("input_format")
                normalized_mode = (
                    normalize_i2c_input_format(saved_mode) if saved_mode is not None else None
                )
                normalized_format = (
                    normalize_i2c_input_format(saved_format) if saved_format is not None else None
                )
                if (
                    normalized_mode is not None
                    and normalized_format is not None
                    and normalized_mode is not normalized_format
                ):
                    raise ValueError(
                        "session input_mode and input_format identify different I2C formats"
                    )
                saved_input_format = (
                    normalized_format or normalized_mode or I2CInputFormat.DECODED_CSV
                )
            except (TypeError, ValueError) as exc:
                st.error(
                    "Session 內的分析設定未通過完整性檢查："
                    f"{_localize_gui_error(exc, domain='session')}"
                )
                loaded_session = None
            if loaded_session is not None:
                if loaded_session.capture_sha256 is None:
                    st.warning(
                        "此 Session 沒有 capture SHA-256；只顯示歷史摘要，未自動套用保存的分析設定，"
                        "也無法驗證重播。請重新分析原始 capture 以建立可重現 Session。"
                    )
                else:
                    session_identity = (
                        loaded_session.capture_sha256,
                        loaded_session.created_at,
                        loaded_session.name,
                        session_upload_digest,
                    )
                    if st.session_state.get("i2c_loaded_session_identity") != session_identity:
                        st.session_state["i2c_smbus_timeout"] = float(saved_timeout)
                        st.session_state["i2c_input_format"] = saved_input_format.value
                        saved_profile = loaded_session.config.get("board_profile_content")
                        st.session_state["i2c_board_profile_yaml"] = (
                            saved_profile if isinstance(saved_profile, str) else ""
                        )
                        st.session_state["i2c_loaded_session_identity"] = session_identity
                st.info(
                    f"Session：{loaded_session.name or '-'}｜工具 {loaded_session.tool_version}｜"
                    f"輸入 {loaded_session.config.get('input_name', '-')}"
                )
                with st.expander("檢視 Session 報告摘要", expanded=False):
                    st.caption(
                        "這是 session 保存的歷史摘要；在提供 capture 並通過 SHA-256 比對前，"
                        "不能視為目前輸入的重新分析結果。"
                    )
                    st.json(loaded_session.report, expanded=False)
    sample_specs = {
        "套件解碼分析器（18 筆）": (
            "builtin-decoded",
            I2CInputFormat.DECODED_CSV,
            "saleae_normal_pmbus_eeprom.csv",
        ),
        "逐位元組解碼（5 筆，含 ACK／語意）": (
            "split-decoded",
            I2CInputFormat.DECODED_CSV,
            "i2c_split_decoded.csv",
        ),
        "原始數位量測（100 kHz、1 筆）": (
            "raw-100khz",
            I2CInputFormat.RAW_DIGITAL,
            "i2c_raw_100khz.csv",
        ),
        "文字追蹤記錄（2 筆）": (
            "text-trace",
            I2CInputFormat.TEXT_TRACE,
            "i2c_text_trace.log",
        ),
    }
    sample_label = st.selectbox(
        "教學範例（可直接載入；完整檔案與欄位契約見 ch01）", list(sample_specs)
    )
    use_sample = st.button("載入內建測試波形")
    if use_sample:
        sample_key, sample_format, _sample_filename = sample_specs[sample_label]
        st.session_state["i2c_input_format"] = sample_format.value
        st.session_state["i2c_sample_active"] = True
        st.session_state["i2c_sample_key"] = sample_key
        st.session_state["i2c_sample_content"] = load_i2c_sample(sample_key)
    input_mode = st.radio(
        "輸入資料型態（必須與檔案格式一致）",
        [fmt.value for fmt in I2CInputFormat],
        format_func=localize_input_format,
        horizontal=True,
        key="i2c_input_format",
        help="解碼 CSV 解析交易欄位；文字追蹤記錄解析 S/Sr/P 與 0xNN token；原始數位 CSV 才會量測 SCL/SDA 頻率。",
    )
    if st.session_state.get("i2c_sample_active"):
        active_sample_key = st.session_state.get("i2c_sample_key")
        active_sample = next(
            (
                (sample_format, filename)
                for sample_key, sample_format, filename in sample_specs.values()
                if sample_key == active_sample_key
            ),
            None,
        )
        if active_sample is None or active_sample[0].value != input_mode:
            st.session_state["i2c_sample_active"] = False
            st.session_state.pop("i2c_sample_content", None)
            st.session_state.pop("i2c_sample_key", None)
            st.warning("已切換輸入格式；原教學範例已清除，請重新載入相符格式的範例或上傳檔案。")
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader(
            "選擇或拖放 Saleae CSV／追蹤記錄檔案",
            type=["csv", "txt", "log"],
            max_upload_size=MAX_UPLOAD_MIB,
        )
    with col2:
        if "i2c_smbus_timeout" not in st.session_state:
            st.session_state["i2c_smbus_timeout"] = DEFAULT_I2C_TIMEOUT_MS
        smbus_timeout = st.number_input(
            "SMBus 時鐘延展逾時（ms）",
            min_value=1.0,
            max_value=100.0,
            step=1.0,
            key="i2c_smbus_timeout",
        )

    csv_content = None
    raw_capture_result = None
    input_name = None
    input_bytes = None
    if uploaded_file is not None:
        try:
            csv_content = decode_uploaded_text(
                uploaded_file, allowed_extensions={".csv", ".txt", ".log"}
            )
            st.session_state["i2c_sample_active"] = False
            input_name = uploaded_file.name
            input_bytes = uploaded_file.getvalue()
            if loaded_session is not None:
                match = capture_matches(loaded_session, input_bytes)
                if match is False:
                    st.error("Session SHA-256 與上傳的 capture 不一致；已停止重播。")
                    csv_content = None
                elif match is None:
                    st.warning(
                        "此 Session 沒有 capture SHA-256，無法驗證重播；本次僅依目前輸入格式分析上傳檔案。"
                    )
                    loaded_session = None
                elif match is True:
                    saved_format = loaded_session.config.get("input_format")
                    if saved_format is None:
                        saved_format = loaded_session.config.get(
                            "input_mode", I2CInputFormat.DECODED_CSV.value
                        )
                    settings_match = True
                    if saved_format is not None and normalize_i2c_input_format(
                        saved_format
                    ) is not normalize_i2c_input_format(input_mode):
                        settings_match = False
                    saved_timeout = loaded_session.config.get(
                        "smbus_timeout_ms", DEFAULT_I2C_TIMEOUT_MS
                    )
                    if float(saved_timeout) != float(smbus_timeout):
                        settings_match = False
                    saved_profile = loaded_session.config.get("board_profile_content", "")
                    current_profile = st.session_state.get("i2c_board_profile_yaml", "")
                    if (
                        isinstance(saved_profile, str)
                        and saved_profile.strip() != str(current_profile).strip()
                    ):
                        settings_match = False
                    if settings_match:
                        st.success("Session SHA-256 與 capture 相符，已套用保存的分析設定。")
                    else:
                        st.warning(
                            "Session SHA-256 與 capture 相符，但目前輸入格式、逾時設定或板級設定檔 "
                            "已被修改；本次分析不宣稱是原設定的重播。"
                        )
                        loaded_session = None
        except ValueError as exc:
            st.error(f"無法讀取 trace：{exc}")
    elif st.session_state.get("i2c_sample_active"):
        csv_content = st.session_state.get("i2c_sample_content")
        if isinstance(csv_content, str):
            sample_key = st.session_state.get("i2c_sample_key", "builtin-decoded")
            sample_filenames = {
                sample_key: filename for _, (sample_key, _, filename) in sample_specs.items()
            }
            input_name = f"builtin:{sample_filenames.get(sample_key, sample_key)}"
            input_bytes = csv_content.encode("utf-8")
            if use_sample:
                st.info(
                    "已載入內建範例 CSV！"
                    if sample_key == "builtin-decoded"
                    else f"已載入範例：{sample_key}"
                )

    board_profile_yaml = None
    with st.expander(
        "板級設定檔（Board Profile；選填，貼上 YAML 以啟用裝置名稱／PMBus 解碼）",
        expanded=False,
    ):
        profile_text = st.text_area(
            "板級設定檔 YAML（Board Profile；留空則不套用）",
            height=100,
            key="i2c_board_profile_yaml",
        )
        if profile_text.strip():
            board_profile_yaml = profile_text

    if csv_content is not None:
        try:
            report, raw_capture_result = analyze_i2c_input(
                csv_content, input_mode, float(smbus_timeout), board_profile_yaml
            )
        except (TypeError, ValueError) as exc:
            st.error(f"無法解析 I2C 輸入：{exc}")
            st.stop()
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("總傳輸次數", report.total_transactions)
        kpi2.metric(
            "已證實協定異常",
            len(report.issues),
            help="只計入有足夠證據的異常；資料缺口另列在品質面板。",
        )
        timing = report.timing_stats
        if timing.frequency_sample_count:
            kpi3.metric(
                "平均時鐘頻率",
                f"{timing.avg_frequency_khz:.1f} kHz",
                help="由來源提供的位元率或位元組持續時間推算；不是從解碼表的交易時間臆測。",
            )
            kpi4.metric(
                "時鐘抖動（Jitter）",
                f"{timing.frequency_jitter_pct:.1f} %",
                help="僅對有來源時序證據的頻率樣本計算。",
            )
        else:
            kpi3.metric(
                "平均時鐘頻率",
                "不可用",
                help="目前檔案沒有逐位元組位元率／持續時間；請匯出原始數位 SCL/SDA 轉態資料才能量測。",
            )
            kpi4.metric(
                "時鐘抖動（Jitter）",
                "不可用",
                help="沒有頻率樣本，因此不顯示 0% 這種容易誤解的數字。",
            )
        st.caption(
            f"時鐘頻率證據（Frequency Evidence）：{localize_evidence(timing.frequency_evidence)}；"
            f"有效時序樣本數：{timing.frequency_sample_count}。"
            f"匯流排使用率證據：{localize_evidence(timing.bus_utilization_evidence)}。"
        )
        if report.data_quality_issues:
            with st.expander("⚠ 資料證據與限制（先看這裡）", expanded=True):
                st.caption(
                    "診斷結果只代表檔案中實際提供的欄位；缺少時間戳記、ACK 或 SCL/SDA 邊緣時，工具不會把未知值當成正常。"
                )
                for quality in report.data_quality_issues:
                    zh_quality_msg = localize_explanatory_text(
                        localize_quality_message(quality.code, quality.message)
                    )
                    st.markdown(f"- **{quality.code}**（{quality.count} 筆）：{zh_quality_msg}")
        st.divider()

        tab_tx, tab_wave, tab_anom, tab_timing, tab_md = st.tabs(
            [
                "📜 封包交易列表（Transactions）",
                "📈 數位方波與協定軌（Waveform）",
                "🚨 異常診斷（Anomalies）",
                "📊 匯流排時序與健康圖表（Bus Timing & Health）",
                "📝 Markdown 診斷報告（Markdown Report）",
            ]
        )

        selected_idx = 0
        if report.transactions:
            tx_options = [
                f"Tx #{t.id}: {f'0x{t.address_7bit:02X}' if t.address_available else '位址未知'} "
                f"({localize_direction(t.direction if t.direction_available else None)})"
                for t in report.transactions
            ]
            selected_idx = st.selectbox(
                "目前交易（Waveform 會聚焦此筆）",
                range(len(tx_options)),
                format_func=lambda i: tx_options[i],
                key="i2c_selected_tx",
            )

        with tab_wave:
            st.subheader("I2C 互動式數位方波與協定疊加（SCL／SDA／Protocol Overlay）")
            if report.transactions:
                selected_tx = report.transactions[selected_idx]
                if raw_capture_result is not None:
                    st.success(
                        "這是邏輯分析儀原始數位轉態的實測 0/1 波形；"
                        "請注意：此為邏輯訊號轉態，不是類比電壓或上升時間（Rise Time）量測。"
                    )
                    raw_wave = raw_decode_to_waveform(
                        raw_capture_result,
                        transaction_index=selected_idx,
                        limits=GUI_ANALYSIS_LIMITS,
                    )
                    st.plotly_chart(
                        I2CWaveformReconstructor.create_plotly_figure(
                            raw_wave,
                            title="實測邏輯分析儀數位波形與協定疊加（Measured Raw Digital I2C Waveform）",
                        ),
                        width="stretch",
                    )
                    st.caption(
                        f"目前選取 Tx #{selected_tx.id}；來源轉態數 {raw_wave.source_transition_count} 個、"
                        f"繪製轉態數 {raw_wave.rendered_transition_count} 個。"
                        f"{'（已執行確定性降取樣）' if raw_wave.downsampled else ''}"
                    )
                else:
                    selected_frequency_samples = frequency_samples_khz([selected_tx])
                    measured_clock_khz = (
                        sum(selected_frequency_samples) / len(selected_frequency_samples)
                        if selected_frequency_samples
                        else None
                    )
                    if measured_clock_khz is None:
                        st.info(
                            "目前顯示的是根據解碼數據重建之理想數位波形（Reconstructed），非邏輯分析儀實測電壓波形。"
                            "此 CSV 缺少 SCL/SDA 轉態邊緣；若要觀察真實實體時序，請匯出原始數位轉態 CSV。"
                        )
                    else:
                        st.caption(
                            f"波形時鐘採用此筆交易來源之時序證據（{len(selected_frequency_samples)} 個樣本）；"
                            "仍屬協定層理想時序重建，非類比電壓量測。"
                        )
                    try:
                        reconstructor = I2CWaveformReconstructor(
                            default_clock_khz=measured_clock_khz or 100.0
                        )
                        wave_data = reconstructor.reconstruct_transaction_waveform(
                            selected_tx,
                            max_points=GUI_ANALYSIS_LIMITS.max_waveform_points,
                        )
                        address_text = (
                            f"0x{selected_tx.address_7bit:02X}"
                            if selected_tx.address_available
                            else "位址未知"
                        )
                        direction_text = (
                            localize_direction(selected_tx.direction)
                            if selected_tx.direction_available
                            and isinstance(selected_tx.direction, I2CDirection)
                            else "方向未知"
                        )
                        fig = reconstructor.create_plotly_figure(
                            wave_data,
                            title=f"理想重建 Tx #{selected_tx.id} 數位波形（Reconstructed Waveform）：{address_text} {direction_text}",
                        )
                        st.plotly_chart(fig, width="stretch")
                    except ResourceLimitError as exc:
                        st.warning(
                            f"這筆交易太大，已完成分析但略過波形繪圖：{exc}。"
                            "請改選較短的交易，或先分段匯出 capture。"
                        )
                    except (TypeError, ValueError) as exc:
                        st.warning(f"此交易缺少可重建數位波形所需的證據：{exc}")
                if selected_tx.clock_stretching_events:
                    stretch_details = []
                    for event in selected_tx.clock_stretching_events:
                        duration_text = f"{float(event.get('duration_ms', 0.0)):.3f} ms"
                        evidence_text = localize_evidence(event.get('evidence', 'unknown'))
                        if event.get("attribution") == "aggregate_unattributable":
                            stretch_details.append(
                                f"彙總列：持續時間 {duration_text}；{evidence_text}；"
                                "無法歸屬特定位元組，也未繪製於任何 ACK 前"
                            )
                        else:
                            stretch_details.append(
                                f"位元組 {event.get('byte_val', '未知')}（byte_val）："
                                f"持續時間 {duration_text}；{evidence_text}；"
                                "延展區段繪製在該 byte ACK 前"
                            )
                    st.caption(
                        "時鐘延展證據（Clock Stretching Evidence）："
                        "來源位元組（byte_val）、持續時間（duration）與來源證據（evidence）："
                        f"{'；'.join(stretch_details)}。"
                    )
            else:
                st.info("無交易資料可繪製波形。")

        with tab_anom:
            if not report.issues:
                if report.data_quality_issues:
                    st.warning("沒有被證明的協定異常；但資料證據不完整，不能直接視為完全正常。")
                else:
                    st.success("🎉 未偵測到任何 I2C/SMBus 時序與通訊異常！")
            else:
                st.caption(
                    f"共 {len(report.issues)} 筆；優先顯示前 50 筆，避免大型 capture 讓瀏覽器一次展開數千面板。"
                )
                for idx, issue in enumerate(report.issues[:50], 1):
                    addr_str = (
                        f"0x{issue.address_7bit:02X}" if issue.address_7bit is not None else "未知"
                    )
                    issue_title = localize_issue_title(issue.code, issue.title)
                    issue_description = localize_issue_description(issue.description)
                    issue_root_cause = localize_issue_root_cause(issue.root_cause_analysis)
                    with st.expander(
                        f"[{localize_severity(issue.severity)}] #{idx}：{issue.code} - {issue_title}（位址：{addr_str}）",
                        expanded=(idx == 1),
                    ):
                        st.markdown(f"**現象描述**：{issue_description}")
                        st.markdown(
                            f"**可能原因（Hypotheses；不是已證明的根因）**：\n{issue_root_cause}"
                        )
                        st.markdown("**排查行動清單**：")
                        for adv in issue.actionable_advice:
                            st.markdown(f"- ✔ {localize_issue_advice(adv)}")

        with tab_timing:
            st.subheader("匯流排交易／協定健康啟發式評等（Bus Health Heuristic）")
            st.caption(
                "健康評等僅根據已知 ACK/NACK 與時序計算；主機讀取最後 1 個位元組的 NACK 為標準正常結束條件。"
                "缺少 ACK 資料時顯示 N/A，嚴格避免把未知狀態誤導為通過。"
            )
            health_df = I2CTimingCharts.get_device_health_summary(report)
            display_health_df = health_df.copy()
            display_health_df["Device Name"] = display_health_df["Device Name"].map(
                lambda name: localize_device_name(str(name))
            )
            display_health_df["Category"] = display_health_df["Category"].map(
                lambda c: localize_category(str(c))
            )
            display_health_df["Health Grade"] = display_health_df["Health Grade"].map(
                lambda g: localize_health_grade(str(g))
            )
            display_health_df = display_health_df.rename(
                columns={
                    "Slave Address": "從裝置 7-bit 位址（Slave Address）",
                    "Device Name": "識別晶片型號（Device Profile）",
                    "Category": "裝置類別（Category）",
                    "Total Transactions": "總傳輸次數",
                    "NACK Count": "NACK 失敗數",
                    "Unknown ACK Count": "未知 ACK 數",
                    "Success Rate": "通訊成功率（Success Rate）",
                    "Clock Stretches": "時鐘延展次數",
                    "Health Grade": "健康等級（Health Grade）",
                }
            )
            st.table(display_health_df)
            c_t1, c_t2 = st.columns(2)
            with c_t1:
                st.plotly_chart(
                    I2CTimingCharts.create_frequency_distribution(report), width="stretch"
                )
            with c_t2:
                st.plotly_chart(
                    I2CTimingCharts.create_bus_activity_timeline(report), width="stretch"
                )

        with tab_tx:
            tx_data = [
                {
                    "交易 ID": t.id,
                    "時間（s）": f"{t.start_time:.6f}" if t.timestamp_available else "不可用",
                    "7-bit 位址": f"0x{t.address_7bit:02X}" if t.address_available else "不可用",
                    "傳輸方向（R/W）": localize_direction(
                        t.direction if t.direction_available else None
                    ),
                    "位址應答（Address ACK）": localize_ack(t.address_ack),
                    "整體狀態（Overall Status）": localize_status(
                        get_transaction_status(
                            t,
                            next_transaction=(
                                report.transactions[index + 1]
                                if index + 1 < len(report.transactions)
                                else None
                            ),
                        )
                    ),
                    "多工拓撲（Topology）": localize_explanatory_text(t.mux_topology or "-"),
                    "資料長度（位元組）": len(t.data_bytes),
                    "原始資料（Hex Dump）": t.hex_dump,
                    "解碼語意（Semantic Meaning）": localize_semantic_summary(t.semantic_summary),
                }
                for index, t in enumerate(report.transactions)
            ]
            st.dataframe(pd.DataFrame(tx_data), width="stretch")

        with tab_md:
            board_profile_metadata = "未套用（none）"
            if board_profile_yaml:
                profile_for_metadata = load_board_profile(board_profile_yaml)
                board_profile_metadata = (
                    f"{profile_for_metadata.board_name}@{profile_for_metadata.version}; "
                    f"sha256={hashlib.sha256(profile_for_metadata.to_yaml().encode('utf-8')).hexdigest()}"
                )
            metadata = {
                "tool": f"fw-diag-tool {__version__}",
                "input_name": input_name or "-",
                "input_sha256": hashlib.sha256(input_bytes).hexdigest()
                if input_bytes is not None
                else None,
                "input_format": input_mode,
                "smbus_timeout_ms": float(smbus_timeout),
                "evidence_sample_count": report.timing_stats.frequency_sample_count,
                "board_profile": board_profile_metadata,
            }
            md_out = I2CReporter.generate_markdown(report, metadata=metadata)
            st.markdown(md_out)
            with st.expander("📄 檢視原始 Markdown 原始碼", expanded=False):
                st.code(md_out, language="markdown")
            st.download_button("下載 Markdown 報告", md_out, file_name="i2c_report.md")
            if input_name is not None and input_bytes is not None:
                session_json = serialize_i2c_session(
                    report.to_dict(),
                    input_name=input_name,
                    input_bytes=input_bytes,
                    input_mode=input_mode,
                    smbus_timeout_ms=float(smbus_timeout),
                    board_profile_yaml=board_profile_yaml,
                )
                st.download_button(
                    "下載可重現 Session（不含原始檔）",
                    session_json,
                    file_name="i2c_analysis.fwsession.json",
                    mime="application/json",
                )
                st.caption("Session 只保存報告、設定與輸入 SHA-256；請另外保留原始 capture。")
