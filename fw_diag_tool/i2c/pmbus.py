"""PMBus Protocol Specification & Command Decoder Engine.

Implements PMBus Power System Management Protocol Specification (v1.2 & v1.3).
Decodes standard PMBus commands, Linear11, Linear16 (VOUT_MODE), Direct format,
and expands STATUS bitfields into actionable diagnostic descriptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PMBusDataType(str, Enum):
    """PMBus data payload representation type."""
    NONE = "None"
    BYTE = "1-Byte Unsigned"
    WORD = "2-Byte Word"
    LINEAR11 = "Linear11"
    LINEAR16 = "Linear16 (VOUT)"
    DIRECT = "Direct Mode"
    STATUS_BYTE = "STATUS_BYTE"
    STATUS_WORD = "STATUS_WORD"
    STATUS_VOUT = "STATUS_VOUT"
    STATUS_IOUT = "STATUS_IOUT"
    STATUS_INPUT = "STATUS_INPUT"
    STATUS_TEMPERATURE = "STATUS_TEMPERATURE"
    STATUS_CML = "STATUS_CML"
    BLOCK_READ = "Block Read (ASCII / Raw)"
    BITFIELD = "Bitfield"


@dataclass
class PMBusCommandDef:
    """Definition of a PMBus Standard Command."""
    code: int
    name: str
    data_type: PMBusDataType
    unit: str
    description: str
    write_len: int
    read_len: int


# Standard PMBus Command Dictionary
PMBUS_COMMANDS: dict[int, PMBusCommandDef] = {
    0x00: PMBusCommandDef(0x00, "PAGE", PMBusDataType.BYTE, "", "Set active PMBus control page (rail)", 1, 1),
    0x01: PMBusCommandDef(0x01, "OPERATION", PMBusDataType.BYTE, "", "Turn output on/off, margin high/low", 1, 1),
    0x02: PMBusCommandDef(0x02, "ON_OFF_CONFIG", PMBusDataType.BYTE, "", "Configure pin/command on/off behavior", 1, 1),
    0x03: PMBusCommandDef(0x03, "CLEAR_FAULTS", PMBusDataType.NONE, "", "Clear all latched fault status bits", 0, 0),
    0x04: PMBusCommandDef(0x04, "PHASE", PMBusDataType.BYTE, "", "Set or report phase number", 1, 1),
    0x10: PMBusCommandDef(0x10, "WRITE_PROTECT", PMBusDataType.BYTE, "", "Set write protect level (0x80/0x40/0x20/0x00)", 1, 1),
    0x20: PMBusCommandDef(0x20, "VOUT_MODE", PMBusDataType.BYTE, "", "Output voltage format & exponent mode", 1, 1),
    0x21: PMBusCommandDef(0x21, "VOUT_COMMAND", PMBusDataType.LINEAR16, "V", "Set nominal output voltage target", 2, 2),
    0x22: PMBusCommandDef(0x22, "VOUT_TRIM", PMBusDataType.LINEAR16, "V", "Fine-tune output voltage adjustment", 2, 2),
    0x24: PMBusCommandDef(0x24, "VOUT_MAX", PMBusDataType.LINEAR16, "V", "Maximum permissible output voltage", 2, 2),
    0x25: PMBusCommandDef(0x25, "VOUT_MARGIN_HIGH", PMBusDataType.LINEAR16, "V", "High margin target voltage", 2, 2),
    0x26: PMBusCommandDef(0x26, "VOUT_MARGIN_LOW", PMBusDataType.LINEAR16, "V", "Low margin target voltage", 2, 2),
    0x35: PMBusCommandDef(0x35, "VIN_ON", PMBusDataType.LINEAR11, "V", "Input voltage threshold for power ON", 2, 2),
    0x36: PMBusCommandDef(0x36, "VIN_OFF", PMBusDataType.LINEAR11, "V", "Input voltage threshold for power OFF", 2, 2),
    0x40: PMBusCommandDef(0x40, "OT_FAULT_LIMIT", PMBusDataType.LINEAR11, "°C", "Over-temperature fault trip point", 2, 2),
    0x41: PMBusCommandDef(0x41, "OT_WARN_LIMIT", PMBusDataType.LINEAR11, "°C", "Over-temperature warning threshold", 2, 2),
    0x44: PMBusCommandDef(0x44, "UT_FAULT_LIMIT", PMBusDataType.LINEAR11, "°C", "Under-temperature fault trip point", 2, 2),
    0x46: PMBusCommandDef(0x46, "IOUT_OC_FAULT_LIMIT", PMBusDataType.LINEAR11, "A", "Output over-current fault trip limit", 2, 2),
    0x4A: PMBusCommandDef(0x4A, "IOUT_OC_WARN_LIMIT", PMBusDataType.LINEAR11, "A", "Output over-current warning threshold", 2, 2),
    0x51: PMBusCommandDef(0x51, "OT_FAULT_RESPONSE", PMBusDataType.BYTE, "", "Action taken upon over-temperature fault", 1, 1),
    
    # Status Commands
    0x78: PMBusCommandDef(0x78, "STATUS_BYTE", PMBusDataType.STATUS_BYTE, "", "Summary of critical unit faults", 1, 1),
    0x79: PMBusCommandDef(0x79, "STATUS_WORD", PMBusDataType.STATUS_WORD, "", "Comprehensive unit status word (2 bytes)", 2, 2),
    0x7A: PMBusCommandDef(0x7A, "STATUS_VOUT", PMBusDataType.STATUS_VOUT, "", "Output voltage fault/warning detail", 1, 1),
    0x7B: PMBusCommandDef(0x7B, "STATUS_IOUT", PMBusDataType.STATUS_IOUT, "", "Output current fault/warning detail", 1, 1),
    0x7C: PMBusCommandDef(0x7C, "STATUS_INPUT", PMBusDataType.STATUS_INPUT, "", "Input voltage/current/power status", 1, 1),
    0x7D: PMBusCommandDef(0x7D, "STATUS_TEMPERATURE", PMBusDataType.STATUS_TEMPERATURE, "", "Thermal fault/warning flags", 1, 1),
    0x7E: PMBusCommandDef(0x7E, "STATUS_CML", PMBusDataType.STATUS_CML, "", "Communication, Memory, and Logic faults", 1, 1),
    0x7F: PMBusCommandDef(0x7F, "STATUS_OTHER", PMBusDataType.BYTE, "", "Other miscellaneous status bits", 1, 1),
    
    # Read Telemetry Commands
    0x88: PMBusCommandDef(0x88, "READ_VIN", PMBusDataType.LINEAR11, "V", "Measured Input Voltage", 0, 2),
    0x89: PMBusCommandDef(0x89, "READ_IIN", PMBusDataType.LINEAR11, "A", "Measured Input Current", 0, 2),
    0x8B: PMBusCommandDef(0x8B, "READ_VOUT", PMBusDataType.LINEAR16, "V", "Measured Output Voltage", 0, 2),
    0x8C: PMBusCommandDef(0x8C, "READ_IOUT", PMBusDataType.LINEAR11, "A", "Measured Output Current", 0, 2),
    0x8D: PMBusCommandDef(0x8D, "READ_TEMPERATURE_1", PMBusDataType.LINEAR11, "°C", "Internal / VR Controller Temperature", 0, 2),
    0x8E: PMBusCommandDef(0x8E, "READ_TEMPERATURE_2", PMBusDataType.LINEAR11, "°C", "External Sensor / Power Stage Temperature", 0, 2),
    0x8F: PMBusCommandDef(0x8F, "READ_TEMPERATURE_3", PMBusDataType.LINEAR11, "°C", "Auxiliary Temperature", 0, 2),
    0x90: PMBusCommandDef(0x90, "READ_FAN_SPEED_1", PMBusDataType.LINEAR11, "RPM", "Measured Fan 1 Speed", 0, 2),
    0x96: PMBusCommandDef(0x96, "READ_POUT", PMBusDataType.LINEAR11, "W", "Calculated Output Power", 0, 2),
    0x97: PMBusCommandDef(0x97, "READ_PIN", PMBusDataType.LINEAR11, "W", "Measured Input Power", 0, 2),
    
    # Identification & Revision
    0x98: PMBusCommandDef(0x98, "PMBUS_REVISION", PMBusDataType.BYTE, "", "PMBus Protocol Revision compliance", 0, 1),
    0x99: PMBusCommandDef(0x99, "MFR_ID", PMBusDataType.BLOCK_READ, "", "Manufacturer identification string", 0, 0),
    0x9A: PMBusCommandDef(0x9A, "MFR_MODEL", PMBusDataType.BLOCK_READ, "", "Manufacturer model number string", 0, 0),
    0x9B: PMBusCommandDef(0x9B, "MFR_REVISION", PMBusDataType.BLOCK_READ, "", "Manufacturer revision string", 0, 0),
    0x9C: PMBusCommandDef(0x9C, "MFR_LOCATION", PMBusDataType.BLOCK_READ, "", "Manufacturer plant location", 0, 0),
    0x9D: PMBusCommandDef(0x9D, "MFR_DATE", PMBusDataType.BLOCK_READ, "", "Manufacturer manufacturing date", 0, 0),
    0x9E: PMBusCommandDef(0x9E, "MFR_SERIAL", PMBusDataType.BLOCK_READ, "", "Manufacturer unit serial number", 0, 0),
    0xAD: PMBusCommandDef(0xAD, "IC_DEVICE_ID", PMBusDataType.BLOCK_READ, "", "IC Device ID code", 0, 0),
    0xAE: PMBusCommandDef(0xAE, "IC_DEVICE_REV", PMBusDataType.BLOCK_READ, "", "IC Device Revision", 0, 0),
}


def decode_linear11(raw_word: int) -> float:
    """Decode a 16-bit PMBus Linear11 floating point number.
    
    Format:
      - Bits [15:11]: 5-bit two's complement exponent N (-16 to +15)
      - Bits [10:0]:  11-bit two's complement mantissa Y (-1024 to +1023)
      - Real Value = Y * 2^N
    """
    raw_word &= 0xFFFF
    
    # Extract 5-bit exponent (bits 15..11)
    exponent_raw = (raw_word >> 11) & 0x1F
    if exponent_raw & 0x10:  # Negative exponent (sign bit 4 is set)
        exponent = exponent_raw - 32
    else:
        exponent = exponent_raw
        
    # Extract 11-bit mantissa (bits 10..0)
    mantissa_raw = raw_word & 0x07FF
    if mantissa_raw & 0x0400:  # Negative mantissa (sign bit 10 is set)
        mantissa = mantissa_raw - 2048
    else:
        mantissa = mantissa_raw
        
    return float(mantissa * (2.0 ** exponent))


def encode_linear11(val: float) -> int:
    """Encode a float value into a 16-bit PMBus Linear11 integer."""
    # Find suitable exponent N in [-16, 15] such that mantissa fits in [-1024, 1023]
    if val == 0.0:
        return 0x0000
        
    best_exp = 0
    best_mant = 0
    min_err = float("inf")
    
    for exp in range(-16, 16):
        mant = round(val / (2.0 ** exp))
        if -1024 <= mant <= 1023:
            err = abs(val - mant * (2.0 ** exp))
            if err < min_err:
                min_err = err
                best_exp = exp
                best_mant = mant
                if err == 0:
                    break
                    
    exp_5bit = (best_exp + 32) & 0x1F if best_exp < 0 else (best_exp & 0x1F)
    mant_11bit = (best_mant + 2048) & 0x07FF if best_mant < 0 else (best_mant & 0x07FF)
    return (exp_5bit << 11) | mant_11bit


def decode_linear16(raw_word: int, vout_mode_exponent: int = -9) -> float:
    """Decode a 16-bit PMBus Linear16 output voltage value.
    
    Format:
      - 16-bit unsigned integer (or signed depending on device).
      - Exponent N is obtained from VOUT_MODE command (typically -9, -10, -12, etc.).
      - Real Value = raw_word * 2^N
    """
    raw_word &= 0xFFFF
    return float(raw_word * (2.0 ** vout_mode_exponent))


def parse_vout_mode_exponent(vout_mode_byte: int) -> int:
    """Extract 5-bit two's complement exponent from VOUT_MODE (0x20) register byte."""
    exponent_raw = vout_mode_byte & 0x1F
    if exponent_raw & 0x10:
        return exponent_raw - 32
    return exponent_raw


def decode_status_byte(status_byte: int) -> list[str]:
    """Decode STATUS_BYTE (0x78) into human-readable active fault strings."""
    flags: list[str] = []
    if status_byte & (1 << 7):
        flags.append("BUSY (Device busy / unable to respond)")
    if status_byte & (1 << 6):
        flags.append("OFF (Unit is NOT providing power to output)")
    if status_byte & (1 << 5):
        flags.append("VOUT_OV (Output Over-Voltage Fault)")
    if status_byte & (1 << 4):
        flags.append("IOUT_OC (Output Over-Current Fault)")
    if status_byte & (1 << 3):
        flags.append("VIN_UV (Input Under-Voltage Fault)")
    if status_byte & (1 << 2):
        flags.append("TEMPERATURE (Thermal Fault or Warning)")
    if status_byte & (1 << 1):
        flags.append("CML (Comm/Memory/Logic Error)")
    if status_byte & (1 << 0):
        flags.append("OTHER_FAULT (Unspecified secondary fault)")
    return flags


def decode_status_word(status_word: int) -> list[str]:
    """Decode STATUS_WORD (0x79, 16-bit) into human-readable active fault strings."""
    low_byte = status_word & 0xFF
    high_byte = (status_word >> 8) & 0xFF
    
    flags = decode_status_byte(low_byte)
    
    if high_byte & (1 << 7):
        flags.append("VOUT_FAULT_WARN (Output Voltage Fault or Warning)")
    if high_byte & (1 << 6):
        flags.append("IOUT_POUT_FAULT_WARN (Output Current or Power Fault/Warning)")
    if high_byte & (1 << 5):
        flags.append("INPUT_FAULT_WARN (Input Voltage/Current/Power Fault/Warning)")
    if high_byte & (1 << 4):
        flags.append("MFR_SPECIFIC (Manufacturer Specific Fault/Warning)")
    if high_byte & (1 << 3):
        flags.append("POWER_GOOD# (Power Good Signal is NEGATED / Inactive)")
    if high_byte & (1 << 2):
        flags.append("FAN_FAULT_WARN (Fan or Airflow Fault/Warning)")
    if high_byte & (1 << 1):
        flags.append("STATUS_OTHER_SET (Bit in STATUS_OTHER is set)")
    if high_byte & (1 << 0):
        flags.append("UNKNOWN_FAULT (Unknown fault occurred)")
        
    return flags


def decode_status_cml(cml_byte: int) -> list[str]:
    """Decode STATUS_CML (0x7E) Communication/Memory/Logic fault flags."""
    flags: list[str] = []
    if cml_byte & (1 << 7):
        flags.append("INVALID_COMMAND (Master sent invalid or unsupported command code)")
    if cml_byte & (1 << 6):
        flags.append("INVALID_DATA (Master sent invalid or out-of-range data payload)")
    if cml_byte & (1 << 5):
        flags.append("PEC_FAILED (Packet Error Check checksum mismatch)")
    if cml_byte & (1 << 4):
        flags.append("MEMORY_FAULT (Internal NVM / Flash / RAM fault detected)")
    if cml_byte & (1 << 3):
        flags.append("PROCESSOR_FAULT (Internal core / MCU processor fault)")
    if cml_byte & (1 << 1):
        flags.append("COMM_FAULT (Other communication fault)")
    if cml_byte & (1 << 0):
        flags.append("OTHER_MEM_LOGIC (Other memory or logic fault)")
    return flags


def decode_pmbus_payload(
    cmd_code: int,
    data_bytes: list[int],
    vout_exponent: int = -9
) -> dict[str, Any]:
    """Decode PMBus data bytes into structured telemetry and diagnostics."""
    cmd_def = PMBUS_COMMANDS.get(cmd_code)
    result: dict[str, Any] = {
        "command_code": f"0x{cmd_code:02X}",
        "command_name": cmd_def.name if cmd_def else f"UNKNOWN_CMD_0x{cmd_code:02X}",
        "raw_bytes": [f"0x{b:02X}" for b in data_bytes],
    }
    
    if not data_bytes:
        result["summary"] = f"{result['command_name']} (No Data / Quick Cmd)"
        return result
        
    if not cmd_def:
        result["summary"] = f"Custom PMBus Cmd 0x{cmd_code:02X}: " + " ".join(f"{b:02X}" for b in data_bytes)
        return result
        
    dtype = cmd_def.data_type
    
    # 1. Linear11 Telemetry (READ_VIN, READ_IOUT, READ_TEMPERATURE, READ_PIN, etc.)
    if dtype == PMBusDataType.LINEAR11 and len(data_bytes) >= 2:
        raw_word = data_bytes[0] | (data_bytes[1] << 8)
        val = decode_linear11(raw_word)
        result["value"] = round(val, 4)
        result["unit"] = cmd_def.unit
        result["summary"] = f"{cmd_def.name} = {result['value']} {cmd_def.unit}"
        
    # 2. Linear16 Output Voltage (READ_VOUT, VOUT_COMMAND, etc.)
    elif dtype == PMBusDataType.LINEAR16 and len(data_bytes) >= 2:
        raw_word = data_bytes[0] | (data_bytes[1] << 8)
        val = decode_linear16(raw_word, vout_exponent)
        result["value"] = round(val, 4)
        result["unit"] = cmd_def.unit
        result["summary"] = f"{cmd_def.name} = {result['value']} {cmd_def.unit} (exp={vout_exponent})"
        
    # 3. Status Byte / Word / CML
    elif dtype == PMBusDataType.STATUS_BYTE and len(data_bytes) >= 1:
        status_byte = data_bytes[0]
        faults = decode_status_byte(status_byte)
        result["status_flags"] = faults
        result["is_fault"] = len(faults) > 0
        result["summary"] = f"STATUS_BYTE=0x{status_byte:02X} -> " + (", ".join(faults) if faults else "OK / All Clean")
        
    elif dtype == PMBusDataType.STATUS_WORD and len(data_bytes) >= 2:
        status_word = data_bytes[0] | (data_bytes[1] << 8)
        faults = decode_status_word(status_word)
        result["status_flags"] = faults
        result["is_fault"] = len(faults) > 0
        result["summary"] = f"STATUS_WORD=0x{status_word:04X} -> " + (", ".join(faults) if faults else "OK / All Clean")
        
    elif dtype == PMBusDataType.STATUS_CML and len(data_bytes) >= 1:
        cml_byte = data_bytes[0]
        faults = decode_status_cml(cml_byte)
        result["status_flags"] = faults
        result["is_fault"] = len(faults) > 0
        result["summary"] = f"STATUS_CML=0x{cml_byte:02X} -> " + (", ".join(faults) if faults else "OK / Comm Normal")
        
    # 4. Single Byte Commands (PAGE, OPERATION, ON_OFF_CONFIG, WRITE_PROTECT)
    elif dtype == PMBusDataType.BYTE and len(data_bytes) >= 1:
        b = data_bytes[0]
        if cmd_code == 0x00:  # PAGE
            result["page"] = b
            result["summary"] = f"PAGE = Rail {b}"
        elif cmd_code == 0x01:  # OPERATION
            on_state = "ON" if (b & 0x80) else "OFF"
            margin = "Margin High" if (b & 0x20) else ("Margin Low" if (b & 0x10) else "Nominal")
            result["summary"] = f"OPERATION = {on_state}, {margin} (0x{b:02X})"
        elif cmd_code == 0x10:  # WRITE_PROTECT
            desc = "Entire memory protected" if b == 0x80 else ("Protect all except PAGE/OPERATION" if b == 0x40 else ("Protect all except PAGE/OPERATION/ON_OFF" if b == 0x20 else "Unprotected"))
            result["summary"] = f"WRITE_PROTECT = 0x{b:02X} ({desc})"
        else:
            result["summary"] = f"{cmd_def.name} = 0x{b:02X}"
            
    # 5. Block Read Strings
    elif dtype == PMBusDataType.BLOCK_READ:
        # PMBus Block read has byte count as first byte
        text_bytes = data_bytes[1:] if len(data_bytes) > 0 and data_bytes[0] == len(data_bytes) - 1 else data_bytes
        ascii_str = "".join(chr(c) if 32 <= c <= 126 else "." for c in text_bytes)
        result["string"] = ascii_str
        result["summary"] = f"{cmd_def.name} = '{ascii_str}'"
        
    else:
        result["summary"] = f"{cmd_def.name}: " + " ".join(f"0x{b:02X}" for b in data_bytes)
        
    return result
