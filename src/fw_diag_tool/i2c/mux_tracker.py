from __future__ import annotations

from typing import Any
from .models import AckType, I2CDirection, I2CTransaction, I2CDiagnosticIssue, Severity


MUX_ADDRESSES = {0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77}


class I2CMuxTracker:
    def __init__(self):
        self.mux_states: dict[int, int] = {}
        self.last_active_mux: int | None = None

    def process_transactions(self, transactions: list[I2CTransaction]) -> list[I2CDiagnosticIssue]:
        issues: list[I2CDiagnosticIssue] = []

        for tx in transactions:
            addr = tx.address_7bit

            if addr in MUX_ADDRESSES:
                if tx.direction == I2CDirection.WRITE and tx.data_bytes and tx.address_ack == AckType.ACK:
                    ctrl_byte = tx.data_bytes[0]
                    self.mux_states[addr] = ctrl_byte
                    self.last_active_mux = addr
                    active_channels = [ch for ch in range(8) if (ctrl_byte & (1 << ch))]
                    tx.semantic_summary = f"I2C MUX 0x{addr:02X} Channel Switch -> {active_channels if active_channels else ['All Disabled']}"
                    tx.device_category = "I2C Multiplexer (PCA9548A/PCA9546)"

                    if len(active_channels) > 1:
                        issues.append(I2CDiagnosticIssue(
                            code="I2C_MUX_MULTI_CHANNEL",
                            title=f"Multiple MUX Channels Enabled Simultaneously (0x{addr:02X}) @ Tx #{tx.id}",
                            severity=Severity.WARNING,
                            category="Topology/MUX",
                            timestamp=tx.start_time,
                            transaction_id=tx.id,
                            address_7bit=addr,
                            description=(
                                f"I2C Mux at 0x{addr:02X} was configured with control byte 0x{ctrl_byte:02X}, "
                                f"enabling channels {active_channels} simultaneously."
                            ),
                            root_cause_analysis=(
                                "Enabling multiple downstream MUX channels simultaneously can cause address collisions "
                                "and excessive bus capacitance (> 400pF). "
                            ),
                            actionable_advice=[
                                "1. Ensure only 1 downstream channel is enabled unless broadcast write is intended.",
                                "2. Verify identical slave addresses on different channels do not respond concurrently."
                            ]
                        ))
                continue

            if self.last_active_mux is not None:
                mask = self.mux_states.get(self.last_active_mux, 0)
                active_channels = [ch for ch in range(8) if (mask & (1 << ch))]
                if active_channels:
                    ch_str = ",".join(f"Ch{c}" for c in active_channels)
                    tx.mux_topology = f"[MUX 0x{self.last_active_mux:02X}: {ch_str}] -> Slave 0x{addr:02X}"
                    tx.mux_channels = active_channels
                else:
                    tx.mux_topology = f"[MUX 0x{self.last_active_mux:02X}: ALL_OFF] -> Slave 0x{addr:02X}"
                    tx.mux_channels = []

        return issues