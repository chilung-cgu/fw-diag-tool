from __future__ import annotations

from .models import (
    SPIDiagnosticIssue,
    SPIOpcode,
    SPISeverity,
    SPITransaction,
)


class SPIAnomalyDetector:
    def __init__(self, max_page_size: int = 256):
        self.max_page_size = max_page_size

    def analyze(self, transactions: list[SPITransaction]) -> list[SPIDiagnosticIssue]:
        issues: list[SPIDiagnosticIssue] = []
        wel_latched = False

        for tx in transactions:
            op = tx.opcode
            if op is None:
                continue

            # Track Write Enable Latch (0x06 WREN or 0x50 Volatile SR Write Enable)
            if op in (SPIOpcode.WRITE_ENABLE, SPIOpcode.VOLATILE_SR_WRITE_ENABLE):
                wel_latched = True
            elif op == SPIOpcode.WRITE_DISABLE:
                wel_latched = False

            # Check 1: Write / Program / Erase without WREN
            is_write_or_erase = op in (
                SPIOpcode.PAGE_PROGRAM,
                SPIOpcode.QUAD_PAGE_PROGRAM,
                SPIOpcode.SECTOR_ERASE_4K,
                SPIOpcode.BLOCK_ERASE_32K,
                SPIOpcode.BLOCK_ERASE_64K,
                SPIOpcode.CHIP_ERASE,
                SPIOpcode.CHIP_ERASE_ALT,
                SPIOpcode.WRITE_STATUS_REG_1,
                SPIOpcode.WRITE_STATUS_REG_2,
                SPIOpcode.WRITE_STATUS_REG_3,
            )

            if is_write_or_erase:
                if not wel_latched:
                    issues.append(
                        SPIDiagnosticIssue(
                            code="SPI_WRITE_NO_WREN",
                            title=f"Write/Erase without Write Enable (0x06) @ Tx #{tx.index}",
                            severity=SPISeverity.CRITICAL,
                            timestamp=tx.start_time,
                            transaction_id=tx.index,
                            description=(
                                f"Command {tx.opcode_name} was issued to Flash memory without a preceding "
                                "Write Enable (0x06 WREN / 0x50) command or after WEL was cleared."
                            ),
                            root_cause_guide=(
                                "【Root Cause 排查建議】\n"
                                "1. NOR Flash 硬體保護機制：執行任何 Page Program, Erase 或 Status Register Write 之前，必須先發送單獨的 0x06 (WREN) 或 0x50 封包並拉高 CS#。\n"
                                "2. 檢查驅動代碼是否遺漏了 spi_flash_write_enable()。\n"
                                "3. 注意：每次 Program 或 Erase 完成後，Flash 硬體會自動將 WEL 歸零，下一次寫入必須重新發送 0x06！"
                            ),
                            details={"opcode": f"0x{op:02X}", "wel_state": False}
                        )
                    )
                # Any write/erase clears WEL latch upon completion
                wel_latched = False

            # Check 2: Page Program Wrap-around Hazard
            if op in (SPIOpcode.PAGE_PROGRAM, SPIOpcode.QUAD_PAGE_PROGRAM) and tx.decoded_details.get("page_wrap_hazard"):
                start_off = tx.decoded_details.get("page_start_offset", 0)
                p_len = tx.data_payload_len
                issues.append(
                    SPIDiagnosticIssue(
                        code="SPI_PAGE_PROGRAM_WRAP",
                        title=f"Page Program Buffer Wrap-Around Hazard @ Tx #{tx.index}",
                        severity=SPISeverity.ERROR,
                        timestamp=tx.start_time,
                        transaction_id=tx.index,
                        description=(
                            f"Page Program started at in-page offset 0x{start_off:02X} with payload length {p_len} bytes. "
                            f"Total 0x{start_off:02X} + {p_len} = {start_off + p_len} exceeds 256-byte page boundary."
                        ),
                        root_cause_guide=(
                            "【Root Cause 排查建議】\n"
                            "1. SPI NOR Flash 內部 Page Buffer 大小固定為 256 bytes。\n"
                            "2. 當寫入位址跨越 Page 邊界時，位址指標會直接 Wrap-around 回當前 Page 的 0x00 offset，導致該 Page 開頭的資料被非預期覆蓋！\n"
                            "3. 修正方案：韌體中封裝 Page Write 驅動時，計算 chunk = min(length, 256 - (addr & 0xFF))，跨 Page 時必須拆分為兩次獨立指令。"
                        ),
                        details={"page_offset": start_off, "payload_len": p_len, "page_size": 256}
                    )
                )

            # Check 3: Truncated Transaction
            if op in (SPIOpcode.READ_DATA, SPIOpcode.FAST_READ, SPIOpcode.PAGE_PROGRAM, SPIOpcode.SECTOR_ERASE_4K) and len(tx.mosi_bytes) < 4:
                issues.append(
                    SPIDiagnosticIssue(
                        code="SPI_TRUNCATED_TX",
                        title=f"Incomplete SPI Command / Early CS Deassertion @ Tx #{tx.index}",
                        severity=SPISeverity.ERROR,
                        timestamp=tx.start_time,
                        transaction_id=tx.index,
                        description=(
                            f"Command {tx.opcode_name} requires at least 4 bytes (Opcode + 24-bit Address), "
                            f"but CS went high after only {len(tx.mosi_bytes)} byte(s)."
                        ),
                        root_cause_guide=(
                            "【Root Cause 排查建議】\n"
                            "1. 檢查硬體 CS# 線路是否有雜訊 Glitch 提前觸發釋放。\n"
                            "2. 檢查 SPI Controller DMA 配置長度是否計算錯誤。\n"
                            "3. Flash 收到不完整位址會直接丟棄此指令。"
                        ),
                        details={"received_bytes": len(tx.mosi_bytes), "expected_min": 4}
                    )
                )

        return issues