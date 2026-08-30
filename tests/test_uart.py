from fw_diag_tool.uart.models import CrashType
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter
from fw_diag_tool.uart.symbols import SymbolTable


def test_kernel_panic_parsing():
    panic_log = """BUG: unable to handle page fault for address: 0000000000000010
RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]
RAX: 0000000000000000 RBX: ffff888102345000 RCX: 0000000000000000
CR2: 0000000000000010
Call Trace:
 <TASK>
 [ffff888100123450] blk_mq_complete_request+0x24/0x50
 [ffff8881001234a0] nvme_irq_handler+0x8c/0x100 [nvme]
 </TASK>"""
    report = UARTCrashParser.parse_log_text(panic_log)
    assert report.crash_type == CrashType.KERNEL_PANIC
    assert report.kernel_panic is not None
    assert report.kernel_panic.faulting_func == "nvme_pci_complete_rq"
    assert report.kernel_panic.faulting_address == "0x0000000000000010"
    assert len(report.kernel_panic.call_trace) == 2
    assert "NULL Pointer Dereference" in report.kernel_panic.root_cause_analysis
    md = UARTReporter.to_markdown(report)
    assert "nvme_pci_complete_rq" in md
    assert "NULL 指標解引用候選（NULL Pointer Dereference）" in md
    assert "kzalloc/kmalloc/devm_*" in md


def test_arm_hardfault_parsing():
    hardfault_log = """HardFault Exception Occurred!
HFSR: 0x40000000 (FORCED)
CFSR: 0x02000000 (DIVBYZERO)
Stacked R0: 0x00000000
Stacked R1: 0x0000000A
Stacked PC: 0x08001234
Stacked LR: 0x08000456
Stacked xPSR: 0x61000000"""
    report = UARTCrashParser.parse_log_text(hardfault_log)
    assert report.crash_type == CrashType.ARM_HARDFAULT
    assert report.arm_hardfault is not None
    assert report.arm_hardfault.pc_faulting == 0x08001234
    assert any("DIVBYZERO" in flag for flag in report.arm_hardfault.fault_flags)
    assert "除以零錯誤" in report.arm_hardfault.root_cause_analysis


def test_arm64_kernel_panic_parsing():
    panic_log = """Internal error: synchronous external abort: 96000210 [#1] SMP
FAR_EL1: ffff800008000000
pc : nvme_poll+0x44/0x180 [nvme]
lr : nvme_irq_handler+0x8c/0x100 [nvme]
sp : ffff80000a003dc0
x0 : 0000000000000000 x1 : ffff800008000000
Call trace:
 nvme_poll+0x44/0x180 [nvme]
 nvme_irq_handler+0x8c/0x100 [nvme]
"""
    report = UARTCrashParser.parse_log_text(panic_log)
    assert report.crash_type == CrashType.KERNEL_PANIC
    assert report.kernel_panic is not None
    assert report.kernel_panic.architecture == "ARM64"
    assert report.kernel_panic.faulting_func == "nvme_poll"
    assert len(report.kernel_panic.call_trace) >= 1


def test_riscv_kernel_panic_parsing():
    panic_log = """Unable to handle kernel paging request at virtual address 0000000000000020
epc : 0000000080201234
ra : 0000000080205678
sp : ffffffff81003d00
status: 0000000200000100 badvaddr: 0000000000000020 cause: 000000000000000d
"""
    report = UARTCrashParser.parse_log_text(panic_log)
    assert report.crash_type == CrashType.KERNEL_PANIC
    assert report.kernel_panic is not None
    assert report.kernel_panic.architecture == "RISC-V"
    assert report.kernel_panic.faulting_address == "0x0000000000000020"
    markdown = UARTReporter.to_markdown(report)
    assert "NULL 指標解引用候選（NULL Pointer Dereference）" in markdown
    assert "無法處理核心 paging request" in markdown
    assert "Unable to handle kernel paging request" in markdown


def test_non_null_kernel_root_cause_keeps_debug_tokens_in_zh_tw_report():
    report = UARTCrashParser.parse_log_text(
        "Unable to handle kernel paging request at virtual address 0000000080200020\n"
        "epc : 0000000080201234\n"
    )

    markdown = UARTReporter.to_markdown(report)

    assert "核心例外（Kernel Exception）" in markdown
    assert "gdb / addr2line" in markdown
    assert "堆疊損毀（Stack Corruption）" in markdown
    assert "0x0000000080200020" in markdown


def test_hardfault_fallback_is_localized_without_dropping_canonical_name():
    report = UARTCrashParser.parse_log_text(
        "HardFault Exception!\nHFSR: 0x00000000\nCFSR: 0x00000000\n"
    )

    markdown = UARTReporter.to_markdown(report)

    assert "ARM Cortex-M HardFault 例外已觸發" in markdown
    assert "ARM Cortex-M HardFault Exception Triggered." in markdown


def test_generic_serial_log_report_explains_unsupported_signature():
    report = UARTCrashParser.parse_log_text("booting firmware\nready\n")

    markdown = UARTReporter.to_markdown(report)

    assert "未辨識 Crash Signature" in markdown
    assert "未偵測到已支援的 Kernel Panic / HardFault 標記" in markdown
    assert "**原始日誌行數（Raw Log Lines）**: `2`" in markdown
    assert "建議下一步" in markdown


def test_symbol_table_from_system_map_text():
    map_text = """# Symbol map comment
ffffffff81000000 T _stext
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


def test_symbol_table_from_system_map_path(tmp_path):
    map_file = tmp_path / "System.map"
    map_file.write_text("08001000 T main\n08002000: init_hw\n", encoding="utf-8")

    st_from_path = SymbolTable.from_system_map(map_file)
    assert len(st_from_path.symbols) == 2
    assert st_from_path.lookup(0x08001010) == ("main", 0x10)

    st_from_str_path = SymbolTable.from_system_map(str(map_file))
    assert len(st_from_str_path.symbols) == 2


def test_symbol_table_lookup_before_first_symbol():
    st = SymbolTable([(0x1000, "start")])
    assert st.lookup(0x0500) is None


def test_symbol_table_empty():
    st = SymbolTable()
    assert st.lookup(0x1234) is None


def test_symbol_table_symbolicate_hardfault():
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
    st = SymbolTable([(0x10, "nvme_pci_complete_rq")])
    report = UARTCrashParser.parse_log_text(
        "BUG: unable to handle page fault for address: 0000000000000010\n"
        "RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]"
    )
    assert report.kernel_panic is not None
    report.kernel_panic.faulting_ip = "0x18"
    report = st.symbolicate(report)
    assert report.kernel_panic.symbolicated_ip == "nvme_pci_complete_rq+0x8"

    # Test non-0x or invalid hex
    report.kernel_panic.faulting_ip = "invalid_hex"
    report = st.symbolicate(report)
    report.kernel_panic.faulting_ip = "0xinvalid"
    report = st.symbolicate(report)
    report.kernel_panic.faulting_ip = "0x9999"  # Symbol not found in table
    report = st.symbolicate(report)


def test_symbol_table_symbolicate_none_matches():
    from fw_diag_tool.uart.models import ARMHardFaultReport, UARTReport

    st = SymbolTable([(0x1000, "main")])
    # Hardfault with None pc/lr and address with no match
    hf = ARMHardFaultReport(pc_faulting=None, lr_exc_return=0x0500)
    report = UARTReport(crash_type=CrashType.ARM_HARDFAULT, summary_title="Test", arm_hardfault=hf)
    report = st.symbolicate(report)
    assert report.arm_hardfault.symbolicated_pc is None
    assert report.arm_hardfault.symbolicated_lr is None
