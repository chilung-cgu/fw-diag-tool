import hashlib
import math
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import yaml

from fw_diag_tool import __version__
from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog
from fw_diag_tool.board_profile import load_board_profile
from fw_diag_tool.codegen.c_header import CHeaderGenerator
from fw_diag_tool.codegen.driver_gen import I2CDriverCodeGenerator
from fw_diag_tool.codegen.dts_gen import DeviceTreeGenerator
from fw_diag_tool.errors import ResourceLimitError
from fw_diag_tool.fault_arena.fixtures import FaultArenaFixtures
from fw_diag_tool.gui.guide_resources import load_guide_text, prepare_guide_markdown
from fw_diag_tool.gui.pages.i2c_builder import (
    I2C_BUILDER_PRESETS,
    MAX_BUILDER_DATA_BYTES,
    MAX_BUILDER_WAVEFORM_POINTS,
    build_i2c_bundle,
    max_write_data_bytes,
    parse_hex_bytes,
    parse_hex_integer,
    preset_widget_state,
)
from fw_diag_tool.gui.pages.i2c_page import analyze_i2c as analyze_i2c_controller
from fw_diag_tool.gui.session_io import (
    capture_matches,
    restore_i2c_board_profile,
    serialize_i2c_session,
)
from fw_diag_tool.gui.uploads import (
    MAX_TEXT_BYTES,
    MAX_UPLOAD_BYTES,
    decode_uploaded_text,
    validate_pasted_text,
)
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
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
    localize_platform,
    localize_preset,
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
from fw_diag_tool.i2c.transfer_spec import Endianness, I2CTransferOperation, I2CTransferSpec
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor
from fw_diag_tool.i2c.waveform_diff import WaveformDiffEngine
from fw_diag_tool.i2c.waveform_diff_report import (
    format_waveform_diff_markdown,
    localize_diff_description,
    localize_diff_hint,
    localize_diff_summary,
    localize_diff_type,
)
from fw_diag_tool.limits import AnalysisLimits
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.mctp.reporter import ServerMgmtReporter
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.resources import (
    load_i2c_sample,
    load_pcie_dmesg_sample,
    load_spi_sample,
    load_waveform_diff_samples,
)
from fw_diag_tool.session.session_manager import SessionManager
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.reporter import SPIReporter
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter

MAX_UPLOAD_MIB = MAX_UPLOAD_BYTES // (1024 * 1024)
DEFAULT_I2C_TIMEOUT_MS = 25.0

# GUI uses fixed safe limits independent of CLI overrides.
GUI_ANALYSIS_LIMITS = AnalysisLimits()
MAX_PACKET_HEX_CHARS = 64 * 1024


def _reset_i2c_session_state() -> None:
    st.session_state["i2c_input_format"] = I2CInputFormat.DECODED_CSV.value
    st.session_state["i2c_smbus_timeout"] = DEFAULT_I2C_TIMEOUT_MS
    st.session_state["i2c_board_profile_yaml"] = ""
    # A session upload supersedes any previously selected teaching sample.
    # Leaving the sample active would analyze the old decoded bytes using the
    # restored raw/text mode when the session is uploaded without its capture.
    st.session_state["i2c_sample_active"] = False
    st.session_state.pop("i2c_sample_content", None)
    st.session_state.pop("i2c_sample_key", None)
    st.session_state.pop("i2c_loaded_session_identity", None)


@st.cache_data(show_spinner=False)
def analyze_i2c_input(
    csv_content: str,
    input_mode: str,
    smbus_timeout_ms: float,
    board_profile_yaml: str | None = None,
) -> tuple[Any, Any]:
    profile = load_board_profile(board_profile_yaml) if board_profile_yaml else None
    return analyze_i2c_controller(
        csv_content,
        input_mode=input_mode,
        input_format=None,
        smbus_timeout_ms=smbus_timeout_ms,
        board_profile=profile,
        limits=GUI_ANALYSIS_LIMITS,
    )


@st.cache_data(show_spinner=False)
def analyze_spi_input(csv_content: str, max_page_size: int = 256) -> Any:
    return SPIDiagnosticEngine(max_page_size=max_page_size).analyze_csv_content(csv_content)


_REGISTER_MEANING_ZH = {
    "OK": "正常（OK）",
    "Normal": "正常（Normal）",
    "Ready": "就緒（Ready）",
    "Busy": "忙碌（Busy）",
    "Unit On": "裝置開啟（Unit On）",
    "Unit Off": "裝置關閉（Unit Off）",
    "Unit is Outputting Power": "裝置正在輸出電力（Unit is Outputting Power）",
    "Unit is Off": "裝置已關閉（Unit is Off）",
    "Vout Overvoltage Fault": "輸出過電壓故障（Vout Overvoltage Fault）",
    "Iout Overcurrent Fault": "輸出過電流故障（Iout Overcurrent Fault）",
    "Vin Undervoltage Fault": "輸入欠電壓故障（Vin Undervoltage Fault）",
    "Overtemperature Alarm": "過溫警報（Overtemperature Alarm）",
    "CML Error": "CML 通訊／記憶體／邏輯錯誤（CML Error）",
    "VOUT Fault/Warning occurred": "發生 VOUT 故障／警告（VOUT Fault/Warning occurred）",
    "IOUT Fault/Warning occurred": "發生 IOUT 故障／警告（IOUT Fault/Warning occurred）",
    "Input Voltage/Current/Power Fault occurred": "發生輸入電壓／電流／功率故障（Input Voltage/Current/Power Fault occurred）",
    "Manufacturer Specific Fault": "製造商專屬故障（Manufacturer Specific Fault）",
    "POWER_GOOD Asserted (Normal)": "POWER_GOOD 有效（正常）（POWER_GOOD Asserted）",
    "POWER_GOOD Negated (Power Rail Down)": "POWER_GOOD 無效（電源軌關閉）（POWER_GOOD Negated）",
    "Overtemperature Fault/Warning occurred": "發生過溫故障／警告（Overtemperature Fault/Warning occurred）",
    "Communication, Memory or Logic (CML) Fault": "通訊／記憶體／邏輯（CML）故障（Communication, Memory or Logic Fault）",
    "Device Busy / Packet Rejected": "裝置忙碌／封包被拒絕（Device Busy / Packet Rejected）",
    "Data Link Protocol Error (Active)": "Data Link Protocol 錯誤（作用中）（Data Link Protocol Error）",
    "Surprise Down Error (Active)": "Surprise Down 錯誤（作用中）（Surprise Down Error）",
    "Poisoned TLP Received (Active)": "收到 Poisoned TLP（作用中）（Poisoned TLP Received）",
    "Flow Control Protocol Error (Active)": "Flow Control Protocol 錯誤（作用中）（Flow Control Protocol Error）",
    "Completion Timeout (Active)": "Completion Timeout（作用中）（Completion Timeout）",
    "Completer Abort (Active)": "Completer Abort（作用中）（Completer Abort）",
    "Unexpected Completion (Active)": "非預期 Completion（作用中）（Unexpected Completion）",
    "Receiver Overflow (Active)": "Receiver Overflow（作用中）（Receiver Overflow）",
    "Malformed TLP (Active)": "Malformed TLP（作用中）（Malformed TLP）",
    "ECRC Error (Active)": "ECRC 錯誤（作用中）（ECRC Error）",
    "Unsupported Request (Active)": "Unsupported Request（作用中）（Unsupported Request）",
    "ACS Violation (Active)": "ACS 違規（作用中）（ACS Violation）",
    "Uncorrectable Internal Error (Active)": "不可修正內部錯誤（作用中）（Uncorrectable Internal Error）",
}


def _localize_register_meaning(value: object) -> str:
    """Make built-in YAML meanings readable while preserving source wording."""
    text = str(value)
    if text in _REGISTER_MEANING_ZH:
        return _REGISTER_MEANING_ZH[text]
    if text.startswith("Raw value: "):
        return f"原始值：{text.removeprefix('Raw value: ')}（Raw value）"
    return text


def render_guide_expander(
    chapter_rel_path: str, label: str = "📖 點擊展開本功能詳細實戰教學手冊"
) -> None:
    markdown = load_guide_text(chapter_rel_path)
    if markdown is not None:
        with st.expander(label, expanded=False):
            st.markdown(prepare_guide_markdown(markdown, chapter_rel_path))


st.set_page_config(page_title="韌體訊號與協定診斷套件", page_icon="⚡", layout="wide")
st.title("⚡ 韌體訊號與協定診斷套件")
st.caption("本機 I2C/PMBus 協定診斷與韌體學習工作台")

menu = st.sidebar.radio(
    "功能導覽",
    [
        "📊 I2C / PMBus 診斷與波形檢視",
        "🎨 I2C 封包模擬器與驅動產生",
        "⚖️ 雙波形對比檢視（Waveform Diff）",
        "📟 UART 崩潰轉儲與 HardFault 分析（Crash Dump）",
        "🌐 MCTP／IPMB 伺服器管理協定解析",
        "🌲 Device Tree（.dts）產生器",
        "🚀 PCIe Config Space 與 AER 診斷",
        "⚡ SPI Flash 協定診斷",
        "🎛 晶片暫存器 Bitfield 解碼器",
        "🛠 C 語言 Register 巨集產生器",
        "🏆 初階 Firmware 實戰除錯實驗室（Fault Arena）",
        "📚 韌體除錯指南與 SOP",
    ],
)

# 1. I2C / PMBus
if menu == "📊 I2C / PMBus 診斷與波形檢視":
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
            st.error(f"無法載入 Session：{exc}")
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
                st.error(f"Session 內的分析設定未通過完整性檢查：{exc}")
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

# 2. Packet Builder & Driver CodeGen
elif menu == "🎨 I2C 封包模擬器與驅動產生":
    st.header("I2C 封包自訂建構、理想波形生成與多平台 C 驅動產出")
    st.caption(
        "這一頁由同一份已驗證的傳輸規格（transfer spec）產生協定示意與程式碼模板；"
        "它不會連線或執行硬體命令，也不是硬體量測。"
    )
    render_guide_expander(
        "chapters/ch02_packet_builder.md", "📖 點擊展開：I2C 封包模擬器與 C 驅動產出教學"
    )

    default_preset_name = next(iter(I2C_BUILDER_PRESETS))
    for state_key, state_value in preset_widget_state(
        I2C_BUILDER_PRESETS[default_preset_name]
    ).items():
        if state_key not in st.session_state:
            st.session_state[state_key] = state_value
    preset_col, apply_col = st.columns([3, 1])
    with preset_col:
        selected_preset_name = st.selectbox(
            "教學預設組（Preset）",
            list(I2C_BUILDER_PRESETS),
            format_func=localize_preset,
            help="預設組只填入可重現的範例值；仍須以目標裝置 datasheet 核對。",
        )
    with apply_col:
        if st.button("套用 Preset", key="i2c_builder_apply_preset"):
            for state_key, state_value in preset_widget_state(
                I2C_BUILDER_PRESETS[selected_preset_name]
            ).items():
                st.session_state[state_key] = state_value

    operation_labels = {
        I2CTransferOperation.REGISTER_WRITE.value: "暫存器寫入（Register Write）",
        I2CTransferOperation.COMBINED_REGISTER_READ.value: (
            "複合暫存器讀取（Combined Register Read；Repeated START）"
        ),
        I2CTransferOperation.DIRECT_WRITE.value: "直接寫入（Direct Write；無暫存器階段）",
        I2CTransferOperation.DIRECT_READ.value: "直接讀取（Direct Read；無暫存器階段）",
    }
    b_col1, b_col2, b_col3 = st.columns(3)
    with b_col1:
        builder_operation_value = st.selectbox(
            "操作類型（Operation）",
            list(operation_labels),
            format_func=lambda value: operation_labels[value],
            key="i2c_builder_operation",
        )
    with b_col2:
        builder_addr_str = st.text_input(
            "從裝置 7-bit 位址（Slave 7-bit Address）",
            key="i2c_builder_address",
            help="合法範圍 0x08～0x77。",
        )
    with b_col3:
        builder_bus_num = st.number_input(
            "I2C 匯流排編號（I2C Bus Number）",
            min_value=0,
            max_value=0xFFFF,
            step=1,
            key="i2c_builder_bus",
        )

    builder_operation = I2CTransferOperation.coerce(builder_operation_value)
    is_register_op = builder_operation in {
        I2CTransferOperation.REGISTER_WRITE,
        I2CTransferOperation.COMBINED_REGISTER_READ,
    }
    is_read_op = builder_operation in {
        I2CTransferOperation.COMBINED_REGISTER_READ,
        I2CTransferOperation.DIRECT_READ,
    }
    builder_reg_str = ""
    builder_register_width = int(st.session_state["i2c_builder_register_width"])
    builder_endianness = str(st.session_state["i2c_builder_endianness"])
    if is_register_op:
        reg_col, width_col, endian_col = st.columns(3)
        with reg_col:
            builder_reg_str = st.text_input(
                "暫存器位移（Register Offset）",
                key="i2c_builder_register",
                help="例如 0x10 或 0x1234。",
            )
        with width_col:
            builder_register_width = int(
                st.selectbox(
                    "暫存器寬度（Register Width，bits）",
                    [8, 16],
                    key="i2c_builder_register_width",
                )
            )
        with endian_col:
            if builder_register_width == 16:
                builder_endianness = st.selectbox(
                    "暫存器位元組順序（Register Byte Order）",
                    [Endianness.BIG.value, Endianness.LITTLE.value],
                    format_func=lambda value: (
                        "大端序（Big-endian；MSB first）"
                        if value == "big"
                        else "小端序（Little-endian；LSB first）"
                    ),
                    key="i2c_builder_endianness",
                )
            else:
                st.caption("8-bit 暫存器只有一個位元組，不受 byte order 影響。")

    builder_data_str = ""
    builder_read_length: int | None = None
    builder_expected_read = ""
    if is_read_op:
        read_col, expected_col = st.columns(2)
        with read_col:
            builder_read_length = int(
                st.number_input(
                    "讀取長度（Read Length；位元組）",
                    min_value=1,
                    max_value=255,
                    step=1,
                    key="i2c_builder_read_length",
                )
            )
        with expected_col:
            builder_expected_read = st.text_input(
                "預期讀回資料（Expected Read Bytes；選填、僅假設）",
                key="i2c_builder_expected_read_data",
                max_chars=MAX_PACKET_HEX_CHARS,
                help="若填寫，位元組數必須等於 Read Length；只標在波形上，不會送到裝置。",
            )
    else:
        write_data_limit = max_write_data_bytes(
            register_operation=is_register_op,
            register_width=builder_register_width,
        )
        builder_data_str = st.text_input(
            "寫入資料位元組（Write Data Bytes；Hex）",
            key="i2c_builder_write_data",
            max_chars=MAX_PACKET_HEX_CHARS,
            help=(
                    f"此操作／寬度最多 {write_data_limit} 個資料位元組（總 Payload 解析器上限 "
                f"{MAX_BUILDER_DATA_BYTES}；波形點數上限 {MAX_BUILDER_WAVEFORM_POINTS}）。"
            ),
        )

    clock_col, timeout_col = st.columns(2)
    with clock_col:
        builder_clock_khz = st.number_input(
            "理想時鐘頻率（Ideal Clock；kHz）",
            min_value=1.0,
            max_value=1000.0,
            step=10.0,
            key="i2c_builder_clock_khz",
        )
    with timeout_col:
        builder_timeout_ms = st.number_input(
            "模板逾時門檻（Template Timeout；ms）",
            min_value=0.001,
            max_value=60_000.0,
            step=1.0,
            key="i2c_builder_timeout_ms",
            help="程式碼模板的 API timeout；不是實測 SMBus tTIMEOUT。",
        )

    try:
        b_addr = parse_hex_integer(builder_addr_str, label="從裝置 7-bit 位址（Slave 7-bit Address）")
        b_reg = (
            parse_hex_integer(builder_reg_str, label="暫存器位移（Register Offset）") if is_register_op else None
        )
        b_data = parse_hex_bytes(
            builder_data_str,
            label="寫入資料位元組（Write Data Bytes）",
            required=not is_read_op,
            max_bytes=(
                max_write_data_bytes(
                    register_operation=is_register_op,
                    register_width=builder_register_width,
                )
                if not is_read_op
                else MAX_BUILDER_DATA_BYTES
            ),
        )
        expected_read_data = parse_hex_bytes(
            builder_expected_read,
            label="預期讀回資料（Expected Read Bytes）",
            max_bytes=255,
        )
        spec = I2CTransferSpec(
            address_7bit=b_addr,
            bus=int(builder_bus_num),
            operation=builder_operation,
            register=b_reg,
            register_width=builder_register_width,
            endianness=builder_endianness,
            data_bytes=b_data,
            read_length=builder_read_length,
            expected_read_data=expected_read_data,
            clock_khz=float(builder_clock_khz),
            timeout_ms=float(builder_timeout_ms),
            max_payload_bytes=MAX_BUILDER_DATA_BYTES,
            max_waveform_points=MAX_BUILDER_WAVEFORM_POINTS,
        )

        st.subheader("標準交易預覽（Canonical Transaction Preview）")
        preview_rows = []
        for index, segment in enumerate(spec.segments, 1):
            payload_labels = [
                ("未知值" if str(getattr(byte, "value", "")).lower() == "unknown" else byte.value)
                if hasattr(byte, "value")
                else f"0x{byte:02X}"
                for byte in segment.bytes
            ]
            if segment.is_read and spec.expected_read_data:
                payload_labels = [
                    f"預期 0x{byte:02X}（假設）" for byte in spec.expected_read_data
                ]
            preview_rows.append(
                {
                    "段落（Segment）": index,
                    "起始（Start）": "重複 START（Sr）" if segment.repeated_start else "START",
                    "方向（Direction）": localize_direction(segment.direction),
                    "7-bit 位址（Address）": f"0x{spec.address_7bit:02X}",
                    "線路位址（Wire Byte）": (
                        f"0x{((spec.address_7bit << 1) | int(segment.is_read)):02X}"
                    ),
                    "負載資料（Payload）": " ".join(payload_labels) or "無（none）",
                    "最終 ACK Slot": (
                        "主機 NACK（Controller NACK；正常讀取結束）"
                        if segment.final_controller_nack
                        else "ACK（理想應答假設）"
                    ),
                    "結束（End）": "STOP 結束條件"
                    if index == len(spec.segments)
                    else "保持連線至 Repeated START（Sr）",
                }
            )
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

        reconstructor = I2CWaveformReconstructor(default_clock_khz=spec.clock_khz)
        wave_data = reconstructor.reconstruct_transfer_spec_waveform(spec)
        st.plotly_chart(
            reconstructor.create_plotly_figure(
                wave_data,
                title=(
                    "理想協定波形模型 (Ideal I2C Transfer Waveform): "
                    f"{operation_labels[spec.operation.value]}"
                ),
            ),
            width="stretch",
        )
        if is_read_op:
            if spec.expected_read_data:
                st.caption(
                    "預期位元組只以假設（assumed）標籤顯示，不是裝置回傳值，也不會寫入生成程式碼。"
                )
            else:
                st.caption(
                    "讀取 Payload 顯示 Unknown；長度已知，但回傳值必須由硬體或 capture 提供。"
                )

        st.subheader("多平台程式碼模板（Driver Templates）")
        st.info(
            "GUI 只產生與下載模板，不會執行任何命令。使用前需補齊 include、handle、"
            "錯誤處理、資源歸屬（ownership）與目標平台初始化。"
        )
        if spec.operation in {
            I2CTransferOperation.REGISTER_WRITE,
            I2CTransferOperation.DIRECT_WRITE,
        }:
            st.warning(
                "寫入操作可能改變 PMBus 電源設定、GPIO、感測器設定（sensor configuration）或 EEPROM。"
                "複製後執行前，必須再次確認匯流排、7-bit address、register、byte order、data、"
                "裝置電源／重設（power/reset）狀態與核心驅動程式資源歸屬（kernel driver ownership）。"
            )
        snippets = I2CDriverCodeGenerator.generate_from_spec(spec)
        for plat, code_txt in snippets.items():
            with st.expander(f"💻 {localize_platform(plat)}", expanded=False):
                st.code(
                    code_txt,
                    language=("bash" if "CLI" in plat else ("cpp" if "Arduino" in plat else "c")),
                )
        bundle, bundle_sha256, spec_sha256 = build_i2c_bundle(spec, snippets)
        hash_col, download_col = st.columns([3, 1])
        with hash_col:
            st.code(
                f"規格 Spec SHA-256：{spec_sha256}\n套件 Bundle SHA-256：{bundle_sha256}",
                language="text",
            )
        with download_col:
            st.download_button(
                "下載傳輸規格與程式碼模板（.zip）",
                bundle,
                file_name="i2c_transfer_bundle.zip",
                mime="application/zip",
            )
    except ResourceLimitError as exc:
        st.error(f"輸入超過安全資源上限：{exc}")
    except (TypeError, ValueError) as exc:
        st.error(f"輸入格式錯誤：{exc}")

# 3. Waveform Diff
elif menu == "⚖️ 雙波形對比檢視（Waveform Diff）":
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
        st.info("已載入內建 Golden/Failing 範例；可直接查看差分，或下載 CSV 後替換成自己的 capture。")
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
                    st.markdown(
                        f"**現象描述**：{localize_diff_description(dp.description)}"
                    )
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

# 4. UART Crash Dump
elif menu == "📟 UART 崩潰轉儲與 HardFault 分析（Crash Dump）":
    st.header("UART 序列埠崩潰轉儲與 ARM Cortex-M HardFault 智慧診斷")
    render_guide_expander(
        "chapters/ch04_uart_crash.md", "📖 點擊展開：UART 崩潰與 ARM HardFault 診斷教學"
    )
    u_mode = st.radio(
        "選擇輸入方式",
        [
            "貼上 UART Log / Crash Dump",
            "載入範例 Linux Kernel Panic Log",
            "載入範例 ARM HardFault Log",
        ],
    )
    u_raw = ""
    u_example_name: str | None = None
    if u_mode == "貼上 UART Log / Crash Dump":
        u_raw = st.text_area(
            "請貼上 UART 輸出內容（UART Log／Crash Dump）：",
            height=200,
            max_chars=MAX_TEXT_BYTES,
        )
    elif u_mode == "載入範例 Linux Kernel Panic Log":
        u_example_name = "uart_kernel_panic_minimal.log"
        u_raw = """BUG: unable to handle page fault for address: 0000000000000010\nRIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]\nRAX: 0000000000000000 RBX: ffff888102345000 RCX: 0000000000000000\nCR2: 0000000000000010\nCall Trace:\n <TASK>\n [ffff888100123450] blk_mq_complete_request+0x24/0x50\n [ffff8881001234a0] nvme_irq_handler+0x8c/0x100 [nvme]\n </TASK>"""
    else:
        u_example_name = "uart_hardfault_minimal.log"
        u_raw = """HardFault Exception Occurred!\nHFSR: 0x40000000 (FORCED)\nCFSR: 0x02000000 (DIVBYZERO)\nStacked R0: 0x00000000\nStacked R1: 0x0000000A\nStacked PC: 0x08001234\nStacked LR: 0x08000456\nStacked xPSR: 0x61000000"""
    if u_example_name is not None:
        st.download_button(
            f"下載此 UART 範例（{u_example_name}）",
            data=u_raw,
            file_name=u_example_name,
            mime="text/plain",
            key="uart_download_example",
        )
    if st.button("執行 UART 崩潰轉儲分析（Crash Dump）") and u_raw.strip():
        try:
            u_report = UARTCrashParser.parse_log_text(validate_pasted_text(u_raw, label="UART log"))
        except (TypeError, ValueError) as exc:
            st.error(f"UART 輸入錯誤：{exc}")
        else:
            st.caption(
                "證據範圍：報告只整理輸入 log 中可解析的 fault 欄位；請用 matching ELF、"
                "symbol、kernel source 與目標板重現確認根因。"
            )
            uart_md = UARTReporter.to_markdown(u_report)
            st.markdown(uart_md)
            st.download_button(
                "下載 UART Markdown 診斷報告",
                data=uart_md,
                file_name="uart_crash_report.md",
                mime="text/markdown",
                key="uart_download_report",
            )

# 5. MCTP / IPMB
elif menu == "🌐 MCTP／IPMB 伺服器管理協定解析":
    st.header("MCTP (DSP0236/PLDM/SPDM) 與 IPMB 伺服器管理協定解碼")
    render_guide_expander(
        "chapters/ch05_mctp_ipmb.md", "📖 點擊展開：MCTP 與 IPMB 伺服器協定解析教學"
    )
    m_sample = "01 08 00 C0 01 00 02 01 00\n20 18 C8 81 00 01 7E"
    m_raw = st.text_area(
        "請輸入 MCTP 或 IPMB 封包十六進位資料（Hex Dump；每行一封包）：",
        height=150,
        max_chars=MAX_TEXT_BYTES,
        value=m_sample,
    )
    st.download_button(
        "下載內建 MCTP／IPMB 範例",
        data=m_sample,
        file_name="mctp_ipmb_minimal.hex",
        mime="text/plain",
        key="mctp_download_example",
    )
    m_protocol_mode = st.selectbox(
        "協定模式（Protocol mode）",
        ["auto", "mctp", "ipmb"],
        format_func=lambda value: {
            "auto": "自動判斷（auto）",
            "mctp": "MCTP",
            "ipmb": "IPMB",
        }[value],
        key="mctp_protocol_mode",
    )
    if st.button("執行伺服器協定解碼") and m_raw.strip():
        try:
            m_report = ServerMgmtParser.parse_text_dump(
                validate_pasted_text(m_raw, label="MCTP/IPMB dump"),
                protocol_mode=m_protocol_mode,
            )
        except (TypeError, ValueError) as exc:
            st.error(f"MCTP/IPMB 輸入錯誤：{exc}")
        else:
            if not m_report.total_frames:
                st.warning(
                    "沒有解出可辨識的 MCTP/IPMB frame；請確認每行是完整 hex bytes，"
                    "並保留原始 capture/協定標頭以便人工核對。"
                )
            else:
                mctp_md = ServerMgmtReporter.to_markdown(m_report)
                st.markdown(mctp_md)
                st.download_button(
                    "下載 MCTP／IPMB Markdown 診斷報告",
                    data=mctp_md,
                    file_name="mctp_ipmb_report.md",
                    mime="text/markdown",
                    key="mctp_download_report",
                )

# 6. Device Tree Generator
elif menu == "🌲 Device Tree（.dts）產生器":
    st.header("Linux Kernel／OpenBMC Device Tree Source（.dts）自動產生")
    render_guide_expander("chapters/ch06_dts_generator.md", "📖 點擊展開：Device Tree 產生器教學")
    dt_b1, dt_b2, dt_b3 = st.columns(3)
    with dt_b1:
        dts_bus = st.number_input(
            "I2C 匯流排編號（Bus Number；&i2c...）", min_value=0, max_value=65535, value=1
        )
    with dt_b2:
        dts_mux = st.text_input("PCA9548A MUX 位址（MUX Address）", value="0x70")
    with dt_b3:
        dts_clock = st.number_input(
            "時鐘頻率（clock-frequency；Hz）", min_value=1, value=400000, step=10000
        )
    dts_mux_compatible = st.text_input(
        "多工器相容字串（MUX compatible）", value="nxp,pca9548"
    )
    dts_devices_text = st.text_area(
        "裝置清單（YAML；每個 device 必須有 addr/channel/name/compatible）",
        value="""- addr: 0x50
  channel: 0
  name: eeprom
  compatible: atmel,24c64
- addr: 0x48
  channel: 1
  name: temp-sensor
  compatible: national,lm75
""",
        height=180,
        max_chars=MAX_TEXT_BYTES,
    )
    if st.button("產生 Device Tree（.dts）"):
        try:
            devices = (
                yaml.safe_load(validate_pasted_text(dts_devices_text, label="Device Tree YAML"))
                or []
            )
            dts_code = DeviceTreeGenerator.generate_dts_from_topology(
                bus_num=int(dts_bus),
                mux_addr=dts_mux,
                devices=devices,
                clock_frequency=int(dts_clock),
                mux_compatible=dts_mux_compatible,
            )
            st.code(dts_code, language="dts")
            st.download_button(
                "下載 i2c_bus.dtsi",
                dts_code,
                file_name=f"i2c_bus{int(dts_bus)}.dtsi",
                mime="text/plain",
            )
        except (TypeError, ValueError, yaml.YAMLError) as exc:
            st.error(f"DTS 輸入錯誤：{exc}")

# 7. PCIe
elif menu == "🚀 PCIe Config Space 與 AER 診斷":
    st.header("PCIe 配置空間、Capability 鏈表與 AER 嚴重錯誤診斷")
    render_guide_expander(
        "chapters/ch07_pcie_aer.md", "📖 點擊展開：PCIe Config Space 與 AER 診斷教學"
    )
    dmesg_mode = "貼上 Linux dmesg AER Error Log"
    if st.button(
        "載入內建 dmesg AER 範例",
        key="pcie_dmesg_load_sample",
        help="載入套件內建的最小 Linux AER log，方便先確認輸出欄位與 TLP Header。",
    ):
        st.session_state["pcie_input_mode"] = dmesg_mode
        st.session_state["pcie_dmesg_sample_active"] = True
        st.session_state["pcie_dmesg_sample_content"] = load_pcie_dmesg_sample()
        st.session_state["pcie_raw_input"] = st.session_state["pcie_dmesg_sample_content"]
    input_mode = st.radio(
        "輸入方式", ["貼上 lspci -xxxx / Hex Dump", dmesg_mode], key="pcie_input_mode"
    )
    if input_mode != dmesg_mode and st.session_state.get("pcie_dmesg_sample_active"):
        st.session_state["pcie_dmesg_sample_active"] = False
        st.session_state.pop("pcie_dmesg_sample_content", None)
        st.session_state["pcie_raw_input"] = ""
    dmesg_sample = st.session_state.get("pcie_dmesg_sample_content")
    if (
        input_mode == dmesg_mode
        and st.session_state.get("pcie_dmesg_sample_active") is True
        and isinstance(dmesg_sample, str)
    ):
        st.info("已載入內建 dmesg AER 範例；可直接分析，或下載檔案後保存到自己的除錯紀錄。")
        st.download_button(
            "下載 dmesg AER 範例",
            data=dmesg_sample,
            file_name="pcie_aer_dmesg.log",
            mime="text/plain",
            key="pcie_dmesg_download_sample",
        )
    raw_input = st.text_area(
        "輸入 Log 或 Dump 內容：", height=200, max_chars=MAX_TEXT_BYTES, key="pcie_raw_input"
    )
    if st.button("執行 PCIe 分析") and raw_input.strip():
        try:
            raw_input = validate_pasted_text(raw_input, label="PCIe log/dump")
        except (TypeError, ValueError) as exc:
            st.error(f"PCIe 輸入錯誤：{exc}")
            st.stop()
        if input_mode == dmesg_mode:
            events = PCIeAnalyzer.parse_dmesg_aer(raw_input)
            st.subheader(
                f"Linux 核心 dmesg AER 診斷結果（Kernel dmesg AER 診斷結果；共 {len(events)} 個事件）"
            )
            if not events:
                st.warning("沒有找到可解析的 AER 事件；請確認貼上的內容包含完整 kernel dmesg。")
            pcie_dmesg_md = PCIeReporter.format_dmesg_events(events)
            st.markdown(pcie_dmesg_md)
            st.download_button(
                "下載 PCIe dmesg Markdown 診斷報告",
                data=pcie_dmesg_md,
                file_name="pcie_dmesg_aer_report.md",
                mime="text/markdown",
                key="pcie_dmesg_download_report",
            )
        else:
            try:
                devices = PCIeAnalyzer.parse_multi_lspci_text(raw_input)
                if not devices:
                    bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(raw_input)
                    devices = [PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)]
            except (TypeError, ValueError) as exc:
                st.error(f"PCIe 輸入錯誤：{exc}")
                devices = []
            if any(cfg.data_quality_issues for cfg in devices):
                st.error(
                    "PCIe 輸入錯誤：部分裝置無法乾淨解碼；請先檢查 Data Quality "
                    "Limitations，不要把空欄位當成有效 Config Space。"
                )
            for cfg_index, cfg in enumerate(devices, 1):
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "廠商／裝置 ID（Vendor / Device ID）",
                    f"0x{cfg.vendor_id:04X} / 0x{cfg.device_id:04X}",
                )
                c2.metric("標頭類型（Header Type）", cfg.header_type.name)
                c3.metric(
                    "Capabilities 數量（Capabilities）",
                    len(cfg.standard_capabilities) + len(cfg.extended_capabilities),
                )
                if cfg.link_info and cfg.link_info.is_degraded:
                    st.error(f"🚨 {PCIeReporter.localize_link_reason(cfg.link_info.degradation_reason)}")
                pcie_cfg_md = PCIeReporter.to_markdown(cfg)
                st.markdown(pcie_cfg_md)
                st.download_button(
                    f"下載 PCIe 診斷報告 #{cfg_index}",
                    data=pcie_cfg_md,
                    file_name=f"pcie_config_report_{cfg_index}.md",
                    mime="text/markdown",
                    key=f"pcie_config_download_{cfg_index}",
                )

# 8. SPI Flash
elif menu == "⚡ SPI Flash 協定診斷":
    st.header("SPI / QSPI Flash 協定解析與寫入異常診斷")
    render_guide_expander(
        "chapters/ch08_spi_flash.md", "📖 點擊展開：SPI Flash 協定與狀態機診斷教學"
    )
    spi_col1, spi_col2 = st.columns([3, 1])
    with spi_col1:
        uploaded_spi = st.file_uploader(
            "選擇 Saleae SPI CSV 檔案",
            type=["csv", "txt"],
            max_upload_size=MAX_UPLOAD_MIB,
        )
    with spi_col2:
        use_spi_sample = st.button("載入內建 SPI 測試波形")
    spi_page_size = st.number_input(
        "Page Size（頁面大小；bytes）",
        min_value=1,
        max_value=4096,
        value=256,
        step=1,
        help="請依實際 Flash datasheet 設定；這會影響 Page Program 跨頁風險判定。",
    )
    csv_text = None
    if uploaded_spi is not None:
        try:
            csv_text = decode_uploaded_text(uploaded_spi, allowed_extensions={".csv", ".txt"})
            st.session_state["spi_sample_active"] = False
        except ValueError as exc:
            st.error(f"無法讀取 SPI trace：{exc}")
    elif use_spi_sample:
        csv_text = load_spi_sample()
        st.session_state["spi_sample_active"] = True
        st.session_state["spi_sample_content"] = csv_text
        st.info("已載入內建 SPI 範例 CSV (Winbond W25Q128)！")
    elif st.session_state.get("spi_sample_active"):
        sample_text = st.session_state.get("spi_sample_content")
        if isinstance(sample_text, str):
            csv_text = sample_text
    if st.session_state.get("spi_sample_active") and isinstance(csv_text, str):
        st.download_button(
            "下載內建 SPI 範例 CSV",
            data=csv_text,
            file_name="spi_w25q128_sample.csv",
            mime="text/csv",
            key="spi_download_example",
        )
    if csv_text is not None:
        try:
            rep = analyze_spi_input(csv_text, int(spi_page_size))
        except (TypeError, ValueError) as exc:
            st.error(f"無法解析 SPI trace：{exc}")
        else:
            st.caption(
                "此頁分析的是 analyzer 已解碼的 MOSI/MISO/CS transaction；沒有 raw SCLK edge 時，"
                "不能證明 CPOL/CPHA、bit timing 或 signal integrity。Page Size 只用於規則判定，"
                "不會自動取代 datasheet。"
            )
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("總傳輸次數", rep.summary.total_transactions)
            s2.metric("讀取次數", rep.summary.read_count)
            s3.metric("Page Program 寫入", rep.summary.write_count)
            s4.metric("異常事件", rep.summary.anomaly_count)
            if rep.summary.detected_flash_chip:
                st.info(f"識別晶片型號: {rep.summary.detected_flash_chip}")
            spi_md = SPIReporter.to_markdown(rep)
            st.markdown(spi_md)
            st.download_button(
                "下載 SPI Markdown 診斷報告",
                data=spi_md,
                file_name="spi_flash_report.md",
                mime="text/markdown",
                key="spi_download_report",
            )

# 9. Register Decoder
elif menu == "🎛 晶片暫存器 Bitfield 解碼器":
    st.header("硬體 / 晶片暫存器 Bitfield 視覺化解碼器")
    render_guide_expander(
        "chapters/ch09_register_codegen.md", "📖 點擊展開：暫存器 Bitfield 解碼教學"
    )
    builtin_map = {
        "PMBus 標準狀態暫存器 (PMBus STATUS_WORD)": "pmbus_standard.yaml",
        "PCIe AER Uncorrectable Error 暫存器": "pcie_aer_registers.yaml",
    }
    choice = st.selectbox("選擇預設暫存器定義檔", list(builtin_map.keys()))
    data_dir = Path(__file__).parent.parent / "data"
    yaml_file = data_dir / builtin_map[choice]
    catalog = RegisterMapCatalog()
    if yaml_file.exists():
        catalog.load_from_yaml(yaml_file.read_text(encoding="utf-8"))
    reg_names = list(catalog.name_map.keys())
    if reg_names:
        r1, r2 = st.columns(2)
        with r1:
            sel_reg = st.selectbox("選擇暫存器", [r.upper() for r in reg_names])
        with r2:
            raw_val_str = st.text_input(
                "輸入暫存器 Raw Hex (如 0x8400, 0x00040000)", value="0x8400"
            )
        try:
            cur_val = int(raw_val_str, 0)
        except ValueError:
            st.error("暫存器值格式錯誤；請輸入整數或 0x 開頭的十六進位值。")
        else:
            try:
                res = catalog.decode_register(sel_reg, cur_val)
            except (TypeError, ValueError) as exc:
                st.error(f"暫存器值無法解碼：{exc}")
            else:
                st.subheader(f"{res.reg_name} (0x{cur_val:08X})")
                if res.description:
                    st.caption(f"暫存器說明（Description）：{_localize_register_meaning(res.description)}")
                st.table(
                    pd.DataFrame(
                        [
                            {
                                "位元範圍（Bit Range）": f.bit_range,
                                "欄位（Field）": f.name,
                                "值（Value）": f.hex_val,
                                "存取權限（Access）": f.access,
                                "意義（Meaning）": (
                                    f"⚠ {_localize_register_meaning(f.meaning)}"
                                    if f.is_warning
                                    else _localize_register_meaning(f.meaning)
                                ),
                            }
                            for f in res.fields
                        ]
                    )
                )
                unmapped_text = f"0x{res.unmapped_bits:08X}"
                if res.unmapped_bits:
                    st.warning(
                        f"有未對應位元（Unmapped bits）：{unmapped_text}；"
                        "這些位元沒有出現在目前 YAML 定義，請回到 datasheet 確認。"
                    )
                else:
                    st.caption("未對應位元（Unmapped bits）：0x00000000")

# 10. C Codegen
elif menu == "🛠 C 語言 Register 巨集產生器":
    st.header("YAML 暫存器定義檔轉換為 C 語言標頭檔（Header；#define／RMW 巨集）")
    render_guide_expander(
        "chapters/ch09_register_codegen.md", "📖 點擊展開：C 語言 Register 巨集產生器教學"
    )
    data_dir = Path(__file__).parent.parent / "data"
    builtin_yamls = list(data_dir.glob("*.yaml"))
    choice_yaml = st.selectbox("選擇 YAML 範本", [y.name for y in builtin_yamls])
    mod_name = st.text_input(
        "模組名稱（Module Name）", value=choice_yaml.replace(".yaml", "").upper()
    )
    try:
        gen = CHeaderGenerator.from_yaml_file(data_dir / choice_yaml)
        c_header = gen.generate_header(module_name=mod_name)
    except (OSError, TypeError, ValueError) as exc:
        st.error(f"C header 輸入錯誤：{exc}")
    else:
        st.info(
            "這是可編輯的 C header 起始模板；套用到 driver 前，請依 datasheet、"
            "register access policy、compiler warning 與 MISRA checker 重新驗證。"
        )
        st.code(c_header, language="c")
        header_filename = CHeaderGenerator.header_filename(mod_name)
        st.download_button(
            f"下載 {header_filename}",
            c_header,
            file_name=header_filename,
            mime="text/x-c",
        )

# 11. Fault Arena
elif menu == "🏆 初階 Firmware 實戰除錯實驗室（Fault Arena）":
    st.header("初階 Firmware 工程師 20 大經典硬韌體故障演練場（Fault Arena）")
    render_guide_expander("chapters/ch10_fault_arena.md", "📖 點擊展開：Fault Arena 實戰除錯手冊")
    arena_cases = [
        "Case 01: I2C Address NACK (Slave 未上電 / Address Pin 浮接)",
        "Case 02: I2C Data NACK (EEPROM 內部寫入週期 tWR 忙碌中)",
        "Case 03: I2C Clock Stretching 逾時 (> 25ms SMBus Hang)",
        "Case 04: I2C EEPROM 24C64 Page Boundary 跨頁覆蓋風險",
        "Case 05: I2C PCA9548A MUX 多通道同時開啟引發匯流排衝突",
        "Case 06: PMBus VOUT_TRIM 負值補碼計算溢位 (127V 誤報)",
        "Case 07: PCIe Gen4 x16 降速至 Gen1 x1 (金手指髒污/SI劣化)",
        "Case 08: PCIe AER Completion Timeout (目標設備 AXI 狀態機死鎖)",
        "Case 09: PCIe AER Malformed TLP (封包長度違反 Max Payload Size)",
        "Case 10: PCIe AER Poisoned TLP (上游主記憶體 ECC 錯誤)",
        "Case 11: SPI NOR Flash Page Program 遺漏 0x06 WREN 寫入無效",
        "Case 12: SPI NOR Flash Page Buffer 256B Wrap-Around 覆蓋",
        "Case 13: SPI JEDEC 讀回全 0xFF (MISO 線路浮接 / 供電斷開)",
        "Case 14: SPI JEDEC 讀回全 0x00 (MISO 對地短路 / 匯流排被鉗位)",
        "Case 15: Linux Kernel Panic: NULL Pointer Dereference at Offset 0x10",
        "Case 16: ARM Cortex-M HardFault: DIVBYZERO 除以零中斷陷阱",
        "Case 17: ARM Cortex-M HardFault: UNALIGNED 未對齊 32-bit 指標存取",
        "Case 18: ARM Cortex-M HardFault: IMPRECISERR 異步總線寫入錯誤",
        "Case 19: MCTP PLDM 感測器數值傳輸異常與封包順序錯亂",
        "Case 20: IPMB Checksum 1/2 校驗碼錯誤引發封包丟棄",
    ]
    sel_case = st.selectbox("選擇實戰演練案例", arena_cases)
    st.info(f"【案例分析】{sel_case}")
    st.caption(
        "案例資料是可重現的 synthetic training artifact（合成教學資料），用來練習觀察、"
        "假設與驗證步驟；不代表真實公司 capture，也不保證單一根因。"
    )
    case_idx = arena_cases.index(sel_case) + 1
    fixture = FaultArenaFixtures.get_case(f"{case_idx:02d}")
    if st.button("🚀 載入此案例模擬資料並自動分析", key=f"run_arena_{case_idx}"):
        data_content = fixture.builder()
        with st.expander("📄 檢視案例合成測試資料", expanded=False):
            st.code(data_content, language="csv" if ".csv" in fixture.filename else "text")
        st.markdown("### 🔍 自動診斷分析結果（Automated Diagnostic Result）")
        arena_report_md: str | None = None
        if fixture.kind == "i2c":
            rep_i2c = I2CDiagnosticEngine().analyze_csv_content(data_content)
            arena_report_md = I2CReporter.generate_markdown(rep_i2c)
        elif fixture.kind == "spi":
            rep_spi = SPIDiagnosticEngine().analyze_csv_content(data_content)
            arena_report_md = SPIReporter.to_markdown(rep_spi)
        elif fixture.kind == "pcie":
            bdf, raw_bytes = PCIeAnalyzer.parse_lspci_text(data_content)
            cfg = PCIeAnalyzer.decode_config_space(raw_bytes, bdf=bdf)
            arena_report_md = PCIeReporter.to_markdown(cfg)
        elif fixture.kind == "uart":
            rep_uart = UARTCrashParser.parse_log_text(data_content)
            arena_report_md = UARTReporter.to_markdown(rep_uart)
        elif fixture.kind in {"server_mgmt", "mctp"}:
            rep_mctp = ServerMgmtParser.parse_text_dump(data_content)
            arena_report_md = ServerMgmtReporter.to_markdown(rep_mctp)
        if arena_report_md is not None:
            st.markdown(arena_report_md)
            st.download_button(
                "下載案例 Markdown 診斷報告",
                data=arena_report_md,
                file_name=f"fault_arena_case_{case_idx:02d}.md",
                mime="text/markdown",
                key=f"arena_download_report_{case_idx}",
            )
    st.markdown("**【標準排查 SOP 與根因（Root Cause）診斷】**：")
    if "01:" in sel_case:
        st.markdown(
            "1. 檢查 Slave 晶片供電 (3.3V/1.8V)。\n2. 檢查硬體 A0/A1/A2 位址設定腳位。\n3. 檢查 7-bit 位址是否未左移。"
        )
    elif "07:" in sel_case:
        st.markdown(
            "1. 檢查 PCIe 插槽金手指與 Riser 卡接觸面。\n2. 檢查 100MHz 差分時脈 (REFCLK) 抖動。\n3. 檢查主機板 BIOS Link Speed 設定。"
        )
    elif "11:" in sel_case:
        st.markdown(
            "1. 每次 Page Program 或 Erase 前必須發送 0x06 (WREN)。\n2. 檢查 Status Register 1 WEL 位元是否為 1。"
        )
    elif "15:" in sel_case:
        st.markdown(
            "1. 檢查 probe 函式中 kzalloc 是否成功。\n2. 使用 addr2line -e vmlinux <RIP> 定位原始碼行號。"
        )
    else:
        st.markdown(
            "1. 參照分層 L1~L7 診斷模型，先確認硬體電氣訊號，再分析協定 Frame 格式，最後檢查驅動狀態機。"
        )

# 12. SOP
elif menu == "📚 韌體除錯指南與 SOP":
    st.header("Firmware 工程師韌體除錯指南與心智模型（SOP／Mental Model）")
    render_guide_expander(
        "chapters/appendix_gui_reading_guide.md", "🧭 點擊展開：附錄 B 12 個 GUI 頁面第一輪閱讀地圖"
    )
    render_guide_expander("chapters/ch12_sop.md", "📖 點擊展開：L1~L7 系統化除錯 SOP 手冊")
    st.info(
        "先確認證據，再提出假設：工具的圖表與報告能縮小範圍，不能取代示波器、datasheet、"
        "kernel source、matching ELF 或目標板上的重現。"
    )
    st.subheader("🎯 L1～L7 分層診斷模型")
    st.table(
        pd.DataFrame(
            [
                {
                    "層次（Layer）": "L1 物理／電氣（Physical / Electrical）",
                    "先問什麼（Question）": "電源、接地、pull-up、線路電平與 clock 是否真的存在？",
                    "本工具能提供的證據（Evidence）": "Raw I2C 的 digital 0/1 edge、tHIGH/tLOW；不能量類比電壓或 PCIe eye。",
                },
                {
                    "層次（Layer）": "L2 連結／框架（Link / Framing）",
                    "先問什麼（Question）": "CS/START/STOP、ACK/NACK、stretch 或 frame boundary 是否合理？",
                    "本工具能提供的證據（Evidence）": "I2C/SPI analyzer decode、raw I2C bit decode、PCIe AER/config 欄位。",
                },
                {
                    "層次（Layer）": "L3 協定（Protocol）",
                    "先問什麼（Question）": "opcode、command、register offset、checksum 或 message type 是否正確？",
                    "本工具能提供的證據（Evidence）": "PMBus、EEPROM、SPI opcode、MCTP/IPMB、PCIe capability 解碼。",
                },
                {
                    "層次（Layer）": "L4 驅動／傳輸（Driver / Transport）",
                    "先問什麼（Question）": "Linux i2c-dev、SPI driver、MCTP transport 或 DMA 是否送出預期序列？",
                    "本工具能提供的證據（Evidence）": "把 capture/log 對回交易順序；不會直接檢查 live kernel state。",
                },
                {
                    "層次（Layer）": "L5 重試／狀態（Retry / State）",
                    "先問什麼（Question）": "是否有 retry、timeout、WREN/Busy、MUX channel 或 reset 狀態機問題？",
                    "本工具能提供的證據（Evidence）": "列出已觀察的重試、NACK、clock stretch、SPI WREN/Busy 證據。",
                },
                {
                    "層次（Layer）": "L6 平台／板級（Platform / Board）",
                    "先問什麼（Question）": "board wiring、Device Tree binding、power/reset/ownership 是否吻合？",
                    "本工具能提供的證據（Evidence）": "產生 DTS/driver 起始模板；必須用 schematic、datasheet、dtc/dt-schema 驗證。",
                },
                {
                    "層次（Layer）": "L7 應用／語意（Application / Meaning）",
                    "先問什麼（Question）": "這個 register/telemetry 值對產品行為代表什麼？",
                    "本工具能提供的證據（Evidence）": "Bitfield/PMBus/sensor 候選解碼；需要正確 device profile 才能下語意結論。",
                },
            ]
        )
    )

    st.subheader("🧭 每次除錯固定走這 7 步")
    st.markdown(
        "1. **保存原始證據**：不要只截圖；保留原始 CSV/log、來源工具設定與 capture 時間。\n"
        "2. **標記輸入型態**：decoded table、raw digital、analog、log 或 register dump；看不到的欄位就是 unavailable。\n"
        "3. **先查 L1**：確認供電、ground、pull-up/termination、CS/START 與 clock；需要時用示波器或公司的 LA。\n"
        "4. **再查 L2/L3**：看 frame boundary、address/opcode、ACK/checksum、register/data 是否符合 datasheet。\n"
        "5. **對回 L4/L5**：把 transaction 對到 driver log、retry/timeout、WREN/Busy、MUX 或 reset state。\n"
        "6. **最後查 L6/L7**：確認 DTS/binding、board variant、symbolicated source 與產品需求；不要由單一圖表直接宣布 root cause。\n"
        "7. **記錄可重現結論**：分開寫 observed facts、hypotheses、下一個 discriminating test 與尚未驗證項目。"
    )

    st.subheader("📏 報告中的證據詞怎麼讀")
    st.table(
        pd.DataFrame(
            [
                {"詞（Term）": "實測（Measured）", "意思（Meaning）": "直接由輸入 timestamp/edge/value 計算。"},
                {"詞（Term）": "推論（Inferred）", "意思（Meaning）": "由多個觀察欄位推論，仍可能有替代解釋。"},
                {"詞（Term）": "協定重建（Reconstructed）", "意思（Meaning）": "依 decoded bytes 畫出的理想示意，不是實測波形。"},
                {"詞（Term）": "假設（Hypothesis）", "意思（Meaning）": "排查方向，不是已證明的 root cause。"},
                {"詞（Term）": "不可用（Unavailable）", "意思（Meaning）": "輸入缺少必要證據；工具不補 0 或猜測。"},
            ]
        )
    )
