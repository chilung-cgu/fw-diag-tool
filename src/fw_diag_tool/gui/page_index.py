"""Global search, breadcrumb navigation, and page index definitions."""

from __future__ import annotations

import streamlit as st

__all__ = [
    "PAGE_INDEX",
    "render_breadcrumb",
    "render_global_search",
    "render_keyboard_shortcuts",
]

# ---------------------------------------------------------------------------
# Page index for global search and navigation
# ---------------------------------------------------------------------------

PAGE_INDEX: list[dict[str, str]] = [
    {
        "title": "I2C / PMBus Diagnosis",
        "url": "i2c-diagnosis",
        "category": "Protocol Analysis",
        "keywords": "i2c pmbus waveform decode csv saleae",
    },
    {
        "title": "I2C Packet Builder",
        "url": "i2c-builder",
        "category": "Protocol Analysis",
        "keywords": "i2c packet builder driver generate simulate",
    },
    {
        "title": "Waveform Diff",
        "url": "waveform-diff",
        "category": "Protocol Analysis",
        "keywords": "waveform diff compare golden failing before after",
    },
    {
        "title": "Cross-Protocol Correlation",
        "url": "correlation",
        "category": "Advanced Analysis",
        "keywords": "correlation timeline cross protocol i2c spi uart cluster",
    },
    {
        "title": "Multi-Session Trend Analysis",
        "url": "session-analytics",
        "category": "Advanced Analysis",
        "keywords": "session trend analytics multi compare progress",
    },
    {
        "title": "Protocol A/B Diff",
        "url": "protocol-diff",
        "category": "Protocol Analysis",
        "keywords": "protocol diff compare baseline candidate i2c spi uart before after",
    },
    {
        "title": "Session A/B Compare",
        "url": "session-compare",
        "category": "Advanced Analysis",
        "keywords": "session compare a/b baseline candidate anomaly delta verdict",
    },
    {
        "title": "Dashboard",
        "url": "dashboard",
        "category": "Overview",
        "keywords": "dashboard overview summary status quick start",
    },
    {
        "title": "UART Crash Dump",
        "url": "uart",
        "category": "System Protocol",
        "keywords": "uart crash kernel panic hardfault arm cortex dump",
    },
    {
        "title": "MCTP / IPMB Protocol",
        "url": "mctp",
        "category": "System Protocol",
        "keywords": "mctp ipmb pldm spdm server management bmc",
    },
    {
        "title": "PCIe Config & AER",
        "url": "pcie",
        "category": "System Protocol",
        "keywords": "pcie config aer lspci link degrade tlp error",
    },
    {
        "title": "SPI Flash Protocol",
        "url": "spi",
        "category": "System Protocol",
        "keywords": "spi flash jedec w25q128 wren erase program opcode",
    },
    {
        "title": "Board Profile Editor",
        "url": "board-profile",
        "category": "Tools",
        "keywords": "board profile topology yaml json i2c mux pca9548 bus device",
    },
    {
        "title": "Device Tree Generator",
        "url": "dts",
        "category": "Tools",
        "keywords": "device tree dts dtsi linux openbmc bsp generate",
    },
    {
        "title": "Register Decoder",
        "url": "register",
        "category": "Tools",
        "keywords": "register bitfield decode pmbus pcie hex raw",
    },
    {
        "title": "C Register Macro Gen",
        "url": "codegen",
        "category": "Tools",
        "keywords": "codegen c header macro register rmw misra yaml",
    },
    {
        "title": "Interactive Tutorial",
        "url": "tutorial",
        "category": "Labs",
        "keywords": "tutorial learn beginner guide step interactive walkthrough",
    },
    {
        "title": "Fault Arena",
        "url": "fault-arena",
        "category": "Labs",
        "keywords": "fault arena debug practice exercise scenario firmware lab",
    },
    {
        "title": "Debug SOP Guide",
        "url": "sop",
        "category": "Labs",
        "keywords": "sop debug guide mental model l1 l7 systematic",
    },
    {
        "title": "I2C Chip Database",
        "url": "chip-db",
        "category": "Labs",
        "keywords": "chip database i2c address lookup eeprom sensor pmbus",
    },
    {
        "title": "Virtual Device Emulator",
        "url": "emulator",
        "category": "Labs",
        "keywords": "emulator virtual device eeprom lm75 ソ ina219 spi flash mux".replace("ソ ", ""),
    },
    {
        "title": "Protocol Fuzz Lab",
        "url": "fuzz-lab",
        "category": "Labs",
        "keywords": "fuzz fuzzing test stress parser edge case random",
    },
    {
        "title": "Batch Analysis",
        "url": "batch-analysis",
        "category": "Advanced Analysis",
        "keywords": "batch parallel multi file directory analysis zip report",
    },
    {
        "title": "Settings & Preferences",
        "url": "settings",
        "category": "Tools",
        "keywords": "settings preferences config timeout language theme spi page size",
    },
]


def render_global_search() -> None:
    """Render a global search box in the sidebar."""
    query = st.sidebar.text_input(
        "Search pages",
        placeholder="e.g. I2C, SPI, crash...",
        key="global_search_query",
    )
    if not query:
        return
    query_lower = query.lower()
    results = [
        p
        for p in PAGE_INDEX
        if query_lower in p["title"].lower()
        or query_lower in p["keywords"]
        or query_lower in p["category"].lower()
    ]
    if results:
        for p in results:
            st.sidebar.markdown(f"- [{p['title']}](/{p['url']})")
    else:
        st.sidebar.caption("No matching pages found.")


def render_breadcrumb(category: str, page_title: str) -> None:
    """Render a breadcrumb navigation bar at the top of a page."""
    st.markdown(
        f"<small style='color:#94a3b8'>"
        f"<a href='/dashboard' style='color:#94a3b8;text-decoration:none'>Home</a>"
        f" &rsaquo; {category}"
        f" &rsaquo; <b>{page_title}</b>"
        f"</small>",
        unsafe_allow_html=True,
    )


def render_keyboard_shortcuts() -> None:
    """Render a collapsible keyboard shortcuts panel in the sidebar."""
    with st.sidebar.expander("Keyboard Shortcuts"):
        st.markdown(
            "- **Ctrl+K** / **Cmd+K** — Focus search\n"
            "- **Ctrl+/** — Toggle sidebar\n"
            "- **R** — Rerun current page"
        )
