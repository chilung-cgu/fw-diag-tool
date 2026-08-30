from __future__ import annotations

from pathlib import Path

from fw_diag_tool.codegen.driver_gen import I2CDriverCodeGenerator
from fw_diag_tool.gui.pages.i2c_builder import I2C_BUILDER_PRESETS
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.localization import (
    localize_category,
    localize_direction,
    localize_explanatory_text,
    localize_health_grade,
    localize_issue_advice,
    localize_issue_description,
    localize_issue_root_cause,
    localize_quality_message,
    localize_semantic_summary,
    localize_speed_mode,
    localize_status,
)
from fw_diag_tool.i2c.models import I2CDirection, I2CSpeedMode
from fw_diag_tool.i2c.reporter import I2CReporter
from fw_diag_tool.i2c.status import TransactionStatus
from fw_diag_tool.i2c.transfer_spec import I2CTransferOperation, I2CTransferSpec

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs" / "chapters"


def test_ch01_contains_step_by_step_golden_guide() -> None:
    ch01 = (DOCS / "ch01_i2c_pmbus.md").read_text(encoding="utf-8")
    assert "## 3. 真實 Fixture 實戰解析：以 i2c_golden.csv 為例" in ch01
    assert "步驟 1：檢視上方 KPI 摘要與資料證據面板" in ch01
    assert "步驟 2：切換至 📜 封包交易列表（Transactions）" in ch01
    assert "步驟 3：切換至 📈 數位方波與協定軌（Waveform）" in ch01
    assert "步驟 4：切換至 🚨 異常診斷（Anomalies）" in ch01
    assert "步驟 5：切換至 📊 匯流排時序與健康圖表（Bus Timing & Health）" in ch01
    assert "步驟 6：切換至 📝 Markdown 診斷報告（Markdown Report）" in ch01


def test_ch01_contains_five_tabs_detailed_teaching() -> None:
    ch01 = (DOCS / "ch01_i2c_pmbus.md").read_text(encoding="utf-8")
    assert "## 4. 五大功能分頁（Tabs）：細項使用與輸出判讀教學" in ch01
    assert "### 4.1 `📜 封包交易列表（Transactions）`" in ch01
    assert "### 4.2 `📈 數位方波與協定軌（Waveform）`" in ch01
    assert "### 4.3 `🚨 異常診斷（Anomalies）`" in ch01
    assert "### 4.4 `📊 匯流排時序與健康圖表（Bus Timing & Health）`" in ch01
    assert "### 4.5 `📝 Markdown 診斷報告（Markdown Report）`" in ch01


def test_i2c_builder_presets_and_operations_are_intact() -> None:
    assert len(I2C_BUILDER_PRESETS) >= 5
    assert I2CTransferOperation.REGISTER_WRITE.value == "register_write"
    assert I2CTransferOperation.COMBINED_REGISTER_READ.value == "combined_register_read"
    assert I2CTransferOperation.DIRECT_WRITE.value == "direct_write"
    assert I2CTransferOperation.DIRECT_READ.value == "direct_read"


def test_localization_helpers_preserve_tokens_and_provide_zh_tw() -> None:
    assert "ACK（正常應答）" == localize_status(TransactionStatus.ACK)
    assert "ACK UNKNOWN（ACK 證據未知/未提供）" == localize_status(TransactionStatus.ACK_UNKNOWN)
    assert "標準模式（Standard-mode，100 kHz）" == localize_speed_mode(I2CSpeedMode.STANDARD_100K)
    assert "一般 I2C 週邊裝置" == localize_category("General I2C Peripheral")
    assert "A（優良：通訊完全正常）" == localize_health_grade("A (Excellent)")
    assert "WRITE（寫入）" == localize_direction(I2CDirection.WRITE)
    assert "READ（讀取）" == localize_direction(I2CDirection.READ)
    assert "未知" in localize_direction(None)


def test_semantic_summary_localization() -> None:
    raw_summary = "ACK attribution unavailable; semantic decoding withheld"
    assert "ACK 歸屬未知；保留語意解碼" == localize_semantic_summary(raw_summary)

    mux_summary = (
        "I2C MUX 0x70 Channel Switch -> [2] (aggregate ACK; per-byte attribution unavailable)"
    )
    assert (
        "I2C 多工器 0x70 通道切換 -> [2]（彙總 ACK；未提供逐位元組歸屬）"
        == localize_semantic_summary(mux_summary)
    )


def test_quality_message_localization() -> None:
    zh_msg = localize_quality_message("I2C_ACK_AGGREGATE_UNATTRIBUTABLE")
    assert "彙總格式" in zh_msg
    assert "保留語意解碼" in zh_msg


def test_mux_hazard_report_text_is_chinese_first() -> None:
    description = localize_issue_description(
        "I2C Mux at 0x70 was configured with control byte 0x05, enabling channels [0, 2] simultaneously."
    )
    root_cause = localize_issue_root_cause(
        "Enabling multiple downstream MUX channels simultaneously can cause address collisions "
        + "and excessive bus capacitance (> 400pF)."
    )
    advice = localize_issue_advice(
        "Ensure only 1 downstream channel is enabled unless broadcast write is intended."
    )

    assert "I2C 多工器控制位元組為 0x05" in description
    assert "同時啟用多個下游 MUX 通道" in root_cause
    assert "除非刻意進行 broadcast write" in advice


def test_explanatory_localization_does_not_corrupt_unexpected_tokens() -> None:
    text = "Unexpected data NACK; payload was not fully accepted; semantic decoding withheld"

    localized = localize_explanatory_text(text)

    assert "un預期" not in localized
    assert localized == "資料 NACK；Payload 未完整接受；保留語意解碼"


def test_sensor_and_pmbus_semantic_summaries_are_chinese_first() -> None:
    assert localize_semantic_summary("Temperature data unavailable") == "溫度資料不可用"
    assert (
        localize_semantic_summary(
            "Sensor response contains 3 byte(s); expected one 16-bit register"
        )
        == "感測器回應包含 3 個位元組；預期一個 16 位元暫存器"
    )
    assert (
        localize_semantic_summary("BUS_VOLTAGE = 12.500 V (INA226) / 5.000 V (INA219)")
        == "匯流排電壓（BUS_VOLTAGE） = 12.500 V (INA226) / 5.000 V (INA219)"
    )
    assert (
        localize_semantic_summary(
            "STATUS_BYTE=0x22 -> VOUT_OV (Output Over-Voltage Fault), CML (Comm/Memory/Logic Error)"
        )
        == "STATUS_BYTE（狀態位元組）=0x22 -> VOUT_OV（輸出過電壓故障）, "
        "CML（通訊／記憶體／邏輯錯誤）"
    )
    assert (
        localize_semantic_summary("WRITE_PROTECT = 0x80 (Entire memory protected)")
        == "WRITE_PROTECT（寫入保護） = 0x80（整個記憶體已保護）"
    )
    assert (
        localize_semantic_summary("MFR_MODEL: block count mismatch (declared 3, received 2)")
        == "MFR_MODEL：Block Read 的 Byte Count 不一致（宣告 3，收到 2）"
    )


def test_markdown_report_localization_contains_mandated_sections() -> None:
    engine = I2CDiagnosticEngine(default_eeprom_page_size=8, smbus_timeout_ms=25.0)
    csv_path = Path(__file__).parents[1] / "tests" / "data" / "saleae_normal_pmbus_eeprom.csv"
    report = engine.analyze_csv_file(str(csv_path))
    md = I2CReporter.generate_markdown(report)

    assert "# I2C / SMBus / PMBus 協定診斷報告（Protocol Diagnostic Report）" in md
    assert "> **總結摘要（Summary）**：" in md
    assert "## 1. 匯流排時序與交易健康啟發評等（Bus Timing & Health）" in md
    assert "## 2. 偵測到的從裝置分佈表（Detected Peripheral Device Map）" in md
    assert "## 3. 封包交易序列與解碼明細（Transaction Sequence & Decoded Telemetry）" in md
    assert "## ⚠ 資料證據與品質限制（Data Quality Limitations）" in md
    assert "## 4. 異常診斷與排查行動建議（Diagnostic Issues & Debugging Advice）" in md


def test_markdown_report_translates_anomaly_prose_but_keeps_issue_tokens() -> None:
    engine = I2CDiagnosticEngine(smbus_timeout_ms=25.0)
    csv_path = Path(__file__).parents[1] / "tests" / "data" / "saleae_anomaly_addr_nack.csv"
    report = engine.analyze_csv_file(str(csv_path))
    md = I2CReporter.generate_markdown(report)

    assert "I2C_ADDR_NACK" in md
    assert "7-bit 位址 0x3A" in md
    assert "位址 NACK" in md
    assert "did NOT acknowledge" not in md
    assert "No byte duration or bitrate evidence" not in md


def test_generated_driver_templates_contain_zh_tw_comments() -> None:
    spec = I2CTransferSpec(
        address_7bit=0x50,
        bus=1,
        operation=I2CTransferOperation.COMBINED_REGISTER_READ,
        register=0x10,
        register_width=8,
        read_length=2,
    )
    snippets = I2CDriverCodeGenerator.generate_from_spec(spec)

    assert "【程式碼模板】" in snippets["Linux Userspace (i2c-dev)"]
    assert "複合暫存器讀取" in snippets["Linux Userspace (i2c-dev)"]
    assert "【指令模板】" in snippets["OpenBMC / Linux CLI (i2c-tools)"]
    assert "【程式碼模板】" in snippets["STM32 HAL C Driver"]
    assert "【程式碼模板】" in snippets["Arduino / Wire.h"]
