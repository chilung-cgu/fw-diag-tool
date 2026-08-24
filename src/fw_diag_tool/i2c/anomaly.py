"""I2C / SMBus / PMBus Anomaly Detection & Junior Engineer Diagnostic Advisor.

Evaluates physical, protocol, timing, and semantic abnormalities:
- Address NACK vs Data NACK diagnosis
- Clock stretching and SMBus 25ms timeout violations
- Missing STOP conditions and Bus Stuck Low scenarios
- EEPROM Page Boundary Wrap-Around hazards
- Frequency jitter and rise-time issues
Provides actionable root-cause analysis and step-by-step debug checklists.
"""

from __future__ import annotations

import math
from bisect import bisect_right

from fw_diag_tool.errors import ResourceLimitError
from fw_diag_tool.i2c.models import (
    AckType,
    I2CDiagnosticIssue,
    I2CDirection,
    I2CTransaction,
    Severity,
    TimingStatistics,
)
from fw_diag_tool.limits import AnalysisLimits, coerce_limits


class I2CAnomalyDetector:
    """Detects bus anomalies and generates step-by-step junior engineer advice."""

    _EEPROM_ACK_POLL_WINDOW_S = 0.010

    def __init__(
        self,
        smbus_timeout_ms: float = 25.0,
        high_jitter_threshold_pct: float = 35.0,
        *,
        limits: AnalysisLimits | None = None,
    ):
        self.limits = coerce_limits(limits)
        self.smbus_timeout_ms = self._positive_finite_config(
            "smbus_timeout_ms", smbus_timeout_ms, maximum=60_000.0
        )
        self.high_jitter_threshold_pct = self._positive_finite_config(
            "high_jitter_threshold_pct", high_jitter_threshold_pct, maximum=10_000.0
        )

    @staticmethod
    def _positive_finite_config(name: str, value: object, *, maximum: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a finite numeric value")
        parsed = float(value)
        if not math.isfinite(parsed) or parsed <= 0 or parsed > maximum:
            raise ValueError(f"{name} must be > 0 and <= {maximum:g}")
        return parsed

    def analyze_transactions(
        self, transactions: list[I2CTransaction], timing_stats: TimingStatistics
    ) -> list[I2CDiagnosticIssue]:
        """Run full battery of diagnostic checks across all transactions."""
        if not isinstance(transactions, list):
            raise TypeError("transactions must be a list")
        if any(not isinstance(tx, I2CTransaction) for tx in transactions):
            raise TypeError("transactions must contain I2CTransaction objects")
        if len(transactions) > self.limits.max_transactions:
            raise ResourceLimitError(
                f"I2C capture exceeds the {self.limits.max_transactions}-transaction safety limit",
                resource="transactions",
                limit=self.limits.max_transactions,
                observed=len(transactions),
            )
        if not isinstance(timing_stats, TimingStatistics):
            raise TypeError("timing_stats must be a TimingStatistics object")
        issues: list[I2CDiagnosticIssue] = []
        eeprom_probe_times = self._build_eeprom_probe_index(transactions)

        if not transactions:
            return issues

        # 1. Transaction-level checks
        for i, tx in enumerate(transactions):
            if not tx.address_available:
                # The engine retains incomplete transactions for evidence reporting, but
                # anomaly text must not turn placeholder 0x00 values into facts.
                continue
            direction_label = tx.direction.value if tx.direction_available else "UNKNOWN"
            # Check Address NACK
            if tx.address_ack == AckType.NACK:
                # Check if this is EEPROM Acknowledge Polling (expected during internal write cycle)
                is_eeprom = bool(tx.device_category and "EEPROM" in tx.device_category)
                if is_eeprom and self._is_confirmed_eeprom_ack_poll(
                    transactions, i, eeprom_probe_times
                ):
                    issues.append(
                        I2CDiagnosticIssue(
                            code="I2C_EEPROM_ACK_POLL",
                            title=f"EEPROM Write Polling NACK on 0x{tx.address_7bit:02X}",
                            severity=Severity.INFO,
                            category="Protocol/EEPROM",
                            timestamp=tx.start_time,
                            transaction_id=tx.id,
                            address_7bit=tx.address_7bit,
                            description=(
                                f"Slave at 0x{tx.address_7bit:02X} returned NACK to address byte during write polling. "
                                f"This is normal behavior while the EEPROM is executing its internal tWR write cycle (~5ms)."
                            ),
                            root_cause_analysis=(
                                "EEPROM hardware disables its I2C receiver during high-voltage page programming. "
                                "Firmware is probing the device until ACK is returned, signaling write completion."
                            ),
                            actionable_advice=[
                                "No bug if subsequent polling transactions succeed with ACK within 5ms to 10ms.",
                                "If polling loops exceed 10ms without ACK, verify write voltage and EEPROM WP pin.",
                            ],
                        )
                    )
                else:
                    issues.append(
                        I2CDiagnosticIssue(
                            code="I2C_ADDR_NACK",
                            title=f"Address NACK on 0x{tx.address_7bit:02X} ({direction_label})",
                            severity=Severity.ERROR,
                            category="Protocol/Addressing",
                            timestamp=tx.start_time,
                            transaction_id=tx.id,
                            address_7bit=tx.address_7bit,
                            description=(
                                f"Slave device at 7-bit address 0x{tx.address_7bit:02X} (8-bit 0x{tx.address_8bit:02X}) "
                                f"did NOT acknowledge its address."
                            ),
                            root_cause_analysis=(
                                "1. Slave is unpowered or in Deep Sleep / Reset state.\n"
                                "2. 7-bit vs 8-bit addressing bug in firmware (e.g. passing 0x50 as 8-bit address instead of shifting left, or vice versa).\n"
                                "3. Hardware address strapping resistors (ADDR/A0/A1/A2 pins) do not match software address.\n"
                                "4. Upstream I2C Switch/Mux (e.g. PCA9548A) channel is closed or disabled.\n"
                                "5. Open-drain bus lines missing pull-up resistors or damaged pull-up circuit."
                            ),
                            actionable_advice=[
                                "【硬體量測】用萬用電表或示波器量測 Slave 晶片 VCC / VDD 供電腳位是否已正常上電。",
                                "【位址檢查】檢查程式碼中傳入的位址是 7-bit (0x50) 還是 8-bit (0xA0)；多數 Linux i2c-dev / HAL 驅動庫要求傳入 7-bit 位址。",
                                "【Pin Strapping】對照電路圖確認 ADDR / A0 / A1 / A2 腳位的上拉 / 下拉電阻設定與實際量測電壓。",
                                "【Mux 通道】若系統中有多路 I2C Switch (PCA9548A)，確認存取前是否已先下 Command 開啟對應 Channel。",
                            ],
                        )
                    )

            # Check Data NACK
            data_packets = [
                pkt for pkt in tx.byte_packets if not pkt.is_address and pkt.byte_available
            ]
            for byte_idx, pkt in enumerate(data_packets) if tx.direction_available else []:
                if pkt.ack == AckType.NACK:
                    if tx.direction == I2CDirection.READ:
                        # Master Read NACK on last byte is normal protocol termination
                        if byte_idx == len(data_packets) - 1:
                            pass  # Normal I2C Master NACK before STOP
                        else:
                            issues.append(
                                I2CDiagnosticIssue(
                                    code="I2C_PREMATURE_READ_NACK",
                                    title=f"Premature Master Read NACK on Byte {byte_idx + 1}/{len(tx.byte_packets)}",
                                    severity=Severity.WARNING,
                                    category="Protocol",
                                    timestamp=pkt.timestamp,
                                    transaction_id=tx.id,
                                    address_7bit=tx.address_7bit,
                                    description=f"Master issued NACK on byte index {byte_idx} before completing intended multi-byte read.",
                                    root_cause_analysis="Master I2C controller receive FIFO aborted transfer early, or firmware read buffer length was configured shorter than expected.",
                                    actionable_advice=[
                                        "檢查 Master 韌體中的 I2C 讀取長度參數 (length / count) 是否與 Slave 資料長度匹配。"
                                    ],
                                )
                            )
                    else:
                        # Slave Write Data NACK (Abnormal!)
                        issues.append(
                            I2CDiagnosticIssue(
                                code="I2C_DATA_NACK",
                                title=f"Slave Data NACK on Byte {byte_idx} (0x{pkt.byte_val:02X}) at 0x{tx.address_7bit:02X}",
                                severity=Severity.ERROR,
                                category="Protocol/SlaveRejection",
                                timestamp=pkt.timestamp,
                                transaction_id=tx.id,
                                address_7bit=tx.address_7bit,
                                affected_bytes=[pkt.byte_val],
                                description=(
                                    f"Slave acknowledged address but sent NACK on data byte 0x{pkt.byte_val:02X} "
                                    f"(offset/byte position {byte_idx})."
                                ),
                                root_cause_analysis=(
                                    "1. Invalid or unsupported register address / command code.\n"
                                    "2. Attempt to write to a Read-Only register.\n"
                                    "3. Slave internal buffer/FIFO full or chip busy processing previous task.\n"
                                    "4. Write protection active (e.g. EEPROM WP pin pulled high, PMBus WRITE_PROTECT active).\n"
                                    "5. Packet Error Check (PEC) checksum byte was incorrect."
                                ),
                                actionable_advice=[
                                    "【暫存器檢查】查閱晶片手冊確認 0x"
                                    + f"{pkt.byte_val:02X}"
                                    + " 是否為合法的可寫入暫存器。",
                                    "【寫入保護】檢查晶片 WP (Write Protect) 腳位電位，或檢查是否啟用了軟體防寫指令 (如 PMBus 0x10 WRITE_PROTECT)。",
                                    "【長度與延遲】在寫入大筆資料時，檢查 Slave 是否需要 Inter-byte delay 或寫入延遲。",
                                ],
                            )
                        )

            # Check Missing STOP / Aborted Transaction
            if (
                not tx.has_stop
                and not tx.is_repeated_start
                and (i == len(transactions) - 1 or transactions[i + 1].is_repeated_start is False)
            ):
                issues.append(
                    I2CDiagnosticIssue(
                        code="I2C_MISSING_STOP",
                        title=f"Missing STOP Condition / Bus Hang on Transaction #{tx.id}",
                        severity=Severity.CRITICAL if tx.is_aborted else Severity.WARNING,
                        category="Protocol/BusState",
                        timestamp=tx.end_time,
                        transaction_id=tx.id,
                        address_7bit=tx.address_7bit,
                        description=f"Transaction #{tx.id} to 0x{tx.address_7bit:02X} ended abruptly without a valid STOP condition.",
                        root_cause_analysis=(
                            "1. Master MCU crashed, hit a watchdog reset, or I2C peripheral encountered an error interrupt midway.\n"
                            "2. Bus Stuck Low: Slave was outputting a '0' bit on SDA when Master aborted, leaving Slave holding SDA low.\n"
                            "3. Physical line noise or clock glitch corrupted the transaction state machine."
                        ),
                        actionable_advice=[
                            "【Bus Recovery】在韌體中實作 9-Clock Reset 機制：將 SCL 切為 GPIO 輸出連續產生 9 個 Clock Pulse (釋放 SDA)，隨後發送 STOP 條件恢復匯流排。",
                            "【Slave Reset】若 Slave 仍持續拉低 SDA/SCL，觸發 Slave 的硬體 Reset 腳位或執行 Power Cycle。",
                        ],
                    )
                )

            # Check EEPROM Page Rollover hazard in transaction decoded values
            if tx.decoded_values and tx.decoded_values.get("rollover_hazard"):
                issues.append(
                    I2CDiagnosticIssue(
                        code="I2C_EEPROM_PAGE_ROLLOVER",
                        title=f"EEPROM Page Boundary Wrap-Around Hazard on 0x{tx.address_7bit:02X}",
                        severity=Severity.ERROR,
                        category="Semantic/EEPROM",
                        timestamp=tx.start_time,
                        transaction_id=tx.id,
                        address_7bit=tx.address_7bit,
                        description=tx.decoded_values.get(
                            "rollover_details", "Page write exceeded page size boundary!"
                        ),
                        root_cause_analysis=(
                            "EEPROM internal address counter increments within the current page boundary. "
                            "When writing past the end of a page, the address wraps to the start of the SAME page, "
                            "silently corrupting previously written bytes at the page base instead of advancing to the next page!"
                        ),
                        actionable_advice=[
                            "【分頁演算法修正】修改韌體寫入驅動，在寫入前計算: remaining_in_page = page_size - (offset % page_size)。",
                            "【批次寫入】若寫入長度大於 remaining_in_page，必須拆分為兩次獨立的 Page Write，並在兩次寫入之間等待 tWR (5ms) 或使用 ACK Polling。",
                        ],
                    )
                )

            # Check Clock Stretching events
            for stretch in tx.clock_stretching_events:
                dur_ms = stretch.get("duration_ms", 0.0)
                if dur_ms >= self.smbus_timeout_ms:
                    issues.append(
                        I2CDiagnosticIssue(
                            code="I2C_SMBUS_TIMEOUT",
                            title=f"SMBus Clock Stretching Timeout ({dur_ms:.2f} ms > {self.smbus_timeout_ms} ms)",
                            severity=Severity.CRITICAL,
                            category="Timing/Physical",
                            timestamp=stretch.get("timestamp", tx.start_time),
                            transaction_id=tx.id,
                            address_7bit=tx.address_7bit,
                            description=(
                                f"Slave at 0x{tx.address_7bit:02X} held SCL low for {dur_ms:.2f} ms, "
                                f"violating SMBus 3.0 tTIMEOUT limit ({self.smbus_timeout_ms} ms)."
                            ),
                            root_cause_analysis=(
                                "Slave MCU firmware entered a deadlock, long blocking interrupt routine, or hardware lockup, "
                                "holding SCL low indefinitely. SMBus-compliant masters and slaves will reset their interfaces."
                            ),
                            actionable_advice=[
                                "【Slave 韌體排查】檢查 Slave 端 I2C 中斷服務常式 (ISR) 是否包含耗時的 printf、阻塞延遲或死鎖。",
                                "【超時機制】Master 端應配置硬體 I2C Timeout (25ms~35ms) 並在超時後觸發 Bus Recovery。",
                            ],
                        )
                    )
                elif dur_ms > 0.1:  # > 100 us
                    issues.append(
                        I2CDiagnosticIssue(
                            code="I2C_LONG_CLOCK_STRETCH",
                            title=f"Noticeable Clock Stretching ({dur_ms * 1000:.1f} µs) on 0x{tx.address_7bit:02X}",
                            severity=Severity.WARNING,
                            category="Timing/Performance",
                            timestamp=stretch.get("timestamp", tx.start_time),
                            transaction_id=tx.id,
                            address_7bit=tx.address_7bit,
                            description=f"Slave held SCL low for {dur_ms * 1000:.1f} µs during byte transfer.",
                            root_cause_analysis="Slave requires significant processing time or is executing an internal ADC conversion / Flash write.",
                            actionable_advice=[
                                "評估是否改用 Polling 或非阻塞方式讀取，避免 Slave 拉低 SCL 拖慢整個匯流排效能。"
                            ],
                        )
                    )

        # 2. Global Bus Health & Timing Checks
        if (
            timing_stats.frequency_jitter_pct > self.high_jitter_threshold_pct
            and timing_stats.avg_frequency_khz > 0
        ):
            issues.append(
                I2CDiagnosticIssue(
                    code="I2C_HIGH_CLOCK_JITTER",
                    title=f"High Clock Frequency Jitter ({timing_stats.frequency_jitter_pct:.1f}% > {self.high_jitter_threshold_pct}%)",
                    severity=Severity.WARNING,
                    category="Physical/Timing",
                    description=(
                        f"Observed SCL clock frequency fluctuates between {timing_stats.min_frequency_khz:.1f} kHz "
                        f"and {timing_stats.max_frequency_khz:.1f} kHz (Average: {timing_stats.avg_frequency_khz:.1f} kHz)."
                    ),
                    root_cause_analysis=(
                        "1. Software bit-banging I2C driver interrupted by high-priority RTOS interrupts / ISRs.\n"
                        "2. Excessive bus capacitance (>400pF) causing slow rise times (t_r) and trigger threshold delay.\n"
                        "3. Pull-up resistors too large (e.g. 10kΩ on Fast-mode 400kHz)."
                    ),
                    actionable_advice=[
                        "【硬體電阻】若運行於 Fast-mode (400kHz)，建議將上拉電阻調整為 2.2kΩ ~ 4.7kΩ，確保上升時間 tr < 300ns。",
                        "【硬體控制器】建議改用 SoC 內建的硬體 I2C Controller (DMA / FIFO)，避免 GPIO Bit-banging 造成時鐘抖動。",
                    ],
                )
            )

        if len(issues) > self.limits.max_findings:
            raise ResourceLimitError(
                f"I2C findings exceed the {self.limits.max_findings}-finding safety limit",
                resource="findings",
                limit=self.limits.max_findings,
                observed=len(issues),
            )
        return issues

    @classmethod
    def _build_eeprom_probe_index(
        cls, transactions: list[I2CTransaction]
    ) -> dict[int, list[tuple[float, int]]]:
        probes: dict[int, list[tuple[float, int]]] = {}
        for index, transaction in enumerate(transactions):
            if (
                transaction.timestamp_available
                and transaction.direction_available
                and transaction.direction == I2CDirection.WRITE
                and transaction.address_ack == AckType.ACK
                and transaction.has_stop
            ):
                probes.setdefault(transaction.address_7bit, []).append(
                    (transaction.start_time, index)
                )
        for candidates in probes.values():
            candidates.sort()
        return probes

    @classmethod
    def _is_confirmed_eeprom_ack_poll(
        cls,
        transactions: list[I2CTransaction],
        nack_index: int,
        probe_times: dict[int, list[tuple[float, int]]] | None = None,
    ) -> bool:
        """Require evidence for an EEPROM write-cycle polling interpretation.

        A lone address NACK is not enough to call something normal ACK polling: it
        may instead indicate a missing device or a permanently failed bus.  We
        therefore require an accepted, stopped write immediately before the NACK,
        no rejected data in that write, and a later accepted probe within a bounded
        tWR-style window.  Missing timestamps deliberately disable this inference.
        """
        if not 0 <= nack_index < len(transactions):
            return False
        nack = transactions[nack_index]
        if (
            nack.address_ack != AckType.NACK
            or nack.data_bytes
            or not nack.timestamp_available
            or not nack.has_stop
            or nack_index == 0
        ):
            return False

        previous = transactions[nack_index - 1]
        if (
            not previous.timestamp_available
            or not previous.has_stop
            or not previous.direction_available
            or previous.direction != I2CDirection.WRITE
            or previous.address_7bit != nack.address_7bit
            or previous.address_ack != AckType.ACK
            or not previous.data_bytes
            or previous.has_unexpected_data_nack
        ):
            return False

        probes = probe_times if probe_times is not None else cls._build_eeprom_probe_index(transactions)
        candidates = probes.get(nack.address_7bit, [])
        if not candidates:
            return False
        probe_index = bisect_right(candidates, (nack.start_time, nack_index))
        if probe_index >= len(candidates):
            return False
        candidate_time, candidate_index = candidates[probe_index]
        return (
            candidate_index > nack_index
            and candidate_time - nack.start_time <= cls._EEPROM_ACK_POLL_WINDOW_S
        )
