from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from fw_diag_tool.spi import (
    SPI_FLASH_DB,
    SPIFlashChip,
    list_manufacturers,
    lookup_by_jedec,
    lookup_by_part_number,
)


def test_spi_flash_chip_is_frozen_dataclass() -> None:
    assert is_dataclass(SPIFlashChip)
    assert [field.name for field in fields(SPIFlashChip)] == [
        "manufacturer",
        "part_number",
        "jedec_id",
        "capacity_bytes",
        "page_size",
        "sector_size",
        "voltage_min",
        "voltage_max",
        "max_freq_mhz",
    ]

    chip = SPI_FLASH_DB[0]
    with pytest.raises(FrozenInstanceError):
        chip.part_number = "changed"  # type: ignore[misc]


def test_database_contains_required_common_chips() -> None:
    parts = {chip.part_number for chip in SPI_FLASH_DB}
    required = {
        "W25Q16JV",
        "W25Q32JV",
        "W25Q64JV",
        "W25Q128JV",
        "W25Q256JV",
        "W25Q512JV",
        "MX25L1606E",
        "MX25L3233F",
        "MX25L6433F",
        "MX25L12835F",
        "MX25L25645G",
        "N25Q032A",
        "N25Q064A",
        "N25Q128A",
        "N25Q256A",
        "MT25QU512A",
        "IS25LP016D",
        "IS25LP032D",
        "IS25LP064D",
        "IS25LP128F",
        "GD25Q16C",
        "GD25Q32C",
        "GD25Q64C",
        "GD25Q128E",
        "GD25Q256E",
        "S25FL128S",
        "S25FL256S",
        "SST25VF016B",
        "SST25VF032B",
    }
    assert required <= parts
    assert len(SPI_FLASH_DB) >= len(required)


@pytest.mark.parametrize(
    ("mfr", "dev", "part"),
    [
        (0xEF, 0x15, "W25Q16JV"),
        (0xEF, 0x18, "W25Q128JV"),
        (0xC2, 0x17, "MX25L6433F"),
        (0x20, 0xBA, "N25Q032A"),
        (0x9D, 0x18, "IS25LP128F"),
        (0xC8, 0x19, "GD25Q256E"),
        (0x01, 0x02, "S25FL256S"),
        (0xBF, 0x4A, "SST25VF032B"),
    ],
)
def test_lookup_by_jedec_matches_memory_or_capacity_byte(mfr: int, dev: int, part: str) -> None:
    matches = lookup_by_jedec(mfr, dev)
    assert matches is not None
    assert matches.part_number == part


def test_lookup_by_jedec_memory_type_returns_first_matching_chip() -> None:
    match = lookup_by_jedec(0xEF, 0x40)
    assert match is not None
    assert match.part_number == "W25Q16JV"


def test_lookup_by_jedec_unknown_manufacturer_returns_none() -> None:
    assert lookup_by_jedec(0x00, 0x15) is None


def test_lookup_by_jedec_unknown_device_returns_none() -> None:
    assert lookup_by_jedec(0xEF, 0x99) is None


def test_lookup_by_jedec_accepts_integer_values_without_hex_prefix() -> None:
    assert lookup_by_jedec(239, 24) == lookup_by_jedec(0xEF, 0x18)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("w25q128", ["W25Q128JV"]),
        ("mx25l", ["MX25L1606E", "MX25L3233F", "MX25L6433F", "MX25L12835F", "MX25L25645G"]),
        ("N25Q", ["N25Q032A", "N25Q064A", "N25Q128A", "N25Q256A"]),
    ],
)
def test_lookup_by_part_number_is_case_insensitive_substring(
    query: str, expected: list[str]
) -> None:
    found = [chip.part_number for chip in lookup_by_part_number(query)]
    assert found[: len(expected)] == expected


def test_lookup_by_part_number_empty_query_returns_all_chips() -> None:
    assert lookup_by_part_number("") == SPI_FLASH_DB


def test_lookup_by_part_number_unknown_query_returns_empty_list() -> None:
    assert lookup_by_part_number("does-not-exist") == []


def test_list_manufacturers_is_sorted_and_unique() -> None:
    manufacturers = list_manufacturers()
    assert manufacturers == sorted(set(manufacturers))
    assert manufacturers == [
        "Cypress/Infineon",
        "GigaDevice",
        "ISSI",
        "Macronix",
        "Microchip/SST",
        "Micron",
        "Winbond",
    ]


def test_chip_specs_have_valid_shapes_and_ranges() -> None:
    for chip in SPI_FLASH_DB:
        assert len(chip.jedec_id) == 3
        assert all(0 <= byte <= 0xFF for byte in chip.jedec_id)
        assert chip.capacity_bytes > 0
        assert chip.page_size > 0
        assert chip.sector_size >= chip.page_size
        assert 0 < chip.voltage_min <= chip.voltage_max
        assert chip.max_freq_mhz > 0


def test_winbond_w25q128_specs() -> None:
    chip = lookup_by_part_number("W25Q128JV")[0]
    assert chip.capacity_bytes == 16 * 1024 * 1024
    assert chip.page_size == 256
    assert chip.sector_size == 4 * 1024
    assert chip.voltage_min == 2.7
    assert chip.voltage_max == 3.6


def test_lookup_result_is_spi_flash_chip() -> None:
    result = lookup_by_jedec(0xEF, 0x18)
    assert isinstance(result, SPIFlashChip)
