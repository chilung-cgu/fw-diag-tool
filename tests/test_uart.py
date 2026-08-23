from fw_diag_tool.uart.models import CrashType
from fw_diag_tool.uart.parser import UARTCrashParser
from fw_diag_tool.uart.reporter import UARTReporter


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
