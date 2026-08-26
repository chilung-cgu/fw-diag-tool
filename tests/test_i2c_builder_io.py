from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from fw_diag_tool.gui.pages.i2c_builder import (
    I2C_BUILDER_PRESETS,
    MAX_BUILDER_WAVEFORM_POINTS,
    build_i2c_bundle,
    max_write_data_bytes,
    parse_hex_bytes,
    parse_hex_integer,
    preset_widget_state,
)
from fw_diag_tool.i2c.transfer_spec import I2CTransferSpec


def test_builder_hex_parsing_is_strict_and_byte_bounded() -> None:
    assert parse_hex_integer("0x50", label="Address") == 0x50
    assert parse_hex_bytes("0xAA, bb 12", label="Data", required=True) == (
        0xAA,
        0xBB,
        0x12,
    )

    with pytest.raises(ValueError, match="at least one"):
        parse_hex_bytes("", label="Data", required=True)
    with pytest.raises(ValueError, match="0x00 and 0xFF"):
        parse_hex_bytes("0x100", label="Data")
    with pytest.raises(ValueError, match="limit is 2"):
        parse_hex_bytes("1 2 3", label="Data", max_bytes=2)


def test_packet_presets_supply_stable_streamlit_widget_state() -> None:
    state = preset_widget_state(I2C_BUILDER_PRESETS["Sensor：direct read"])

    assert state["i2c_builder_operation"] == "direct_read"
    assert state["i2c_builder_register"] == ""
    assert state["i2c_builder_read_length"] == 2


def test_builder_bundle_is_deterministic_and_self_verifying() -> None:
    spec = I2CTransferSpec(
        address_7bit=0x50,
        operation="register_write",
        register=0x10,
        data_bytes=[0xAA, 0xBB],
    )
    snippets = {
        "Linux Userspace (i2c-dev)": "int example(void) { return 0; }",
        "OpenBMC / Linux CLI (i2c-tools)": "i2ctransfer 1 w3@0x50 0x10 0xAA 0xBB",
        "Arduino / Wire.h": "void setup(void) { Wire.begin(); }",
    }

    first, first_sha, spec_sha = build_i2c_bundle(spec, snippets)
    second, second_sha, second_spec_sha = build_i2c_bundle(spec, snippets)

    assert first == second
    assert first_sha == second_sha == hashlib.sha256(first).hexdigest()
    assert spec_sha == second_spec_sha
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        stored_spec = archive.read("transfer_spec.json")
    assert "SAFETY.txt" in names
    assert "snippets/OpenBMC_Linux_CLI_i2c-tools.sh" in names
    assert "snippets/Arduino_Wire.h.cpp" in names
    assert manifest["spec_sha256"] == hashlib.sha256(stored_spec).hexdigest()


def test_builder_write_limit_accounts_for_register_bytes_and_waveform_budget() -> None:
    direct_limit = max_write_data_bytes(register_operation=False, register_width=8)
    reg8_limit = max_write_data_bytes(register_operation=True, register_width=8)
    reg16_limit = max_write_data_bytes(register_operation=True, register_width=16)

    assert direct_limit == 3702
    assert reg8_limit == 3701
    assert reg16_limit == 3700
    assert direct_limit > reg8_limit > reg16_limit
    assert 10 + 27 * (1 + direct_limit) <= MAX_BUILDER_WAVEFORM_POINTS
