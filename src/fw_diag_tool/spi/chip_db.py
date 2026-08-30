"""Common SPI NOR flash chip identification database."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SPIFlashChip:
    """SPI flash geometry and electrical specifications."""

    manufacturer: str
    part_number: str
    jedec_id: tuple[int, int, int]
    capacity_bytes: int
    page_size: int
    sector_size: int
    voltage_min: float
    voltage_max: float
    max_freq_mhz: int


def _chip(
    manufacturer: str,
    part_number: str,
    jedec_id: tuple[int, int, int],
    capacity_mbit: int,
    *,
    voltage_min: float = 2.7,
    voltage_max: float = 3.6,
    max_freq_mhz: int = 104,
    page_size: int = 256,
    sector_size: int = 4096,
) -> SPIFlashChip:
    return SPIFlashChip(
        manufacturer=manufacturer,
        part_number=part_number,
        jedec_id=jedec_id,
        capacity_bytes=capacity_mbit * 1024 * 1024 // 8,
        page_size=page_size,
        sector_size=sector_size,
        voltage_min=voltage_min,
        voltage_max=voltage_max,
        max_freq_mhz=max_freq_mhz,
    )


SPI_FLASH_DB: list[SPIFlashChip] = [
    _chip("Winbond", "W25Q16JV", (0xEF, 0x40, 0x15), 16, max_freq_mhz=133),
    _chip("Winbond", "W25Q32JV", (0xEF, 0x40, 0x16), 32, max_freq_mhz=133),
    _chip("Winbond", "W25Q64JV", (0xEF, 0x40, 0x17), 64, max_freq_mhz=133),
    _chip("Winbond", "W25Q128JV", (0xEF, 0x40, 0x18), 128, max_freq_mhz=133),
    _chip("Winbond", "W25Q256JV", (0xEF, 0x40, 0x19), 256, max_freq_mhz=133),
    _chip("Winbond", "W25Q512JV", (0xEF, 0x40, 0x20), 512, max_freq_mhz=166),
    _chip("Winbond", "W25Q80JV", (0xEF, 0x40, 0x14), 8, max_freq_mhz=133),
    _chip("Winbond", "W25Q01JV", (0xEF, 0x40, 0x21), 1024, max_freq_mhz=166),
    _chip("Macronix", "MX25L1606E", (0xC2, 0x20, 0x15), 16, max_freq_mhz=86),
    _chip("Macronix", "MX25L3233F", (0xC2, 0x20, 0x16), 32, max_freq_mhz=104),
    _chip("Macronix", "MX25L6433F", (0xC2, 0x20, 0x17), 64, max_freq_mhz=104),
    _chip("Macronix", "MX25L12835F", (0xC2, 0x20, 0x18), 128, max_freq_mhz=104),
    _chip("Macronix", "MX25L25645G", (0xC2, 0x20, 0x19), 256, max_freq_mhz=133),
    _chip("Macronix", "MX25L51245G", (0xC2, 0x20, 0x20), 512, max_freq_mhz=133),
    _chip("Macronix", "MX25L12873F", (0xC2, 0x20, 0x18), 128, max_freq_mhz=133),
    _chip("Micron", "N25Q032A", (0x20, 0xBA, 0x16), 32),
    _chip("Micron", "N25Q064A", (0x20, 0xBA, 0x17), 64),
    _chip("Micron", "N25Q128A", (0x20, 0xBA, 0x18), 128),
    _chip("Micron", "N25Q256A", (0x20, 0xBA, 0x19), 256),
    _chip(
        "Micron",
        "MT25QU512A",
        (0x20, 0xBB, 0x20),
        512,
        voltage_min=1.7,
        voltage_max=2.0,
        max_freq_mhz=200,
    ),
    _chip("Micron", "N25Q512A", (0x20, 0xBA, 0x20), 512, max_freq_mhz=108),
    _chip("ISSI", "IS25LP016D", (0x9D, 0x60, 0x15), 16, voltage_min=2.3),
    _chip("ISSI", "IS25LP032D", (0x9D, 0x60, 0x16), 32, voltage_min=2.3),
    _chip("ISSI", "IS25LP064D", (0x9D, 0x60, 0x17), 64, voltage_min=2.3),
    _chip("ISSI", "IS25LP128F", (0x9D, 0x60, 0x18), 128, voltage_min=2.3),
    _chip("ISSI", "IS25LP256D", (0x9D, 0x60, 0x19), 256, voltage_min=2.3),
    _chip("GigaDevice", "GD25Q16C", (0xC8, 0x40, 0x15), 16),
    _chip("GigaDevice", "GD25Q32C", (0xC8, 0x40, 0x16), 32),
    _chip("GigaDevice", "GD25Q64C", (0xC8, 0x40, 0x17), 64),
    _chip("GigaDevice", "GD25Q128E", (0xC8, 0x40, 0x18), 128),
    _chip("GigaDevice", "GD25Q256E", (0xC8, 0x60, 0x19), 256),
    _chip("GigaDevice", "GD25Q80C", (0xC8, 0x40, 0x14), 8),
    _chip("GigaDevice", "GD25Q512E", (0xC8, 0x60, 0x20), 512),
    _chip("Cypress/Infineon", "S25FL128S", (0x01, 0x20, 0x18), 128),
    _chip("Cypress/Infineon", "S25FL256S", (0x01, 0x02, 0x19), 256),
    _chip("Cypress/Infineon", "S25FL512S", (0x01, 0x02, 0x20), 512),
    _chip("Microchip/SST", "SST25VF016B", (0xBF, 0x25, 0x41), 16, max_freq_mhz=20),
    _chip("Microchip/SST", "SST25VF032B", (0xBF, 0x25, 0x4A), 32, max_freq_mhz=20),
    _chip("Microchip/SST", "SST26VF032B", (0xBF, 0x26, 0x42), 32, max_freq_mhz=104),
]


def lookup_by_jedec(mfr_id: int, dev_id: int) -> SPIFlashChip | None:
    """Return the first chip matching manufacturer and either device byte."""
    for chip in SPI_FLASH_DB:
        if chip.jedec_id[0] == mfr_id and dev_id in chip.jedec_id[1:]:
            return chip
    return None


def lookup_by_part_number(query: str) -> list[SPIFlashChip]:
    """Return chips whose part number contains ``query`` case-insensitively."""
    normalized = query.casefold()
    return [chip for chip in SPI_FLASH_DB if normalized in chip.part_number.casefold()]


def list_manufacturers() -> list[str]:
    """Return unique manufacturer names in lexical order."""
    return sorted({chip.manufacturer for chip in SPI_FLASH_DB})


__all__ = [
    "SPI_FLASH_DB",
    "SPIFlashChip",
    "list_manufacturers",
    "lookup_by_jedec",
    "lookup_by_part_number",
]
