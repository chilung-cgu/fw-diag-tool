from __future__ import annotations


class I2CDriverCodeGenerator:
    # Generates ready-to-use C driver snippets across 4 mainstream firmware platforms

    @staticmethod
    def generate_all_snippets(
        addr_7bit: int,
        reg_offset: int | None = None,
        data_bytes: list[int] | None = None,
        is_read: bool = False,
        bus_num: int = 1,
    ) -> dict[str, str]:
        data = data_bytes or [0x00]
        addr_hex = f"0x{addr_7bit:02X}"
        reg_hex = f"0x{reg_offset:02X}" if reg_offset is not None else "0x00"
        data_hex = f"0x{data[0]:02X}" if data else "0x00"
        data_len = len(data)

        snippets = {}

        # 1. Linux Userspace i2c-dev
        if is_read:
            snippets["Linux Userspace (i2c-dev)"] = "\n".join([
                "// Linux Userspace i2c-dev Read",
                f'int file = open("/dev/i2c-{bus_num}", O_RDWR);',
                f"ioctl(file, I2C_SLAVE, {addr_hex});",
                f"int32_t res = i2c_smbus_read_byte_data(file, {reg_hex});",
                "if (res < 0) {",
                '    perror("Failed to read from I2C device");',
                "} else {",
                "    uint8_t data = (uint8_t)res;",
                "}",
            ])
        else:
            snippets["Linux Userspace (i2c-dev)"] = "\n".join([
                "// Linux Userspace i2c-dev Write",
                f'int file = open("/dev/i2c-{bus_num}", O_RDWR);',
                f"ioctl(file, I2C_SLAVE, {addr_hex});",
                f"if (i2c_smbus_write_byte_data(file, {reg_hex}, {data_hex}) < 0) {{",
                '    perror("Failed to write to I2C device");',
                "}",
            ])

        # 2. OpenBMC / Linux CLI i2c-tools
        if is_read:
            snippets["OpenBMC / Linux CLI (i2c-tools)"] = "\n".join([
                f"# Read 1 byte from device {addr_hex} register {reg_hex}",
                f"i2cget -y -f {bus_num} {addr_hex} {reg_hex} b",
                "",
                "# Or block read using i2ctransfer:",
                f"i2ctransfer -y {bus_num} w1@{addr_hex} {reg_hex} r{data_len}",
            ])
        else:
            snippets["OpenBMC / Linux CLI (i2c-tools)"] = "\n".join([
                f"# Write byte {data_hex} to device {addr_hex} register {reg_hex}",
                f"i2cset -y -f {bus_num} {addr_hex} {reg_hex} {data_hex} b",
            ])

        # 3. STM32 HAL
        if is_read:
            snippets["STM32 HAL C Driver"] = "\n".join([
                "// STM32 HAL Memory Read",
                f"uint8_t rx_buf[{data_len}];",
                f"HAL_StatusTypeDef status = HAL_I2C_Mem_Read(&hi2c1, ({addr_hex} << 1), {reg_hex}, I2C_MEMADD_SIZE_8BIT, rx_buf, {data_len}, 100);",
                "if (status != HAL_OK) {",
                "    // Handle I2C NACK or Timeout Error",
                "}",
            ])
        else:
            data_arr = ", ".join(f"0x{b:02X}" for b in data)
            snippets["STM32 HAL C Driver"] = "\n".join([
                "// STM32 HAL Memory Write",
                f"uint8_t tx_buf[{data_len}] = {{ {data_arr} }};",
                f"HAL_StatusTypeDef status = HAL_I2C_Mem_Write(&hi2c1, ({addr_hex} << 1), {reg_hex}, I2C_MEMADD_SIZE_8BIT, tx_buf, {data_len}, 100);",
                "if (status != HAL_OK) {",
                "    // Handle I2C Error",
                "}",
            ])

        # 4. Arduino Wire
        if is_read:
            snippets["Arduino / Wire.h"] = "\n".join([
                "// Arduino Wire Read",
                f"Wire.beginTransmission({addr_hex});",
                f"Wire.write({reg_hex});",
                "Wire.endTransmission(false); // Repeated Start",
                f"Wire.requestFrom({addr_hex}, {data_len});",
                "if (Wire.available()) {",
                "    uint8_t val = Wire.read();",
                "}",
            ])
        else:
            snippets["Arduino / Wire.h"] = "\n".join([
                "// Arduino Wire Write",
                f"Wire.beginTransmission({addr_hex});",
                f"Wire.write({reg_hex});",
                f"Wire.write({data_hex});",
                "uint8_t err = Wire.endTransmission();",
                "if (err != 0) {",
                "    // 1: Data too long, 2: NACK on address, 3: NACK on data, 4: Other",
                "}",
            ])

        return snippets