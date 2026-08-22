from __future__ import annotations


class VirtualSPIFlashW25Q128:
    # Simulates a Winbond W25Q128 SPI NOR Flash (128 Mbit / 16 MB)

    JEDEC_ID = [0xEF, 0x40, 0x18]

    def __init__(self, total_size: int = 16777216):
        self.total_size = total_size
        self.memory: bytearray = bytearray(total_size)
        self.wel_latched = False
        self.busy = False

    def read_jedec_id(self) -> list[int]:
        return list(self.JEDEC_ID)

    def write_enable(self) -> None:
        self.wel_latched = True

    def write_disable(self) -> None:
        self.wel_latched = False

    def page_program(self, address: int, data: list[int]) -> bool:
        if not self.wel_latched:
            return False
        start_offset = address & 0xFF
        for i, val in enumerate(data):
            addr = (address & ~0xFF) + ((start_offset + i) % 256)
            if addr < self.total_size:
                self.memory[addr] = val & 0xFF
        self.wel_latched = False
        self.busy = True
        return True

    def sector_erase(self, address: int) -> bool:
        if not self.wel_latched:
            return False
        sector_start = (address // 4096) * 4096
        for i in range(4096):
            addr = sector_start + i
            if addr < self.total_size:
                self.memory[addr] = 0xFF
        self.wel_latched = False
        self.busy = True
        return True

    def read_data(self, address: int, length: int) -> list[int]:
        result = []
        for i in range(length):
            addr = address + i
            if addr < self.total_size:
                result.append(self.memory[addr])
            else:
                result.append(0xFF)
        return result
