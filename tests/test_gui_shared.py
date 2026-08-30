from __future__ import annotations

from fw_diag_tool.gui.shared import (
    _FAULT_ARENA_CASES_ZH,
    DEFAULT_I2C_TIMEOUT_MS,
    GUI_ANALYSIS_LIMITS,
    MAX_PACKET_HEX_CHARS,
    _localize_gui_error,
    _localize_mctp_error,
    _localize_pcie_input_error,
    _localize_register_description,
    _localize_register_meaning,
    analyze_i2c_input,
    analyze_spi_input,
    render_guide_expander,
)


def test_shared_constants_are_sensible():
    assert GUI_ANALYSIS_LIMITS.max_upload_bytes == 20 * 1024 * 1024
    assert MAX_PACKET_HEX_CHARS == 64 * 1024
    assert DEFAULT_I2C_TIMEOUT_MS == 25.0


def test_localize_register_meaning_known():
    assert "正常" in _localize_register_meaning("OK")
    assert "原始值" in _localize_register_meaning("Raw value: 0x12")


def test_localize_register_meaning_passthrough():
    assert _localize_register_meaning("SomeUnknownValue") == "SomeUnknownValue"


def test_localize_register_description():
    desc = _localize_register_description("PMBus Standard Status Byte")
    assert "PMBus 標準狀態位元組" in desc


def test_localize_pcie_input_error():
    err = _localize_pcie_input_error(
        "Invalid hex input: cannot extract at least 64 bytes of PCI configuration space."
    )
    assert "十六進位輸入無效" in err


def test_localize_gui_error_domains():
    assert "必須介於 0x08～0x77" in _localize_gui_error(
        "address_7bit must be between 8 and 119", domain="i2c_builder"
    )
    assert "必須提供明確的 timestamp" in _localize_gui_error(
        "SPI CSV must provide an explicit timestamp column", domain="spi"
    )
    assert "暫存器值必須是整數" in _localize_gui_error(
        "register value must be an integer", domain="register"
    )
    assert "缺少 addr" in _localize_gui_error("devices[0] is missing addr", domain="dts")
    assert "Session JSON 格式無效" in _localize_gui_error("invalid session JSON", domain="session")


def test_localize_mctp_error():
    msg = _localize_mctp_error("payload must be text")
    assert "必須是文字" in msg


def test_fault_arena_cases_structure():
    assert len(_FAULT_ARENA_CASES_ZH) == 30
    for case in _FAULT_ARENA_CASES_ZH:
        assert "case_id" in case
        assert "label" in case
        assert "symptom" in case
        assert "hypothesis" in case
        assert "check" in case


def test_callables_exist():
    assert callable(analyze_i2c_input)
    assert callable(analyze_spi_input)
    assert callable(render_guide_expander)
