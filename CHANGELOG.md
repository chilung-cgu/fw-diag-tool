# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2026-08-30

### Added
- Protocol A/B Diff page (protocol_diff_ui) -- I2C/SPI/UART dual-file upload, diff engine comparison, Markdown report download
- Session A/B Compare page (session_compare_ui) -- dual .fwsession.json upload, metric delta cards, verdict badge, report export
- Dashboard health check panel -- runtime environment, dependency versions, Python/Streamlit status overview
- Toast notification integration -- show_success_toast/show_error_toast feedback on I2C/SPI/PCIe/UART/MCTP analysis pages
- HTML report enhancements -- light theme CSS, metadata header grid, print-friendly styles (partial)
- Global search index entries for Protocol Diff and Session Compare pages
- i18n translation keys for protocol_diff/session_compare

### Fixed
- batch.py undefined variable bug -- I2C used stale `report`, SPI/UART variable shadowing resolved

### Changed
- Navigation pages expanded from 22 to 24 (Protocol Diff, Session Compare)
- pyproject.toml version bumped to 1.3.0
- Test suite grown to 900+ tests

## [1.2.0] - 2026-08-30

### Added
- GUI 現代化重構：st.navigation 導覽、12→20 個模組化頁面、暗色主題 CSS
- 跨協定時間線關聯分析頁面 (correlation_ui) — I2C/SPI/UART 多協定時間對齊與異常叢集偵測
- Board Profile 視覺化拓撲編輯器 — 表單式拓撲定義、YAML 產出/匯入、位址衝突偵測
- 互動式教學導覽頁面 — 3 條學習路徑、6 步驟互動教學
- i18n 翻譯註冊表 (TranslationRegistry) — 多語言 domain-based 翻譯與向下相容橋接
- INA219 功率監控器 + PCA9548A I2C MUX 模擬器（含 GUI 分頁）
- HTML 報告產生器 — Markdown→HTML 轉換、暗色主題 CSS、自包含檔案
- batch_analyze_directory() — 多協定目錄級批次分析 (CLI + API)
- CLI `batch` 子命令 — 支援 Markdown/HTML/SARIF/manifest 多格式匯出
- SARIF 匯出整合至 GUI（I2C 診斷頁面下載按鈕）
- 4 新 MkDocs 教學章節 (ch13 晶片資料庫、ch14 模擬器、ch15 Fuzz 測試、ch16 總覽)
- shared.py 新增 render_html_download() helper

### Changed
- 導覽結構從 sidebar 分頁遷移至 st.navigation() 6 大分類 (20 pages)
- gui/shared.py 重構為集中式 helper 模組
- pyproject.toml 版本升至 1.2.0
- 測試套件從 ~590 增長至 729 tests

## [1.1.1] - 2026-08-24

### Security & Privacy
- GUI remote bind now requires explicit --allow-remote flag
- Streamlit telemetry disabled by default (browser.gatherUsageStats=false)
- Session files use POSIX 0700/0600 permissions

### Fixed
- MCTP/IPMB demux no longer uses address-only fallback for IPMB classification
- PCIe multi-device parser preserves undecodable chunks as data-quality issues
- Raw I2C waveform downsampling replaces hard rejection above render limit
- CSV parser normalizes csv.Error to InputFormatError (no traceback)

### Added
- ProtocolMode enum (auto/mctp/ipmb) with CLI --protocol flag and GUI selectbox
- AmbiguousProtocolError for frames that fail both protocol structural checks
- EvidenceMetric dataclass with measured/unavailable factory methods
- MCTP multi-packet message reassembly with sequence/tag tracking
- UART SymbolTable for offline crash symbolication from System.map/nm output
- Raw SPI digital transition parser supporting CPOL/CPHA modes 0-3
- DiagnosticReportEnvelope standard JSON format for CI pipelines
- SARIF 2.1.0 report builder for security scanning integration
- Batch manifest builder with pass/fail statistics
- Diagnostic bundle (.fw-diag-bundle.zip) with privacy manifest
- Board Profile YAML upload in I2C GUI page
- Hypothesis property-based tests for parser robustness
- Deterministic stride downsampling for large waveform captures

### Changed
- Coverage gates: branch=true, fail_under=80 in CI
- mypy: disallow_untyped_defs enabled for fw_diag_tool.*
- CI adds mkdocs build --strict gate and nightly cron schedule
- Version source unified: pyproject.toml is the single authority
- Wheel includes docs/ via force-include; sdist excludes build artifacts

## [1.1.0] - 2026-08-23

### Added
- Saleae Raw Digital CSV edge analyzer (Time,SCL,SDA) with true SCL clock period and stretch timing
- Board Profile schema supporting YAML/JSON server motherboard topologies (buses, muxes, devices)
- Hunt-Szymanski dynamic sequence alignment in Waveform Diff with retry detection and dropped transaction markers
- Session v2 schema with SHA-256 capture hashing, board profile metadata, and automated v1 migration
- Fault Arena 20-case fixture generators with in-GUI one-click automated diagnosis
- CLI options: --board-profile for hardware topology and --fail-on for CI/CD gates
- MkDocs search documentation configuration (mkdocs.yml) and in-app chapter reading expanders
- SPI Flash sample CSV bundled for offline practice in Web GUI

### Fixed
- Fixed false 360 kHz / 0% jitter metrics by requiring explicit duration or raw digital edge evidence
- Corrected I2C Read-final controller NACK semantics as valid bus termination
- Added SPI Flash BUSY (WIP=1) and WREN/Reset dual-command interlock tracking
- Fixed UART Panic signature recognition for ARM64 and RISC-V kernel dumps
- Guarded PCIe 64-byte short dump from parsing non-existent extended capabilities
- Sanitized rich Markdown report rendering in Web GUI and replaced external links with in-page expanders

## [1.0.0] - 2026-08-23

### Added
- I2C / SMBus / PMBus waveform reconstruction engine with SCL/SDA digital overlay
- PCIe Config Space parser with AER TLP Header Log decoding and Link degradation detection
- SPI NOR Flash protocol decoder with JEDEC ID lookup and WREN state machine tracking
- UART Crash Dump analyzer for Linux Kernel Panic and ARM Cortex-M HardFault
- MCTP (DSP0236/DSP0240 PLDM/SPDM) and IPMB server management protocol decoders
- Device Tree (.dts) auto-generator for Linux/OpenBMC BSP development
- C Header code generator producing MISRA-oriented RMW bitfield templates
- Multi-platform I2C driver snippet generator (Linux/OpenBMC/STM32 HAL/Arduino)
- Golden vs Failing Waveform Diff engine for A/B hardware comparison
- Virtual device emulators: EEPROM 24C64, LM75 temperature sensor, W25Q128 SPI Flash
- Fuzzing test generator for parser stress testing
- Session state persistence (.fwsession JSON)
- Interactive Streamlit Web GUI with 12 diagnostic pages and 20-case Fault Arena
- GitHub Actions CI/CD pipeline with Python 3.10-3.12 matrix testing
- Comprehensive Junior FW Engineer guide (docs/JUNIOR_FW_GUIDE.md)

### Fixed
- MCTP DSP0236 header version detection and SOM=0 payload offset alignment
- IPMB Response NetFn odd/even masking and Completion Code extraction
- ARM HardFault BFARVALID bit linkage preventing stale address false positives
- PMBus Linear16 signed two's complement handling for VOUT_TRIM negative values
- PMBus VOUT_MODE dynamic exponent update on Read transactions
- PCIe diagnostics AttributeError from stale property names
- PCIe Config TLP DW2 extended register number collision with BDF fields
- EEPROM page_size <= 0 division-by-zero crash guard
