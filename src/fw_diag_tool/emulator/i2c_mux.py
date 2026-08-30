from __future__ import annotations

from typing import Any


class VirtualPCA9548A:
    """Simulates an NXP/TI PCA9548A / TCA9548A 8-Channel I2C Bus Multiplexer."""

    NUM_CHANNELS: int = 8

    def __init__(self, addr_7bit: int = 0x70):
        if (
            isinstance(addr_7bit, bool)
            or not isinstance(addr_7bit, int)
            or not 0 <= addr_7bit <= 0x7F
        ):
            raise ValueError("addr_7bit must be an integer in range 0..0x7F")
        self.addr = addr_7bit
        self.control_reg: int = 0x00
        self.downstream_devices: dict[int, list[Any]] = {ch: [] for ch in range(self.NUM_CHANNELS)}

    def select_channel(self, channel: int) -> None:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel < self.NUM_CHANNELS:
            raise ValueError(f"channel must be an integer in range 0..{self.NUM_CHANNELS - 1}")
        self.control_reg = 1 << channel

    def select_channels(self, channels: list[int]) -> None:
        if not isinstance(channels, list):
            raise TypeError("channels must be a list of integer channel numbers")
        mask = 0
        for idx, ch in enumerate(channels):
            if isinstance(ch, bool) or not isinstance(ch, int) or not 0 <= ch < self.NUM_CHANNELS:
                raise ValueError(f"channels[{idx}] must be an integer in range 0..{self.NUM_CHANNELS - 1}")
            mask |= 1 << ch
        self.control_reg = mask

    def deselect_all(self) -> None:
        self.control_reg = 0x00

    def read_control(self) -> int:
        return self.control_reg & 0xFF

    def write_control(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
            raise ValueError("control register value must be an integer in range 0..0xFF")
        self.control_reg = value

    def get_active_channels(self) -> list[int]:
        return [ch for ch in range(self.NUM_CHANNELS) if bool(self.control_reg & (1 << ch))]

    def reset(self) -> None:
        """Simulate hardware active-low RESET# pin asserted."""
        self.control_reg = 0x00

    def attach_device(self, channel: int, device: Any) -> None:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel < self.NUM_CHANNELS:
            raise ValueError(f"channel must be an integer in range 0..{self.NUM_CHANNELS - 1}")
        if device is None:
            raise ValueError("device cannot be None")
        if not hasattr(device, "addr"):
            raise ValueError("device must have an 'addr' attribute indicating its 7-bit I2C address")
        if device not in self.downstream_devices[channel]:
            self.downstream_devices[channel].append(device)

    def detach_device(self, channel: int, device: Any | None = None) -> None:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel < self.NUM_CHANNELS:
            raise ValueError(f"channel must be an integer in range 0..{self.NUM_CHANNELS - 1}")
        if device is None:
            self.downstream_devices[channel].clear()
        elif device in self.downstream_devices[channel]:
            self.downstream_devices[channel].remove(device)

    def get_devices_on_channel(self, channel: int) -> list[Any]:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel < self.NUM_CHANNELS:
            raise ValueError(f"channel must be an integer in range 0..{self.NUM_CHANNELS - 1}")
        return list(self.downstream_devices[channel])

    def detect_address_conflicts(self) -> dict[int, list[tuple[int, Any]]]:
        """Detect if multiple currently active channels host devices sharing the same 7-bit I2C address."""
        active_channels = self.get_active_channels()
        addr_map: dict[int, list[tuple[int, Any]]] = {}
        for ch in active_channels:
            for dev in self.downstream_devices[ch]:
                dev_addr = getattr(dev, "addr", None)
                if dev_addr is not None:
                    addr_map.setdefault(dev_addr, []).append((ch, dev))
        return {addr: items for addr, items in addr_map.items() if len(items) > 1}

    def write(self, data_bytes: list[int]) -> dict[str, Any]:
        if not isinstance(data_bytes, list):
            raise TypeError("data_bytes must be a list of integers")
        for index, value in enumerate(data_bytes):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
                raise ValueError(f"data_bytes[{index}] must be an integer in range 0..0xFF")
        if not data_bytes:
            return {"type": "Address Probe", "summary": "PCA9548A Address Probe"}

        ctrl_byte = data_bytes[0]
        self.write_control(ctrl_byte)
        active_chs = self.get_active_channels()
        ch_str = ", ".join(f"CH{ch}" for ch in active_chs) if active_chs else "None (All Disabled)"
        return {
            "type": "Write Control Register",
            "control": self.control_reg,
            "active_channels": active_chs,
            "summary": f"Set control register to 0x{self.control_reg:02X} (Active: {ch_str})",
        }

    def read(self, num_bytes: int = 1) -> bytes:
        if isinstance(num_bytes, bool) or not isinstance(num_bytes, int) or num_bytes < 0:
            raise ValueError("num_bytes must be a non-negative integer")
        if num_bytes > 1:
            raise ValueError(f"read requests {num_bytes} byte(s), but control register provides 1 byte(s)")
        return bytes([self.control_reg][:num_bytes])

    def route_write(self, addr_7bit: int, data_bytes: list[int]) -> list[dict[str, Any]]:
        """Route an I2C write transaction to all devices matching addr_7bit on active channels."""
        if (
            isinstance(addr_7bit, bool)
            or not isinstance(addr_7bit, int)
            or not 0 <= addr_7bit <= 0x7F
        ):
            raise ValueError("addr_7bit must be an integer in range 0..0x7F")
        active_channels = self.get_active_channels()
        results: list[dict[str, Any]] = []
        for ch in active_channels:
            for dev in self.downstream_devices[ch]:
                if getattr(dev, "addr", None) == addr_7bit and hasattr(dev, "write"):
                    dev_res = dev.write(data_bytes)
                    results.append({"channel": ch, "device": dev, "result": dev_res})
        return results

    def route_read(self, addr_7bit: int, num_bytes: int = 2) -> list[tuple[int, Any, bytes]]:
        """Route an I2C read transaction to devices matching addr_7bit on active channels."""
        if (
            isinstance(addr_7bit, bool)
            or not isinstance(addr_7bit, int)
            or not 0 <= addr_7bit <= 0x7F
        ):
            raise ValueError("addr_7bit must be an integer in range 0..0x7F")
        active_channels = self.get_active_channels()
        results: list[tuple[int, Any, bytes]] = []
        for ch in active_channels:
            for dev in self.downstream_devices[ch]:
                if getattr(dev, "addr", None) == addr_7bit and hasattr(dev, "read"):
                    dev_res = dev.read(num_bytes)
                    results.append((ch, dev, dev_res))
        return results
