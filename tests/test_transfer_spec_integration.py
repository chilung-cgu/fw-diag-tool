from typing import Any

import pytest

from fw_diag_tool.codegen.driver_gen import I2CDriverCodeGenerator
from fw_diag_tool.errors import ResourceLimitError
from fw_diag_tool.i2c.transfer_spec import (
    UNKNOWN_BYTE,
    Endianness,
    I2CTransferOperation,
    I2CTransferSpec,
)
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor


def test_register_write_golden_segments_and_all_platforms() -> None:
    spec = I2CTransferSpec(
        address_7bit=0x50,
        bus=2,
        operation=I2CTransferOperation.REGISTER_WRITE,
        register=0x10,
        data_bytes=[0xAA, 0xBB],
    )
    assert spec.canonical_bytes == (0x10, 0xAA, 0xBB)
    snippets = I2CDriverCodeGenerator.generate_from_spec(spec)
    assert "0x10, 0xAA, 0xBB" in snippets["Linux Userspace (i2c-dev)"]
    assert "i2ctransfer 2 w3@0x50 0x10 0xAA 0xBB" in snippets[
        "OpenBMC / Linux CLI (i2c-tools)"
    ]
    assert "-y" not in snippets["OpenBMC / Linux CLI (i2c-tools)"]
    assert "TEMPLATE" in snippets["STM32 HAL C Driver"]
    assert "Wire.write(0xAA);" in snippets["Arduino / Wire.h"]


@pytest.mark.parametrize("read_length", [1, 2, 4])
def test_combined_register_read_has_repeated_start_unknown_rx_and_final_nack(
    read_length: int,
) -> None:
    spec = I2CTransferSpec(
        address_7bit=0x50,
        operation="combined_register_read",
        register=0x10,
        read_length=read_length,
    )
    assert spec.segments[0].bytes == (0x10,)
    assert spec.segments[1].bytes == (UNKNOWN_BYTE,) * read_length
    waveform = I2CWaveformReconstructor().reconstruct_transfer_spec_waveform(spec)
    labels = [annotation.label for annotation in waveform.annotations]
    assert "START" in labels
    assert "Sr" in labels
    assert "STOP" in labels
    assert labels.count("Unknown") == read_length
    assert labels.count("NACK") == 1
    assert all("0x00" not in annotation.label for annotation in waveform.annotations)
    assert waveform.source_transition_count >= waveform.rendered_transition_count
    assert all(
        not (
            waveform.scl[index] != waveform.scl[index - 1]
            and waveform.sda[index] != waveform.sda[index - 1]
        )
        for index in range(1, len(waveform.time_us))
    )


@pytest.mark.parametrize(
    ("endianness", "expected"),
    [(Endianness.BIG, (0x12, 0x34)), (Endianness.LITTLE, (0x34, 0x12))],
)
def test_16_bit_register_endianness_is_canonical(endianness: Endianness, expected: tuple[int, int]) -> None:
    spec = I2CTransferSpec(
        address_7bit=0x50,
        operation="register_write",
        register=0x1234,
        register_width=16,
        endianness=endianness,
        data_bytes=[0xAA],
    )
    assert spec.register_bytes == expected
    assert spec.canonical_bytes == expected + (0xAA,)


def test_direct_modes_have_no_register_phase() -> None:
    write = I2CTransferSpec(address=0x48, operation="direct_write", data_bytes=[0x11, 0x22])
    read = I2CTransferSpec(address=0x48, operation="direct_read", read_length=3)
    assert write.register_bytes == ()
    assert write.segments[0].bytes == (0x11, 0x22)
    assert read.register_bytes == ()
    assert len(read.segments) == 1
    assert len(read.segments[0].bytes) == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"address_7bit": 0x07, "operation": "direct_read", "read_length": 1},
        {"address_7bit": 0x78, "operation": "direct_read", "read_length": 1},
        {"address_7bit": 0x50, "operation": "direct_read", "read_length": 0},
        {"address_7bit": 0x50, "operation": "register_write", "register": 0x100, "data_bytes": [0x00]},
        {"address_7bit": 0x50, "operation": "direct_write", "data_bytes": []},
    ],
)
def test_transfer_spec_rejects_invalid_ranges(
    kwargs: dict[str, Any],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        I2CTransferSpec(**kwargs)  # type: ignore[arg-type]


def test_transfer_spec_rejects_payload_and_waveform_resource_limits() -> None:
    with pytest.raises(ResourceLimitError, match="payload"):
        I2CTransferSpec(
            address_7bit=0x50,
            operation="register_write",
            register=0x10,
            data_bytes=[0xAA, 0xBB],
            max_payload_bytes=2,
        )
    with pytest.raises(ResourceLimitError, match="waveform"):
        I2CTransferSpec(
            address_7bit=0x50,
            operation="direct_read",
            read_length=4,
            max_waveform_points=1,
        )


def test_expected_read_data_is_visual_assumption_only() -> None:
    spec = I2CTransferSpec(
        address_7bit=0x50,
        operation="direct_read",
        read_length=2,
        expected_read_data=[0x12, 0x34],
    )
    waveform = I2CWaveformReconstructor().reconstruct_transfer_spec_waveform(spec)
    assert [a.label for a in waveform.annotations].count("Expected 0x12") == 1
    assert [a.label for a in waveform.annotations].count("Expected 0x34") == 1
    snippet = I2CDriverCodeGenerator.generate_from_spec(spec)["Arduino / Wire.h"]
    assert "0x12" not in snippet
    assert "0x34" not in snippet


def test_little_endian_stm32_combined_read_preserves_repeated_start_contract() -> None:
    spec = I2CTransferSpec(
        address_7bit=0x50,
        operation="combined_register_read",
        register=0x1234,
        register_width=16,
        endianness="little",
        read_length=2,
    )

    snippet = I2CDriverCodeGenerator.generate_from_spec(spec)["STM32 HAL C Driver"]

    assert "{ 0x34, 0x12 }" in snippet
    assert "HAL_I2C_Master_Seq_Transmit_IT" in snippet
    assert "HAL_I2C_Master_Seq_Receive_IT" in snippet
    assert "void HAL_I2C_MasterTxCpltCallback" in snippet
    assert "// HAL_I2C_Master_Seq_Receive_IT" not in snippet
    assert "I2C_FIRST_FRAME" in snippet
    assert "I2C_LAST_FRAME" in snippet
    assert "HAL_I2C_Master_Transmit(" not in snippet


def test_legacy_read_data_bytes_only_implies_receive_length() -> None:
    snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x50,
        reg_offset=0x10,
        is_read=True,
        data_bytes=[0x00, 0x00, 0x00],
    )

    assert "rx_buf[3]" in snippets["Linux Userspace (i2c-dev)"]


def test_operation_argument_is_sufficient_for_new_read_callers() -> None:
    snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x50,
        operation="direct_read",
        read_length=4,
    )

    assert "i2ctransfer 1 r4@0x50" in snippets["OpenBMC / Linux CLI (i2c-tools)"]


def test_combined_read_operation_argument_is_sufficient_without_is_read() -> None:
    snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x50,
        operation="combined_register_read",
        reg_offset=0x10,
        read_length=4,
    )

    assert "i2ctransfer 1 w1@0x50 0x10 r4" in snippets[
        "OpenBMC / Linux CLI (i2c-tools)"
    ]
    assert "HAL_I2C_Mem_Read" in snippets["STM32 HAL C Driver"]


def test_linux_direct_read_checks_slave_selection_and_arduino_short_read() -> None:
    snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x48, reg_offset=None, is_read=True, read_length=4
    )
    linux = snippets["Linux Userspace (i2c-dev)"]
    arduino = snippets["Arduino / Wire.h"]
    assert 'if (ioctl(file, I2C_SLAVE, 0x48) < 0)' in linux
    assert "Handle short read" in arduino


def test_stm32_fractional_timeout_rounds_up_to_integer_milliseconds() -> None:
    spec = I2CTransferSpec(
        address_7bit=0x50,
        operation="direct_read",
        read_length=1,
        timeout_ms=25.001,
    )
    snippet = I2CDriverCodeGenerator.generate_from_spec(spec)["STM32 HAL C Driver"]
    assert "ceil(25.001) = 26" in snippet
    assert "rx_buf, 1, 26);" in snippet
