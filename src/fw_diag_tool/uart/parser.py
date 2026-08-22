from __future__ import annotations

import re

from .models import (
    ARMHardFaultReport,
    CallTraceFrame,
    CrashType,
    KernelPanicReport,
    UARTReport,
)


class UARTCrashParser:
    # Parses Linux Kernel Panic and ARM Cortex-M HardFault dumps

    @classmethod
    def parse_log_text(cls, log_text: str) -> UARTReport:
        text = log_text.strip()
        lines = text.splitlines()

        # Check for ARM Cortex-M HardFault
        if any(keyword in text for keyword in ("HardFault", "HFSR", "CFSR", "Stacked R0", "MMFSR", "BFSR")):
            hf_report = cls.parse_arm_hardfault(text)
            return UARTReport(
                crash_type=CrashType.ARM_HARDFAULT,
                summary_title="ARM Cortex-M HardFault Crash Dump",
                arm_hardfault=hf_report,
                raw_log_lines=len(lines)
            )

        # Check for Linux Kernel Panic / Oops
        if any(keyword in text for keyword in ("Kernel panic", "BUG:", "Oops:", "Call Trace:", "RIP:")):
            kp_report = cls.parse_kernel_panic(text)
            return UARTReport(
                crash_type=CrashType.KERNEL_PANIC,
                summary_title=f"Linux Kernel Panic: {kp_report.panic_reason}",
                kernel_panic=kp_report,
                raw_log_lines=len(lines)
            )

        return UARTReport(
            crash_type=CrashType.GENERIC_LOG,
            summary_title="Generic Serial Boot Log / Normal Output",
            raw_log_lines=len(lines)
        )

    @classmethod
    def parse_kernel_panic(cls, text: str) -> KernelPanicReport:
        lines = text.splitlines()
        arch = "x86_64" if "RIP:" in text or "RAX:" in text else ("ARM64" if "PC is at" in text or "x0:" in text else "Generic")
        reason = "Fatal Kernel Exception / Panic"
        faulting_ip = None
        faulting_func = None
        faulting_addr = None
        regs: dict[str, str] = {}
        call_trace: list[CallTraceFrame] = []
        in_call_trace = False

        for line in lines:
            line_s = line.strip()

            if "BUG: unable to handle" in line_s or "Kernel panic" in line_s or "Oops:" in line_s:
                reason = line_s
                m_addr = re.search(r"address:?\s*([0-9a-fA-Fx]+)", line_s)
                if m_addr:
                    faulting_addr = m_addr.group(1)

            m_rip = re.search(r"(?:RIP|PC):\s*(?:[0-9a-fA-F]+:)?(?:\[?<([0-9a-fA-F]+)>\]?|\[([0-9a-fA-F]+)\])?\s*([A-Za-z0-9_]+)\+([0-9a-fA-Fx]+)/([0-9a-fA-Fx]+)(?:\s*\[([A-Za-z0-9_]+)\])?", line_s)
            if m_rip:
                faulting_ip = m_rip.group(1) or m_rip.group(2) or "N/A"
                faulting_func = m_rip.group(3)
                regs["IP_FUNC"] = f"{faulting_func}+{m_rip.group(4)}" + (f" [{m_rip.group(6)}]" if m_rip.group(6) else "")

            for m_reg in re.finditer(r"([A-Z0-9_]{2,4}):\s*([0-9a-fA-F]{8,16})", line_s):
                r_name = m_reg.group(1)
                r_val = m_reg.group(2)
                if r_name not in ("RIP", "RSP", "EIP", "ESP", "CR2"):
                    regs[r_name] = f"0x{r_val}"
                elif r_name == "CR2":
                    faulting_addr = f"0x{r_val}"

            if "Call Trace:" in line_s:
                in_call_trace = True
                continue

            if in_call_trace:
                if not line_s or line_s.startswith("Code:") or line_s.startswith("Kernel panic") or line_s.startswith("CR2:"):
                    in_call_trace = False
                else:
                    m_frame = re.search(r"(?:\[?<([0-9a-fA-F]+)>\]?|\[([0-9a-fA-F]+)\])\s*([A-Za-z0-9_]+)\+([0-9a-fA-Fx]+)/([0-9a-fA-Fx]+)(?:\s*\[([A-Za-z0-9_]+)\])?", line_s)
                    if m_frame:
                        call_trace.append(CallTraceFrame(
                            index=len(call_trace) + 1,
                            address=f"0x{m_frame.group(1) or m_frame.group(2)}",
                            function_name=m_frame.group(3),
                            offset=f"+{m_frame.group(4)}",
                            module=m_frame.group(6),
                            raw_line=line_s
                        ))

        rc_lines = []
        checklist = []
        if faulting_addr and int(faulting_addr, 0) < 0x1000:
            rc_lines.append(f"💥 【NULL Pointer Dereference】存取位址 {faulting_addr} 落在 Page 0 (0x00~0x1000) 範圍，表示程式碼解引用了 NULL 指標。")
            checklist.append("檢查驅動 probe/open 流程中是否對 kzalloc/kmalloc/devm_* 回傳值進行了 NULL 檢查。")
            checklist.append("反組譯肇事函式檢查出錯行號對應之 C 語言結構體指標變數。")
        else:
            rc_lines.append(f"💥 【Kernel Exception】核心在執行函式時發生異常 (位址: {faulting_addr or 'N/A'})。")
            checklist.append("使用 gdb / addr2line (addr2line -e vmlinux <RIP_ADDR>) 定位確切原始碼行號。")
            checklist.append("檢查 Call Trace 頂層函式的傳入參數與本地陣列邊界，確認是否發生 Stack Corruption。")

        return KernelPanicReport(
            architecture=arch,
            panic_reason=reason,
            faulting_ip=faulting_ip,
            faulting_func=faulting_func,
            faulting_address=faulting_addr,
            registers=regs,
            call_trace=call_trace,
            root_cause_analysis="\n".join(rc_lines),
            actionable_checklist=checklist
        )

    @classmethod
    def parse_arm_hardfault(cls, text: str) -> ARMHardFaultReport:
        def extract_hex(pattern: str) -> int | None:
            m = re.search(pattern, text, re.IGNORECASE)
            return int(m.group(1), 16) if m else None

        hfsr = extract_hex(r"HFSR\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)") or 0
        cfsr = extract_hex(r"CFSR\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)") or 0
        bfar = extract_hex(r"BFAR\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")
        pc = extract_hex(r"(?:PC|Faulting\s*PC|Stacked\s*PC)\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")
        lr = extract_hex(r"(?:LR|Stacked\s*LR)\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")
        r0 = extract_hex(r"R0\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")
        r1 = extract_hex(r"R1\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")
        r2 = extract_hex(r"R2\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")
        r3 = extract_hex(r"R3\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")
        r12 = extract_hex(r"R12\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")
        xpsr = extract_hex(r"(?:xPSR|PSR)\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)")

        ufsr = (cfsr >> 16) & 0xFFFF
        bfsr = (cfsr >> 8) & 0xFF
        mmfsr = cfsr & 0xFF

        fault_flags = []
        rc_lines = []
        checklist = []

        if hfsr & (1 << 30):
            fault_flags.append("HFSR.FORCED (HardFault generated by escalation of a configurable fault)")
        if hfsr & (1 << 1):
            fault_flags.append("HFSR.VECTTBL (Vector Table Read Fault on Exception Processing)")

        if ufsr & (1 << 9):
            fault_flags.append("UFSR.DIVBYZERO (Division by Zero trapped)")
            rc_lines.append("💥 【除以零錯誤 (DIVBYZERO)】程式碼中執行了除以 0 運算。")
            checklist.append("檢查運算式分母變數，於除法前加入 if (denom == 0) 防護。")
        if ufsr & (1 << 8):
            fault_flags.append("UFSR.UNALIGNED (Unaligned memory access trapped)")
            rc_lines.append("💥 【記憶體未對齊存取 (UNALIGNED)】以 32-bit (uint32_t*) 讀寫了非 4 位元組對齊的記憶體位址。")
            checklist.append("檢查指標強制型別轉換 (如 (uint32_t*)&buf[1])，改用 memcpy 或 __packed 結構體。")
        if ufsr & (1 << 0):
            fault_flags.append("UFSR.UNDEFINSTR (Undefined instruction executed)")
            rc_lines.append("💥 【未定義指令 (UNDEFINSTR)】CPU 嘗試執行非法 Opcode，通常為函式指標跑飛或 Flash 程式碼被覆蓋。")

        if bfsr & (1 << 2):
            fault_flags.append("BFSR.IMPRECISERR (Imprecise Data Bus Error - asynchronous bus write fault)")
            rc_lines.append("💥 【非精確總線錯誤 (IMPRECISERR)】周邊匯流排寫入無效位址（例如存取了未開時鐘的周邊暫存器）。")
            checklist.append("檢查是否有周邊在 RCC Clock 未開啟前就被寫入暫存器。")
            checklist.append("在啟動代碼中暫時開啟 SCB->ACTLR |= SCB_ACTLR_DISDEFWBUF_Msk 禁用 Write Buffer 以強制轉為 Precise 錯誤抓取精確行號。")
        if bfsr & (1 << 1):
            addr_s = f"0x{bfar:08X}" if bfar else "N/A"
            fault_flags.append(f"BFSR.PRECISERR (Precise Data Bus Error at address: {addr_s})")
            rc_lines.append(f"💥 【精確總線錯誤 (PRECISERR)】存取了非法實體位址 {addr_s}。")

        if pc is not None:
            checklist.append(f"使用 arm-none-eabi-addr2line -e firmware.elf 0x{pc:08X} 定位出錯源碼行號。")

        return ARMHardFaultReport(
            hfsr_raw=hfsr,
            cfsr_raw=cfsr,
            mmfsr_raw=mmfsr,
            bfsr_raw=bfsr,
            ufsr_raw=ufsr,
            bfar_raw=bfar,
            r0=r0, r1=r1, r2=r2, r3=r3, r12=r12,
            lr_exc_return=lr,
            pc_faulting=pc,
            xpsr=xpsr,
            fault_flags=fault_flags,
            root_cause_analysis="\n".join(rc_lines) if rc_lines else "ARM Cortex-M HardFault Exception Triggered.",
            actionable_checklist=checklist
        )