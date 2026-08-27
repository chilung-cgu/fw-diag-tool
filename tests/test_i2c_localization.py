from __future__ import annotations

from pathlib import Path

from fw_diag_tool.gui.pages.i2c_builder import I2C_BUILDER_PRESETS
from fw_diag_tool.i2c.transfer_spec import I2CTransferOperation

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

