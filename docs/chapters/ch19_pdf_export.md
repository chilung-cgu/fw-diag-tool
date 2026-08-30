# Ch19 — PDF 報告匯出

## 功能概述

fw-diag-tool 可把協定分析產生的 Markdown 報告轉成可攜式的獨立 PDF，方便附在 bug ticket、設計審查或現場 RCA 紀錄中。PDF 產生器使用 Python 套件 `fpdf2`，不需要另外安裝系統命令列轉檔工具；支援標題、metadata 橫幅、表格、程式碼區塊、引用與一般清單。

PDF 是分析報告的靜態快照。若需要互動式圖表、原始波形或完整 JSON provenance，請另外保存 Markdown、JSON 與原始輸入檔案。

## 安裝 fpdf2

在專案根目錄安裝已鎖定的 PDF 額外依賴：

```bash
uv sync --extra pdf
```

此 extra 目前宣告 `fpdf2>=2.7.0`。也可以在已安裝 fw-diag-tool 的環境執行：

```bash
uv pip install "fpdf2>=2.7.0"
```

若不使用 `uv`，也可在隔離的 virtualenv 中執行 `python -m pip install "fpdf2>=2.7.0"`；不要把依賴直接裝進系統 Python。

用下列指令確認目前 `uv` 環境真的能匯入套件：

```bash
uv run python -c "from fpdf import FPDF; print(FPDF.__name__)"
```

若未安裝 extra，CLI 不會偽造空檔案；它會顯示「PDF 匯出需安裝 pdf 額外套件」的警告並略過 PDF 產生。GUI 則顯示安裝提示。

## CLI 用法

I2C、SMBus 與 PMBus CSV 的基本命令如下：

```bash
fw-diag i2c analyze input.csv --pdf report.pdf
```

若使用專案工作環境，建議加上 `uv run`：

```bash
uv run fw-diag i2c analyze input.csv --pdf report.pdf
```

命令仍會把分析摘要輸出到終端；`--pdf` 會在指定路徑建立 PDF，父目錄不存在時會自動建立。可同時保留 Markdown 與結構化 JSON：

```bash
uv run fw-diag i2c analyze input.csv --md report.md --json report.json --pdf report.pdf
```

`input.csv` 預期是工具支援的 decoded CSV；文字 trace 或 raw digital CSV 請依 ch01 的輸入格式加上 `--text-trace` 或 `--raw-digital`。其他已提供 `--pdf` 的協定命令（例如 `spi analyze`、`pcie analyze`、`uart analyze`）也採同一輸出模式。

## GUI 用法

1. 執行 `uv run fw-diag gui`，開啟要分析的協定頁面，例如 I2C、SPI、PCIe 或 UART。
2. 上傳檔案或貼入文字，完成分析並確認畫面中的報告摘要與 evidence 欄位。
3. 在報告下方找到 **下載 PDF 報告（I2C）**（協定名稱會依頁面變更）並點擊下載。瀏覽器會取得 `.pdf` 檔案；可在 `filename_prefix` 對應的下載名稱下保存。
4. 若畫面只顯示「PDF 匯出需安裝 pdf 額外套件：`pip install fw-diag-tool[pdf]`」，先停止 GUI，在同一個環境執行上節的 `uv sync --extra pdf`，再重新啟動。

GUI 的 PDF 下載按鈕只會在已有 Markdown 報告時顯示；空白輸入或分析失敗不會產生 PDF。Session Analytics 頁面用於比較多個 Session，目前不把趨勢圖直接匯出成 PDF；請先保存各協定報告，再從對應協定頁面匯出。

## CJK 字型支援

產生器會依作業系統尋找 CJK 字型，優先使用 Noto Sans CJK、文泉驛、AR PL、PingFang 或 Windows 微軟正黑體／新細明體等候選路徑，並註冊到 fpdf2。若有 DejaVu Sans 等 Unicode 字型，會設定為 fallback 以補足其他字元。

這表示繁體中文通常可以直接輸出，但是否有字形取決於執行 PDF 的那台機器；容器或精簡 Linux 映像可能沒有任何 CJK 字型。若 PDF 出現方框或缺字，請在該環境安裝 Noto CJK（例如發行版的 `fonts-noto-cjk` 套件）後重試，或把自有字型放到程式列出的候選路徑。不要只在開發機安裝字型後就假設 CI／部署主機也有相同字形。

少數沒有穩定字形的符號會先做安全替換，例如 `⚡`、`📜`、`✔`、`✖` 與 `•` 轉為文字標記；這是為了避免 PDF 編碼錯誤，不代表所有 emoji 都能保留原貌。

## 證據層級、限制與邊界

**Measured（輸入中已量測／已記錄）**：PDF 會忠實呈現 Markdown 報告內的交易、異常、時間統計、輸入檔 SHA-256 與其他 metadata；數值來源仍是原本的分析器與輸入檔案。

**Inferred（格式轉換結果）**：標題層級、表格欄寬、頁首頁尾、報告產生時間與字型 fallback 是 PDF 產生器的排版推導。它不會重新判讀協定，也不會因為排版而增加新的硬體證據。

**Unavailable（PDF 本身不提供）**：互動式 Plotly 操作、原始邏輯分析儀波形、類比電壓／邊緣、未寫入 Markdown 的 JSON 欄位，以及未安裝 CJK 字型時的完整中文字形。Markdown 中的外部連結與圖片不會變成可互動網頁元件；請把原始檔、Markdown 與 JSON 一起歸檔。

PDF 產生還受以下條件限制：

- 必須安裝 `fpdf2` 且輸出路徑可寫；檔案寫入失敗會回報錯誤。
- 報告是靜態 A4 文件，長表格會跨頁；複雜 CSS、互動圖表與所有 Markdown 擴充語法不保證保留。
- PDF 不包含原始 capture 內容，Session 的 `capture_sha256` 也只有在報告 metadata 有輸出時才會看到；需要重現時仍要保存原始檔。
- 同一份報告在不同字型或 fpdf2 版本上可能有換行與頁數差異，做正式審查時請固定執行環境並核對輸出檔。
