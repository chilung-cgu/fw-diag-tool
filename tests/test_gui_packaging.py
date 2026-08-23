from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from fw_diag_tool import __version__
from fw_diag_tool.cli import app
from fw_diag_tool.gui.uploads import MAX_UPLOAD_BYTES, decode_uploaded_text
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.resources import load_i2c_sample

APP_PATH = Path(__file__).resolve().parents[1] / "src" / "fw_diag_tool" / "gui" / "app.py"


@dataclass
class FakeUpload:
    name: str
    content: bytes
    reported_size: int | None = None

    @property
    def size(self) -> int:
        return self.reported_size if self.reported_size is not None else len(self.content)

    def getvalue(self) -> bytes:
        return self.content


def test_version_is_exposed_by_package_and_cli():
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == __version__ == "1.1.0"


def test_launch_gui_propagates_streamlit_exit_code(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=7))

    result = CliRunner().invoke(app, ["gui"])

    assert result.exit_code == 7


def test_packaged_i2c_sample_is_analyzable():
    sample = load_i2c_sample()
    report = I2CDiagnosticEngine().analyze_csv_content(sample)

    assert sample.startswith("Time [s],Packet ID,Address")
    assert report.total_transactions == 18


@pytest.mark.parametrize(
    ("upload", "allowed_extensions", "message"),
    [
        (FakeUpload("trace.bin", b"data"), {".csv"}, "不支援的檔案格式"),
        (FakeUpload("trace.csv", b""), {".csv"}, "檔案是空的"),
        (FakeUpload("trace.csv", b"a\x00b"), {".csv"}, "二進位資料"),
        (FakeUpload("trace.csv", b"\xff"), {".csv"}, "UTF-8"),
        (
            FakeUpload("trace.csv", b"x", reported_size=MAX_UPLOAD_BYTES + 1),
            {".csv"},
            "20 MiB",
        ),
    ],
)
def test_upload_preflight_rejects_invalid_input(upload, allowed_extensions, message):
    with pytest.raises(ValueError, match=message):
        decode_uploaded_text(upload, allowed_extensions=allowed_extensions)


def test_upload_preflight_accepts_utf8_bom():
    upload = FakeUpload("trace.csv", b"\xef\xbb\xbfTime,Data\n0,0x12\n")

    assert decode_uploaded_text(upload, allowed_extensions={".csv"}).startswith("Time,Data")


def test_gui_builtin_sample_runs_from_package_resource():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()

    at.button[0].click().run()

    assert not at.exception
    assert any(info.value == "已載入內建範例 CSV！" for info in at.info)
    assert any(metric.label == "總傳輸次數" and metric.value == "18" for metric in at.metric)


def test_gui_respects_pcie_mode_and_rejects_invalid_register_value():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🚀 PCIe Config & AER 診斷").run()
    at.radio[0].set_value("貼上 Linux dmesg AER Error Log")
    at.text_area[0].input("AER: Corrected error received: 0000:00:1c.0")
    at.button[0].click().run()

    assert not at.exception
    assert any("Kernel dmesg AER 診斷結果" in item.value for item in at.subheader)

    at.sidebar.radio[0].set_value("🎛 晶片暫存器 Bitfield 解碼器").run()
    at.text_input[0].input("not-hex").run()

    assert not at.exception
    assert any("暫存器值格式錯誤" in error.value for error in at.error)
    assert not at.table


def test_gui_pcie_invalid_dump_is_reported_without_streamlit_exception():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🚀 PCIe Config & AER 診斷").run()
    at.text_area[0].input("not a config dump").run()
    at.button[0].click().run()

    assert not at.exception
    assert any("PCIe 輸入錯誤" in error.value for error in at.error)


def test_gui_c_header_invalid_module_name_is_reported():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🛠 C 語言 Register 巨集產生器").run()
    at.text_input[0].input("9-not-a-c-identifier").run()

    assert not at.exception
    assert any("C header 輸入錯誤" in error.value for error in at.error)


def test_gui_packet_builder_read_template_is_explicit_about_length():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🎨 I2C 封包模擬器與驅動產生").run()
    at.selectbox[0].set_value("Read").run()
    at.number_input[0].set_value(4).run()

    assert not at.exception
    assert any("rx_buf[4]" in block.value for block in at.code)
    assert any("r4" in block.value for block in at.code)
    assert any("不是硬體量測" in caption.value for caption in at.caption)


def test_gui_dts_generator_requires_and_renders_explicit_device_topology():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🌲 Device Tree (.dts) 產生器").run()
    at.button[0].click().run()

    assert not at.exception
    assert not at.error
    assert len(at.code) == 1
    assert "clock-frequency = <400000>;" in at.code[0].value
    assert 'compatible = "atmel,24c64";' in at.code[0].value


def test_gui_sop_page_explains_all_layers_and_evidence_terms():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("📚 韌體除錯指南 & SOP").run()

    assert not at.exception
    assert any("L1" in item.value and "L7" in item.value for item in at.subheader)
    assert any("Measured" in str(item.value) for item in at.table)


def test_gui_spi_flash_page_sample_runs_without_exception():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("⚡ SPI Flash 協定診斷").run()
    at.button[0].click().run()

    assert not at.exception
    assert any(metric.label == "總傳輸次數" and metric.value == "4" for metric in at.metric)
    assert any("Winbond W25Q128" in info.value for info in at.info)


def test_gui_uart_crash_page_sample_runs_without_exception():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("📟 UART Crash & HardFault 分析").run()
    at.radio[0].set_value("載入範例 Linux Kernel Panic Log").run()
    at.button[0].click().run()

    assert not at.exception
    assert any("nvme_pci_complete_rq" in item.value for item in at.markdown)


def test_gui_mctp_page_sample_runs_without_exception():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🌐 MCTP / IPMB 伺服器協定解析").run()
    at.button[0].click().run()

    assert not at.exception
    assert any("MCTP Packets" in item.value for item in at.markdown)


def test_gui_fault_arena_runs_without_exception():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🏆 Junior FW 實戰除錯實驗室 (Fault Arena)").run()

    assert not at.exception
    assert any("案例分析" in item.value for item in at.info)
    at.button[0].click().run()
    assert not at.exception
    assert any("自動診斷分析結果" in item.value for item in at.markdown)
