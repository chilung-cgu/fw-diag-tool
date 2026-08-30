# GUI 現代化重構 + 新功能 Design Spec

> **Date:** 2026-08-30
> **Status:** Approved
> **Scope:** Refactor the monolithic `app.py` into modular page files, adopt Streamlit modern APIs, unify input patterns, add custom YAML register upload, and strengthen test coverage for low-coverage modules.

## 1. Problem Statement

`src/fw_diag_tool/gui/app.py` is a 2,236-line monolith that renders all 12 GUI pages through a single `st.sidebar.radio` + `if/elif` chain. This makes individual pages hard to develop, test, and maintain independently. Additionally:

- Streamlit 1.62.0 supports `st.navigation`/`st.Page` (since 1.36), `st.fragment` (since 1.37), and `st.dialog` (since 1.37), none of which are used.
- Only 2 of 12 pages have been extracted to `gui/pages/` (`i2c_page.py`, `i2c_builder.py`).
- UART, MCTP, PCIe, and DTS pages only accept `st.text_area` input — no file upload.
- Analysis caching uses `show_spinner=False` with no explicit spinner, causing silent loading.
- The register decoder only supports 2 built-in YAML definitions with no custom upload.
- Several modules have coverage below 80%: `waveform_diff_report.py` (57.6%), `uart/symbols.py` (67.4%), `emulator/lm75.py` (69.1%), `emulator/spi_flash.py` (72.0%).

## 2. Architecture

### 2.1 Page Module Structure

```
src/fw_diag_tool/gui/
├── app.py                    # Slim router (~150 lines): st.navigation + shared config
├── shared.py                 # Shared helpers: localization dicts, guide expander, cached analyzers
├── uploads.py                # (existing) File upload utilities
├── session_io.py             # (existing) Session serialization
├── pages/
│   ├── __init__.py
│   ├── i2c_page.py           # (existing) I2C analysis controller
│   ├── i2c_builder.py        # (existing) I2C packet builder logic
│   ├── i2c_diagnosis.py      # NEW: Full I2C diagnosis page UI (extracted from app.py:564-1144)
│   ├── i2c_builder_ui.py     # NEW: I2C builder page UI (extracted from app.py:1145-1447)
│   ├── waveform_diff_ui.py   # NEW: Waveform Diff page UI (extracted from app.py:1448-1583)
│   ├── uart_ui.py            # NEW: UART Crash Dump page UI (extracted from app.py:1584-1642)
│   ├── mctp_ui.py            # NEW: MCTP/IPMB page UI (extracted from app.py:1643-1711)
│   ├── dts_ui.py             # NEW: Device Tree page UI (extracted from app.py:1712-1764)
│   ├── pcie_ui.py            # NEW: PCIe AER page UI (extracted from app.py:1765-1908)
│   ├── spi_ui.py             # NEW: SPI Flash page UI (extracted from app.py:1909-1987)
│   ├── register_ui.py        # NEW: Register Decoder page UI (extracted from app.py:1988-2054)
│   ├── codegen_ui.py         # NEW: C Header Codegen page UI (extracted from app.py:2055-2086)
│   ├── fault_arena_ui.py     # NEW: Fault Arena page UI (extracted from app.py:2087-2145)
│   └── sop_ui.py             # NEW: SOP Guide page UI (extracted from app.py:2146-2236)
```

### 2.2 Navigation Model

Replace the current `st.sidebar.radio` with `st.navigation` using `st.Page` objects grouped into sections:

```python
pages = {
    "協定分析與波形": [
        st.Page(i2c_diagnosis.render, title="I2C / PMBus 診斷與波形檢視", icon="📊"),
        st.Page(i2c_builder_ui.render, title="I2C 封包模擬器與驅動產生", icon="🎨"),
        st.Page(waveform_diff_ui.render, title="雙波形對比檢視", icon="⚖️"),
    ],
    "系統協定診斷": [
        st.Page(uart_ui.render, title="UART 崩潰轉儲與 HardFault 分析", icon="📟"),
        st.Page(mctp_ui.render, title="MCTP／IPMB 伺服器管理協定解析", icon="🌐"),
        st.Page(pcie_ui.render, title="PCIe 設定空間與 AER 診斷", icon="🚀"),
        st.Page(spi_ui.render, title="SPI Flash 協定診斷", icon="⚡"),
    ],
    "產生器與硬體工具": [
        st.Page(dts_ui.render, title="Device Tree 產生器", icon="🌲"),
        st.Page(register_ui.render, title="暫存器 Bitfield 解碼器", icon="🎛"),
        st.Page(codegen_ui.render, title="C Register 巨集產生器", icon="🛠"),
    ],
    "實驗室與學習": [
        st.Page(fault_arena_ui.render, title="Firmware 實戰除錯實驗室", icon="🏆"),
        st.Page(sop_ui.render, title="韌體除錯指南與 SOP", icon="📚"),
    ],
}
nav = st.navigation(pages)
nav.run()
```

### 2.3 Shared Module (`shared.py`)

Extracted from app.py lines 100-530:
- `GUI_ANALYSIS_LIMITS`, `MAX_PACKET_HEX_CHARS`
- `_reset_i2c_session_state()`
- `analyze_i2c_input()` and `analyze_spi_input()` (cached)
- All localization dicts (`_REGISTER_MEANING_ZH`, `_REGISTER_DESCRIPTION_ZH`, `_PCIE_INPUT_ERROR_ZH`, `_FAULT_ARENA_CASES_ZH`)
- All localization helper functions (`_localize_register_meaning`, `_localize_register_description`, `_localize_pcie_input_error`, `_localize_gui_error`, `_localize_mctp_error`)
- `render_guide_expander()`

### 2.4 New Features

**2.4.1 File Upload for Text-Only Pages**

Add `st.file_uploader` alongside existing `st.text_area` for UART, MCTP, PCIe, and DTS pages. Pattern:
```python
uploaded = st.file_uploader("上傳檔案", type=["txt", "log", "hex", "dmesg"])
if uploaded:
    raw = decode_uploaded_text(uploaded)
else:
    raw = st.text_area(...)
```

**2.4.2 Explicit Loading Spinners**

Replace `show_spinner=False` with descriptive spinners:
```python
@st.cache_data(show_spinner="正在解析 I2C 協定並計算時序統計...")
```

**2.4.3 Custom Register YAML Upload**

Add a third option to the register decoder selectbox: "上傳自訂暫存器定義 YAML" which triggers a `st.file_uploader` for YAML files, validated through `RegisterMapCatalog.load_from_yaml()`.

## 3. Testing Strategy

- Each new page module gets an import/syntax test in `tests/test_gui_page_modules.py`
- The existing `test_gui_packaging.py` AppTest is updated to verify the new navigation structure
- Low-coverage modules get targeted boundary tests:
  - `tests/test_waveform_diff_report.py`: cover all 7 regex patterns + edge cases
  - `tests/test_uart.py`: add `SymbolTable.from_system_map` and symbolication tests
  - `tests/test_emulator.py`: add LM75 CONFIG/THYST/TOS and SPI `sector_erase`/`write_disable` tests

## 4. Success Criteria

- `app.py` reduced from 2,236 lines to < 200 lines
- All 12 pages render identically (verified by existing tests + new module tests)
- `pytest` 590+ tests pass, `ruff` clean, `mypy` clean, `mkdocs build --strict` clean
- Overall coverage remains >= 85%, target modules reach >= 80%
- UART, MCTP, PCIe, DTS pages accept both file upload and text area input
- Register decoder accepts custom YAML upload
- Loading spinners visible during analysis

## 5. Non-Goals

- No new protocol support (QSPI, PLDM deep decode, etc.) in this iteration
- No Mermaid diagrams or documentation restructuring (separate effort)
- No `st.fragment` for table-waveform linking (deferred — requires deeper Streamlit interaction model exploration)

