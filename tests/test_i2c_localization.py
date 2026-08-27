from __future__ import annotations

from pathlib import Path

from fw_diag_tool.codegen.driver_gen import I2CDriverCodeGenerator
from fw_diag_tool.gui.pages.i2c_builder import I2C_BUILDER_PRESETS
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.localization import (
    localize_category,
    localize_direction,
    localize_health_grade,
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
    assert "### 4.1 `📜 封包交易列表 (Transactions)`" in ch01
    assert "### 4.2 `📈 數位方波與協定軌 (Waveform)`" in ch01
    assert "### 4.3 `🚨 異常診斷 (Anomalies)`" in ch01
    assert "### 4.4 `📊 匯流排時序與健康圖表 (Bus Timing & Health)`" in ch01
    assert "### 4.5 `📝 Markdown 診斷報告 (Markdown Report)`" in ch01


def test_i2c_builder_presets_and_operations_are_intact() -> None:
    assert len(I2C_BUILDER_PRESETS) >= 5
    assert I2CTransferOperation.REGISTER_WRITE.value == "register_write"
    assert I2CTransferOperation.COMBINED_REGISTER_READ.value == "combined_register_read"
    assert I2CTransferOperation.DIRECT_WRITE.value == "direct_write"
    assert I2CTransferOperation.DIRECT_READ.value == "direct_read"


def test_localization_helpers_preserve_tokens_and_provide_zh_tw() -> None:
    assert "ACK（正常應答）" == localize_status(TransactionStatus.ACK)
    assert "ACK UNKNOWN（ACK 證據未知/未提供）" == localize_status(TransactionStatus.ACK_UNKNOWN)
    assert "Standard-mode（標準模式 100 kHz）" == localize_speed_mode(I2CSpeedMode.STANDARD_100K)
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
        "I2C 多工器 0x70 通道切換 -> [2] (Aggregate ACK；未提供單 Byte 歸屬)"
        == localize_semantic_summary(mux_summary)
    )


def test_quality_message_localization() -> None:
    zh_msg = localize_quality_message("I2C_ACK_AGGREGATE_UNATTRIBUTABLE")
    assert "Aggregate" in zh_msg
    assert "保留語意解碼" in zh_msg


def test_markdown_report_localization_contains_mandated_sections() -> None:
    engine = I2CDiagnosticEngine(default_eeprom_page_size=8, smbus_timeout_ms=25.0)
    csv_path = Path(__file__).parents[1] / "tests" / "data" / "saleae_normal_pmbus_eeprom.csv"
    report = engine.analyze_csv_file(str(csv_path))
    md = I2CReporter.generate_markdown(report)

    assert "# I2C / SMBus / PMBus Protocol Diagnostic Report (協定診斷報告)" in md
    assert "> **總結摘要 (Summary)**:" in md
    assert "## 1. 匯流排時序與交易健康啟發評等 (Bus Timing & Health)" in md
    assert "## 2. 偵測之從裝置分佈表 (Detected Peripheral Device Map)" in md
    assert "## 3. 封包交易序列與解碼明細 (Transaction Sequence & Decoded Telemetry)" in md
    assert "## ⚠ 資料證據與品質限制 (Data Quality Limitations)" in md
    assert "## 4. 異常診斷與排查行動建議 (Diagnostic Issues & Debugging Advice)" in md


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
