from __future__ import annotations

from fw_diag_tool.errors import ResourceLimitError
from fw_diag_tool.limits import AnalysisLimits, coerce_limits

from .models import (
    SPIDiagnosticIssue,
    SPIOpcode,
    SPISeverity,
    SPITransaction,
)


class SPIAnomalyDetector:
    def __init__(self, max_page_size: int = 256, *, limits: AnalysisLimits | None = None):
        self.limits = coerce_limits(limits)
        if (
            isinstance(max_page_size, bool)
            or not isinstance(max_page_size, int)
            or max_page_size <= 0
        ):
            raise ValueError("max_page_size must be a positive integer")
        self.max_page_size = max_page_size

    def analyze(self, transactions: list[SPITransaction]) -> list[SPIDiagnosticIssue]:
        if len(transactions) > self.limits.max_transactions:
            raise ResourceLimitError(
                f"SPI capture exceeds the {self.limits.max_transactions}-transaction safety limit",
                resource="transactions",
                limit=self.limits.max_transactions,
                observed=len(transactions),
            )
        issues: list[SPIDiagnosticIssue] = []
        # A capture may begin after WREN.  ``None`` means the latch state was
        # not observed, not that the flash was proven to have WEL=0.
        wel_latched: bool | None = None
        volatile_wel_latched = False
        reset_armed = False
        flash_busy: bool | None = None

        for tx in transactions:
            op = tx.opcode
            if op is None:
                continue

            # 1. JEDEC ID Line Fault Check (Floating or Shorted MISO)
            if op == SPIOpcode.JEDEC_ID and len(tx.miso_bytes) >= 4:
                miso_id_bytes = tx.miso_bytes[1:4]
                if all(b == 0xFF for b in miso_id_bytes):
                    issues.append(
                        SPIDiagnosticIssue(
                            code="SPI_JEDEC_LINE_FAULT",
                            title=f"JEDEC ID Read Returned All 0xFF (Floating MISO / No Power) @ Tx #{tx.index}",
                            severity=SPISeverity.CRITICAL,
                            timestamp=tx.start_time,
                            transaction_id=tx.index,
                            description="JEDEC ID command (0x9F) returned [0xFF, 0xFF, 0xFF]. Flash device did not drive MISO line.",
                            root_cause_guide=(
                                "【Root Cause 排查建議】\n"
                                "1. 檢查 SPI Flash 供電電壓 (VCC/3.3V/1.8V) 是否未開啟或接地不良。\n"
                                "2. 檢查 MISO 線路是否斷路或處於高阻抗 (High-Z) 狀態（因上拉電阻讀回全 1）。\n"
                                "3. 檢查 CS# (Chip Select) 是否未正確拉低以選中目標晶片。"
                            ),
                            details={"miso_bytes": [f"0x{b:02X}" for b in miso_id_bytes]},
                        )
                    )
                elif all(b == 0x00 for b in miso_id_bytes):
                    issues.append(
                        SPIDiagnosticIssue(
                            code="SPI_JEDEC_LINE_FAULT",
                            title=f"JEDEC ID Read Returned All 0x00 (MISO Short to GND / Bus Clamped) @ Tx #{tx.index}",
                            severity=SPISeverity.CRITICAL,
                            timestamp=tx.start_time,
                            transaction_id=tx.index,
                            description="JEDEC ID command (0x9F) returned [0x00, 0x00, 0x00]. MISO line is clamped to GND.",
                            root_cause_guide=(
                                "【Root Cause 排查建議】\n"
                                "1. 檢查 MISO 線路是否對地短路 (Short-to-GND) 或被其他元件持續拉低。\n"
                                "2. 檢查 SPI Clock 極性與相位 (CPOL/CPHA) 是否設定錯誤。"
                            ),
                            details={"miso_bytes": [f"0x{b:02X}" for b in miso_id_bytes]},
                        )
                    )

            # 2. Track Write Enable Latches
            frame_valid = not bool(
                tx.decoded_details.get("response_truncated")
                or tx.decoded_details.get("response_overlong")
            )
            if not frame_valid:
                # A truncated/overlong frame cannot prove either its command
                # side effect or the WEL transition it would normally cause.
                # Leave state unchanged and rely on the explicit quality issue.
                tx.wel_state_before = wel_latched
                continue
            if op == SPIOpcode.WRITE_ENABLE:
                if frame_valid:
                    wel_latched = True
                    volatile_wel_latched = True
            elif op == SPIOpcode.VOLATILE_SR_WRITE_ENABLE:
                if frame_valid:
                    volatile_wel_latched = True
            elif op == SPIOpcode.WRITE_DISABLE:
                if frame_valid:
                    wel_latched = False
                    volatile_wel_latched = False
            elif op == SPIOpcode.ENABLE_RESET:
                reset_armed = frame_valid
            elif op == SPIOpcode.RESET_DEVICE:
                if reset_armed and frame_valid:
                    # Most flashes require the preceding 0x66 reset-enable
                    # command.  A bare 0x99 is not proof of reset completion.
                    wel_latched = False
                    volatile_wel_latched = False
                    tx.decoded_details["wel_reset_evidence"] = "device-reset"
                else:
                    tx.decoded_details["reset_evidence"] = "reset-enable-not-observed"
                reset_armed = False
            elif op != SPIOpcode.ENABLE_RESET:
                # RESET ENABLE is a short-lived command sequence; any other
                # opcode invalidates the arm before a later 0x99.
                reset_armed = False

            if op == SPIOpcode.READ_STATUS_REG_1:
                observed_wel = tx.decoded_details.get("wel")
                if isinstance(observed_wel, bool):
                    wel_latched = observed_wel
                    tx.wel_state_before = observed_wel
                    tx.decoded_details["wel_evidence"] = "status-read"
                else:
                    tx.wel_state_before = wel_latched
                observed_busy = tx.decoded_details.get("busy")
                if isinstance(observed_busy, bool):
                    flash_busy = observed_busy
                    tx.decoded_details["busy_state_observed"] = observed_busy

            # 3. Write / Program / Erase without WREN Checks
            is_array_write_or_erase = op in (
                SPIOpcode.PAGE_PROGRAM,
                SPIOpcode.QUAD_PAGE_PROGRAM,
                SPIOpcode.SECTOR_ERASE_4K,
                SPIOpcode.BLOCK_ERASE_32K,
                SPIOpcode.BLOCK_ERASE_64K,
                SPIOpcode.CHIP_ERASE,
                SPIOpcode.CHIP_ERASE_ALT,
            )
            is_sr_write = op in (
                SPIOpcode.WRITE_STATUS_REG_1,
                SPIOpcode.WRITE_STATUS_REG_2,
                SPIOpcode.WRITE_STATUS_REG_3,
            )

            if flash_busy is True and (is_array_write_or_erase or op == SPIOpcode.WRITE_ENABLE):
                issues.append(
                    SPIDiagnosticIssue(
                        code="SPI_FLASH_BUSY",
                        title=f"Command issued while Flash is BUSY (WIP=1) @ Tx #{tx.index}",
                        severity=SPISeverity.ERROR,
                        timestamp=tx.start_time,
                        transaction_id=tx.index,
                        description=(
                            f"Command {tx.opcode_name} was issued while the most recent observed "
                            "status register reported BUSY=1. The internal write/erase cycle has not finished."
                        ),
                        root_cause_guide=(
                            "【排查建議】確認韌體是否有對 Status Register 1 進行 Busy Polling (RDSR 0x05 直到 WIP=0)，"
                            "避免在前一次 Program/Erase 尚未完成時發送新指令導致指令被晶片忽略或損壞。"
                        ),
                        details={"opcode": f"0x{op:02X}", "busy_state": True},
                    )
                )

            if is_array_write_or_erase:
                tx.wel_state_before = wel_latched
                if wel_latched is False:
                    issues.append(
                        SPIDiagnosticIssue(
                            code="SPI_WEL_NOT_LATCHED",
                            title=f"Write/Erase observed with WEL=0 @ Tx #{tx.index}",
                            severity=SPISeverity.WARNING,
                            timestamp=tx.start_time,
                            transaction_id=tx.index,
                            description=(
                                f"Command {tx.opcode_name} was issued while the most recent observed "
                                "status register reported WEL=0. The flash may reject the operation."
                            ),
                            root_cause_guide=(
                                "【排查建議】確認 WREN 是否真的被送出並讀回 WEL=1；檢查 WP#、保護區域與狀態暫存器寫入流程。"
                            ),
                            details={
                                "opcode": f"0x{op:02X}",
                                "wel_state": False,
                                "evidence": "status-read",
                            },
                        )
                    )
                elif wel_latched is None:
                    issues.append(
                        SPIDiagnosticIssue(
                            code="SPI_WEL_STATE_UNKNOWN",
                            title=f"Write/Erase WEL state was not observed @ Tx #{tx.index}",
                            severity=SPISeverity.WARNING,
                            timestamp=tx.start_time,
                            transaction_id=tx.index,
                            description=(
                                f"No WREN or status-read evidence before {tx.opcode_name} was present "
                                "inside this capture; the operation's latch state cannot be proven."
                            ),
                            root_cause_guide=(
                                "【排查建議】擴大擷取範圍至 WREN 與 RDSR，確認 WEL=1 後再判斷寫入是否被接受。"
                            ),
                            details={
                                "opcode": f"0x{op:02X}",
                                "wel_state": None,
                                "evidence": "unobserved",
                            },
                        )
                    )
                if wel_latched is True:
                    # A successful array operation normally clears WEL.  Keep
                    # the post-operation state conservative if it was not
                    # explicitly observed.
                    wel_latched = False
                else:
                    wel_latched = None
                volatile_wel_latched = False
                flash_busy = True

            elif is_sr_write:
                tx.wel_state_before = wel_latched
                if wel_latched is False and not volatile_wel_latched:
                    issues.append(
                        SPIDiagnosticIssue(
                            code="SPI_WRITE_NO_WREN",
                            title=f"Write Status Register without WREN (0x06 / 0x50) @ Tx #{tx.index}",
                            severity=SPISeverity.CRITICAL,
                            timestamp=tx.start_time,
                            transaction_id=tx.index,
                            description=f"Status Register write {tx.opcode_name} issued without 0x06 (WREN) or 0x50 (Volatile WREN).",
                            root_cause_guide="【Root Cause 排查建議】寫入狀態暫存器前需發送 0x06 或 0x50 指令。\n",
                            details={"opcode": f"0x{op:02X}"},
                        )
                    )
                elif wel_latched is None and not volatile_wel_latched:
                    issues.append(
                        SPIDiagnosticIssue(
                            code="SPI_WEL_STATE_UNKNOWN",
                            title=f"Status-register write WEL state was not observed @ Tx #{tx.index}",
                            severity=SPISeverity.WARNING,
                            timestamp=tx.start_time,
                            transaction_id=tx.index,
                            description=(
                                f"No WREN or status evidence was captured before {tx.opcode_name}; "
                                "the write-enable precondition cannot be proven."
                            ),
                            root_cause_guide="擴大擷取範圍至 WREN/RDSR，確認狀態暫存器寫入前的 WEL 狀態。",
                            details={
                                "opcode": f"0x{op:02X}",
                                "wel_state": None,
                                "evidence": "unobserved",
                            },
                        )
                    )
                wel_latched = False
                volatile_wel_latched = False

            # 4. Page Program Wrap-around Hazard
            if op in (
                SPIOpcode.PAGE_PROGRAM,
                SPIOpcode.QUAD_PAGE_PROGRAM,
            ) and tx.decoded_details.get("page_wrap_hazard"):
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
                            f"Total 0x{start_off:02X} + {p_len} = {start_off + p_len} exceeds {self.max_page_size}-byte page boundary."
                        ),
                        root_cause_guide=(
                            "【Root Cause 排查建議】\n"
                            f"1. 目前設定的 SPI NOR Page Buffer 為 {self.max_page_size} bytes；請以 datasheet 確認。\n"
                            "2. 跨 Page 寫入時位址指標可能 Wrap-around 回同一頁開頭，覆蓋既有資料。\n"
                            f"3. 修正方案：韌體中封裝 Page Write 驅動時，計算 chunk = min(length, page_size - (addr % page_size))。"
                        ),
                        details={
                            "page_offset": start_off,
                            "payload_len": p_len,
                            "page_size": self.max_page_size,
                        },
                    )
                )

            # 5. Truncated Transaction Checks
            four_byte_ops = (
                SPIOpcode.READ_DATA,
                SPIOpcode.FAST_READ,
                SPIOpcode.PAGE_PROGRAM,
                SPIOpcode.QUAD_PAGE_PROGRAM,
                SPIOpcode.SECTOR_ERASE_4K,
                SPIOpcode.BLOCK_ERASE_32K,
                SPIOpcode.BLOCK_ERASE_64K,
            )
            if op in four_byte_ops and len(tx.mosi_bytes) < 4:
                issues.append(
                    SPIDiagnosticIssue(
                        code="SPI_TRUNCATED_TX",
                        title=f"Incomplete SPI Command / Early CS Deassertion @ Tx #{tx.index}",
                        severity=SPISeverity.ERROR,
                        timestamp=tx.start_time,
                        transaction_id=tx.index,
                        description=f"Command {tx.opcode_name} requires at least 4 bytes (Opcode + 24-bit Address), but CS went high after {len(tx.mosi_bytes)} byte(s).",
                        root_cause_guide="【Root Cause 排查建議】檢查 CS# 線路是否有訊號雜訊或 DMA 長度配置不足。\n",
                        details={"received_bytes": len(tx.mosi_bytes), "expected_min": 4},
                    )
                )

        if len(issues) > self.limits.max_findings:
            raise ResourceLimitError(
                f"SPI findings exceed the {self.limits.max_findings}-finding safety limit",
                resource="findings",
                limit=self.limits.max_findings,
                observed=len(issues),
            )
        return issues
