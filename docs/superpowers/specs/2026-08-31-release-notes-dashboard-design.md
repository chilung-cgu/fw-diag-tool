# Release Notes Dashboard 累積更新設計規格

> **Date:** 2026-08-31
> **Status:** Approved by the standing user direction「方案 A，後續由我客觀選擇」與「請繼續」
> **Baseline:** v1.7.0 (`9bbc2c4`, tag `v1.7.0`)

## 1. 問題與證據

目前套件的版本權威來源是 `pyproject.toml` 的 `1.7.0`，tag `v1.7.0` 也指向目前 HEAD；但使用者在 v1.7.0 GUI 看到的 What's New 仍是 v1.5.0，根因是版本文字分散且其中一處硬編：

| 觀察 | 直接證據 | 判定 |
|---|---|---|
| 套件目前版本是 1.7.0 | `pyproject.toml:3`、`src/fw_diag_tool/__init__.py` | Verified |
| v1.7.0 已有功能提交與 tag | `git show 9bbc2c4`、`git tag v1.7.0` | Verified |
| Dashboard What's New 仍顯示 v1.5.0 | `src/fw_diag_tool/i18n/domains/gui.py:394-400`、`dashboard_ui.py:533-543` | Verified |
| CHANGELOG 最新標題仍是 1.6.0 | `CHANGELOG.md:5` | Verified |
| v1.7 release task 曾要求更新 CHANGELOG，但提交未包含 | `docs/superpowers/plans/2026-08-30-v1.7-comprehensive.md` Task 8 與 `git show --name-only 9bbc2c4` | Verified |

因此這不是「近期沒有更新」，而是 v1.7.0 release preparation 遺漏文件與 UI metadata 同步。

## 2. 目標

1. Dashboard 顯示與安裝套件版本相符的目前版本，不再硬編任何歷史版本號。
2. GUI 可離線顯示最近三個版本的摘要，並可瀏覽所有已發布版本。
3. v1.0.0 至 v1.7.0 的摘要有中英文內容、日期、分類與可選的本地導覽連結。
4. manifest 可在 wheel 與 source checkout 中以相同 API 載入，資料錯誤時提供可理解的降級訊息。
5. 用測試把 `pyproject.toml`、manifest、CHANGELOG 的版本順序與存在性綁成一個 release contract，避免下一次遺漏。
6. 保留現有 v1.7.0 tag 的不可變性；本工作分支是未發布的 metadata/UI 修正，不重打 tag、不自動 push。

## 3. 非目標

- 本階段不建立需要帳號、網路或通知狀態的獨立 Update Center。
- 不在執行期解析根目錄 `CHANGELOG.md`；wheel 不保證包含該根目錄檔案，Markdown parser 也會把格式錯誤帶進 UI。
- 不修改 CLI batch/report exit semantics、JSON envelope、bundle integrity 或 coverage gate；這些是稽核後的獨立 P0/P1 工作，另立 plan。
- 不把 commit message 中的測試數字當成即時 release 證據；manifest 只描述已核對的功能摘要。

## 4. 方案比較與選擇

### 方案 A：GUI 執行期解析 CHANGELOG

優點是沒有第二份資料；缺點是 root changelog 未被 wheel 明確打包、Markdown heading/locale 解析脆弱、UI 需要知道文件格式，且無法自然表達分類與導覽 CTA。Reject。

### 方案 B：套件內結構化 Release Notes manifest（採用）

在 `src/fw_diag_tool/resources/release_notes.json` 保存雙語、版本排序、摘要、分類、協定與可選 page/doc route；`release_notes.py` 只做 schema 驗證與 typed loading；Dashboard 是薄呈現層。CHANGELOG 仍是人類可讀的公開文件，測試驗證兩者的版本集合與最新版本一致。未來新增版本只能 prepend 新 entry，既有 entry 的 version、date、source_ref、highlight ID 與內容不可改寫。

這個方案能離線工作、可被 wheel 打包、可由測試精確驗證，並把未來新增版本限制為 append-only 的新 entry。

### 方案 C：獨立 Update Center 與已讀狀態

可提供搜尋、未讀徽章與版本通知，但會引入 session/local-state 契約、遷移與額外 UI 複雜度。等真正需要通知或大量版本搜尋時再以 v1.9/v2 個別規格處理。Defer。

## 5. 資料契約

### 5.1 JSON 結構

```json
{
  "schema_version": 1,
  "releases": [
    {
      "version": "1.7.0",
      "date": "2026-08-30",
      "source_ref": "CHANGELOG.md#1.7.0",
      "summary": {
        "zh-TW": "補齊非 I2C 協定的拓撲、資料庫與統計視覺化。",
        "en-US": "Adds topology, protocol databases, and interactive statistics beyond I2C."
      },
      "highlights": [
        {
          "id": "v1.7-pcie-topology",
          "category": "field_rca",
          "protocols": ["PCIe"],
          "title": {
            "zh-TW": "PCIe 拓撲樹",
            "en-US": "PCIe topology tree"
          },
          "summary": {
            "zh-TW": "以 bridge hierarchy 與 AER 標記協助定位裝置路徑。",
            "en-US": "Shows bridge hierarchy and AER markers to narrow the failing path."
          },
          "page": "pcie",
          "doc": "chapters/ch07_pcie_aer.md"
        }
      ]
    }
  ]
}
```

`releases` 必須由新到舊排列，且目前只接受穩定的 `x.y.z` 版本字串；最多 100 個 release。每個版本只能出現一次；每個 highlight 的 `id` 也只能出現一次。`summary` 與每個雙語欄位都必須同時包含 `zh-TW` 和 `en-US`，且每個純文字欄位長度為 1 至 500 個字元，不得含 HTML tag、外部 URL scheme 或單獨的 `$` LaTeX 分隔符。`category` 只接受 `field_rca`、`evidence_replay`、`teaching`、`team`、`quality`、`ux`。`protocols` 只能包含 `I2C`、`SPI`、`UART`、`PCIe`、`MCTP` 且不得重複（可為空陣列）；每個版本最多 12 個 highlights。`page` 只能是小寫英數與連字號組成的 route slug；Dashboard 會再以 `PAGE_INDEX` 過濾未註冊 route。`doc` 是相對於 `docs/` 的 Markdown path（例如 `chapters/ch07_pcie_aer.md`），不含 `..`、絕對路徑或反斜線。`source_ref` 必須是相對的 `CHANGELOG.md#...` 參照。

### 5.2 Python API

`src/fw_diag_tool/release_notes.py` 提供：

```python
@dataclass(frozen=True)
class ReleaseHighlight: ...


@dataclass(frozen=True)
class ReleaseNote: ...


class ReleaseNotesError(ValueError): ...


def parse_release_notes(payload: Mapping[str, object]) -> tuple[ReleaseNote, ...]: ...


def load_release_notes() -> tuple[ReleaseNote, ...]: ...


def localized_text(mapping: Mapping[str, str], locale: str) -> str: ...
```

Loader 使用 `importlib.resources.files("fw_diag_tool.resources")`，因此 source checkout 與 wheel/zip import 都走同一個資源邊界。`schema_version` 嚴格要求為 `1`；未知版本直接轉成 `ReleaseNotesError`，由 GUI 顯示 localized warning。日期以 `date.fromisoformat()` 驗證為有效的 `YYYY-MM-DD`。讀取 JSON 時拒絕 duplicate object keys；所有 schema/長度/排序/路徑/資源讀取錯誤轉成 `ReleaseNotesError`；不把 malformed data 靜默當成空歷史。GUI 每次 render 先快照一個 locale，再用純函式依 `locale` -> `zh-TW` -> `en-US` fallback 取 manifest 文字，不能因未知 locale 產生 `KeyError`。

## 6. Dashboard UX 與資料流

資料流固定為：

```text
release_notes.json
        -> release_notes.load_release_notes()
        -> dashboard_ui._render_release_notes()
        -> localized cards + full-history selector
```

Dashboard 的 What's New 區塊：

1. 標題不含版本號；另以 caption 顯示目前安裝版本。
2. 以三個有邊界的 card/container 顯示最新三版，每張包含版本、日期、雙語選定的摘要、分類/協定與最多一個本地導覽 CTA。
3. 以單一、不巢狀的 expander 提供完整歷史 selectbox；選擇任一版本可看到同一份摘要與 highlights。
4. 若目前 `__version__` 不在 manifest，仍顯示可用歷史，但以 warning 明確指出 release metadata 不完整。
5. manifest 缺失或無法解析時，不回退到 v1.5.0 等硬編內容；顯示 localized unavailable 訊息並保留其餘 Dashboard 功能。
6. 顯示文字用純文字或 `unsafe_allow_html=False` 的安全 Markdown；manifest 不提供任意 HTML 或外部 URL。page/doc route 只接受 loader 驗證過的本地值。動態 manifest 文字不得交給 `unsafe_allow_html=True`；doc 在 history expander 內只顯示驗證過的本地 path caption，不建立巢狀 expander。

分類標籤、狀態、錯誤與 CTA 全部走 `gui` domain 的 zh-TW/en-US keys；版本號、日期與內容由 manifest 提供，不再把版本寫入 i18n template。

## 7. 文件與 release contract

- `CHANGELOG.md` 新增經 commit/tag 證據核對的 `[1.7.0] - 2026-08-30` 區塊。
- `README.md` 的目前版本與 highlights 改成 v1.7.0；不在本次順手重寫整份功能矩陣。
- consistency tests 讀取 `pyproject.toml` 的 version、manifest 第一筆與 CHANGELOG 第一個 heading，確認三者相同；同時確認每個 manifest release 都有對應 CHANGELOG heading。
- consistency tests 同時確認 `uv.lock` 的 `fw-diag-tool` package version 與 `pyproject.toml` 一致，並在 release checklist 執行 `uv lock --check`，避免 `uv run --locked` 因升版後 lock drift 失敗。
- consistency tests 確認每筆 `source_ref` 的版本片段與該筆 manifest version 相同，且對應的 CHANGELOG heading 唯一存在；新增版本只能放在 manifest/CHANGELOG 的 head。
- packaging tests 確認 wheel 包含 `fw_diag_tool/resources/release_notes.json`，並在無 source checkout 的 isolated environment 載入 manifest。
- release checklist 增加「先寫 CHANGELOG/manifest，再建立 tag」的順序；既有 tag 不做 destructive rewrite。

## 8. 測試與驗收

### Loader

- 正常 manifest 回傳 descending tuple，dataclasses frozen 且欄位型別穩定。
- 缺 schema、錯 schema、duplicate version/highlight、非 descending 版本、缺雙語欄位、超長文字、unsafe path 都產生 `ReleaseNotesError`。
- 目前資源包含 v1.0.0 至 v1.7.0，第一筆等於 package `__version__`。

### GUI

- render helper 不再輸出 `v1.5.0`；mock/real AppTest 可看到 v1.7.0、v1.6.0、v1.5.0 三個版本。
- zh-TW 與 en-US 皆有標題、摘要、分類與 unavailable fallback。
- malformed loader 只產生 warning，不讓 Dashboard render crash。

### Release/packaging

```bash
uv run --locked --extra pdf pytest tests/test_release_notes.py tests/test_dashboard_health_enhanced.py tests/test_packaging.py -q
uv run ruff check src/fw_diag_tool/release_notes.py src/fw_diag_tool/gui/pages/dashboard_ui.py tests/test_release_notes.py
uv run mypy src/fw_diag_tool/release_notes.py
uv run mkdocs build --strict
```

完整 suite 與 coverage 是最後 gate；若現有 optional PDF dependency 或 coverage threshold 失敗，必須如實標示為環境/既有 gate 問題，不把它歸因於 release-note 功能。

## 9. 風險與後續

### 本階段已接受的風險

- CHANGELOG 內容與 manifest 摘要仍有兩份文字；consistency test 只保證版本集合，不保證每個句子相同。若未來手動維護成本升高，再設計由 manifest 產生 changelog 的單向 generator。
- 目前只顯示最新三版與 selectbox 歷史；不做搜尋、未讀狀態或遠端通知。

### 稽核後獨立待辦（不在本 diff）

- CI 必須安裝 `pdf` extra 或將 PDF tests 明確 skip。
- batch/report/fuzz 的失敗 exit code 與 format/protocol enum 需要契約化。
- 五協定輸出需要統一 versioned JSON envelope。
- bundle 需要 hash/path/privacy 驗證；coverage branch gate 需重新產生並核對。
