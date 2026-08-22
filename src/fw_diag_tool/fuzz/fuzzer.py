from __future__ import annotations

import random


class FuzzingGenerator:
    """Generates malformed / edge-case inputs for stress-testing parsers."""

    @staticmethod
    def fuzz_i2c_csv(seed: int | None = None, num_rows: int = 50) -> str:
        rng = random.Random(seed)
        header_options = [
            "Time,Packet ID,Address,Read/Write,Data,ACK/NACK",
            "Timestamp,Index,Addr,RW,Bytes,Status",
            "t,id,addr,rw,data,ack",
        ]
        lines = [rng.choice(header_options)]

        addr_choices = ["0x50", "0x48", "0x58", "0x70", "invalid", "", "9999", "N/A"]
        rw_choices = ["Write", "Read", "W", "R", "write", "read", "INVALID", ""]
        ack_choices = ["ACK", "NACK", "OK", "FAIL", ""]
        data_choices = [
            "0x12",
            "0x00 0xFF",
            "AA BB CC",
            "",
            "garbage",
            "NaN",
            "-1",
            "0xFFFFFFFFFFFFFFFFFFFFF",
        ]

        t = 0.001
        for i in range(num_rows):
            t += rng.uniform(0.00001, 0.01)
            row = ",".join(
                [
                    f"{t:.6f}",
                    str(rng.randint(0, 100))
                    if rng.random() > 0.05
                    else rng.choice(["", "NaN", "abc"]),
                    rng.choice(addr_choices),
                    rng.choice(rw_choices),
                    rng.choice(data_choices),
                    rng.choice(ack_choices),
                ]
            )
            lines.append(row)

            # Randomly inject empty lines or comments
            if rng.random() < 0.05:
                lines.append("")
            elif rng.random() < 0.03:
                lines.append("# comment line")
            elif rng.random() < 0.02:
                lines.append(",,,,")

        return "\n".join(lines)

    @staticmethod
    def fuzz_hex_dump(seed: int | None = None, num_lines: int = 20) -> str:
        rng = random.Random(seed)
        lines: list[str] = []
        for _ in range(num_lines):
            n_bytes = rng.randint(0, 16)
            hex_str = " ".join(f"0x{rng.randint(0, 255):02X}" for _ in range(n_bytes))
            lines.append(hex_str)
        return "\n".join(lines)

    @staticmethod
    def fuzz_uart_log(seed: int | None = None) -> str:
        rng = random.Random(seed)
        templates = [
            "BUG: unable to handle page fault for address: {addr}\nRIP: 0010:{func}+0x{off}/0x{sz} [{mod}]\nCall Trace:\n <TASK>\n [ffff888102347d80] {caller}+0x24/0x50",
            "HardFault Exception\nHFSR: 0x{hfsr:08X}\nCFSR: 0x{cfsr:08X}\nStacked PC: 0x{pc:08X}",
            "Kernel panic - not syncing: Attempted to kill init!\nCR2: {cr2}",
            "Random garbage text with no crash pattern\nJust normal log output\nNothing special here",
            "",
        ]
        chosen = rng.choice(templates)
        try:
            return chosen.format(
                addr=f"{rng.randint(0, 0xFFFFFFFF):08X}",
                func=rng.choice(["nvme_probe", "i2c_transfer", "spi_sync", "__kmalloc"]),
                off=f"{rng.randint(0, 255):02X}",
                sz=f"{rng.randint(16, 4096):X}",
                mod=rng.choice(["nvme", "i2c_core", "spi_nor", "kernel"]),
                hfsr=rng.randint(0, 0xFFFFFFFF),
                cfsr=rng.randint(0, 0xFFFFFFFF),
                pc=rng.randint(0, 0xFFFFFFFF),
                cr2=f"0x{rng.randint(0, 0xFFFFFFFF):08X}",
            )
        except Exception:
            return chosen
