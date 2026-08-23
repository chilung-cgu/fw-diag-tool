"""Peripheral Sensor Decoders for Common I2C Chips.

Decodes register reads and writes for LM75/TMP102, INA219/INA226,
PCA9555/TCA9539 GPIO Expanders, and generic register-based I2C sensors.
"""

from __future__ import annotations

from typing import Any


def _validate_bytes(data_bytes: list[int]) -> None:
    if not isinstance(data_bytes, list):
        raise TypeError("data_bytes must be a list of integers")
    for index, value in enumerate(data_bytes):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
            raise ValueError(f"data_bytes[{index}] must be an integer in range 0..0xFF")


def _validate_pointer(reg_pointer: int | None) -> int | None:
    if reg_pointer is None:
        return None
    if (
        isinstance(reg_pointer, bool)
        or not isinstance(reg_pointer, int)
        or not 0 <= reg_pointer <= 0xFF
    ):
        raise ValueError("reg_pointer must be None or an integer in range 0..0xFF")
    return reg_pointer


def decode_lm75_temperature(data_bytes: list[int]) -> dict[str, Any]:
    """Decode 9-bit/12-bit two's complement temperature from LM75/TMP75/TMP102."""
    _validate_bytes(data_bytes)
    if len(data_bytes) < 2:
        if len(data_bytes) == 1:
            raw_8bit = data_bytes[0]
            temp_c = raw_8bit if raw_8bit < 128 else raw_8bit - 256
            return {
                "temp_c": float(temp_c),
                "evidence": "truncated",
                "is_complete": False,
                "required_bytes": 2,
                "received_bytes": 1,
                "summary": f"Temperature = {temp_c:.1f} °C (8-bit MSB)",
            }
        return {
            "evidence": "truncated",
            "is_complete": False,
            "required_bytes": 2,
            "received_bytes": 0,
            "summary": "Temperature data unavailable",
        }

    raw_16 = (data_bytes[0] << 8) | data_bytes[1]

    # 12-bit standard (TMP102 / high-res LM75)
    raw_12 = raw_16 >> 4
    if raw_12 & 0x0800:
        signed_12 = raw_12 - 4096
    else:
        signed_12 = raw_12
    temp_12bit = signed_12 * 0.0625

    # 9-bit classic LM75 (0.5°C step)
    raw_9 = raw_16 >> 7
    if raw_9 & 0x0100:
        signed_9 = raw_9 - 512
    else:
        signed_9 = raw_9
    temp_9bit = signed_9 * 0.5

    return {
        "temp_c": round(temp_12bit, 4),
        "temp_c_9bit": round(temp_9bit, 1),
        "raw_hex": f"0x{raw_16:04X}",
        "summary": f"Temperature = {temp_12bit:.2f} °C (LM75/TMP102, raw 0x{raw_16:04X})",
    }


def decode_ina2xx_power(reg_pointer: int | None, data_bytes: list[int]) -> dict[str, Any]:
    """Decode INA219 / INA226 Voltage, Current, and Power registers."""
    _validate_bytes(data_bytes)
    _validate_pointer(reg_pointer)
    ptr = reg_pointer if reg_pointer is not None else 0x00
    reg_names = {
        0x00: "CONFIGURATION",
        0x01: "SHUNT_VOLTAGE",
        0x02: "BUS_VOLTAGE",
        0x03: "POWER",
        0x04: "CURRENT",
        0x05: "CALIBRATION",
        0x06: "MASK_ENABLE",
        0x07: "ALERT_LIMIT",
    }
    reg_name = reg_names.get(ptr, f"REG_0x{ptr:02X}")

    if len(data_bytes) < 2:
        return {
            "register": reg_name,
            "evidence": "truncated",
            "is_complete": False,
            "required_bytes": 2,
            "received_bytes": len(data_bytes),
            "summary": f"{reg_name}: " + " ".join(f"0x{b:02X}" for b in data_bytes),
        }

    raw_16 = (data_bytes[0] << 8) | data_bytes[1]
    res: dict[str, Any] = {"register": reg_name, "raw_16": f"0x{raw_16:04X}"}

    if ptr == 0x02:  # BUS_VOLTAGE
        # INA226: LSB = 1.25 mV; INA219: bits [15:3] * 4 mV
        ina226_v = raw_16 * 0.00125
        ina219_v = (raw_16 >> 3) * 0.004
        res["bus_voltage_v"] = round(ina226_v, 3)
        res["summary"] = f"BUS_VOLTAGE = {ina226_v:.3f} V (INA226) / {ina219_v:.3f} V (INA219)"
    elif ptr == 0x01:  # SHUNT_VOLTAGE
        # INA226: LSB = 2.5 uV, INA219: LSB = 10 uV (signed 16-bit)
        signed_val = raw_16 if raw_16 < 32768 else raw_16 - 65536
        shunt_mv = (signed_val * 2.5) / 1000.0
        res["shunt_mv"] = round(shunt_mv, 4)
        res["summary"] = f"SHUNT_VOLTAGE = {shunt_mv:.4f} mV"
    elif ptr == 0x00:  # CONFIG
        res["summary"] = f"CONFIGURATION = 0x{raw_16:04X}"
    else:
        res["summary"] = f"{reg_name} = 0x{raw_16:04X}"

    return res


def decode_pca9555_gpio(reg_pointer: int | None, data_bytes: list[int]) -> dict[str, Any]:
    """Decode PCA9555 / TCA9539 16-bit GPIO expander register accesses."""
    _validate_bytes(data_bytes)
    _validate_pointer(reg_pointer)
    ptr = reg_pointer if reg_pointer is not None else 0x00
    reg_names = {
        0x00: "INPUT_PORT_0",
        0x01: "INPUT_PORT_1",
        0x02: "OUTPUT_PORT_0",
        0x03: "OUTPUT_PORT_1",
        0x04: "POLARITY_INV_PORT_0",
        0x05: "POLARITY_INV_PORT_1",
        0x06: "CONFIG_DIR_PORT_0",
        0x07: "CONFIG_DIR_PORT_1",
    }
    reg_name = reg_names.get(ptr, f"REG_0x{ptr:02X}")

    if not data_bytes:
        return {"register": reg_name, "summary": f"{reg_name} pointer set"}

    byte_strs = [f"0b{b:08b} (0x{b:02X})" for b in data_bytes]
    summary = f"{reg_name} = " + ", ".join(byte_strs)

    return {
        "register": reg_name,
        "bytes": [f"0x{b:02X}" for b in data_bytes],
        "summary": summary,
    }
