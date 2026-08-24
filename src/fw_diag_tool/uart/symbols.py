from __future__ import annotations

import bisect
import re
from pathlib import Path

from .models import UARTReport


class SymbolTable:
    """Parses and queries symbol maps (e.g. System.map, nm output) for crash symbolication."""

    def __init__(self, symbols: list[tuple[int, str]] | None = None) -> None:
        self.symbols: list[tuple[int, str]] = sorted(symbols or [], key=lambda x: x[0])
        self._addrs: list[int] = [addr for addr, _ in self.symbols]

    @classmethod
    def from_system_map(cls, content_or_path: str | Path) -> SymbolTable:
        if isinstance(content_or_path, Path):
            text = content_or_path.read_text(encoding="utf-8")
        elif "\n" not in content_or_path and Path(content_or_path).exists():
            text = Path(content_or_path).read_text(encoding="utf-8")
        else:
            text = str(content_or_path)
        symbols: list[tuple[int, str]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(
                r"^(?:0x)?([0-9a-fA-F]+)(?:\s+[a-zA-Z]\s+|\s*[:\s]\s*)([a-zA-Z0-9_$.]+)",
                line,
            )
            if m:
                try:
                    addr = int(m.group(1), 16)
                    name = m.group(2).strip()
                    symbols.append((addr, name))
                except ValueError:
                    continue
        return cls(symbols)

    def lookup(self, address: int) -> tuple[str, int] | None:
        if not self.symbols:
            return None
        idx = bisect.bisect_right(self._addrs, address) - 1
        if idx < 0:
            return None
        sym_addr, sym_name = self.symbols[idx]
        offset = address - sym_addr
        return sym_name, offset

    def symbolicate(self, report: UARTReport) -> UARTReport:
        if report.arm_hardfault:
            hf = report.arm_hardfault
            if hf.pc_faulting is not None:
                match = self.lookup(hf.pc_faulting)
                if match:
                    name, offset = match
                    hf.symbolicated_pc = f"{name}+0x{offset:X}"
            if hf.lr_exc_return is not None:
                match = self.lookup(hf.lr_exc_return)
                if match:
                    name, offset = match
                    hf.symbolicated_lr = f"{name}+0x{offset:X}"
        if report.kernel_panic:
            kp = report.kernel_panic
            if kp.faulting_ip and kp.faulting_ip.startswith("0x"):
                try:
                    ip_val = int(kp.faulting_ip, 16)
                    match = self.lookup(ip_val)
                    if match:
                        name, offset = match
                        kp.symbolicated_ip = f"{name}+0x{offset:X}"
                except ValueError:
                    pass
        return report


__all__ = ["SymbolTable"]
