from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CrashType(str, Enum):
    KERNEL_PANIC = "Linux Kernel Panic / Oops"
    ARM_HARDFAULT = "ARM Cortex-M HardFault"
    WATCHDOG_RESET = "Hardware Watchdog Timeout Reset"
    GENERIC_LOG = "Generic Serial Log / Boot Trace"


@dataclass
class CallTraceFrame:
    index: int
    function_name: str
    offset: str
    module: str | None = None
    address: str | None = None
    raw_line: str = ""


@dataclass
class KernelPanicReport:
    architecture: str  # "x86_64", "ARM64", "ARM32", "RISC-V"
    panic_reason: str
    faulting_ip: str | None = None  # RIP / PC
    faulting_func: str | None = None
    faulting_address: str | None = None  # CR2 / FAR
    registers: dict[str, str] = field(default_factory=dict)
    call_trace: list[CallTraceFrame] = field(default_factory=list)
    modules_linked: list[str] = field(default_factory=list)
    root_cause_analysis: str = ""
    actionable_checklist: list[str] = field(default_factory=list)


@dataclass
class ARMHardFaultReport:
    hfsr_raw: int = 0
    cfsr_raw: int = 0
    mmfsr_raw: int = 0
    bfsr_raw: int = 0
    ufsr_raw: int = 0
    bfar_raw: int | None = None
    mmfar_raw: int | None = None
    # Stacked registers
    r0: int | None = None
    r1: int | None = None
    r2: int | None = None
    r3: int | None = None
    r12: int | None = None
    lr_exc_return: int | None = None
    pc_faulting: int | None = None
    xpsr: int | None = None
    # Fault breakdown flags
    fault_flags: list[str] = field(default_factory=list)
    root_cause_analysis: str = ""
    actionable_checklist: list[str] = field(default_factory=list)


@dataclass
class UARTReport:
    crash_type: CrashType
    summary_title: str
    kernel_panic: KernelPanicReport | None = None
    arm_hardfault: ARMHardFaultReport | None = None
    raw_log_lines: int = 0