from __future__ import annotations

from io import StringIO

from rich.console import Console

from fw_diag_tool.spi.models import (
    SPIDataQualityIssue,
    SPIDiagnosticIssue,
    SPIReport,
    SPIReportSummary,
    SPISeverity,
    SPITransaction,
)
from fw_diag_tool.spi.reporter import (
    SPIReporter,
    _contains_cjk,
    _localize_chip_name,
    _localize_detail,
    _localize_detail_key,
    _localize_detail_value,
    _localize_issue_description,
    _localize_issue_title,
    _localize_opcode_name,
    _localize_quality_message,
    _localize_root_cause,
)
from fw_diag_tool.spi.reporter import (
    _localize_severity as _localize_spi_severity,
)
from fw_diag_tool.uart.models import (
    ARMHardFaultReport,
    CallTraceFrame,
    CrashType,
    KernelPanicReport,
    UARTReport,
)
from fw_diag_tool.uart.reporter import (
    UARTReporter,
    _localize_analysis_text,
    _localize_checklist_item,
    _localize_crash_type,
    _localize_fault_flag,
    _localize_hardfault_summary,
    _localize_panic_reason,
)
from fw_diag_tool.uart.timing import UARTTimingAnalysis

# ============================================================================
# SPI Reporter Coverage Tests
# ============================================================================


def test_spi_contains_cjk_helper() -> None:
    """Test CJK unicode detection helper in SPI reporter."""
    assert _contains_cjk("繁體中文") is True
    assert _contains_cjk("Pure ASCII 1234") is False
    assert _contains_cjk("") is False


def test_spi_localize_chip_name() -> None:
    """Test chip name localization mappings and fallbacks."""
    assert _localize_chip_name("") == ""
    assert "未知／通用" in _localize_chip_name("Unknown / Generic SPI Flash")
    assert "未知製造商" in _localize_chip_name("Unknown Manufacturer / Model")
    assert _localize_chip_name("W25Q128FV") == "W25Q128FV"


def test_spi_localize_opcode_name() -> None:
    """Test opcode name localization regex, dict lookups, and unmapped fallbacks."""
    assert _localize_opcode_name("") == "無資料（No Data）"
    assert "讀取 JEDEC ID" in _localize_opcode_name("Read JEDEC ID (0x9F)")
    assert "未知 Opcode" in _localize_opcode_name("Unmapped Opcode (0x77)")
    assert "未知 Opcode" in _localize_opcode_name("Unknown Opcode")
    assert "未知 Opcode" in _localize_opcode_name("Unknown Opcode (0x00)")
    assert _localize_opcode_name("No Data") == "無資料（No Data）"
    assert _localize_opcode_name("已本地化中文") == "已本地化中文"
    assert "未知 Opcode" in _localize_opcode_name("CustomRawCommand")


def test_spi_localize_detail_key_and_value() -> None:
    """Test detail key/value localization for SPI transactions."""
    # Keys
    assert "製造商 ID" in _localize_detail_key("mfr_id")
    assert _localize_detail_key("已中文化欄位") == "已中文化欄位"
    assert "欄位（unknown_key）" in _localize_detail_key("unknown_key")

    # Values
    assert _localize_detail_value(True) == "是（True）"
    assert _localize_detail_value(False) == "否（False）"
    assert _localize_detail_value(42) == "42"
    assert _localize_detail_value(3.14) == "3.14"
    assert "Status Read" in _localize_detail_value("status-read")
    assert "未觀察到" in _localize_detail_value("unobserved")
    assert "裝置重設" in _localize_detail_value("device-reset")
    assert "未觀察到 reset-enable" in _localize_detail_value("reset-enable-not-observed")
    assert _localize_detail_value("0x1234") == "0x1234"
    assert _localize_detail_value("中文數值") == "中文數值"
    assert "未知值（random_val）" in _localize_detail_value("random_val")

    # Full detail pair
    assert "識別晶片" in _localize_detail("identified_chip", "Unknown / Generic SPI Flash")
    assert "製造商 ID" in _localize_detail("mfr_id", "0xEF")


def test_spi_localize_severity() -> None:
    """Test SPI severity enum and string localization."""
    assert "資訊" in _localize_spi_severity(SPISeverity.INFO)
    assert "警告" in _localize_spi_severity(SPISeverity.WARNING)
    assert "錯誤" in _localize_spi_severity(SPISeverity.ERROR)
    assert "嚴重" in _localize_spi_severity(SPISeverity.CRITICAL)
    assert "錯誤" in _localize_spi_severity("ERROR")
    assert _localize_spi_severity("已中文嚴重度") == "已中文嚴重度"
    assert "未知嚴重度" in _localize_spi_severity("UNKNOWN_SEV")


def test_spi_localize_quality_message() -> None:
    """Test SPI data quality limitation code and message localization."""
    # Standard exact match
    msg_empty = _localize_quality_message(
        "SPI_SOURCE_EMPTY",
        "The capture has no data rows after removing the header/comments; no SPI protocol conclusion can be established.",
    )
    assert "移除標題列" in msg_empty

    # Custom non-standard message with known code
    msg_custom = _localize_quality_message("SPI_SOURCE_EMPTY", "Custom empty message")
    assert "原始訊息" in msg_custom

    # CJK message
    assert _localize_quality_message("CUSTOM", "中文資料品質限制") == "中文資料品質限制"

    # Unknown code
    msg_unk = _localize_quality_message("SPI_UNKNOWN_CODE", "Something weird")
    assert "未知資料品質問題" in msg_unk


def test_spi_localize_issue_title_and_description() -> None:
    """Test SPI anomaly title and description localization regex and prefixes."""
    # Titles
    assert _localize_issue_title("") == "未知 SPI 異常（無標題）"
    assert "MISO 浮接" in _localize_issue_title(
        "JEDEC ID Read Returned All 0xFF (Floating MISO / No Power) @ Tx #1"
    )
    assert "對地短路" in _localize_issue_title(
        "JEDEC ID Read Returned All 0x00 (MISO Short to GND / Bus Clamped) @ Tx #2"
    )
    assert "未知原因" in _localize_issue_title(
        "JEDEC ID Read Returned All 0xFF (Random Reason) @ Tx #3"
    )
    assert "Flash 忙碌" in _localize_issue_title(
        "Command issued while Flash is BUSY (WIP=1) @ Tx #4"
    )
    assert "觀察到寫入／抹除時 WEL=0" in _localize_issue_title(
        "Write/Erase observed with WEL=0 @ Tx #5"
    )
    assert "寫入／抹除的 WEL 狀態未觀察到" in _localize_issue_title(
        "Write/Erase WEL state was not observed @ Tx #6"
    )
    assert "未先執行 WREN" in _localize_issue_title(
        "Write Status Register without WREN (0x06 / 0x50) @ Tx #7"
    )
    assert "Status Register 寫入的 WEL 狀態未觀察到" in _localize_issue_title(
        "Status-register write WEL state was not observed @ Tx #8"
    )
    assert "Wrap-around" in _localize_issue_title("Page Program Buffer Wrap-Around Hazard @ Tx #9")
    assert "CS 提早解除" in _localize_issue_title(
        "Incomplete SPI Command / Early CS Deassertion @ Tx #10"
    )
    assert _localize_issue_title("已中文化標題") == "已中文化標題"
    assert "未知 SPI 異常" in _localize_issue_title("Completely Custom SPI Anomaly")

    # Descriptions
    desc_ff = _localize_issue_description(
        "JEDEC ID command (0x9F) returned [0xFF, 0xFF, 0xFF]. Flash device did not drive MISO line."
    )
    assert "未驅動 MISO" in desc_ff
    desc_00 = _localize_issue_description(
        "JEDEC ID command (0x9F) returned [0x00, 0x00, 0x00]. MISO line is clamped to GND."
    )
    assert "箝位至 GND" in desc_00

    desc_busy = _localize_issue_description(
        "Command Page Program (0x02) was issued while the most recent observed status register reported BUSY=1. The internal write/erase cycle has not finished."
    )
    assert "BUSY=1" in desc_busy

    desc_wel0 = _localize_issue_description(
        "Command Sector Erase 4KB (0x20) was issued while the most recent observed status register reported WEL=0. The flash may reject the operation."
    )
    assert "WEL=0" in desc_wel0

    desc_wel_unk = _localize_issue_description(
        "No WREN or status-read evidence before Page Program (0x02) was present inside this capture; the operation's latch state cannot be proven."
    )
    assert "latch（鎖存）狀態" in desc_wel_unk

    desc_stat_nowren = _localize_issue_description(
        "Status Register write Write Status Register-1 (0x01) issued without 0x06 (WREN) or 0x50 (Volatile WREN)."
    )
    assert "0x06（WREN）" in desc_stat_nowren

    desc_stat_unk = _localize_issue_description(
        "No WREN or status evidence was captured before Write Status Register-1 (0x01); the write-enable precondition cannot be proven."
    )
    assert "寫入使能前提" in desc_stat_unk

    desc_wrap = _localize_issue_description(
        "Page Program started at in-page offset 0xFC with payload length 10 bytes. Total 0xFC + 10 = 262 exceeds 256-byte page boundary."
    )
    assert "page boundary" in desc_wrap

    desc_trunc = _localize_issue_description(
        "Command Read Data (0x03) requires at least 4 bytes (Opcode + 24-bit Address), but CS went high after 2 byte(s)."
    )
    assert "CS 在收到 2 byte(s) 後已拉高" in desc_trunc

    assert _localize_issue_description("中文描述文字") == "中文描述文字"
    assert "未知 SPI 異常描述" in _localize_issue_description("Unmapped English Description")


def test_spi_localize_root_cause() -> None:
    """Test SPI root cause guide string localization."""
    assert _localize_root_cause("") == ""
    rc_multiline = _localize_root_cause(
        "【Root Cause 排查建議】\n1. 檢查線路\nRoot Cause: Power rail drop"
    )
    assert "【根因排查建議（Root Cause）】" in rc_multiline
    assert "根因：Power rail drop" in rc_multiline
    assert _localize_root_cause("純英文排查提示") == "純英文排查提示"
    assert "根因排查指南" in _localize_root_cause("Inspect logic analyzer sample rate")


def test_spi_format_time() -> None:
    """Test time formatting with float, nan, inf, and invalid inputs."""
    assert SPIReporter._format_time(0.123456) == "0.123456"
    assert SPIReporter._format_time(float("nan")) == "n/a"
    assert SPIReporter._format_time(float("inf")) == "n/a"
    assert SPIReporter._format_time("invalid") == "n/a"
    assert SPIReporter._format_time(None) == "n/a"
    assert SPIReporter._format_time(True) == "n/a"


def test_spi_render_terminal_branches() -> None:
    """Test SPIReporter.render_terminal with all anomaly and quality branches."""
    # 1. Report with Critical/Error anomalies and Quality Issues
    report_bad = SPIReport(
        summary=SPIReportSummary(
            total_transactions=10,
            read_count=4,
            write_count=3,
            erase_count=1,
            status_poll_count=2,
            anomaly_count=2,
            detected_flash_chip="Winbond W25Q128",
        ),
        transactions=[
            SPITransaction(
                index=1,
                start_time=0.0001,
                end_time=0.0002,
                duration_us=100.0,
                mosi_bytes=[0x9F, 0x00, 0x00, 0x00],
                miso_bytes=[0x00, 0xEF, 0x40, 0x18],
                opcode=0x9F,
                opcode_name="Read JEDEC ID (0x9F)",
                address=None,
                data_payload_len=3,
                decoded_details={"mfr_id": "0xEF", "identified_chip": "W25Q128"},
            ),
        ],
        anomalies=[
            SPIDiagnosticIssue(
                code="SPI_JEDEC_ALL_FF",
                transaction_id=1,
                timestamp=0.0001,
                severity=SPISeverity.CRITICAL,
                title="JEDEC ID Read Returned All 0xFF (Floating MISO / No Power) @ Tx #1",
                description="JEDEC ID command (0x9F) returned [0xFF, 0xFF, 0xFF]. Flash device did not drive MISO line.",
                root_cause_guide="【Root Cause 排查建議】\n檢查供電電壓與 MISO 上拉電阻。",
            ),
            SPIDiagnosticIssue(
                code="SPI_PAGE_WRAP",
                transaction_id=2,
                timestamp=0.0002,
                severity=SPISeverity.WARNING,
                title="Page Program Buffer Wrap-Around Hazard @ Tx #2",
                description="Page Program started at in-page offset 0xFC with payload length 10 bytes. Total 0xFC + 10 = 262 exceeds 256-byte page boundary.",
                root_cause_guide="Root Cause: Buffer wrap-around hazard detected.",
            ),
        ],
        data_quality_issues=[
            SPIDataQualityIssue(
                code="SPI_CS_UNTERMINATED",
                message="The capture ended while CS was still asserted; the final transaction may be truncated.",
                count=1,
            ),
        ],
    )

    buf = StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None)
    SPIReporter.render_terminal(report_bad, console=console)
    out = buf.getvalue()
    assert "SPI / QSPI Flash" in out
    assert "Winbond W25Q128" in out
    assert "JEDEC ID 讀取回傳全為 0xFF" in out
    assert "SPI_CS_UNTERMINATED" in out

    # 2. Clean report with no anomalies and no quality issues
    report_clean = SPIReport(
        summary=SPIReportSummary(
            total_transactions=5,
            read_count=5,
            write_count=0,
            erase_count=0,
            status_poll_count=0,
            anomaly_count=0,
            detected_flash_chip=None,
        ),
        transactions=[],
        anomalies=[],
        data_quality_issues=[],
    )
    buf_clean = StringIO()
    console_clean = Console(file=buf_clean, force_terminal=False, color_system=None)
    SPIReporter.render_terminal(report_clean, console=console_clean)
    assert "未偵測到 SPI／Flash 異常" in buf_clean.getvalue()

    # 3. Report with quality issues but no anomalies
    report_quality_only = SPIReport(
        summary=SPIReportSummary(
            total_transactions=1,
            read_count=1,
            write_count=0,
            erase_count=0,
            status_poll_count=0,
            anomaly_count=0,
            detected_flash_chip=None,
        ),
        transactions=[],
        anomalies=[],
        data_quality_issues=[
            SPIDataQualityIssue(
                code="SPI_NO_TRANSACTIONS",
                message="Input rows were present but no CS-framed SPI transaction was decoded; check chip-select polarity and capture framing.",
                count=1,
            )
        ],
    )
    buf_q = StringIO()
    console_q = Console(file=buf_q, force_terminal=False, color_system=None)
    SPIReporter.render_terminal(report_quality_only, console=console_q)
    assert "未能由現有證據證明 SPI 異常" in buf_q.getvalue()


def test_spi_to_markdown_full_options() -> None:
    """Test SPIReporter.to_markdown with statistics, quality issues, anomalies, and transaction logs."""
    report = SPIReport(
        summary=SPIReportSummary(
            total_transactions=2,
            read_count=1,
            write_count=1,
            erase_count=0,
            status_poll_count=0,
            anomaly_count=1,
            detected_flash_chip="Macronix MX25L128",
        ),
        transactions=[
            SPITransaction(
                index=1,
                start_time=0.0001,
                end_time=0.0002,
                duration_us=100.0,
                mosi_bytes=[0x03, 0x00, 0x10, 0x00],
                miso_bytes=[0x00, 0x00, 0x00, 0x00] + [0xAA] * 16,
                opcode=0x03,
                opcode_name="Read Data (0x03)",
                address=0x001000,
                data_payload_len=16,
                decoded_details={"read_address": "0x001000", "read_bytes": 16},
            ),
            SPITransaction(
                index=2,
                start_time=0.0003,
                end_time=0.0005,
                duration_us=200.0,
                mosi_bytes=[],
                miso_bytes=[],
                opcode=None,
                opcode_name=None,  # type: ignore[arg-type]
                address=None,
                data_payload_len=0,
                decoded_details={},
            ),
        ],
        anomalies=[
            SPIDiagnosticIssue(
                code="SPI_BUSY_COMMAND",
                transaction_id=1,
                timestamp=0.0001,
                severity=SPISeverity.ERROR,
                title="Command issued while Flash is BUSY (WIP=1) @ Tx #1",
                description="Command Read Data (0x03) was issued while the most recent observed status register reported BUSY=1. The internal write/erase cycle has not finished.",
                root_cause_guide="【Root Cause 排查建議】\n確認狀態暫存器 WIP 位元清零。",
            ),
        ],
        data_quality_issues=[
            SPIDataQualityIssue(
                code="SPI_RESPONSE_TRUNCATED",
                message="One or more SPI commands ended before the minimum response or payload bytes required for a trustworthy decode were captured.",
                count=1,
            )
        ],
    )

    md = SPIReporter.to_markdown(report)
    assert "# SPI / QSPI Flash 診斷報告" in md
    assert "Macronix MX25L128" in md
    assert "SPI 操作統計" in md
    assert "資料品質限制" in md
    assert "協定異常與根因分析" in md
    assert "SPI 交易記錄" in md
    assert "Read Data" in md


# ============================================================================
# UART Reporter Coverage Tests
# ============================================================================


def test_uart_localize_helpers() -> None:
    """Test UART localization helpers for crash types, panic reasons, analysis, and fault flags."""
    # Crash type
    assert "Linux 核心" in _localize_crash_type(CrashType.KERNEL_PANIC.value)
    assert "ARM Cortex-M" in _localize_crash_type(CrashType.ARM_HARDFAULT.value)
    assert "Watchdog" in _localize_crash_type(CrashType.WATCHDOG_RESET.value)
    assert "一般序列埠" in _localize_crash_type(CrashType.GENERIC_LOG.value)
    assert _localize_crash_type("CustomCrashType") == "CustomCrashType"

    # Panic reasons
    assert _localize_panic_reason("") == ""
    assert "BUG：無法處理 page fault" in _localize_panic_reason(
        "BUG: unable to handle page fault for address: 0x00000000"
    )
    assert "Kernel panic（核心 Panic）" in _localize_panic_reason(
        "Kernel panic - not syncing: VFS: Unable to mount root fs"
    )
    assert "中斷期間發生致命例外" in _localize_panic_reason("Fatal exception in interrupt")
    assert "內部錯誤（Internal error）：同步 external abort" in _localize_panic_reason(
        "Internal error: synchronous external abort: 96000010"
    )
    assert "內部錯誤（Internal error）：" in _localize_panic_reason(
        "Internal error: Oops: 0000 [#1] SMP"
    )
    assert "無法處理核心 paging request" in _localize_panic_reason(
        "Unable to handle kernel paging request at virtual address ffff8800"
    )
    assert _localize_panic_reason("Unmapped panic string") == "Unmapped panic string"

    # Analysis text
    assert _localize_analysis_text("") == ""
    raw_analysis = (
        "NULL Pointer Dereference 候選\n"
        "Kernel Exception 發生\n"
        "Stack Corruption 偵測到\n"
        "fault context 遺失\n"
        "總線錯誤與總線被鎖定 (位址: 0x2000)"
    )
    loc_analysis = _localize_analysis_text(raw_analysis)
    assert "NULL 指標解引用候選" in loc_analysis
    assert "核心例外" in loc_analysis
    assert "堆疊損毀" in loc_analysis
    assert "故障上下文" in loc_analysis
    assert "匯流排錯誤" in loc_analysis
    assert "（位址：" in loc_analysis

    # Checklist
    assert _localize_checklist_item("") == ""
    assert "Call Trace（呼叫追蹤）" in _localize_checklist_item("Inspect Call Trace")
    assert "堆疊損毀（Stack Corruption）" in _localize_checklist_item("Check for Stack Corruption")

    # Fault flags
    assert "HFSR.FORCED" in _localize_fault_flag(
        "HFSR.FORCED (HardFault generated by escalation of a configurable fault)"
    )
    assert "UFSR.DIVBYZERO" in _localize_fault_flag("UFSR.DIVBYZERO (Division by Zero trapped)")
    assert "BFSR.BFARVALID" in _localize_fault_flag("BFSR.BFARVALID (Fault Address: 0x20000000)")
    assert "MMFSR.MMARVALID" in _localize_fault_flag("MMFSR.MMARVALID (Fault Address: 0x20000004)")
    assert "BFSR.PRECISERR" in _localize_fault_flag(
        "BFSR.PRECISERR (Precise Data Bus Error at address: 0x08000000)"
    )
    assert _localize_fault_flag("UNKNOWN_FLAG") == "UNKNOWN_FLAG"

    # HardFault summary
    assert "已觸發" in _localize_hardfault_summary("ARM Cortex-M HardFault Exception Triggered.")
    assert "自訂摘要" in _localize_hardfault_summary("自訂摘要")


def test_uart_render_terminal_and_markdown_kernel_panic() -> None:
    """Test UARTReporter for Kernel Panic with terminal output and markdown."""
    kp = KernelPanicReport(
        architecture="x86_64",
        panic_reason="Kernel panic - not syncing: Fatal exception in interrupt",
        faulting_ip="0xffffffff81001234",
        faulting_func="nvme_irq_handler",
        faulting_address="0x0000000000000010",
        modules_linked=["nvme", "nvme_core"],
        call_trace=[
            CallTraceFrame(
                index=1, function_name="nvme_irq_handler", offset="0x8c/0x100", module="nvme"
            ),
            CallTraceFrame(
                index=2, function_name="blk_mq_complete_request", offset="0x24/0x50", module=""
            ),
        ],
        root_cause_analysis="NULL Pointer Dereference 候選: nvme_irq_handler",
        actionable_checklist=["Inspect Call Trace", "Check for Stack Corruption"],
    )
    report = UARTReport(
        crash_type=CrashType.KERNEL_PANIC,
        summary_title="Kernel Panic in NVMe Driver",
        raw_log_lines=50,
        kernel_panic=kp,
    )

    # 1. Terminal render
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None)
    UARTReporter.render_terminal(report, console=console)
    out = buf.getvalue()
    assert "Kernel Panic 摘要" in out
    assert "nvme_irq_handler" in out
    assert "呼叫追蹤／堆疊框架" in out

    # 2. Markdown render
    md = UARTReporter.to_markdown(report)
    assert "# UART 崩潰轉儲分析" in md
    assert "## 1. 崩潰摘要" in md
    assert "## 2. 呼叫追蹤" in md
    assert "## 3. 根因分析與除錯清單" in md


def test_uart_render_terminal_and_markdown_arm_hardfault() -> None:
    """Test UARTReporter for ARM HardFault with terminal output and markdown."""
    hf = ARMHardFaultReport(
        hfsr_raw=0x40000000,
        cfsr_raw=0x00000100,
        ufsr_raw=0x0000,
        bfsr_raw=0x01,
        mmfsr_raw=0x00,
        pc_faulting=0x08001234,
        lr_exc_return=0xFFFFFFF9,
        bfar_raw=0x20000000,
        mmfar_raw=None,
        fault_flags=[
            "HFSR.FORCED (HardFault generated by escalation of a configurable fault)",
            "BFSR.BFARVALID (Fault Address: 0x20000000)",
        ],
        root_cause_analysis="ARM Cortex-M HardFault Exception Triggered.",
        actionable_checklist=["Verify PC pointer address", "Check MPU configuration"],
    )
    report = UARTReport(
        crash_type=CrashType.ARM_HARDFAULT,
        summary_title="ARM Cortex-M HardFault Crash",
        raw_log_lines=30,
        arm_hardfault=hf,
    )

    # 1. Terminal render
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None)
    UARTReporter.render_terminal(report, console=console)
    out = buf.getvalue()
    assert "ARM Cortex-M HardFault 暫存器" in out
    assert "0x08001234" in out
    assert "Fault 旗標" in out

    # 2. Markdown render
    md = UARTReporter.to_markdown(report)
    assert "# UART 崩潰轉儲分析" in md
    assert "## 1. HardFault 暫存器" in md
    assert "## 2. Fault Flags 與根因" in md


def test_uart_render_terminal_and_markdown_generic_log_with_timing() -> None:
    """Test UARTReporter for generic logs with full UARTTimingAnalysis."""
    report = UARTReport(
        crash_type=CrashType.GENERIC_LOG,
        summary_title="Generic Serial Boot Log",
        raw_log_lines=120,
    )
    timing = UARTTimingAnalysis(
        total_log_duration_s=12.345,
        line_count=120,
        timestamp_coverage=0.98,
        boot_phase_durations={"bootloader": 1.2, "kernel": 4.5, "userspace": 6.645},
        crash_to_reset_interval_s=0.5,
    )

    # 1. Terminal render
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None)
    UARTReporter.render_terminal(report, console=console, timing=timing)
    out = buf.getvalue()
    assert "未辨識 Crash Signature" in out
    assert "UART 時序分析摘要" in out
    assert "12.345 秒" in out
    assert "98.0%" in out

    # 2. Markdown render
    md = UARTReporter.to_markdown(report, timing=timing)
    assert "未辨識 Crash Signature" in md
    assert "UART 時序分析" in md
    assert "12.345 秒" in md
    assert "Bootloader" in md
    assert "崩潰至重置間隔" in md


def test_uart_timing_none_fields_fallback() -> None:
    """Test UART timing reporting when all duration fields are None."""
    report = UARTReport(
        crash_type=CrashType.WATCHDOG_RESET,
        summary_title="Watchdog Reset Log",
        raw_log_lines=15,
    )
    timing_none = UARTTimingAnalysis(
        total_log_duration_s=None,
        line_count=15,
        timestamp_coverage=0.0,
        boot_phase_durations={"bootloader": None, "kernel": None, "userspace": None},
        crash_to_reset_interval_s=None,
    )

    buf = StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None)
    UARTReporter.render_terminal(report, console=console, timing=timing_none)
    out = buf.getvalue()
    assert "N/A" in out

    md = UARTReporter.to_markdown(report, timing=timing_none)
    assert "N/A" in md


def test_spi_localize_unknown_severity_and_quality_fallbacks() -> None:
    assert "未知嚴重度" in _localize_spi_severity("NOTICE")
    assert _localize_spi_severity("自訂嚴重度") == "自訂嚴重度"
    assert "未知資料品質問題" in _localize_quality_message("CUSTOM", "raw message")
    assert "原始訊息" in _localize_quality_message("SPI_SOURCE_EMPTY", "different message")


def test_spi_localize_detail_identified_chip_and_unknown_values() -> None:
    assert "未知／通用" in _localize_detail("identified_chip", "Unknown / Generic SPI Flash")
    assert _localize_detail("custom_key", "custom value").startswith("欄位（custom_key）")
    assert _localize_detail("flag", None).endswith("未知值（None）")


def test_spi_markdown_empty_report_uses_unavailable_statistics() -> None:
    report = SPIReport(summary=SPIReportSummary(), transactions=[])
    markdown = SPIReporter.to_markdown(report)
    assert "未知／通用 SPI Flash" in markdown
    assert "無時間戳資料（Unavailable）" in markdown
    assert "無（None）" in markdown


def test_uart_generic_report_without_timing_has_next_step_only() -> None:
    report = UARTReport(
        crash_type=CrashType.GENERIC_LOG,
        summary_title="normal",
        raw_log_lines=2,
    )
    terminal = StringIO()
    UARTReporter.render_terminal(report, console=Console(file=terminal, force_terminal=False))
    markdown = UARTReporter.to_markdown(report)
    assert "未辨識 Crash Signature" in terminal.getvalue()
    assert "建議下一步" in markdown
    assert "UART 時序分析" not in markdown


def test_uart_kernel_panic_report_handles_optional_fields_absent() -> None:
    report = UARTReport(
        crash_type=CrashType.KERNEL_PANIC,
        summary_title="panic",
        raw_log_lines=1,
        kernel_panic=KernelPanicReport(
            architecture="arm64",
            panic_reason="custom panic",
        ),
    )
    terminal = StringIO()
    UARTReporter.render_terminal(report, console=Console(file=terminal, force_terminal=False))
    markdown = UARTReporter.to_markdown(report)
    assert "Kernel Panic 摘要" in terminal.getvalue()
    assert "custom panic" in markdown
