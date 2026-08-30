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
from fw_diag_tool.resources import load_i2c_sample, load_pcie_lspci_sample

APP_PATH = Path(__file__).resolve().parents[1] / "src" / "fw_diag_tool" / "gui" / "app.py"


def i2c_diagnosis_render() -> None:
    from fw_diag_tool.gui.pages.i2c_diagnosis import render

    render()


def pcie_render() -> None:
    from fw_diag_tool.gui.pages.pcie_ui import render

    render()


def register_render() -> None:
    from fw_diag_tool.gui.pages.register_ui import render

    render()


def codegen_render() -> None:
    from fw_diag_tool.gui.pages.codegen_ui import render

    render()


def i2c_builder_render() -> None:
    from fw_diag_tool.gui.pages.i2c_builder_ui import render

    render()


def dts_render() -> None:
    from fw_diag_tool.gui.pages.dts_ui import render

    render()


def sop_render() -> None:
    from fw_diag_tool.gui.pages.sop_ui import render

    render()


def spi_render() -> None:
    from fw_diag_tool.gui.pages.spi_ui import render

    render()


def uart_render() -> None:
    from fw_diag_tool.gui.pages.uart_ui import render

    render()


def mctp_render() -> None:
    from fw_diag_tool.gui.pages.mctp_ui import render

    render()


def fault_arena_render() -> None:
    from fw_diag_tool.gui.pages.fault_arena_ui import render

    render()


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
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()

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
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    at.button[0].click().run()

    at.number_input[0].set_value(30.0).run()

    assert not at.exception
    assert any(metric.label == "總傳輸次數" and metric.value == "18" for metric in at.metric)


def test_gui_builtin_sample_is_cleared_when_input_format_changes():
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    at.button[0].click().run()
    assert any(metric.label == "總傳輸次數" and metric.value == "18" for metric in at.metric)

    at.radio[0].set_value("raw_digital").run()

    assert not at.exception
    assert any("原教學範例已清除" in item.value for item in at.warning)
    assert not any(metric.label == "總傳輸次數" for metric in at.metric)


def test_gui_teaching_selector_routes_text_and_raw_samples_to_declared_parsers():
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()

    at.selectbox[0].set_value("文字追蹤記錄（2 筆）").run()
    at.button[0].click().run()
    assert not at.exception
    assert any(metric.label == "總傳輸次數" and metric.value == "2" for metric in at.metric)

    at.selectbox[0].set_value("原始數位量測（100 kHz、1 筆）").run()
    at.button[0].click().run()
    assert not at.exception
    assert any(metric.label == "總傳輸次數" and metric.value == "1" for metric in at.metric)
    assert any(
        metric.label == "平均時鐘頻率" and metric.value == "100.0 kHz" for metric in at.metric
    )


def test_gui_waveform_explains_clock_stretch_byte_evidence():
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    stretch_csv = Path("examples/data/i2c_clock_stretch.csv").read_bytes()
    at.file_uploader[1].upload("i2c_clock_stretch.csv", stretch_csv, "text/csv").run()

    assert not at.exception
    assert any(
        "byte_val" in caption.value
        and "source_clock_stretch" in caption.value
        and "ACK 前" in caption.value
        for caption in at.caption
    )


def test_gui_waveform_keeps_aggregate_clock_stretch_unattributed():
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    aggregate_csv = (
        "Time,Packet ID,Address,Data,Read/Write,ACK/NACK,Duration,Clock Stretch [s]\n"
        '0.001000,0,0x50,"0x10 0x20",Write,ACK,0.000090,0.000250\n'
    )
    at.file_uploader[1].upload(
        "aggregate_clock_stretch.csv", aggregate_csv.encode("utf-8"), "text/csv"
    ).run()

    assert not at.exception
    assert any(
        "彙總列" in caption.value
        and "source_clock_stretch" in caption.value
        and "無法歸屬特定位元組，也未繪製於任何 ACK 前" in caption.value
        for caption in at.caption
    )
    assert not any("延展區段繪製在該 byte ACK 前" in caption.value for caption in at.caption)


def test_gui_session_restores_raw_input_format_before_replay():
    raw = Path("examples/data/i2c_raw_100khz.csv").read_bytes()
    session = serialize_i2c_session(
        {"total_transactions": 1},
        input_name="raw.csv",
        input_bytes=raw,
        input_mode="raw_digital",
        smbus_timeout_ms=30.0,
    )
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
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

    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
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

    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    at.file_uploader[0].upload("legacy.fwsession.json", legacy_session, "application/json").run()
    assert at.radio[0].value == "decoded_csv"
    assert at.number_input[0].value == 25.0
    at.file_uploader[1].upload("raw.csv", raw, "text/csv").run()

    assert not at.exception
    assert any("沒有 capture SHA-256" in item.value for item in at.warning)
    assert not any("SHA-256 與 capture 相符" in item.value for item in at.success)


def test_gui_accepts_version_alias_session_without_streamlit_exception():
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    content = b'{"version":"2.0","config":{},"report":{}}'
    at.file_uploader[0].upload("malformed.fwsession.json", content, "application/json").run()

    assert not at.exception
    assert not at.error
    assert any("Session" in info.value for info in at.info)


def test_gui_invalid_session_json_is_localized():
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    at.file_uploader[0].upload(
        "invalid.fwsession.json", b"not-json", "application/json"
    ).run()

    assert not at.exception
    assert any("Session JSON 格式無效" in error.value for error in at.error)
    assert not any("invalid session JSON" in error.value for error in at.error)


def test_gui_loads_session_settings_and_replays_matching_capture():
    sample = load_i2c_sample()
    session = serialize_i2c_session(
        {"total_transactions": 18},
        input_name="capture.csv",
        input_bytes=sample.encode("utf-8"),
        input_mode="Saleae Analyzer table / text trace",
        smbus_timeout_ms=30.0,
    )
    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()

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

    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    at.file_uploader[0].upload(
        "first.fwsession.json", first_session.encode("utf-8"), "application/json"
    ).run()
    at.file_uploader[1].upload("raw.csv", raw, "text/csv").run()
    at.file_uploader[0].upload("second.fwsession.json", second_session, "application/json").run()
    at.file_uploader[1].upload("decoded.csv", sample, "text/csv").run()

    assert not at.exception
    assert not at.error
    assert at.radio[0].value == "decoded_csv"
    assert at.number_input[0].value == 25.0
    assert any(
        "- **板級設定檔（Board profile）**: `未套用（none）`" in item.value for item in at.markdown
    )


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

    at = AppTest.from_function(i2c_diagnosis_render, default_timeout=15).run()
    at.file_uploader[0].upload(
        "valid.fwsession.json", json.dumps(session_payload).encode("utf-8"), "application/json"
    ).run()
    at.file_uploader[1].upload("raw.csv", raw, "text/csv").run()
    at.file_uploader[0].upload(
        "invalid.fwsession.json", json.dumps(bad_payload).encode("utf-8"), "application/json"
    ).run()

    assert not at.exception
    assert any("smbus_timeout_ms" in item.value for item in at.error)
    assert not any(
        "must be a finite value between 1 and 100" in item.value for item in at.error
    )
    assert at.radio[0].value == "decoded_csv"
    assert at.number_input[0].value == 25.0
    assert at.text_area[0].value == ""


def test_gui_respects_pcie_mode_and_rejects_invalid_register_value():
    at = AppTest.from_function(pcie_render, default_timeout=15).run()
    at.radio[0].set_value("貼上 Linux dmesg AER 錯誤日誌（AER Error Log）")
    at.text_area[0].input("AER: Corrected error received: 0000:00:1c.0")
    next(button for button in at.button if button.label == "執行 PCIe 分析").click().run()

    assert not at.exception
    assert any("Kernel dmesg AER 診斷結果" in item.value for item in at.subheader)

    at_reg = AppTest.from_function(register_render, default_timeout=15).run()
    at_reg.text_input[0].input("not-hex").run()

    assert not at_reg.exception
    assert any("暫存器值格式錯誤" in error.value for error in at_reg.error)
    assert not at_reg.table


def test_gui_register_decoder_localizes_builtin_descriptions():
    at = AppTest.from_function(register_render, default_timeout=15).run()

    assert not at.exception
    assert any(
        item.value.startswith("暫存器說明（Description）：PMBus 標準狀態字") for item in at.caption
    )


def test_gui_pcie_invalid_dump_is_reported_without_streamlit_exception():
    at = AppTest.from_function(pcie_render, default_timeout=15).run()
    at.text_area[0].input("not a config dump").run()
    next(button for button in at.button if button.label == "執行 PCIe 分析").click().run()

    assert not at.exception
    assert any("PCIe 輸入錯誤" in error.value for error in at.error)
    assert any("十六進位輸入無效" in error.value for error in at.error)


def test_gui_pcie_loads_lspci_sample_and_shows_vendor_id():
    at = AppTest.from_function(pcie_render, default_timeout=30).run()

    assert load_pcie_lspci_sample().rstrip("\n") == Path(
        "examples/data/pcie_aer_lspci.txt"
    ).read_text(encoding="utf-8").rstrip("\n")
    next(
        button
        for button in at.button
        if button.label == "載入內建 lspci PCIe 設定空間範例（Config Space）"
    ).click().run()

    assert not at.exception
    assert any("已載入內建 lspci PCIe 設定空間範例（Config Space）" in item.value for item in at.info)
    next(button for button in at.button if button.label == "執行 PCIe 分析").click().run()

    assert not at.exception
    assert any(
        metric.label == "廠商／裝置 ID（Vendor / Device ID）"
        and metric.value == "0x10EE / 0x7024"
        for metric in at.metric
    )
    assert any(metric.label == "能力數量（Capabilities）" for metric in at.metric)
    assert any(
        metric.label == "標頭類型（Header Type）"
        and "端點裝置（TYPE_0_ENDPOINT）" in metric.value
        for metric in at.metric
    )
    assert any(
        "Extended Capabilities" in item.value
        and "進階錯誤回報（Advanced Error Reporting；AER）" in item.value
        for item in at.markdown
    )


def test_gui_c_header_invalid_module_name_is_reported():
    at = AppTest.from_function(codegen_render, default_timeout=15).run()
    at.text_input[0].input("9-not-a-c-identifier").run()

    assert not at.exception
    assert any("C 標頭檔輸入錯誤" in error.value for error in at.error)
    assert not any(
        "must produce a C identifier beginning with a letter" in error.value
        for error in at.error
    )


def test_gui_c_header_prompt_is_chinese_first_and_keeps_codegen_tokens():
    at = AppTest.from_function(codegen_render, default_timeout=15).run()

    assert not at.exception
    assert any(
        "C 語言標頭檔起始模板（C header template）" in info.value
        and "datasheet" in info.value
        and "MISRA checker" in info.value
        for info in at.info
    )


def test_gui_packet_builder_read_template_is_explicit_about_length():
    at = AppTest.from_function(i2c_builder_render, default_timeout=15).run()
    at.selectbox[0].set_value("Temperature sensor：combined register read")
    at.button[0].click().run()
    at.number_input[1].set_value(4).run()

    assert not at.exception
    assert any("rx_buf[4]" in block.value for block in at.code)
    assert any("r4" in block.value for block in at.code)
    assert any("不是硬體量測" in caption.value for caption in at.caption)


def test_gui_packet_builder_supports_direct_read_without_register_field():
    at = AppTest.from_function(i2c_builder_render, default_timeout=15).run()
    at.selectbox[0].set_value("Sensor：direct read")
    at.button[0].click().run()

    assert not at.exception
    assert not any(field.label == "暫存器位移（Register Offset）" for field in at.text_input)
    assert any("直接讀取：不會送出暫存器階段。" in block.value for block in at.code)
    assert any("i2ctransfer 1 r2@0x40" in block.value for block in at.code)


def test_gui_packet_builder_uses_little_endian_register_bytes_and_safe_cli():
    at = AppTest.from_function(i2c_builder_render, default_timeout=15).run()
    at.selectbox[0].set_value("EEPROM：16-bit little-endian register write")
    at.button[0].click().run()

    cli_blocks = [block.value for block in at.code if "i2ctransfer" in block.value]
    assert not at.exception
    assert any("0x34 0x12 0xAA" in block for block in cli_blocks)
    assert all("i2ctransfer -y" not in block for block in cli_blocks)
    assert any("寫入操作可能改變" in warning.value for warning in at.warning)


def test_gui_packet_builder_validates_before_rendering_or_codegen():
    at = AppTest.from_function(i2c_builder_render, default_timeout=15).run()
    at.text_input(key="i2c_builder_address").set_value("0x78").run()

    assert not at.exception
    assert any("輸入格式錯誤" in error.value and "位址必須介於" in error.value for error in at.error)
    assert not any("address_7bit must be between" in error.value for error in at.error)
    assert not any("i2ctransfer" in block.value for block in at.code)


def test_gui_dts_generator_localizes_device_validation_error():
    at = AppTest.from_function(dts_render, default_timeout=15).run()
    at.text_area[0].set_value("- bad: x").run()
    at.button[0].click().run()

    assert not at.exception
    assert any("DTS 輸入錯誤" in error.value and "缺少 addr" in error.value for error in at.error)
    assert not any("is missing addr" in error.value for error in at.error)


def test_gui_dts_generator_requires_and_renders_explicit_device_topology():
    at = AppTest.from_function(dts_render, default_timeout=15).run()
    at.button[0].click().run()

    assert not at.exception
    assert not at.error
    assert len(at.code) == 1
    assert "clock-frequency = <400000>;" in at.code[0].value
    assert 'compatible = "atmel,24c64";' in at.code[0].value


def test_gui_sop_page_explains_all_layers_and_evidence_terms():
    at = AppTest.from_function(sop_render, default_timeout=15).run()

    assert not at.exception
    assert any("L1" in item.value and "L7" in item.value for item in at.subheader)
    assert any("Measured" in str(item.value) for item in at.table)


def test_gui_spi_flash_page_sample_runs_without_exception():
    at = AppTest.from_function(spi_render, default_timeout=15).run()
    at.button[0].click().run()

    assert not at.exception
    assert any(metric.label == "總傳輸次數" and metric.value == "4" for metric in at.metric)
    assert any("Winbond W25Q128" in info.value for info in at.info)
    assert any(field.label == "頁面大小（Page Size；bytes）" for field in at.number_input)
    assert any(metric.label == "頁面程式寫入（Page Program）" for metric in at.metric)
    assert any(
        "本頁分析的是分析器已解碼" in caption.value and "signal integrity" in caption.value
        for caption in at.caption
    )
    assert any(button.label == "下載 SPI Markdown 診斷報告" for button in at.download_button)


def test_gui_spi_invalid_csv_localizes_parser_error():
    at = AppTest.from_function(spi_render, default_timeout=15).run()
    at.file_uploader[0].upload("invalid.csv", b"garbage\n", "text/csv").run()

    assert not at.exception
    assert any(
        "SPI CSV 必須提供明確的 timestamp 欄位" in error.value for error in at.error
    )
    assert not any("must provide an explicit timestamp column" in error.value for error in at.error)


def test_gui_register_decoder_localizes_decode_error():
    at = AppTest.from_function(register_render, default_timeout=15).run()
    at.text_input[0].set_value("0x100000000").run()

    assert not at.exception
    assert any("暫存器值必須介於 0 和 0xFFFFFFFF" in error.value for error in at.error)
    assert not any("register value must be between 0 and 0xFFFFFFFF" in error.value for error in at.error)


def test_gui_uart_crash_page_sample_runs_without_exception():
    at = AppTest.from_function(uart_render, default_timeout=15).run()
    assert at.radio[0].options == [
        "貼上 UART 日誌（UART Log）／崩潰轉儲（Crash Dump）",
        "載入範例：Linux 核心 Panic 日誌（Kernel Panic Log）",
        "載入範例：ARM Cortex-M HardFault 日誌（HardFault Log）",
    ]
    at.radio[0].set_value("載入範例：Linux 核心 Panic 日誌（Kernel Panic Log）").run()
    at.button[0].click().run()

    assert not at.exception
    assert any("nvme_pci_complete_rq" in item.value for item in at.markdown)
    assert any(button.label.startswith("下載此 UART 範例") for button in at.download_button)
    assert any(button.label == "下載 UART Markdown 診斷報告" for button in at.download_button)
    assert any("使用相同建置版本的 ELF" in item.value for item in at.caption)
    assert not any("matching ELF、symbol、kernel source" in item.value for item in at.caption)


def test_gui_mctp_page_sample_runs_without_exception():
    at = AppTest.from_function(mctp_render, default_timeout=15).run()
    at.button[0].click().run()

    assert not at.exception
    assert any("MCTP Packets" in item.value for item in at.markdown)
    assert any(button.label == "下載內建 MCTP／IPMB 範例" for button in at.download_button)
    assert any(button.label == "下載 MCTP／IPMB Markdown 診斷報告" for button in at.download_button)


def test_gui_mctp_protocol_mode_is_visible_before_execute_and_persists():
    at = AppTest.from_function(mctp_render, default_timeout=15).run()

    assert not at.exception
    assert len(at.selectbox) == 1
    assert at.selectbox[0].value == "auto"

    at.selectbox[0].set_value("ipmb").run()
    assert not at.exception
    assert len(at.selectbox) == 1
    assert at.selectbox[0].value == "ipmb"


def test_gui_mctp_page_is_zh_tw_first_and_states_evidence_boundary():
    at = AppTest.from_function(mctp_render, default_timeout=15).run()

    assert not at.exception
    assert at.text_area[0].label.startswith("請貼上 MCTP／IPMB 封包的十六進位位元組")
    assert "空白、逗號或分號分隔" in at.text_area[0].help
    assert at.selectbox[0].options == [
        "自動判斷（auto；依結構／Checksum 證據）",
        "強制 MCTP（DSP0236）",
        "強制 IPMB（IPMI v2.0／Checksum）",
    ]
    assert any(
        "證據範圍" in caption.value
        and "MCTP／IPMB" in caption.value
        and "DSP0236" in caption.value
        and "PLDM" in caption.value
        and "SPDM" in caption.value
        and "不是實體鏈路的 Measured 量測" in caption.value
        for caption in at.caption
    )

    at.text_area[0].set_value("01").run()
    next(button for button in at.button if button.label.startswith("執行 MCTP／IPMB")).click().run()

    assert not at.exception
    assert any("封包框架（frame）" in warning.value for warning in at.warning)
    assert any("十六進位位元組（hex bytes）" in warning.value for warning in at.warning)
    assert not any("no recognizable MCTP packet or IPMB frame" in warning.value for warning in at.warning)


def test_gui_fault_arena_mctp_cases_render_protocol_reports():
    at = AppTest.from_function(fault_arena_render, default_timeout=15).run()

    at.selectbox[0].set_value("Case 19: MCTP PLDM 感測器數值傳輸異常與封包順序錯亂").run()
    at.button[0].click().run()
    assert not at.exception
    assert any("MCTP Packets" in item.value for item in at.markdown)

    at.selectbox[0].set_value("Case 20: IPMB Checksum 1/2 校驗碼錯誤引發封包丟棄").run()
    at.button[0].click().run()
    assert not at.exception
    assert any("IPMB Frames" in item.value for item in at.markdown)


def test_gui_fault_arena_case04_uses_eeprom_profile_and_case_sop_metadata():
    at = AppTest.from_function(fault_arena_render, default_timeout=15).run()
    at.selectbox[0].set_value(
        "Case 04: I2C EEPROM Page Boundary 跨頁覆蓋風險（Page Rollover）"
    ).run()

    assert any("故障現象（Observed symptom）" in item.value for item in at.markdown)
    assert any("Page Rollover" in item.value for item in at.markdown)
    at.button[0].click().run()

    assert not at.exception
    assert any("EEPROM Page Rollover" in item.value for item in at.markdown)


def test_gui_pcie_dmesg_event_shows_captured_tlp_header():
    at = AppTest.from_function(pcie_render, default_timeout=15).run()
    at.radio[0].set_value("貼上 Linux dmesg AER 錯誤日誌（AER Error Log）")
    at.text_area[0].input(
        "[  124.582910] pcieport 0000:00:01.0: AER: Uncorrected (Fatal) error received: 0000:01:00.0\n"
        "[  124.582922] pcieport 0000:00:01.0:    [18] MalformedTLP           (First)\n"
        "[  124.582925] pcieport 0000:00:01.0:   TLP Header: 00000001 0100000f fe000000 00000000"
    )
    next(button for button in at.button if button.label == "執行 PCIe 分析").click().run()

    assert not at.exception
    assert any("擷取到的 TLP Header" in item.value for item in at.markdown)
    assert any("00000001 0100000f fe000000 00000000" in item.value for item in at.markdown)


def test_gui_fault_arena_runs_without_exception():
    at = AppTest.from_function(fault_arena_render, default_timeout=15).run()

    assert not at.exception
    assert any("案例分析" in item.value for item in at.info)
    at.button[0].click().run()
    assert not at.exception
    assert any("自動診斷分析結果" in item.value for item in at.markdown)
