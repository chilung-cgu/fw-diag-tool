# GUI 現代化重構 + 新功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the monolithic `app.py` (2,236 lines) into 12 independent page modules with Streamlit `st.navigation` routing, unify input methods, add custom YAML register upload, add explicit loading spinners, and strengthen test coverage for low-coverage modules.

**Architecture:** Extract shared helpers into `gui/shared.py`, extract each page's UI into `gui/pages/*_ui.py`, then replace the `st.sidebar.radio` + `if/elif` dispatch with `st.navigation`/`st.Page` grouped into 4 sidebar sections. Add file upload to text-only pages and custom YAML support to the register decoder.

**Tech Stack:** Python 3.10+, Streamlit 1.62.0 (`st.navigation`, `st.Page`), Pydantic V2, Plotly, pytest, ruff, mypy

**Spec:** `docs/superpowers/specs/2026-08-30-gui-modernization-design.md`

## Global Constraints

- Python >= 3.10 (no `tomllib`, no 3.11+ features)
- `uv run` for all project commands
- All existing 590 tests must keep passing after every task
- `ruff check`, `mypy src/fw_diag_tool/`, `mkdocs build --strict` must stay clean
- Branch coverage must remain >= 85%
- zh-TW localization for all user-facing strings; keep existing English protocol tokens intact
- Zero-LaTeX policy: no `$...$` or LaTeX macros in any string
- Git identity from existing `~/.gitconfig` — never override

---

### Task 1: Extract shared helpers into `gui/shared.py`

**Files:**
- Create: `src/fw_diag_tool/gui/shared.py`
- Modify: `src/fw_diag_tool/gui/app.py` (lines 100-530 extracted)
- Test: `tests/test_gui_shared.py`

**Interfaces:**
- Consumes: `fw_diag_tool.gui.pages.i2c_page.analyze_i2c`, `fw_diag_tool.gui.uploads`, `fw_diag_tool.i2c.localization`, `fw_diag_tool.board_profile`, `fw_diag_tool.spi.engine.SPIDiagnosticEngine`, `fw_diag_tool.analyzers.register_mapper.RegisterMapCatalog`
- Produces: `GUI_ANALYSIS_LIMITS`, `MAX_PACKET_HEX_CHARS`, `DEFAULT_I2C_TIMEOUT_MS`, `_reset_i2c_session_state()`, `analyze_i2c_input(csv_content, input_mode, smbus_timeout_ms, board_profile_yaml) -> tuple[Any, Any]`, `analyze_spi_input(csv_content, max_page_size) -> Any`, `render_guide_expander(chapter_file, label)`, all `_localize_*` functions, all `_*_ZH` dicts, `_FAULT_ARENA_CASES_ZH` list

- [ ] **Step 1: Create `gui/shared.py` with all shared code**

Create `src/fw_diag_tool/gui/shared.py` containing:
1. All imports needed by the shared functions
2. Constants: `GUI_ANALYSIS_LIMITS`, `MAX_PACKET_HEX_CHARS`, `DEFAULT_I2C_TIMEOUT_MS` (currently defined as `25.0` on line 103 of app.py)
3. `_reset_i2c_session_state()` function (app.py lines 106-117)
4. `analyze_i2c_input()` cached function (app.py lines 119-135)
5. `analyze_spi_input()` cached function (app.py lines 137-139)
6. All localization dicts: `_REGISTER_MEANING_ZH`, `_REGISTER_DESCRIPTION_ZH`, `_PCIE_INPUT_ERROR_ZH`, `_FAULT_ARENA_CASES_ZH`
7. All localization helpers: `_localize_register_meaning`, `_localize_register_description`, `_localize_pcie_input_error`, `_localize_gui_error`, `_localize_mctp_error`
8. `render_guide_expander()` function (app.py lines 532-540)

- [ ] **Step 2: Write import test for shared module**

Create `tests/test_gui_shared.py`:
```python
from fw_diag_tool.gui.shared import (
    GUI_ANALYSIS_LIMITS,
    MAX_PACKET_HEX_CHARS,
    analyze_i2c_input,
    analyze_spi_input,
    render_guide_expander,
)


def test_shared_constants_are_sensible():
    assert GUI_ANALYSIS_LIMITS.max_upload_bytes == 20 * 1024 * 1024
    assert MAX_PACKET_HEX_CHARS == 64 * 1024


def test_localize_register_meaning_known():
    from fw_diag_tool.gui.shared import _localize_register_meaning
    assert "正常" in _localize_register_meaning("OK")


def test_localize_register_meaning_passthrough():
    from fw_diag_tool.gui.shared import _localize_register_meaning
    assert _localize_register_meaning("SomeUnknownValue") == "SomeUnknownValue"
```

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_gui_shared.py -v`
Expected: PASS

- [ ] **Step 4: Update app.py to import from shared**

In `app.py`, replace the inline definitions (lines ~100-530) with imports from `gui.shared`. The app.py should now import these from shared instead of defining them locally. Remove the now-redundant code from app.py.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: 590+ passed, 0 failed

- [ ] **Step 6: Run static checks**

Run: `uv run ruff check src/fw_diag_tool/ tests/ && uv run mypy src/fw_diag_tool/`
Expected: All clean

- [ ] **Step 7: Commit**

```bash
git add src/fw_diag_tool/gui/shared.py tests/test_gui_shared.py src/fw_diag_tool/gui/app.py
git commit -m "refactor(gui): extract shared helpers into gui/shared.py"
```

---

### Task 2: Extract simple pages (UART, MCTP, DTS, SPI, Register, Codegen, Fault Arena, SOP)

**Files:**
- Create: `src/fw_diag_tool/gui/pages/uart_ui.py`, `mctp_ui.py`, `dts_ui.py`, `spi_ui.py`, `register_ui.py`, `codegen_ui.py`, `fault_arena_ui.py`, `sop_ui.py`
- Modify: `src/fw_diag_tool/gui/app.py` (remove extracted sections)
- Test: `tests/test_gui_page_modules.py`

**Interfaces:**
- Consumes: `fw_diag_tool.gui.shared` (all localization, guide expander, analyze_spi_input), `fw_diag_tool.gui.uploads` (decode_uploaded_text, validate_pasted_text, MAX_TEXT_BYTES), domain engines and reporters
- Produces: Each module exports `def render() -> None` that renders the full page UI using Streamlit calls

Each page module follows this pattern:
```python
"""UART Crash Dump page UI."""
from __future__ import annotations

import streamlit as st

from fw_diag_tool.gui.shared import render_guide_expander, ...
from fw_diag_tool.gui.uploads import MAX_TEXT_BYTES, validate_pasted_text
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter


def render() -> None:
    st.header("UART 序列埠崩潰轉儲與 ARM Cortex-M HardFault 智慧診斷")
    render_guide_expander(...)
    # ... rest of the page code from app.py
```

- [ ] **Step 1: Extract 8 simpler page modules**

For each of these 8 pages, create a `gui/pages/*_ui.py` file with a `render()` function containing the UI code currently in app.py:
- `uart_ui.py` (from app.py:1584-1642)
- `mctp_ui.py` (from app.py:1643-1711)
- `dts_ui.py` (from app.py:1712-1764)
- `spi_ui.py` (from app.py:1909-1987)
- `register_ui.py` (from app.py:1988-2054)
- `codegen_ui.py` (from app.py:2055-2086)
- `fault_arena_ui.py` (from app.py:2087-2145)
- `sop_ui.py` (from app.py:2146-2236)

Imports for each module should reference `fw_diag_tool.gui.shared` for localization/helpers.

- [ ] **Step 2: Write import and syntax tests**

Create `tests/test_gui_page_modules.py`:
```python
import importlib
import pytest

PAGE_MODULES = [
    "fw_diag_tool.gui.pages.uart_ui",
    "fw_diag_tool.gui.pages.mctp_ui",
    "fw_diag_tool.gui.pages.dts_ui",
    "fw_diag_tool.gui.pages.spi_ui",
    "fw_diag_tool.gui.pages.register_ui",
    "fw_diag_tool.gui.pages.codegen_ui",
    "fw_diag_tool.gui.pages.fault_arena_ui",
    "fw_diag_tool.gui.pages.sop_ui",
]


@pytest.mark.parametrize("module_name", PAGE_MODULES)
def test_page_module_imports_and_has_render(module_name: str):
    mod = importlib.import_module(module_name)
    assert callable(getattr(mod, "render", None)), f"{module_name} missing render()"
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_gui_page_modules.py -v`
Expected: 8 passed

- [ ] **Step 4: Remove extracted code from app.py**

Delete the corresponding `elif` blocks from app.py for these 8 pages. app.py should still work because the remaining 4 complex pages (I2C diagnosis, I2C builder, Waveform Diff, PCIe) stay inline temporarily.

- [ ] **Step 5: Full test suite + static checks**

Run: `uv run pytest --tb=short -q && uv run ruff check src/ tests/ && uv run mypy src/fw_diag_tool/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/fw_diag_tool/gui/pages/ tests/test_gui_page_modules.py src/fw_diag_tool/gui/app.py
git commit -m "refactor(gui): extract 8 page modules from monolithic app.py"
```

---

### Task 3: Extract complex pages (I2C Diagnosis, I2C Builder, Waveform Diff, PCIe)

**Files:**
- Create: `src/fw_diag_tool/gui/pages/i2c_diagnosis.py`, `i2c_builder_ui.py`, `waveform_diff_ui.py`, `pcie_ui.py`
- Modify: `src/fw_diag_tool/gui/app.py` (remove remaining page sections)
- Modify: `tests/test_gui_page_modules.py` (add new modules)

**Interfaces:**
- Consumes: `fw_diag_tool.gui.shared` (analyze_i2c_input, _reset_i2c_session_state, all localization), `fw_diag_tool.gui.pages.i2c_page` (analyze_i2c), `fw_diag_tool.gui.pages.i2c_builder` (build_i2c_bundle, presets, parsers), `fw_diag_tool.gui.session_io`, all domain-specific imports
- Produces: Each module exports `def render() -> None`

These 4 pages are more complex due to:
- I2C Diagnosis (580 lines): heavy session state, 5-tab layout, KPI cards, Plotly waveforms, anomaly expanders
- I2C Builder (303 lines): preset system, endianness/register-width state, multi-platform code gen, zip bundle
- Waveform Diff (136 lines): dual file upload state management, Golden/Failing sample state
- PCIe AER (144 lines): dual input mode (lspci/dmesg), sample state management, AER capability detection

- [ ] **Step 1: Extract the 4 complex page modules**

Create each file with a `render()` function. Pay attention to session state keys — they must be preserved exactly as-is (`i2c_sample_active`, `i2c_input_format`, `pcie_input_mode`, `waveform_diff_sample_active`, etc.).

- [ ] **Step 2: Add to test_gui_page_modules.py**

Add these 4 modules to the parametrized list:
```python
"fw_diag_tool.gui.pages.i2c_diagnosis",
"fw_diag_tool.gui.pages.i2c_builder_ui",
"fw_diag_tool.gui.pages.waveform_diff_ui",
"fw_diag_tool.gui.pages.pcie_ui",
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_gui_page_modules.py -v`
Expected: 12 passed

- [ ] **Step 4: Strip app.py down to router skeleton**

After extraction, app.py should contain only:
1. `st.set_page_config()`
2. `st.title()` and `st.caption()`
3. The `st.sidebar.radio` dispatch (temporarily — will be replaced in Task 4)
4. Calls to each page's `render()` function

- [ ] **Step 5: Full test suite + static checks**

Run: `uv run pytest --tb=short -q && uv run ruff check src/ tests/ && uv run mypy src/fw_diag_tool/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/fw_diag_tool/gui/pages/ src/fw_diag_tool/gui/app.py tests/test_gui_page_modules.py
git commit -m "refactor(gui): extract 4 complex pages, app.py is now a thin router"
```

---

### Task 4: Migrate to `st.navigation` / `st.Page` with grouped sidebar

**Files:**
- Modify: `src/fw_diag_tool/gui/app.py` (replace radio dispatch with st.navigation)
- Modify: `tests/test_gui.py` (update syntax assertions)
- Modify: `tests/test_gui_packaging.py` (if it references radio or menu patterns)

**Interfaces:**
- Consumes: All 12 `gui/pages/*_ui.py` modules (each has `render()`)
- Produces: New `app.py` using `st.navigation()` with 4 grouped sections

- [ ] **Step 1: Rewrite app.py with st.navigation**

Replace the entire `st.sidebar.radio` + `if/elif` chain with:
```python
import streamlit as st
from fw_diag_tool import __version__
from fw_diag_tool.gui.pages import (
    i2c_diagnosis, i2c_builder_ui, waveform_diff_ui,
    uart_ui, mctp_ui, pcie_ui, spi_ui,
    dts_ui, register_ui, codegen_ui,
    fault_arena_ui, sop_ui,
)

st.set_page_config(page_title="韌體訊號與協定診斷套件", page_icon="⚡", layout="wide")

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
st.sidebar.caption(f"fw-diag-tool v{__version__}")
nav.run()
```

- [ ] **Step 2: Update test_gui.py assertions**

Update `test_gui_app_syntax` to check for `st.navigation` instead of `st.sidebar.radio`:
```python
def test_gui_app_syntax():
    code = Path("src/fw_diag_tool/gui/app.py").read_text(encoding="utf-8")
    assert "st.set_page_config" in code
    assert "st.navigation" in code
    assert "st.Page" in code
```

- [ ] **Step 3: Update test_gui_packaging.py if needed**

Check if `test_gui_packaging.py` references the old menu/radio pattern and update accordingly.

- [ ] **Step 4: Full test suite + static checks**

Run: `uv run pytest --tb=short -q && uv run ruff check src/ tests/ && uv run mypy src/fw_diag_tool/`
Expected: All pass

- [ ] **Step 5: Verify app.py line count**

Run: `wc -l src/fw_diag_tool/gui/app.py`
Expected: < 200 lines

- [ ] **Step 6: Commit**

```bash
git add src/fw_diag_tool/gui/app.py tests/test_gui.py tests/test_gui_packaging.py
git commit -m "feat(gui): migrate to st.navigation with grouped sidebar sections"
```

---

### Task 5: Add file upload to text-only pages (UART, MCTP, PCIe, DTS)

**Files:**
- Modify: `src/fw_diag_tool/gui/pages/uart_ui.py`
- Modify: `src/fw_diag_tool/gui/pages/mctp_ui.py`
- Modify: `src/fw_diag_tool/gui/pages/pcie_ui.py`
- Modify: `src/fw_diag_tool/gui/pages/dts_ui.py`
- Test: `tests/test_gui_page_modules.py` (add upload-support assertions)

**Interfaces:**
- Consumes: `fw_diag_tool.gui.uploads.decode_uploaded_text`, `fw_diag_tool.gui.uploads.MAX_UPLOAD_BYTES`
- Produces: Each page's `render()` now accepts both file upload and text area input

- [ ] **Step 1: Add file_uploader to UART page**

In `uart_ui.py`, add above the text_area for the "貼上" mode:
```python
uploaded_file = st.file_uploader(
    "上傳 UART 日誌檔案（.txt / .log）",
    type=["txt", "log"],
    key="uart_file_upload",
)
if uploaded_file:
    u_raw = decode_uploaded_text(uploaded_file)
else:
    u_raw = st.text_area(...)
```

- [ ] **Step 2: Add file_uploader to MCTP page**

Same pattern in `mctp_ui.py`:
```python
uploaded_file = st.file_uploader(
    "上傳 MCTP／IPMB Hex Dump 檔案（.txt / .hex / .log）",
    type=["txt", "hex", "log"],
    key="mctp_file_upload",
)
```

- [ ] **Step 3: Add file_uploader to PCIe page**

In `pcie_ui.py`, add file upload for both lspci and dmesg modes:
```python
uploaded_file = st.file_uploader(
    "上傳 PCIe 設定空間或 AER 日誌檔案（.txt / .log / .dmesg）",
    type=["txt", "log", "dmesg"],
    key="pcie_file_upload",
)
```

- [ ] **Step 4: Add file_uploader to DTS page**

In `dts_ui.py`:
```python
uploaded_yaml = st.file_uploader(
    "上傳裝置定義 YAML 檔案",
    type=["yaml", "yml"],
    key="dts_yaml_upload",
)
```

- [ ] **Step 5: Add assertions to test_gui_page_modules.py**

```python
@pytest.mark.parametrize("module_name", [
    "fw_diag_tool.gui.pages.uart_ui",
    "fw_diag_tool.gui.pages.mctp_ui",
    "fw_diag_tool.gui.pages.pcie_ui",
    "fw_diag_tool.gui.pages.dts_ui",
])
def test_page_imports_upload_support(module_name: str):
    mod = importlib.import_module(module_name)
    source = inspect.getsource(mod)
    assert "file_uploader" in source or "decode_uploaded_text" in source
```

- [ ] **Step 6: Full test suite + static checks**

Run: `uv run pytest --tb=short -q && uv run ruff check src/ tests/ && uv run mypy src/fw_diag_tool/`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/fw_diag_tool/gui/pages/ tests/test_gui_page_modules.py
git commit -m "feat(gui): add file upload to UART, MCTP, PCIe, DTS pages"
```

---

### Task 6: Add explicit loading spinners

**Files:**
- Modify: `src/fw_diag_tool/gui/shared.py` (update `@st.cache_data` decorators)
- Modify: `src/fw_diag_tool/gui/pages/i2c_diagnosis.py` (add spinner around analysis)
- Modify: `src/fw_diag_tool/gui/pages/spi_ui.py` (add spinner)
- Modify: `src/fw_diag_tool/gui/pages/waveform_diff_ui.py` (add spinner)

**Interfaces:**
- Consumes: Streamlit `st.cache_data(show_spinner=...)` API
- Produces: User-visible loading messages during analysis

- [ ] **Step 1: Update cache decorators in shared.py**

Change:
```python
@st.cache_data(show_spinner=False)
def analyze_i2c_input(...):
```
To:
```python
@st.cache_data(show_spinner="正在解析 I2C 協定並計算時序統計...")
def analyze_i2c_input(...):
```

And:
```python
@st.cache_data(show_spinner="正在解析 SPI Flash 傳輸序列...")
def analyze_spi_input(...):
```

- [ ] **Step 2: Add spinners to waveform diff analysis**

In `waveform_diff_ui.py`, wrap the dual analysis calls:
```python
with st.spinner("正在執行雙波形語意比對..."):
    # golden and failing analysis + diff
```

- [ ] **Step 3: Verify spinners appear in source**

Run: `rg -n 'spinner|show_spinner' src/fw_diag_tool/gui/`
Expected: Multiple hits with descriptive zh-TW messages

- [ ] **Step 4: Full test suite**

Run: `uv run pytest --tb=short -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/fw_diag_tool/gui/
git commit -m "feat(gui): add explicit zh-TW loading spinners for analysis operations"
```

---

### Task 7: Add custom YAML upload to register decoder

**Files:**
- Modify: `src/fw_diag_tool/gui/pages/register_ui.py`
- Test: `tests/test_gui_page_modules.py` (add register YAML test)

**Interfaces:**
- Consumes: `fw_diag_tool.analyzers.register_mapper.RegisterMapCatalog`, `fw_diag_tool.gui.uploads.decode_uploaded_text`
- Produces: Register decoder page accepts custom YAML file upload as a third option

- [ ] **Step 1: Add custom YAML option to register_ui.py**

Modify the selectbox to include a custom upload option:
```python
builtin_map = {
    "PMBus 標準狀態暫存器（PMBus STATUS_WORD）": "pmbus_standard.yaml",
    "PCIe AER 不可修正錯誤暫存器（Uncorrectable Error）": "pcie_aer_registers.yaml",
}
choice = st.selectbox(
    "選擇暫存器定義檔",
    list(builtin_map.keys()) + ["📤 上傳自訂暫存器定義 YAML"],
)

catalog = RegisterMapCatalog()
if choice == "📤 上傳自訂暫存器定義 YAML":
    uploaded_yaml = st.file_uploader(
        "上傳自訂暫存器定義 YAML 檔案",
        type=["yaml", "yml"],
        key="register_custom_yaml",
    )
    if uploaded_yaml:
        try:
            yaml_text = decode_uploaded_text(uploaded_yaml)
            catalog.load_from_yaml(yaml_text)
        except Exception as exc:
            st.error(f"YAML 載入失敗：{exc}")
            catalog = RegisterMapCatalog()
else:
    data_dir = Path(__file__).parent.parent.parent / "data"
    yaml_file = data_dir / builtin_map[choice]
    if yaml_file.exists():
        catalog.load_from_yaml(yaml_file.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Write test for custom YAML option**

Add to `tests/test_gui_page_modules.py`:
```python
def test_register_ui_supports_custom_yaml():
    import inspect
    from fw_diag_tool.gui.pages import register_ui
    source = inspect.getsource(register_ui)
    assert "上傳自訂" in source
    assert "file_uploader" in source
```

- [ ] **Step 3: Full test suite + static checks**

Run: `uv run pytest --tb=short -q && uv run ruff check src/ tests/ && uv run mypy src/fw_diag_tool/`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/fw_diag_tool/gui/pages/register_ui.py tests/test_gui_page_modules.py
git commit -m "feat(gui): register decoder supports custom YAML upload"
```

---

### Task 8: Strengthen test coverage for `waveform_diff_report.py`

**Files:**
- Modify: `tests/test_waveform_diff_report.py`

**Interfaces:**
- Consumes: `fw_diag_tool.i2c.waveform_diff_report` (all `localize_diff_*` functions, all regex patterns)
- Produces: Coverage for `waveform_diff_report.py` increases from 57.6% to >= 85%

The module has 7 regex patterns and 4 public functions. Current tests cover 3 functions partially. Need to add tests for all regex pattern branches.

- [ ] **Step 1: Add tests for all diff type localization**

```python
from fw_diag_tool.i2c.waveform_diff_report import (
    localize_diff_type,
    localize_diff_description,
    localize_diff_hint,
    localize_diff_summary,
)


def test_localize_diff_type_all_known_keys():
    known = [
        "NACK_MISMATCH", "ADDRESS_MISMATCH", "DIRECTION_MISMATCH",
        "DATA_MISMATCH", "RETRY_SEQUENCE", "DROPPED_TRANSACTION",
        "UNEXPECTED_EXTRA_TX", "PHASE_SHIFT",
    ]
    for key in known:
        result = localize_diff_type(key)
        assert key in result  # English token preserved
        assert "（" in result  # Chinese annotation present


def test_localize_diff_type_unknown_passthrough():
    assert localize_diff_type("UNKNOWN_TYPE") == "UNKNOWN_TYPE"
```

- [ ] **Step 2: Add tests for description regex branches**

```python
def test_localize_direction_mismatch_description():
    desc = "Direction mismatch: Golden=Write, Failing=Read"
    result = localize_diff_description(desc)
    assert "Golden" in result or "方向" in result


def test_localize_data_mismatch_description():
    desc = "Data payload divergence on 0x50: Golden=0x1234, Failing=0x5678"
    result = localize_diff_description(desc)
    assert "0x50" in result


def test_localize_dropped_transaction_description():
    desc = "Dropped Transaction: golden transaction #3 to 0x48 was not observed in the failing trace."
    result = localize_diff_description(desc)
    assert "0x48" in result


def test_localize_address_mismatch_description():
    desc = "Address mismatch: Golden sent 0x50, Failing sent 0x48"
    result = localize_diff_description(desc)
    assert "0x50" in result and "0x48" in result
```

- [ ] **Step 3: Add tests for retry, extra, and phase regex patterns**

```python
def test_localize_retry_description():
    desc = "Retry sequence difference: Golden has 2 retries, Failing has 0."
    result = localize_diff_description(desc)
    assert isinstance(result, str) and len(result) > 0


def test_localize_extra_tx_description():
    desc = "Unexpected extra transaction in the failing trace at index #5."
    result = localize_diff_description(desc)
    assert isinstance(result, str) and len(result) > 0


def test_localize_phase_shift_description():
    desc = "Phase shift: transaction #3 in Golden corresponds to #5 in Failing."
    result = localize_diff_description(desc)
    assert isinstance(result, str) and len(result) > 0
```

- [ ] **Step 4: Run coverage for the module**

Run: `uv run pytest tests/test_waveform_diff_report.py -v --cov=fw_diag_tool.i2c.waveform_diff_report --cov-report=term-missing`
Expected: Coverage >= 85%

- [ ] **Step 5: Full test suite**

Run: `uv run pytest --tb=short -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add tests/test_waveform_diff_report.py
git commit -m "test(waveform-diff): cover all regex localization branches in diff report"
```

---

### Task 9: Strengthen test coverage for `uart/symbols.py` and emulators

**Files:**
- Modify: `tests/test_uart.py`
- Modify: `tests/test_emulator.py`

**Interfaces:**
- Consumes: `fw_diag_tool.uart.symbols.SymbolTable`, `fw_diag_tool.emulator.lm75.VirtualLM75`, `fw_diag_tool.emulator.spi_flash.VirtualSPIFlashW25Q128`
- Produces: Coverage for `uart/symbols.py` >= 85%, `emulator/lm75.py` >= 85%, `emulator/spi_flash.py` >= 80%

- [ ] **Step 1: Add SymbolTable tests to test_uart.py**

```python
from fw_diag_tool.uart.symbols import SymbolTable


def test_symbol_table_from_system_map_text():
    map_text = """ffffffff81000000 T _stext
ffffffff81001000 T do_fault
ffffffff81002000 T handle_pte_fault
"""
    st = SymbolTable.from_system_map(map_text)
    assert len(st.symbols) == 3
    result = st.lookup(0xFFFFFFFF81001050)
    assert result is not None
    name, offset = result
    assert name == "do_fault"
    assert offset == 0x50


def test_symbol_table_lookup_before_first_symbol():
    st = SymbolTable([(0x1000, "start")])
    assert st.lookup(0x0500) is None


def test_symbol_table_empty():
    st = SymbolTable()
    assert st.lookup(0x1234) is None


def test_symbol_table_symbolicate_hardfault():
    from fw_diag_tool.uart.parser import UARTCrashParser
    st = SymbolTable([(0x08001200, "main"), (0x08000400, "reset_handler")])
    report = UARTCrashParser.parse_log_text(
        "HardFault Exception Occurred!\nHFSR: 0x40000000 (FORCED)\n"
        "CFSR: 0x02000000 (DIVBYZERO)\nStacked PC: 0x08001234\nStacked LR: 0x08000456"
    )
    report = st.symbolicate(report)
    assert report.arm_hardfault is not None
    assert report.arm_hardfault.symbolicated_pc == "main+0x34"
    assert report.arm_hardfault.symbolicated_lr == "reset_handler+0x56"


def test_symbol_table_symbolicate_kernel_panic():
    from fw_diag_tool.uart.parser import UARTCrashParser
    st = SymbolTable([(0x10, "nvme_pci_complete_rq")])
    report = UARTCrashParser.parse_log_text(
        "BUG: unable to handle page fault for address: 0000000000000010\n"
        "RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]"
    )
    # symbolicate uses the hex IP if present
    report = st.symbolicate(report)
    assert report.kernel_panic is not None
```

- [ ] **Step 2: Add LM75 register tests to test_emulator.py**

```python
def test_lm75_config_register_write_and_read():
    from fw_diag_tool.emulator.lm75 import VirtualLM75
    lm = VirtualLM75()
    lm.write([0x01, 0x60])  # write CONFIG = 0x60
    assert lm.config_reg == 0x60
    lm.write([0x01])  # set pointer to CONFIG
    data = lm.read(1)
    assert data == bytes([0x60])


def test_lm75_thyst_register_read():
    from fw_diag_tool.emulator.lm75 import VirtualLM75
    lm = VirtualLM75()
    lm.write([0x02])  # set pointer to THYST
    data = lm.read(2)
    assert len(data) == 2
    assert data == bytes([(0x4B00 >> 8) & 0xFF, 0x4B00 & 0xFF])


def test_lm75_tos_register_read():
    from fw_diag_tool.emulator.lm75 import VirtualLM75
    lm = VirtualLM75()
    lm.write([0x03])  # set pointer to TOS
    data = lm.read(2)
    assert len(data) == 2
    assert data == bytes([(0x5000 >> 8) & 0xFF, 0x5000 & 0xFF])
```

- [ ] **Step 3: Add SPI sector_erase and write_disable tests to test_emulator.py**

```python
def test_spi_flash_sector_erase():
    from fw_diag_tool.emulator.spi_flash import VirtualSPIFlashW25Q128
    flash = VirtualSPIFlashW25Q128(total_size=65536)
    flash.write_enable()
    flash.page_program(0x0000, [0xAA] * 16)
    flash.complete_operation()
    assert flash.read_data(0x0000, 1) == [0xAA]
    flash.write_enable()
    result = flash.sector_erase(0x0000)
    assert result is True
    flash.complete_operation()
    assert flash.read_data(0x0000, 1) == [0xFF]


def test_spi_flash_sector_erase_without_wren():
    from fw_diag_tool.emulator.spi_flash import VirtualSPIFlashW25Q128
    flash = VirtualSPIFlashW25Q128(total_size=65536)
    result = flash.sector_erase(0x0000)
    assert result is False


def test_spi_flash_write_disable():
    from fw_diag_tool.emulator.spi_flash import VirtualSPIFlashW25Q128
    flash = VirtualSPIFlashW25Q128(total_size=65536)
    flash.write_enable()
    assert flash.wel_latched is True
    flash.write_disable()
    assert flash.wel_latched is False
```

- [ ] **Step 4: Run targeted coverage**

Run: `uv run pytest tests/test_uart.py tests/test_emulator.py -v --cov=fw_diag_tool.uart.symbols --cov=fw_diag_tool.emulator.lm75 --cov=fw_diag_tool.emulator.spi_flash --cov-report=term-missing`
Expected: All target modules >= 80%

- [ ] **Step 5: Full test suite**

Run: `uv run pytest --tb=short -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add tests/test_uart.py tests/test_emulator.py
git commit -m "test: strengthen coverage for uart/symbols, lm75, and spi_flash emulators"
```

---

### Task 10: Final verification and cleanup

**Files:**
- Modify: `src/fw_diag_tool/gui/pages/__init__.py` (ensure clean exports)
- No test file changes expected

**Interfaces:**
- Consumes: All prior task outputs
- Produces: Clean final state verified by all gates

- [ ] **Step 1: Verify app.py line count**

Run: `wc -l src/fw_diag_tool/gui/app.py`
Expected: < 200 lines

- [ ] **Step 2: Full test suite with coverage**

Run: `uv run pytest --tb=short -q --cov=fw_diag_tool --cov-report=term-missing`
Expected: 590+ passed, overall coverage >= 85%

- [ ] **Step 3: Static checks**

Run: `uv run ruff check src/ tests/ && uv run mypy src/fw_diag_tool/ && uv run mkdocs build --strict`
Expected: All clean

- [ ] **Step 4: Verify no regressions in git diff**

Run: `git diff --stat`
Review that only expected files are modified.

- [ ] **Step 5: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: final cleanup after GUI modernization refactor"
```

