from __future__ import annotations


class VirtualSPIFlashW25Q128:
    # Simulates a Winbond W25Q128 SPI NOR Flash (128 Mbit / 16 MB)

    JEDEC_ID = [0xEF, 0x40, 0x18]

    def __init__(self, total_size: int = 16777216):
        if isinstance(total_size, bool) or not isinstance(total_size, int) or total_size <= 0:
            raise ValueError("total_size must be a positive integer")
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
        self._validate_address(address)
        self._validate_bytes(data)
        if not data or len(data) > 256:
            raise ValueError("page program data length must be in range 1..256")
        if not self.wel_latched:
            return False
        start_offset = address & 0xFF
        addresses = [
            (address & ~0xFF) + ((start_offset + index) % 256) for index in range(len(data))
        ]
        if any(addr >= self.total_size for addr in addresses):
            raise ValueError("page program address exceeds flash capacity")
        for addr, val in zip(addresses, data):
            self.memory[addr] = val
        self.wel_latched = False
        self.busy = True
        return True

    def sector_erase(self, address: int) -> bool:
        self._validate_address(address)
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
        self._validate_address(address)
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise ValueError("length must be a non-negative integer")
        if address + length > self.total_size:
            raise ValueError("read exceeds flash capacity")
        return list(self.memory[address : address + length])

    def _validate_address(self, address: int) -> None:
        if (
            isinstance(address, bool)
            or not isinstance(address, int)
            or not 0 <= address < self.total_size
        ):
            raise ValueError(f"address must be an integer in range 0..0x{self.total_size - 1:X}")

    @staticmethod
    def _validate_bytes(data: list[int]) -> None:
        if not isinstance(data, list):
            raise TypeError("data must be a list of integers")
        for index, value in enumerate(data):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
                raise ValueError(f"data[{index}] must be an integer in range 0..0xFF")
