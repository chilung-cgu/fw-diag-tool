"""UART Crash Dump Before/After Analysis and Diff Engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .models import UARTReport


@dataclass
class UARTDiffResult:
    crash_type_changed: bool = False
    baseline_crash_type: str = ""
    candidate_crash_type: str = ""
    fault_address_changed: bool = False
    new_symbols: list[str] = field(default_factory=list)
    resolved_symbols: list[str] = field(default_factory=list)
    summary: str = ""
    baseline_fault_address: str | None = None
    candidate_fault_address: str | None = None
    common_symbols: list[str] = field(default_factory=list)

    @property
    def is_identical(self) -> bool:
        """Return True if crash types, fault addresses, and call trace symbols match."""
        return (
            not self.crash_type_changed
            and not self.fault_address_changed
            and len(self.new_symbols) == 0
            and len(self.resolved_symbols) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "crash_type_changed": self.crash_type_changed,
            "baseline_crash_type": self.baseline_crash_type,
            "candidate_crash_type": self.candidate_crash_type,
            "fault_address_changed": self.fault_address_changed,
            "new_symbols": list(self.new_symbols),
            "resolved_symbols": list(self.resolved_symbols),
            "common_symbols": list(self.common_symbols),
            "new_anomalies": list(self.new_symbols),
            "resolved_anomalies": list(self.resolved_symbols),
            "common_anomalies": list(self.common_symbols),
            "summary": self.summary,
            "baseline_fault_address": self.baseline_fault_address,
            "candidate_fault_address": self.candidate_fault_address,
            "is_identical": self.is_identical,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class UARTDiffEngine:
    """Compares baseline vs candidate UART crash dump reports."""

    @classmethod
    def _extract_fault_address(cls, report: UARTReport) -> str | None:
        if report.kernel_panic:
            kp = report.kernel_panic
            return kp.faulting_address or kp.faulting_ip
        if report.arm_hardfault:
            hf = report.arm_hardfault
            if hf.bfar_raw is not None:
                return f"0x{hf.bfar_raw:08X}"
            if hf.mmfar_raw is not None:
                return f"0x{hf.mmfar_raw:08X}"
            if hf.pc_faulting is not None:
                return f"0x{hf.pc_faulting:08X}"
        return None

    @classmethod
    def _extract_symbols(cls, report: UARTReport) -> set[str]:
        symbols: set[str] = set()
        if report.kernel_panic:
            kp = report.kernel_panic
            if kp.faulting_func:
                symbols.add(kp.faulting_func.strip())
            if kp.symbolicated_ip:
                symbols.add(kp.symbolicated_ip.strip())
            for frame in kp.call_trace:
                if frame.function_name and frame.function_name.strip():
                    symbols.add(frame.function_name.strip())
        if report.arm_hardfault:
            hf = report.arm_hardfault
            if hf.symbolicated_pc:
                symbols.add(hf.symbolicated_pc.strip())
            if hf.symbolicated_lr:
                symbols.add(hf.symbolicated_lr.strip())
        return symbols

    @classmethod
    def compare(
        cls,
        baseline_report: UARTReport,
        candidate_report: UARTReport,
    ) -> UARTDiffResult:
        if not isinstance(baseline_report, UARTReport) or not isinstance(
            candidate_report, UARTReport
        ):
            raise TypeError("baseline_report and candidate_report must be UARTReport instances")

        b_crash_type = (
            baseline_report.crash_type.value
            if hasattr(baseline_report.crash_type, "value")
            else str(baseline_report.crash_type)
        )
        c_crash_type = (
            candidate_report.crash_type.value
            if hasattr(candidate_report.crash_type, "value")
            else str(candidate_report.crash_type)
        )
        crash_type_changed = baseline_report.crash_type != candidate_report.crash_type

        b_addr = cls._extract_fault_address(baseline_report)
        c_addr = cls._extract_fault_address(candidate_report)
        fault_address_changed = b_addr != c_addr

        b_syms = cls._extract_symbols(baseline_report)
        c_syms = cls._extract_symbols(candidate_report)
        new_symbols = sorted(c_syms - b_syms)
        resolved_symbols = sorted(b_syms - c_syms)
        common_symbols = sorted(b_syms & c_syms)

        if (
            not crash_type_changed
            and not fault_address_changed
            and not new_symbols
            and not resolved_symbols
        ):
            summary = "Baseline 與 Candidate UART 崩潰報告完全一致，未偵測到差異。"
        else:
            parts = []
            if crash_type_changed:
                parts.append(f"崩潰類型變更（{b_crash_type} -> {c_crash_type}）")
            else:
                parts.append(f"崩潰類型相同（{b_crash_type}）")

            if fault_address_changed:
                parts.append(f"故障位址變更（{b_addr or 'None'} -> {c_addr or 'None'}）")
            else:
                parts.append(f"故障位址相同（{b_addr or 'None'}）")

            parts.append(f"新增 {len(new_symbols)} 個符號")
            parts.append(f"消除 {len(resolved_symbols)} 個符號")
            summary = f"UART 對比結果：{'，'.join(parts)}。"

        return UARTDiffResult(
            crash_type_changed=crash_type_changed,
            baseline_crash_type=b_crash_type,
            candidate_crash_type=c_crash_type,
            fault_address_changed=fault_address_changed,
            new_symbols=new_symbols,
            resolved_symbols=resolved_symbols,
            summary=summary,
            baseline_fault_address=b_addr,
            candidate_fault_address=c_addr,
            common_symbols=common_symbols,
        )


__all__ = ["UARTDiffEngine", "UARTDiffResult"]
