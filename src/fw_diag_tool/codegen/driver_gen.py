from __future__ import annotations


class I2CDriverCodeGenerator:
    # Generates ready-to-use C driver snippets across 4 mainstream firmware platforms

    @staticmethod
    def _validate_int(name: str, value: int, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    @classmethod
    def generate_all_snippets(
        cls,
        addr_7bit: int,
        reg_offset: int | None = None,
        data_bytes: list[int] | None = None,
        is_read: bool = False,
        bus_num: int = 1,
        read_length: int | None = None,
        register_width: int = 8,
    ) -> dict[str, str]:
        cls._validate_int("addr_7bit", addr_7bit, 0x08, 0x77)
        cls._validate_int("bus_num", bus_num, 0, 0xFFFF)
        cls._validate_int("register_width", register_width, 8, 16)
        if register_width not in (8, 16):
            raise ValueError("register_width must be 8 or 16 bits")
        if not isinstance(is_read, bool):
            raise TypeError("is_read must be a boolean")

        if reg_offset is not None:
            cls._validate_int("reg_offset", reg_offset, 0, (1 << register_width) - 1)

        if data_bytes is not None and not isinstance(data_bytes, list):
            raise TypeError("data_bytes must be a list of byte values")
        data = list(data_bytes or [])
        for index, value in enumerate(data):
            cls._validate_int(f"data_bytes[{index}]", value, 0, 0xFF)

        if is_read:
            rx_length = read_length if read_length is not None else (len(data) or 1)
            cls._validate_int("read_length", rx_length, 1, 0xFF)
        else:
            if read_length is not None:
                raise ValueError("read_length is only valid for read operations")
            if not data:
                raise ValueError("write operations require at least one data byte")
            rx_length = 0

        addr_hex = f"0x{addr_7bit:02X}"
        if reg_offset is None:
            reg_bytes: list[int] = []
            reg_hex = ""
        elif register_width == 8:
            reg_bytes = [reg_offset]
            reg_hex = f"0x{reg_offset:02X}"
        else:
            reg_bytes = [(reg_offset >> 8) & 0xFF, reg_offset & 0xFF]
            reg_hex = f"0x{reg_offset:04X}"

        tx_bytes = reg_bytes + data
        snippets: dict[str, str] = {}

        if is_read and reg_bytes:
            reg_array = ", ".join(f"0x{value:02X}" for value in reg_bytes)
            snippets["Linux Userspace (i2c-dev)"] = "\n".join(
                [
                    "// Linux Userspace i2c-dev combined register read",
                    f'int file = open("/dev/i2c-{bus_num}", O_RDWR);',
                    f"uint8_t reg_buf[{len(reg_bytes)}] = {{ {reg_array} }};",
                    f"uint8_t rx_buf[{rx_length}];",
                    "struct i2c_msg msgs[2] = {",
                    f"    {{ .addr = {addr_hex}, .flags = 0, .len = sizeof(reg_buf), .buf = reg_buf }},",
                    f"    {{ .addr = {addr_hex}, .flags = I2C_M_RD, .len = sizeof(rx_buf), .buf = rx_buf }},",
                    "};",
                    "struct i2c_rdwr_ioctl_data transfer = { .msgs = msgs, .nmsgs = 2 };",
                    "if (ioctl(file, I2C_RDWR, &transfer) < 0) {",
                    '    perror("Failed to read from I2C device");',
                    "}",
                ]
            )
        elif is_read:
            snippets["Linux Userspace (i2c-dev)"] = "\n".join(
                [
                    "// Linux Userspace i2c-dev direct read",
                    f'int file = open("/dev/i2c-{bus_num}", O_RDWR);',
                    f"ioctl(file, I2C_SLAVE, {addr_hex});",
                    f"uint8_t rx_buf[{rx_length}];",
                    "if (read(file, rx_buf, sizeof(rx_buf)) != sizeof(rx_buf)) {",
                    '    perror("Failed to read from I2C device");',
                    "}",
                ]
            )
        else:
            tx_array = ", ".join(f"0x{value:02X}" for value in tx_bytes)
            snippets["Linux Userspace (i2c-dev)"] = "\n".join(
                [
                    "// Linux Userspace i2c-dev write",
                    f'int file = open("/dev/i2c-{bus_num}", O_RDWR);',
                    f"ioctl(file, I2C_SLAVE, {addr_hex});",
                    f"uint8_t tx_buf[{len(tx_bytes)}] = {{ {tx_array} }};",
                    "if (write(file, tx_buf, sizeof(tx_buf)) != sizeof(tx_buf)) {",
                    '    perror("Failed to write to I2C device");',
                    "}",
                ]
            )

        reg_cli = " ".join(f"0x{value:02X}" for value in reg_bytes)
        if is_read and reg_bytes:
            snippets["OpenBMC / Linux CLI (i2c-tools)"] = "\n".join(
                [
                    f"# Combined register read from {addr_hex} using a repeated START",
                    (
                        f"i2ctransfer -y {bus_num} w{len(reg_bytes)}@{addr_hex} "
                        f"{reg_cli} r{rx_length}"
                    ),
                ]
            )
        elif is_read:
            snippets["OpenBMC / Linux CLI (i2c-tools)"] = "\n".join(
                [
                    f"# Direct read of {rx_length} byte(s) from {addr_hex}",
                    f"i2ctransfer -y {bus_num} r{rx_length}@{addr_hex}",
                ]
            )
        else:
            tx_cli = " ".join(f"0x{value:02X}" for value in tx_bytes)
            snippets["OpenBMC / Linux CLI (i2c-tools)"] = "\n".join(
                [
                    f"# Write {len(data)} data byte(s) to {addr_hex}",
                    f"i2ctransfer -y {bus_num} w{len(tx_bytes)}@{addr_hex} {tx_cli}",
                ]
            )

        data_array = ", ".join(f"0x{value:02X}" for value in data)
        mem_size = f"I2C_MEMADD_SIZE_{register_width}BIT"
        if is_read and reg_offset is not None:
            snippets["STM32 HAL C Driver"] = "\n".join(
                [
                    "// STM32 HAL combined memory read",
                    f"uint8_t rx_buf[{rx_length}];",
                    (
                        "HAL_StatusTypeDef status = HAL_I2C_Mem_Read(&hi2c1, "
                        f"({addr_hex} << 1), {reg_hex}, {mem_size}, rx_buf, "
                        f"{rx_length}, 100);"
                    ),
                    "if (status != HAL_OK) {",
                    "    // Handle I2C NACK or timeout",
                    "}",
                ]
            )
        elif is_read:
            snippets["STM32 HAL C Driver"] = "\n".join(
                [
                    "// STM32 HAL direct read",
                    f"uint8_t rx_buf[{rx_length}];",
                    (
                        "HAL_StatusTypeDef status = HAL_I2C_Master_Receive(&hi2c1, "
                        f"({addr_hex} << 1), rx_buf, {rx_length}, 100);"
                    ),
                    "if (status != HAL_OK) {",
                    "    // Handle I2C NACK or timeout",
                    "}",
                ]
            )
        elif reg_offset is not None:
            snippets["STM32 HAL C Driver"] = "\n".join(
                [
                    "// STM32 HAL memory write",
                    f"uint8_t tx_buf[{len(data)}] = {{ {data_array} }};",
                    (
                        "HAL_StatusTypeDef status = HAL_I2C_Mem_Write(&hi2c1, "
                        f"({addr_hex} << 1), {reg_hex}, {mem_size}, tx_buf, "
                        f"{len(data)}, 100);"
                    ),
                    "if (status != HAL_OK) {",
                    "    // Handle I2C error",
                    "}",
                ]
            )
        else:
            snippets["STM32 HAL C Driver"] = "\n".join(
                [
                    "// STM32 HAL direct write",
                    f"uint8_t tx_buf[{len(data)}] = {{ {data_array} }};",
                    (
                        "HAL_StatusTypeDef status = HAL_I2C_Master_Transmit(&hi2c1, "
                        f"({addr_hex} << 1), tx_buf, {len(data)}, 100);"
                    ),
                    "if (status != HAL_OK) {",
                    "    // Handle I2C error",
                    "}",
                ]
            )

        arduino_reg_lines = [f"Wire.write(0x{value:02X});" for value in reg_bytes]
        if is_read:
            arduino_lines = ["// Arduino Wire combined register read"]
            if reg_bytes:
                arduino_lines.extend([f"Wire.beginTransmission({addr_hex});", *arduino_reg_lines])
                arduino_lines.append("Wire.endTransmission(false); // Repeated START")
            arduino_lines.extend(
                [
                    f"uint8_t rx_buf[{rx_length}];",
                    f"uint8_t received = Wire.requestFrom({addr_hex}, {rx_length});",
                    "for (uint8_t i = 0; (i < received) && Wire.available(); ++i) {",
                    "    rx_buf[i] = Wire.read();",
                    "}",
                ]
            )
            snippets["Arduino / Wire.h"] = "\n".join(arduino_lines)
        else:
            arduino_lines = [
                "// Arduino Wire write",
                f"Wire.beginTransmission({addr_hex});",
                *arduino_reg_lines,
                *[f"Wire.write(0x{value:02X});" for value in data],
                "uint8_t err = Wire.endTransmission();",
                "if (err != 0) {",
                "    // Handle address or data NACK",
                "}",
            ]
            snippets["Arduino / Wire.h"] = "\n".join(arduino_lines)

        return snippets
