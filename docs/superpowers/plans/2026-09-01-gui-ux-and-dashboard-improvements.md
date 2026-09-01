# GUI UI/UX 呈現與儀表板架構優化實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復韌體診斷工具 Streamlit GUI 的 Release Notes 導覽迴路、按鈕語意化、卡片邊框排版、Session 趨勢分析空狀態頁尾與在地化，並統一全域註冊進入點與麵包屑導覽體驗。

**Architecture:** 依循 Streamlit 多頁架構與 i18n 翻譯機制，解耦 Release Notes 導覽映射、重構卡片邊框排版容器、修補 Session 趨勢分析之空狀態頁尾與示範載入流程，並統一 app.py 與各頁面的 render_breadcrumb 導覽契約。

**Tech Stack:** Python 3.10+, Streamlit, Plotly, Pandas, Pydantic, Pytest

**Spec:** docs/superpowers/plans/2026-09-01-gui-ux-and-dashboard-improvements.md

## Global Constraints

- 全面禁止行內 LaTeX（Zero Inline LaTeX），禁止任何單一美元符號包夾。
- 保留既有 1306+ 個單元測試通過，維持 Python 3.10+ 相容性。
- 遵循繁體中文（台灣用語）介面規範，維護 src/fw_diag_tool/i18n/ 多語系辭典。
- 導覽連結必須能被 PAGE_INDEX 與 resolve_page 精確解析，禁止破壞現有 URL 路由。

---

### Task 1: 修復 Release Notes 資源清單與導覽路由映射

**Files:**
- Modify: `src/fw_diag_tool/resources/release_notes.json`
- Modify: `src/fw_diag_tool/i18n/domains/gui.py`
- Test: `tests/test_release_notes.py`

**Interfaces:**
- Consumes: `PAGE_INDEX` in `src/fw_diag_tool/gui/page_index.py`
- Produces: Corrected `release_notes.json` with valid page URLs (`spi-chip-db`, `unified-report`, `session-analytics`).

- [ ] **Step 1: Write the failing test**

在 `tests/test_release_notes.py` 中新增測試 `test_shipped_highlights_target_valid_registered_pages`，驗證所有 release notes 中的 highlight 頁面皆存在於 `PAGE_INDEX` 且不產生無效的 dashboard 自環。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_notes.py::test_shipped_highlights_target_valid_registered_pages -v`

- [ ] **Step 3: Write minimal implementation**

修改 `src/fw_diag_tool/resources/release_notes.json`：
1. 將 `v17-spi-chip-db` 的 `"page": "spi"` 改為 `"page": "spi-chip-db"`。
2. 將 `v16-unified-report` 的 `"page": "dashboard"` 改為 `"page": "unified-report"`。
3. 將 `v17-plotly-stats` 與 `v16-protocol-statistics` 的 `"page": "dashboard"` 改為 `"page": "session-analytics"`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_notes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fw_diag_tool/resources/release_notes.json tests/test_release_notes.py
git commit -m "fix(gui): correct release notes target page routes"
```

---

### Task 2: 重構 Dashboard 更新紀錄卡片 UI / UX 與邊框排版

**Files:**
- Modify: `src/fw_diag_tool/gui/pages/dashboard_ui.py`
- Modify: `src/fw_diag_tool/i18n/domains/gui.py`
- Test: `tests/test_dashboard_enhanced.py`

**Interfaces:**
- Consumes: `ReleaseNote`, `ReleaseHighlight` from `fw_diag_tool.release_notes`
- Produces: `_render_release_card`, `_render_release_notes` with distinct button labels and bordered containers.

- [ ] **Step 1: Write the failing test**

在 `tests/test_dashboard_enhanced.py` 中新增測試，驗證 `_get_highlight_button_label` 支援依目標頁面自訂按鈕標題。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dashboard_enhanced.py::test_release_card_button_label_customization -v`

- [ ] **Step 3: Write minimal implementation**

在 `src/fw_diag_tool/gui/pages/dashboard_ui.py` 中：
1. 實作 `_get_highlight_button_label(highlight, locale)`：依據 `highlight.title` 產生動態按鈕標籤（如「前往 SPI Flash 晶片資料庫」）。
2. 在 `_render_release_card` 中，為每個 highlight 項目使用 `st.container(border=True)` 包裹，提升視覺分界並使 3 欄式版面高度清晰對齊。
3. 若目標頁面為當前頁面（`dashboard`），避免呈現自環按鈕，改為標註或導向對應章節。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dashboard_enhanced.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fw_diag_tool/gui/pages/dashboard_ui.py src/fw_diag_tool/i18n/domains/gui.py tests/test_dashboard_enhanced.py
git commit -m "fix(gui): enhance release notes card layout and contextual link labels"
```

---

### Task 3: 修復 Session 趨勢分析頁面空狀態頁尾與範例引導

**Files:**
- Modify: `src/fw_diag_tool/gui/pages/session_analytics_ui.py`
- Modify: `src/fw_diag_tool/i18n/domains/gui.py`
- Test: `tests/test_session_analytics.py`

**Interfaces:**
- Consumes: `analyze_session_trends`, `compute_health_score` from `fw_diag_tool.session.analytics`
- Produces: `render()` with complete footer rendering on empty state, sample session loader, and bilingual i18n support.

- [ ] **Step 1: Write the failing test**

在 `tests/test_session_analytics.py` 中新增測試 `test_session_analytics_sample_sessions_generator`。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_analytics.py::test_session_analytics_sample_sessions_generator -v`

- [ ] **Step 3: Write minimal implementation**

在 `src/fw_diag_tool/gui/pages/session_analytics_ui.py` 中：
1. 實作 `_get_sample_trend_sessions()`：產生 3 個代表不同除錯階段（Degrading -> Improving -> Clean）的範例 session 結構。
2. 在 `render()` 中加入「🚀 載入示範趨勢 Session」按鈕，存入 `st.session_state["session_analytics_demo_active"]`。
3. 修正空狀態邏輯：在 `if not uploaded and not demo_active:` 分支中渲染 `st.info(...)` 並確保呼叫 `render_page_footer()` 後再 `return`。
4. 導入 `t(...)` 與在地化字串，提供完整的繁體中文支援。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_analytics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fw_diag_tool/gui/pages/session_analytics_ui.py tests/test_session_analytics.py
git commit -m "fix(gui): ensure footer renders on empty session analytics and add sample loader"
```

---

### Task 4: 統一全域註冊進入點風格與導覽體驗

**Files:**
- Modify: `src/fw_diag_tool/gui/app.py`
- Modify: `src/fw_diag_tool/gui/pages/spi_chip_db_ui.py`
- Modify: `src/fw_diag_tool/gui/pages/protocol_diff_ui.py`
- Test: `tests/test_gui.py`

**Interfaces:**
- Consumes: `PAGE_INDEX`, `render_breadcrumb` from `fw_diag_tool.gui.page_index`
- Produces: Unified `.render` convention across all 26 pages in `app.py`.

- [ ] **Step 1: Write the failing test**

在 `tests/test_gui.py` 中驗證 `spi_chip_db_ui` 具有標準 `render` 函式。

- [ ] **Step 2: Run test to verify it passes or fails**

Run: `uv run pytest tests/test_gui.py -v`

- [ ] **Step 3: Write minimal implementation**

1. 在 `src/fw_diag_tool/gui/app.py` 中將 `spi_chip_db_ui.page` 改為 `spi_chip_db_ui.render`。
2. 在 `protocol_diff_ui.py` 加入「載入 Golden vs Failing 範例」按鈕支援。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_gui.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fw_diag_tool/gui/app.py src/fw_diag_tool/gui/pages/spi_chip_db_ui.py tests/test_gui.py
git commit -m "refactor(gui): standardize page entry points to render convention"
```

---

### Task 5: 執行全套件測試矩陣與回歸驗證

- [ ] **Step 1: Run full pytest suite**

Run: `uv run pytest`
Expected: 1306+ passed

- [ ] **Step 2: Run ruff lint & format check**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: Clean with 0 errors

- [ ] **Step 3: Run mypy typecheck**

Run: `uv run mypy src/fw_diag_tool`
Expected: Clean with 0 errors
