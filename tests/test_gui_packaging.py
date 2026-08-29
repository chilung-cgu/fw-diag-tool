from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from fw_diag_tool import __version__
from fw_diag_tool.board_profile import load_board_profile
from fw_diag_tool.cli import app
from fw_diag_tool.errors import ResourceLimitError
from fw_diag_tool.gui.session_io import serialize_i2c_session
from fw_diag_tool.gui.uploads import (
    MAX_TEXT_BYTES,
    MAX_UPLOAD_BYTES,
    decode_uploaded_text,
    validate_pasted_text,
)
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
    assert result.output.strip() == __version__ == "1.1.1"


def test_launch_gui_propagates_streamlit_exit_code(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=7))

    result = CliRunner().invoke(app, ["gui"])

    assert result.exit_code == 7


def test_launch_gui_disables_telemetry_and_caps_streamlit_uploads(monkeypatch):
    calls = []
    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("subprocess.run", fake_run)

    result = CliRunner().invoke(app, ["gui"])

    assert result.exit_code == 0
    args, kwargs = calls[0]
    assert "--browser.gatherUsageStats=false" in args
    assert "--server.maxUploadSize=20" in args
    assert "--server.maxMessageSize=20" in args
    assert kwargs["check"] is False


def test_launch_gui_rejects_remote_bind_without_explicit_opt_in(monkeypatch):
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = CliRunner().invoke(app, ["gui", "--host", "0.0.0.0"])

    assert result.exit_code == 2
    assert "--allow-remote" in result.output
    assert called is False


def test_launch_gui_allows_remote_bind_with_explicit_opt_in(monkeypatch):
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("subprocess.run", fake_run)

    result = CliRunner().invoke(app, ["gui", "--host", "0.0.0.0", "--allow-remote"])

    assert result.exit_code == 0
    assert "--server.address=0.0.0.0" in calls[0]
    assert "authentication and TLS" in result.output


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


def test_pasted_text_limit_is_enforced_by_utf8_bytes():
    assert validate_pasted_text("é", label="UART log") == "é"

    with pytest.raises(ResourceLimitError) as error:
        validate_pasted_text("é" * (MAX_TEXT_BYTES // 2 + 1), label="UART log")

    assert error.value.resource == "UART log"
    assert error.value.limit == MAX_TEXT_BYTES


def test_gui_builtin_sample_runs_from_package_resource():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()

    at.button[0].click().run()

    assert not at.exception
    assert any(info.value == "已載入內建範例 CSV！" for info in at.info)
    assert any(metric.label == "總傳輸次數" and metric.value == "18" for metric in at.metric)
    assert any(
        "I2C / SMBus / PMBus 協定診斷報告（Protocol Diagnostic Report）" in item.value
        for item in at.markdown
    )
    assert not any("No byte duration or bitrate evidence" in item.value for item in at.markdown)


def test_gui_builtin_sample_survives_configuration_rerun():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.button[0].click().run()

    at.number_input[0].set_value(30.0).run()

    assert not at.exception
    assert any(metric.label == "總傳輸次數" and metric.value == "18" for metric in at.metric)


def test_gui_builtin_sample_is_cleared_when_input_format_changes():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.button[0].click().run()
    assert any(metric.label == "總傳輸次數" and metric.value == "18" for metric in at.metric)

    at.radio[0].set_value("raw_digital").run()

    assert not at.exception
    assert any("原教學範例已清除" in item.value for item in at.warning)
    assert not any(metric.label == "總傳輸次數" for metric in at.metric)


def test_gui_teaching_selector_routes_text_and_raw_samples_to_declared_parsers():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()

    at.selectbox[0].set_value("文字追蹤記錄（2 筆）").run()
    at.button[0].click().run()
    assert not at.exception
    assert any(metric.label == "總傳輸次數" and metric.value == "2" for metric in at.metric)

    at.selectbox[0].set_value("原始數位量測（100 kHz、1 筆）").run()
    at.button[0].click().run()
    assert not at.exception
    assert any(metric.label == "總傳輸次數" and metric.value == "1" for metric in at.metric)
    assert any(metric.label == "平均時鐘頻率" and metric.value == "100.0 kHz" for metric in at.metric)


def test_gui_session_restores_raw_input_format_before_replay():
    raw = Path("examples/data/i2c_raw_100khz.csv").read_bytes()
    session = serialize_i2c_session(
        {"total_transactions": 1},
        input_name="raw.csv",
        input_bytes=raw,
        input_mode="raw_digital",
        smbus_timeout_ms=30.0,
    )
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.file_uploader[0].upload("raw.fwsession.json", session.encode(), "application/json").run()
    at.file_uploader[1].upload("raw.csv", raw, "text/csv").run()

    assert not at.exception
    assert at.radio[0].value == "raw_digital"
    assert any(metric.label == "總傳輸次數" and metric.value == "1" for metric in at.metric)


def test_gui_session_without_capture_clears_previous_teaching_sample():
    raw = Path("examples/data/i2c_raw_100khz.csv").read_bytes()
    session = serialize_i2c_session(
        {"total_transactions": 1},
        input_name="raw.csv",
        input_bytes=raw,
        input_mode="raw_digital",
        smbus_timeout_ms=30.0,
    )

    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.button[0].click().run()
    assert any(metric.label == "總傳輸次數" and metric.value == "18" for metric in at.metric)

    at.file_uploader[0].upload(
        "raw.fwsession.json", session.encode("utf-8"), "application/json"
    ).run()

    assert not at.exception
    assert not at.error
    assert at.radio[0].value == "raw_digital"
    assert not any(metric.label == "總傳輸次數" for metric in at.metric)


def test_gui_session_without_sha_does_not_claim_replay():
    raw = Path("examples/data/i2c_raw_100khz.csv").read_bytes()
    legacy_session = json.dumps(
        {
            "version": "1.0",
            "name": "legacy",
            "data": {"old": "summary"},
            "provenance": {"input_mode": "raw_digital", "smbus_timeout_ms": 30.0},
        }
    ).encode("utf-8")

    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.file_uploader[0].upload(
        "legacy.fwsession.json", legacy_session, "application/json"
    ).run()
    assert at.radio[0].value == "decoded_csv"
    assert at.number_input[0].value == 25.0
    at.file_uploader[1].upload("raw.csv", raw, "text/csv").run()

    assert not at.exception
    assert any("沒有 capture SHA-256" in item.value for item in at.warning)
    assert not any("SHA-256 與 capture 相符" in item.value for item in at.success)


def test_gui_accepts_version_alias_session_without_streamlit_exception():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    content = b'{"version":"2.0","config":{},"report":{}}'
    at.file_uploader[0].upload("malformed.fwsession.json", content, "application/json").run()

    assert not at.exception
    assert not at.error
    assert any("Session" in info.value for info in at.info)


def test_gui_loads_session_settings_and_replays_matching_capture():
    sample = load_i2c_sample()
    session = serialize_i2c_session(
        {"total_transactions": 18},
        input_name="capture.csv",
        input_bytes=sample.encode("utf-8"),
        input_mode="Saleae Analyzer table / text trace",
        smbus_timeout_ms=30.0,
    )
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()

    at.file_uploader[0].upload(
        "analysis.fwsession.json", session.encode("utf-8"), "application/json"
    ).run()
    at.file_uploader[1].upload("capture.csv", sample.encode("utf-8"), "text/csv").run()

    assert not at.exception
    assert at.number_input[0].value == 30.0
    assert any("SHA-256 與 capture 相符" in item.value for item in at.success)
    assert any(metric.label == "總傳輸次數" and metric.value == "18" for metric in at.metric)


def test_gui_session_replacement_resets_missing_saved_settings():
    raw = Path("examples/data/i2c_raw_100khz.csv").read_bytes()
    sample = load_i2c_sample().encode("utf-8")
    profile = load_board_profile(
        {
            "board_name": "board-a",
            "version": "1",
            "i2c_buses": [{"bus_num": 0, "speed_mode": "standard", "devices": []}],
        }
    )
    first_session = serialize_i2c_session(
        {},
        input_name="raw.csv",
        input_bytes=raw,
        input_mode="raw_digital",
        smbus_timeout_ms=30.0,
        board_profile=profile,
    )
    second_payload = json.loads(
        serialize_i2c_session(
            {},
            input_name="decoded.csv",
            input_bytes=sample,
            input_mode="decoded_csv",
        )
    )
    for key in (
        "input_mode",
        "input_format",
        "smbus_timeout_ms",
        "board_profile_name",
        "board_profile_version",
        "board_profile_sha256",
        "board_profile_hash",
        "board_profile_content",
    ):
        second_payload["config"].pop(key, None)
    second_session = json.dumps(second_payload).encode("utf-8")

    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.file_uploader[0].upload(
        "first.fwsession.json", first_session.encode("utf-8"), "application/json"
    ).run()
    at.file_uploader[1].upload("raw.csv", raw, "text/csv").run()
    at.file_uploader[0].upload(
        "second.fwsession.json", second_session, "application/json"
    ).run()
    at.file_uploader[1].upload("decoded.csv", sample, "text/csv").run()

    assert not at.exception
    assert not at.error
    assert at.radio[0].value == "decoded_csv"
    assert at.number_input[0].value == 25.0
    assert any("- **板級設定檔（Board profile）**: `未套用（none）`" in item.value for item in at.markdown)


def test_gui_invalid_session_settings_clear_previous_state():
    raw = Path("examples/data/i2c_raw_100khz.csv").read_bytes()
    profile = load_board_profile(
        {
            "board_name": "board-a",
            "version": "1",
            "i2c_buses": [{"bus_num": 0, "speed_mode": "standard", "devices": []}],
        }
    )
    session_payload = json.loads(
        serialize_i2c_session(
            {},
            input_name="raw.csv",
            input_bytes=raw,
            input_mode="raw_digital",
            smbus_timeout_ms=30.0,
            board_profile=profile,
        )
    )
    bad_payload = dict(session_payload)
    bad_payload["config"] = dict(session_payload["config"])
    bad_payload["config"]["smbus_timeout_ms"] = "bad"

    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.file_uploader[0].upload(
        "valid.fwsession.json", json.dumps(session_payload).encode("utf-8"), "application/json"
    ).run()
    at.file_uploader[1].upload("raw.csv", raw, "text/csv").run()
    at.file_uploader[0].upload(
        "invalid.fwsession.json", json.dumps(bad_payload).encode("utf-8"), "application/json"
    ).run()

    assert not at.exception
    assert any("smbus_timeout_ms" in item.value for item in at.error)
    assert at.radio[0].value == "decoded_csv"
    assert at.number_input[0].value == 25.0
    assert at.text_area[0].value == ""


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
    at.selectbox[0].set_value("Temperature sensor：combined register read")
    at.button[0].click().run()
    at.number_input[1].set_value(4).run()

    assert not at.exception
    assert any("rx_buf[4]" in block.value for block in at.code)
    assert any("r4" in block.value for block in at.code)
    assert any("不是硬體量測" in caption.value for caption in at.caption)


def test_gui_packet_builder_supports_direct_read_without_register_field():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🎨 I2C 封包模擬器與驅動產生").run()
    at.selectbox[0].set_value("Sensor：direct read")
    at.button[0].click().run()

    assert not at.exception
    assert not any(field.label == "暫存器位移（Register Offset）" for field in at.text_input)
    assert any("直接讀取：不會送出暫存器階段。" in block.value for block in at.code)
    assert any("i2ctransfer 1 r2@0x40" in block.value for block in at.code)


def test_gui_packet_builder_uses_little_endian_register_bytes_and_safe_cli():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🎨 I2C 封包模擬器與驅動產生").run()
    at.selectbox[0].set_value("EEPROM：16-bit little-endian register write")
    at.button[0].click().run()

    cli_blocks = [block.value for block in at.code if "i2ctransfer" in block.value]
    assert not at.exception
    assert any("0x34 0x12 0xAA" in block for block in cli_blocks)
    assert all("i2ctransfer -y" not in block for block in cli_blocks)
    assert any("寫入操作可能改變" in warning.value for warning in at.warning)


def test_gui_packet_builder_validates_before_rendering_or_codegen():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🎨 I2C 封包模擬器與驅動產生").run()
    at.text_input[0].set_value("0x78").run()

    assert not at.exception
    assert any("address_7bit must be between" in error.value for error in at.error)
    assert not any("i2ctransfer" in block.value for block in at.code)


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


def test_gui_mctp_protocol_mode_is_visible_before_execute_and_persists():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🌐 MCTP / IPMB 伺服器協定解析").run()

    assert not at.exception
    assert len(at.selectbox) == 1
    assert at.selectbox[0].value == "auto"

    at.selectbox[0].set_value("ipmb").run()
    assert not at.exception
    assert len(at.selectbox) == 1
    assert at.selectbox[0].value == "ipmb"


def test_gui_fault_arena_mctp_cases_render_protocol_reports():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🏆 Junior FW 實戰除錯實驗室 (Fault Arena)").run()

    at.selectbox[0].set_value("Case 19: MCTP PLDM 感測器數值傳輸異常與封包順序錯亂").run()
    at.button[0].click().run()
    assert not at.exception
    assert any("MCTP Packets" in item.value for item in at.markdown)

    at.selectbox[0].set_value("Case 20: IPMB Checksum 1/2 校驗碼錯誤引發封包丟棄").run()
    at.button[0].click().run()
    assert not at.exception
    assert any("IPMB Frames" in item.value for item in at.markdown)


def test_gui_pcie_dmesg_event_shows_captured_tlp_header():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🚀 PCIe Config & AER 診斷").run()
    at.radio[0].set_value("貼上 Linux dmesg AER Error Log")
    at.text_area[0].input(
        "[  124.582910] pcieport 0000:00:01.0: AER: Uncorrected (Fatal) error received: 0000:01:00.0\n"
        "[  124.582922] pcieport 0000:00:01.0:    [18] MalformedTLP           (First)\n"
        "[  124.582925] pcieport 0000:00:01.0:   TLP Header: 00000001 0100000f fe000000 00000000"
    )
    at.button[0].click().run()

    assert not at.exception
    assert any("擷取到的 TLP Header" in item.value for item in at.markdown)
    assert any("00000001 0100000f fe000000 00000000" in item.value for item in at.markdown)


def test_gui_fault_arena_runs_without_exception():
    at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    at.sidebar.radio[0].set_value("🏆 Junior FW 實戰除錯實驗室 (Fault Arena)").run()

    assert not at.exception
    assert any("案例分析" in item.value for item in at.info)
    at.button[0].click().run()
    assert not at.exception
    assert any("自動診斷分析結果" in item.value for item in at.markdown)
