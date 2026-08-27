from __future__ import annotations

import math
from collections.abc import Iterable

from fw_diag_tool.i2c.transfer_spec import (
    Endianness,
    I2CTransferOperation,
    I2CTransferSpec,
)


class I2CDriverCodeGenerator:
    """Generate platform templates from one validated canonical transfer."""

    @staticmethod
    def _validate_int(name: str, value: int, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    @classmethod
    def generate_from_spec(cls, spec: I2CTransferSpec) -> dict[str, str]:
        """Generate all four snippets from the same canonical segment list."""

        if not isinstance(spec, I2CTransferSpec):
            raise TypeError("spec must be an I2CTransferSpec")
        spec.validate()
        return {
            "Linux Userspace (i2c-dev)": cls._linux_i2c_dev(spec),
            "OpenBMC / Linux CLI (i2c-tools)": cls._linux_cli(spec),
            "STM32 HAL C Driver": cls._stm32_hal(spec),
            "Arduino / Wire.h": cls._arduino(spec),
        }

    # ``generate`` is a convenient explicit name for new callers.
    generate = generate_from_spec

    @classmethod
    def generate_all_snippets(
        cls,
        addr_7bit: int | I2CTransferSpec | None = None,
        reg_offset: int | None = None,
        data_bytes: list[int] | None = None,
        is_read: bool = False,
        bus_num: int = 1,
        read_length: int | None = None,
        register_width: int = 8,
        *,
        spec: I2CTransferSpec | None = None,
        operation: I2CTransferOperation | str | None = None,
        endianness: Endianness | str = Endianness.BIG,
        clock_khz: float = 100.0,
        timeout_ms: float = 100.0,
    ) -> dict[str, str]:
        """Compatibility wrapper around :meth:`generate_from_spec`.

        Existing callers can retain the historical arguments.  Passing a
        spec as the first positional argument or via ``spec=`` opts directly
        into the canonical model.
        """

        if isinstance(addr_7bit, I2CTransferSpec):
            if spec is not None and spec is not addr_7bit:
                raise ValueError("spec conflicts with positional I2CTransferSpec")
            spec = addr_7bit
        if spec is not None:
            if (
                any(value is not None for value in (reg_offset, data_bytes, read_length))
                or is_read
                or bus_num != 1
                or register_width != 8
            ):
                raise ValueError("legacy generator arguments cannot be combined with spec")
            return cls.generate_from_spec(spec)

        if addr_7bit is None:
            raise TypeError("addr_7bit or spec is required")
        if isinstance(addr_7bit, I2CTransferSpec):
            raise TypeError("addr_7bit must be an integer when spec is not supplied")
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
        if operation is None:
            if is_read:
                operation = (
                    I2CTransferOperation.COMBINED_REGISTER_READ
                    if reg_offset is not None
                    else I2CTransferOperation.DIRECT_READ
                )
            else:
                operation = (
                    I2CTransferOperation.REGISTER_WRITE
                    if reg_offset is not None
                    else I2CTransferOperation.DIRECT_WRITE
                )
        else:
            operation = I2CTransferOperation.coerce(operation)
            operation_is_read = operation in {
                I2CTransferOperation.COMBINED_REGISTER_READ,
                I2CTransferOperation.DIRECT_READ,
            }
            if is_read and not operation_is_read:
                raise ValueError("operation conflicts with is_read")
            # ``operation`` is the canonical argument for new callers.  Keep
            # the historical ``is_read=False`` default from making a read
            # operation fail when callers omit that legacy flag.
            is_read = operation_is_read
        if is_read:
            # Historical callers sometimes supplied ``data_bytes`` only to
            # imply a receive length.  Preserve that read-only compatibility
            # behavior while keeping the canonical spec free of TX payload.
            rx_length = read_length if read_length is not None else (len(data_bytes or []) or 1)
            spec_data_bytes = None
        else:
            if read_length is not None:
                raise ValueError("read_length is only valid for read operations")
            rx_length = None
            spec_data_bytes = data_bytes
        generated_spec = I2CTransferSpec(
            address_7bit=addr_7bit,
            bus=bus_num,
            operation=operation,
            register=reg_offset,
            register_width=register_width,
            endianness=endianness,
            data_bytes=spec_data_bytes,
            read_length=rx_length,
            clock_khz=clock_khz,
            timeout_ms=timeout_ms,
        )
        return cls.generate_from_spec(generated_spec)

    @staticmethod
    def _hex(byte: int) -> str:
        return f"0x{byte:02X}"

    @classmethod
    def _bytes_literal(cls, values: Iterable[int]) -> str:
        return ", ".join(cls._hex(value) for value in values)

    @staticmethod
    def _timeout_literal(timeout_ms: float) -> str:
        # STM32 HAL timeout parameters are integer milliseconds.  Round up so
        # a fractional GUI value never silently shortens the requested budget.
        return str(math.ceil(timeout_ms))

    @staticmethod
    def _read_length(spec: I2CTransferSpec) -> int:
        if spec.read_length is None:
            raise ValueError("read operation has no read_length")
        return spec.read_length

    @classmethod
    def _linux_i2c_dev(cls, spec: I2CTransferSpec) -> str:
        address = cls._hex(spec.address_7bit)
        lines = [
            "// 【程式碼模板】Linux userspace i2c-dev；正式產品請補充完整錯誤處理與 close() 機制。",
            "// 前置引用：<fcntl.h>, <linux/i2c-dev.h>, <linux/i2c.h>, <sys/ioctl.h>, <unistd.h>, <stdint.h>, <stdio.h>。",
            "// 安全防護：確認匯流排編號與 7-bit 位址，寫入操作請置於明確的人工安全檢查之後。",
            f"// 提示：模板逾時 {spec.timeout_ms:g} ms 需由應用程式自行實作 deadline 機制。",
            f'int file = open("/dev/i2c-{spec.bus}", O_RDWR);',
            'if (file < 0) { perror("open i2c bus"); return; }',
        ]
        segment = spec.segments[0]
        if spec.operation == I2CTransferOperation.COMBINED_REGISTER_READ:
            reg_bytes = tuple(int(byte) for byte in segment.bytes)
            length = cls._read_length(spec)
            reg_array = cls._bytes_literal(reg_bytes)
            lines.extend(
                [
                    "// 複合暫存器讀取 (Combined Register Read)：兩個 i2c_msg 由 Repeated START 連接。",
                    f"uint8_t reg_buf[{len(reg_bytes)}] = {{ {reg_array} }};",
                    f"uint8_t rx_buf[{length}]; // 接收緩衝區；資料由目標裝置於執行期回傳。",
                    "struct i2c_msg msgs[2] = {",
                    f"    {{ .addr = {address}, .flags = 0, .len = sizeof(reg_buf), .buf = reg_buf }},",
                    f"    {{ .addr = {address}, .flags = I2C_M_RD, .len = sizeof(rx_buf), .buf = rx_buf }},",
                    "};",
                    "struct i2c_rdwr_ioctl_data transfer = { .msgs = msgs, .nmsgs = 2 };",
                    "if (ioctl(file, I2C_RDWR, &transfer) < 0) {",
                    '    perror("Failed to read from I2C device");',
                    "}",
                ]
            )
        elif spec.operation == I2CTransferOperation.DIRECT_READ:
            length = cls._read_length(spec)
            lines.extend(
                [
                    "// 直接讀取 (Direct Read)：不發送暫存器位移階段。",
                    f"if (ioctl(file, I2C_SLAVE, {address}) < 0) {{",
                    '    perror("select I2C slave");',
                    "    close(file);",
                    "    return;",
                    "}",
                    f"uint8_t rx_buf[{length}]; // 接收緩衝區；資料由目標裝置於執行期回傳。",
                    "if (read(file, rx_buf, sizeof(rx_buf)) != sizeof(rx_buf)) {",
                    '    perror("Failed to read from I2C device");',
                    "}",
                ]
            )
        else:
            payload = tuple(int(byte) for byte in segment.bytes)
            lines.extend(
                [
                    f"if (ioctl(file, I2C_SLAVE, {address}) < 0) {{",
                    '    perror("select I2C slave");',
                    "    close(file);",
                    "    return;",
                    "}",
                    f"uint8_t tx_buf[{len(payload)}] = {{ {cls._bytes_literal(payload)} }};",
                    "if (write(file, tx_buf, sizeof(tx_buf)) != sizeof(tx_buf)) {",
                    '    perror("Failed to write to I2C device");',
                    "}",
                ]
            )
        lines.append("close(file);")
        return "\n".join(lines)

    @classmethod
    def _linux_cli(cls, spec: I2CTransferSpec) -> str:
        address = cls._hex(spec.address_7bit)
        lines = [
            "# 【指令模板】OpenBMC/Linux i2c-tools 指令；在硬體執行前請確認所有參數。",
            f"# 前置條件：已安裝 i2c-tools、/dev/i2c-{spec.bus} 存在且具備存取權限。",
            "# 安全防護：刻意省略自動確認旗標，讓 i2ctransfer 在執行前先進行互動確認。",
            "# 安全防護：執行前請對照硬體確認 Bus 編號、7-bit 位址、暫存器位元組與寫入資料。",
            f"# 提示：模板逾時 {spec.timeout_ms:g} ms 僅供參考；i2c-tools 無跨平台單一指令 deadline。",
        ]
        if spec.operation == I2CTransferOperation.COMBINED_REGISTER_READ:
            segment = spec.segments[0]
            reg_cli = " ".join(cls._hex(int(byte)) for byte in segment.bytes)
            lines.extend(
                [
                    f"# 從 {address} 進行複合暫存器讀取；i2ctransfer 自動送出 Repeated START。",
                    f"i2ctransfer {spec.bus} w{len(segment.bytes)}@{address} {reg_cli} r{cls._read_length(spec)}",
                ]
            )
        elif spec.operation == I2CTransferOperation.DIRECT_READ:
            lines.extend(
                [
                    f"# 從 {address} 直接讀取 {cls._read_length(spec)} 個位元組。",
                    f"i2ctransfer {spec.bus} r{cls._read_length(spec)}@{address}",
                ]
            )
        else:
            payload = tuple(int(byte) for byte in spec.segments[0].bytes)
            lines.extend(
                [
                    f"# 向 {address} 寫入 {len(payload)} 個位元組資料。",
                    (
                        f"i2ctransfer {spec.bus} w{len(payload)}@{address} "
                        f"{' '.join(cls._hex(byte) for byte in payload)}"
                    ),
                ]
            )
        return "\n".join(lines)

    @classmethod
    def _stm32_hal(cls, spec: I2CTransferSpec) -> str:
        address = cls._hex(spec.address_7bit)
        shifted_address = f"({address} << 1)"
        timeout = cls._timeout_literal(spec.timeout_ms)
        lines = [
            "// 【程式碼模板】STM32 HAL；請傳入已完成初始化之 I2C_HandleTypeDef (hi2c1)。",
            "// 前置引用：CubeMX 時鐘/腳位配置、HAL_I2C_Init() 與應用層錯誤處理。",
            "// 安全防護：STM32 HAL API 需傳入左移 1 位元的 8-bit 位址 (Shifted Address)。",
            f"// HAL 逾時設定為 ceil({spec.timeout_ms:g}) = {timeout} ms 整數值。",
        ]
        asynchronous_sequential_read = False
        if spec.operation == I2CTransferOperation.COMBINED_REGISTER_READ:
            length = cls._read_length(spec)
            if spec.endianness == Endianness.BIG:
                lines.extend(
                    [
                        "// 複合暫存器讀取 (HAL API 會自動產生 Repeated START)。",
                        f"uint8_t rx_buf[{length}]; // 接收緩衝區；資料由目標裝置於執行期回傳。",
                        (
                            "HAL_StatusTypeDef status = HAL_I2C_Mem_Read(&hi2c1, "
                            f"{shifted_address}, {cls._hex(spec.register or 0)}, "
                            f"I2C_MEMADD_SIZE_{spec.register_width}BIT, rx_buf, {length}, {timeout});"
                        ),
                    ]
                )
            else:
                asynchronous_sequential_read = True
                reg_bytes = tuple(int(byte) for byte in spec.register_bytes)
                lines.extend(
                    [
                        "// Little-endian register phase requires sequential HAL calls to preserve Sr.",
                        "// Place these declarations and callbacks at file scope; callbacks run after the caller returns.",
                        f"static uint8_t reg_buf[{len(reg_bytes)}] = {{ {cls._bytes_literal(reg_bytes)} }};",
                        f"static uint8_t rx_buf[{length}]; // RX values are supplied by the target at runtime.",
                        "static volatile HAL_StatusTypeDef status;",
                        "static volatile uint8_t transfer_done;",
                        "// Merge these callback hooks with the project's existing HAL callbacks if present.",
                        "void i2c_start_transfer(void) {",
                        "    transfer_done = 0;",
                        (
                            "    status = HAL_I2C_Master_Seq_Transmit_IT(&hi2c1, "
                            f"{shifted_address}, reg_buf, sizeof(reg_buf), I2C_FIRST_FRAME);"
                        ),
                        "    if (status != HAL_OK) {",
                        "        // Handle immediate NACK, busy, or invalid HAL state.",
                        "    }",
                        "}",
                        "void HAL_I2C_MasterTxCpltCallback(I2C_HandleTypeDef *hi2c) {",
                        (
                            "    if (hi2c == &hi2c1) { status = "
                            "HAL_I2C_Master_Seq_Receive_IT(&hi2c1, "
                            f"{shifted_address}, rx_buf, {length}, I2C_LAST_FRAME); "
                            "if (status != HAL_OK) transfer_done = 1; }"
                        ),
                        "}",
                        "void HAL_I2C_MasterRxCpltCallback(I2C_HandleTypeDef *hi2c) {",
                        "    if (hi2c == &hi2c1) transfer_done = 1;",
                        "}",
                        "void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c) {",
                        "    if (hi2c == &hi2c1) { status = HAL_ERROR; transfer_done = 1; }",
                        "}",
                        f"// Application must wait for transfer_done with a {timeout} ms overall timeout.",
                    ]
                )
        elif spec.operation == I2CTransferOperation.DIRECT_READ:
            length = cls._read_length(spec)
            lines.extend(
                [
                    "// Direct read: no register phase is sent.",
                    f"uint8_t rx_buf[{length}]; // RX values are supplied by the target at runtime.",
                    (
                        "HAL_StatusTypeDef status = HAL_I2C_Master_Receive(&hi2c1, "
                        f"{shifted_address}, rx_buf, {length}, {timeout});"
                    ),
                ]
            )
        else:
            payload = tuple(int(byte) for byte in spec.segments[0].bytes)
            if (
                spec.operation == I2CTransferOperation.REGISTER_WRITE
                and spec.endianness == Endianness.BIG
            ):
                data = spec.data_bytes
                lines.extend(
                    [
                        "// Register write (HAL emits the register phase in big-endian order).",
                        f"uint8_t tx_buf[{len(data)}] = {{ {cls._bytes_literal(data)} }};",
                        (
                            "HAL_StatusTypeDef status = HAL_I2C_Mem_Write(&hi2c1, "
                            f"{shifted_address}, {cls._hex(spec.register or 0)}, "
                            f"I2C_MEMADD_SIZE_{spec.register_width}BIT, tx_buf, {len(data)}, {timeout});"
                        ),
                    ]
                )
            else:
                lines.extend(
                    [
                        "// Direct/canonical write payload (register bytes precede data bytes).",
                        f"uint8_t tx_buf[{len(payload)}] = {{ {cls._bytes_literal(payload)} }};",
                        (
                            "HAL_StatusTypeDef status = HAL_I2C_Master_Transmit(&hi2c1, "
                            f"{shifted_address}, tx_buf, sizeof(tx_buf), {timeout});"
                        ),
                    ]
                )
        if not asynchronous_sequential_read:
            lines.extend(
                [
                    "if (status != HAL_OK) {",
                    "    // Handle HAL_I2C_ERROR_AF (NACK), timeout, arbitration loss, or bus error.",
                    "}",
                ]
            )
        return "\n".join(lines)

    @classmethod
    def _arduino(cls, spec: I2CTransferSpec) -> str:
        address = cls._hex(spec.address_7bit)
        lines = [
            "// 【程式碼模板】Arduino Wire.h；請先呼叫 Wire.begin() 並完成匯流排配置。",
            "// 前置引用：包含 <Wire.h>，選擇正確的控制器並檢查 endTransmission() 回傳狀態。",
            "// 安全防護：對板卡上電前請確認 7-bit 位址與寫入資料符合晶片規範。",
            f"// 提示：模板逾時 {spec.timeout_ms:g} ms 未由 Wire 函式庫原生強制，需自行加入 Watchdog/逾時機制。",
        ]
        if spec.operation == I2CTransferOperation.COMBINED_REGISTER_READ:
            lines.extend(
                [
                    "// 複合暫存器讀取；false 參數確保發送 Repeated START (不釋放匯流排)。",
                    f"Wire.beginTransmission({address});",
                    *[f"Wire.write({cls._hex(int(byte))});" for byte in spec.register_bytes],
                    "uint8_t tx_err = Wire.endTransmission(false); // 保持 Bus 連線，發送 Repeated START",
                    "if (tx_err != 0) { /* 處理位址或暫存器 NACK 錯誤 */ }",
                ]
            )
            length = cls._read_length(spec)
            lines.extend(
                [
                    f"uint8_t rx_buf[{length}]; // 接收緩衝區；資料由目標裝置於執行期回傳。",
                    f"uint8_t received = Wire.requestFrom({address}, {length});",
                    f"if (received != {length}) {{ /* 處理讀取長度不足；請檢查板卡的 Wire Buffer 限制 */ }}",
                    "for (uint8_t i = 0; (i < received) && Wire.available(); ++i) {",
                    "    rx_buf[i] = Wire.read();",
                    "}",
                ]
            )
        elif spec.operation == I2CTransferOperation.DIRECT_READ:
            length = cls._read_length(spec)
            lines.extend(
                [
                    "// Direct read: no register phase is sent.",
                    f"uint8_t rx_buf[{length}]; // RX values are supplied by the target at runtime.",
                    f"uint8_t received = Wire.requestFrom({address}, {length});",
                    f"if (received != {length}) {{ /* Handle short read; verify the board's Wire buffer limit. */ }}",
                    "for (uint8_t i = 0; (i < received) && Wire.available(); ++i) {",
                    "    rx_buf[i] = Wire.read();",
                    "}",
                ]
            )
        else:
            payload = tuple(int(byte) for byte in spec.segments[0].bytes)
            lines.extend(
                [
                    "// Verify this payload fits the target board's Wire TX buffer; split it if required.",
                    f"Wire.beginTransmission({address});",
                    *[f"Wire.write({cls._hex(byte)});" for byte in payload],
                    "uint8_t err = Wire.endTransmission();",
                    "if (err != 0) {",
                    "    // Handle address or data NACK.",
                    "}",
                ]
            )
        return "\n".join(lines)


__all__ = ["I2CDriverCodeGenerator"]
