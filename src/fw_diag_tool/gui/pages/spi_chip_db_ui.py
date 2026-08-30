"""SPI NOR flash chip database browser."""

from __future__ import annotations

import streamlit as st

from fw_diag_tool.gui.shared import render_page_footer
from fw_diag_tool.i18n import t
from fw_diag_tool.spi import (
    SPI_FLASH_DB,
    SPIFlashChip,
    list_manufacturers,
    lookup_by_jedec,
)


def _format_capacity(capacity_bytes: int) -> str:
    if capacity_bytes >= 1024 * 1024:
        return f"{capacity_bytes / (1024 * 1024):g} MiB"
    return f"{capacity_bytes / 1024:g} KiB"


def _chip_row(chip: SPIFlashChip) -> dict[str, str | int]:
    return {
        "製造商 / Manufacturer": chip.manufacturer,
        "料號 / Part number": chip.part_number,
        "JEDEC ID": " ".join(f"0x{byte:02X}" for byte in chip.jedec_id),
        "容量 / Capacity": _format_capacity(chip.capacity_bytes),
        "Page 大小 / Page size": f"{chip.page_size} B",
        "Sector 大小 / Sector size": f"{chip.sector_size} B",
        "電壓 / Voltage": f"{chip.voltage_min:g}–{chip.voltage_max:g} V",
        "最高頻率 / Max frequency": f"{chip.max_freq_mhz} MHz",
    }


def page() -> None:
    """Render the SPI flash chip database browser."""
    st.header(t("title_spi_chip_db", domain="gui"))
    st.caption(t("spi_chip_db_caption", domain="gui"))

    manufacturers = [t("spi_chip_db_all_manufacturers", domain="gui"), *list_manufacturers()]
    selected_manufacturer = st.selectbox(
        t("spi_chip_db_manufacturer", domain="gui"), manufacturers, key="spi_chip_db_manufacturer"
    )
    query = st.text_input(
        t("spi_chip_db_search", domain="gui"), key="spi_chip_db_search", placeholder="W25Q128"
    )

    filtered = [
        chip
        for chip in SPI_FLASH_DB
        if (
            selected_manufacturer == manufacturers[0]
            or chip.manufacturer == selected_manufacturer
        )
        and query.casefold() in chip.part_number.casefold()
    ]
    st.subheader(t("spi_chip_db_table_heading", domain="gui"))
    st.dataframe([_chip_row(chip) for chip in filtered], hide_index=True, use_container_width=True)

    st.subheader(t("spi_chip_db_jedec_heading", domain="gui"))
    mfr_col, type_col, capacity_col = st.columns(3)
    mfr_id = mfr_col.text_input(
        t("spi_chip_db_mfr_byte", domain="gui"), value="EF", max_chars=2, key="spi_jedec_mfr"
    )
    mem_type = type_col.text_input(
        t("spi_chip_db_mem_type_byte", domain="gui"), value="40", max_chars=2, key="spi_jedec_type"
    )
    capacity = capacity_col.text_input(
        t("spi_chip_db_capacity_byte", domain="gui"), value="18", max_chars=2, key="spi_jedec_capacity"
    )

    if st.button(t("spi_chip_db_lookup_button", domain="gui"), key="spi_jedec_lookup"):
        try:
            ids = [int(value.strip().removeprefix("0x"), 16) for value in (mfr_id, mem_type, capacity)]
            if any(value < 0 or value > 0xFF for value in ids):
                raise ValueError
        except ValueError:
            st.error(t("spi_chip_db_invalid_hex", domain="gui"))
        else:
            match = next(
                (chip for chip in SPI_FLASH_DB if chip.jedec_id == tuple(ids)),
                None,
            )
            if match is None:
                match = lookup_by_jedec(ids[0], ids[1])
            if match is None:
                match = lookup_by_jedec(ids[0], ids[2])
            if match is None:
                st.warning(t("spi_chip_db_not_found", domain="gui"))
            else:
                st.success(t("spi_chip_db_match_heading", domain="gui"))
                st.dataframe([_chip_row(match)], hide_index=True, use_container_width=True)

    render_page_footer()


def render() -> None:
    """Compatibility entry point used by page-module tests and callers."""
    page()


__all__ = ["page", "render"]
