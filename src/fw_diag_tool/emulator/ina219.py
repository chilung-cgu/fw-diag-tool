from __future__ import annotations

import math
from typing import Any


class VirtualINA219:
    """Simulates a Texas Instruments INA219 Bidirectional Current/Power Monitor."""

    REG_CONFIG: int = 0x00
    REG_SHUNT_V: int = 0x01
    REG_BUS_V: int = 0x02
    REG_POWER: int = 0x03
    REG_CURRENT: int = 0x04
    REG_CALIBRATION: int = 0x05

    def __init__(
        self,
        addr_7bit: int = 0x40,
        shunt_ohms: float = 0.1,
        max_expected_amps: float = 3.2,
    ):
        if (
            isinstance(addr_7bit, bool)
            or not isinstance(addr_7bit, int)
            or not 0 <= addr_7bit <= 0x7F
        ):
            raise ValueError("addr_7bit must be an integer in range 0..0x7F")
        if (
            isinstance(shunt_ohms, bool)
            or not isinstance(shunt_ohms, (int, float))
            or not math.isfinite(float(shunt_ohms))
            or shunt_ohms <= 0
        ):
            raise ValueError("shunt_ohms must be a positive finite number")
        if (
            isinstance(max_expected_amps, bool)
            or not isinstance(max_expected_amps, (int, float))
            or not math.isfinite(float(max_expected_amps))
            or max_expected_amps <= 0
        ):
            raise ValueError("max_expected_amps must be a positive finite number")

        self.addr = addr_7bit
        self.shunt_ohms: float = float(shunt_ohms)
        self.current_lsb_ma: float = (float(max_expected_amps) / 32768.0) * 1000.0
        if self.current_lsb_ma <= 0:
            self.current_lsb_ma = 0.1

        self.config_reg: int = 0x399F
        self.cal_reg: int = 0x0000
        self.shunt_voltage_uv: float = 0.0
        self.bus_voltage_v: float = 0.0
        self.last_cmd: int = 0x00
        self.overflow: bool = False

    def set_shunt_resistance(self, ohms: float) -> None:
        if (
            isinstance(ohms, bool)
            or not isinstance(ohms, (int, float))
            or not math.isfinite(float(ohms))
            or ohms <= 0
        ):
            raise ValueError("shunt resistance (ohms) must be a positive finite number")
        self.shunt_ohms = float(ohms)

    def set_bus_voltage(self, volts: float) -> None:
        if (
            isinstance(volts, bool)
            or not isinstance(volts, (int, float))
            or not math.isfinite(float(volts))
            or not 0.0 <= float(volts) <= 32.0
        ):
            raise ValueError("bus voltage (volts) must be a finite number between 0.0 and 32.0V")
        self.bus_voltage_v = float(volts)

    def set_shunt_voltage(self, microvolts: float) -> None:
        if (
            isinstance(microvolts, bool)
            or not isinstance(microvolts, (int, float))
            or not math.isfinite(float(microvolts))
            or not -320000.0 <= float(microvolts) <= 320000.0
        ):
            raise ValueError(
                "shunt voltage (microvolts) must be a finite number between -320000.0 and +320000.0 uV"
            )
        self.shunt_voltage_uv = float(microvolts)

    def set_current_lsb(self, lsb_ma: float) -> None:
        if (
            isinstance(lsb_ma, bool)
            or not isinstance(lsb_ma, (int, float))
            or not math.isfinite(float(lsb_ma))
            or lsb_ma <= 0
        ):
            raise ValueError("current_lsb_ma must be a positive finite number")
        self.current_lsb_ma = float(lsb_ma)

    def calculate_expected_calibration(
        self, current_lsb_ma: float | None = None, shunt_ohms: float | None = None
    ) -> int:
        c_lsb = current_lsb_ma if current_lsb_ma is not None else self.current_lsb_ma
        r_shunt = shunt_ohms if shunt_ohms is not None else self.shunt_ohms
        if c_lsb <= 0 or r_shunt <= 0:
            return 0
        cal = int(0.04096 / ((c_lsb / 1000.0) * r_shunt))
        return cal & 0xFFFF

    def write_calibration(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF:
            raise ValueError("calibration register value must be an integer in range 0..0xFFFF")
        self.cal_reg = value

    def calculate_current(self) -> float:
        if self.cal_reg == 0:
            return 0.0
        raw_shunt = round(self.shunt_voltage_uv / 10.0)
        raw_current = (raw_shunt * self.cal_reg) // 4096
        return float(raw_current * self.current_lsb_ma)

    def calculate_power(self) -> float:
        if self.cal_reg == 0:
            return 0.0
        raw_power = self.read_register(self.REG_POWER)
        power_lsb_mw = 20.0 * self.current_lsb_ma
        return float(raw_power * power_lsb_mw)

    def read_register(self, addr: int) -> int:
        if isinstance(addr, bool) or not isinstance(addr, int) or not 0 <= addr <= 5:
            raise ValueError(f"unsupported INA219 register address: {addr}")
        if addr == self.REG_CONFIG:
            return self.config_reg & 0xFFFF
        if addr == self.REG_SHUNT_V:
            raw = round(self.shunt_voltage_uv / 10.0)
            raw = max(-32768, min(32767, raw))
            return raw & 0xFFFF
        if addr == self.REG_BUS_V:
            raw_13bit = round((self.bus_voltage_v * 1000.0) / 4.0) & 0x1FFF
            return ((raw_13bit << 3) | (1 << 1) | (1 if self.overflow else 0)) & 0xFFFF
        if addr == self.REG_POWER:
            if self.cal_reg == 0:
                return 0
            raw_shunt = round(self.shunt_voltage_uv / 10.0)
            raw_current_signed = (raw_shunt * self.cal_reg) // 4096
            raw_bus = round((self.bus_voltage_v * 1000.0) / 4.0) & 0x1FFF
            raw_power = (abs(raw_current_signed) * raw_bus) // 5000
            if raw_power > 0xFFFF:
                self.overflow = True
                raw_power = 0xFFFF
            return raw_power & 0xFFFF
        if addr == self.REG_CURRENT:
            if self.cal_reg == 0:
                return 0
            raw_shunt = round(self.shunt_voltage_uv / 10.0)
            raw_current = (raw_shunt * self.cal_reg) // 4096
            raw_current = max(-32768, min(32767, raw_current))
            return raw_current & 0xFFFF
        if addr == self.REG_CALIBRATION:
            return self.cal_reg & 0xFFFF
        return 0

    def write(self, data_bytes: list[int]) -> dict[str, Any]:
        if not isinstance(data_bytes, list):
            raise TypeError("data_bytes must be a list of integers")
        for index, value in enumerate(data_bytes):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
                raise ValueError(f"data_bytes[{index}] must be an integer in range 0..0xFF")
        if not data_bytes:
            return {"type": "Address Probe", "summary": "INA219 Address Probe"}

        ptr_reg = data_bytes[0]
        if ptr_reg not in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05):
            raise ValueError(f"unsupported INA219 register pointer: 0x{ptr_reg:02X}")
        self.last_cmd = ptr_reg
        ptr_names = {
            0x00: "CONFIG",
            0x01: "SHUNT_V",
            0x02: "BUS_V",
            0x03: "POWER",
            0x04: "CURRENT",
            0x05: "CALIBRATION",
        }
        name = ptr_names.get(ptr_reg, f"REG_0x{ptr_reg:02X}")

        if len(data_bytes) >= 3:
            val_16bit = (data_bytes[1] << 8) | data_bytes[2]
            if ptr_reg == 0x00:
                self.config_reg = val_16bit
                if val_16bit & 0x8000:
                    self.reset()
                    return {"type": "Reset", "register": name, "summary": "INA219 Reset executed"}
                return {
                    "type": "Write Register",
                    "register": name,
                    "value": val_16bit,
                    "summary": f"Write CONFIG = 0x{val_16bit:04X}",
                }
            if ptr_reg == 0x05:
                self.write_calibration(val_16bit)
                return {
                    "type": "Write Register",
                    "register": name,
                    "value": val_16bit,
                    "summary": f"Write CALIBRATION = 0x{val_16bit:04X}",
                }
            return {
                "type": "Write Register",
                "register": name,
                "value": val_16bit,
                "summary": f"Ignored write to read-only register {name}",
            }

        return {
            "type": "Set Register Pointer",
            "register": name,
            "summary": f"Set pointer to {name} (0x{ptr_reg:02X})",
        }

    def read(self, num_bytes: int = 2) -> bytes:
        if isinstance(num_bytes, bool) or not isinstance(num_bytes, int) or num_bytes < 0:
            raise ValueError("num_bytes must be a non-negative integer")
        if num_bytes > 2:
            raise ValueError(f"read requests {num_bytes} byte(s), but register provides 2 byte(s)")
        ptr = self.last_cmd
        val = self.read_register(ptr)
        raw = bytes([(val >> 8) & 0xFF, val & 0xFF])
        return raw[:num_bytes]

    def reset(self) -> None:
        self.config_reg = 0x399F
        self.cal_reg = 0x0000
        self.overflow = False
        self.last_cmd = 0x00
