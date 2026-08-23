from __future__ import annotations

from dataclasses import dataclass, field

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .models import AckType, I2CAnalysisReport, I2CTransaction
from .waveform import I2CWaveformReconstructor


@dataclass
class DivergencePoint:
    tx_index: int
    golden_tx: I2CTransaction | None
    failing_tx: I2CTransaction | None
    mismatch_type: str  # "NACK_MISMATCH", "DATA_MISMATCH", "DIRECTION_MISMATCH", "MISSING_TX"
    description: str
    root_cause_hint: str


@dataclass
class WaveformDiffReport:
    is_identical: bool
    total_compared: int
    divergence_points: list[DivergencePoint] = field(default_factory=list)
    summary: str = ""
    golden_first_tx: I2CTransaction | None = None
    failing_first_tx: I2CTransaction | None = None


class WaveformDiffEngine:
    # Compares Golden (Normal) vs Failing (Defective) I2C traces and pinpoints root divergence

    @staticmethod
    def _ack_outcome(tx: I2CTransaction) -> str:
        """Return a comparison-safe ACK outcome, excluding normal read termination NACK."""
        if tx.address_ack == AckType.NACK:
            return "address_nack"
        if tx.has_unexpected_data_nack:
            return "data_nack"
        if tx.address_ack == AckType.NONE or any(
            packet.ack == AckType.NONE for packet in tx.byte_packets if not packet.is_address
        ):
            return "unknown"
        return "ok"

    @classmethod
    def compare_reports(
        cls,
        golden: I2CAnalysisReport,
        failing: I2CAnalysisReport,
    ) -> WaveformDiffReport:
        divergences: list[DivergencePoint] = []
        g_txs = golden.transactions
        f_txs = failing.transactions
        max_len = max(len(g_txs), len(f_txs))

        if not max_len:
            return WaveformDiffReport(
                is_identical=False,
                total_compared=0,
                summary=(
                    "Insufficient evidence: both golden and failing traces contain no transactions; "
                    "protocol identity cannot be established."
                ),
            )

        for idx in range(max_len):
            g = g_txs[idx] if idx < len(g_txs) else None
            f = f_txs[idx] if idx < len(f_txs) else None

            if g is None and f is not None:
                divergences.append(
                    DivergencePoint(
                        tx_index=idx + 1,
                        golden_tx=None,
                        failing_tx=f,
                        mismatch_type="UNEXPECTED_EXTRA_TX",
                        description=f"Failing trace has unexpected extra transaction #{f.id} to 0x{f.address_7bit:02X} {f.direction.value}",
                        root_cause_hint="檢查韌體是否進入非預期重試迴圈 (Retry Loop)。",
                    )
                )
                break
            elif g is not None and f is None:
                divergences.append(
                    DivergencePoint(
                        tx_index=idx + 1,
                        golden_tx=g,
                        failing_tx=None,
                        mismatch_type="MISSING_TX",
                        description=f"Failing trace terminated prematurely. Expected transaction #{g.id} to 0x{g.address_7bit:02X} was never sent.",
                        root_cause_hint="通訊在上一筆交易失敗後中斷，檢查上一筆交易是否引發了 Bus Hang 或 Driver Exit。",
                    )
                )
                break

            # Both exist: compare address, ACK, direction, and data bytes
            if g and f:
                if g.address_7bit != f.address_7bit:
                    divergences.append(
                        DivergencePoint(
                            tx_index=idx + 1,
                            golden_tx=g,
                            failing_tx=f,
                            mismatch_type="ADDRESS_MISMATCH",
                            description=f"Address mismatch: Golden sent 0x{g.address_7bit:02X}, Failing sent 0x{f.address_7bit:02X}",
                            root_cause_hint="檢查晶片 Address Pin 硬體配置或驅動定址常數。",
                        )
                    )
                    break

                g_ack_outcome = cls._ack_outcome(g)
                f_ack_outcome = cls._ack_outcome(f)
                if g_ack_outcome != f_ack_outcome:
                    divergences.append(
                        DivergencePoint(
                            tx_index=idx + 1,
                            golden_tx=g,
                            failing_tx=f,
                            mismatch_type="NACK_MISMATCH",
                            description=(
                                f"ACK outcome mismatch on 0x{g.address_7bit:02X}: "
                                f"Golden={g_ack_outcome}, Failing={f_ack_outcome}. "
                                "A final controller NACK on a read is treated as normal termination."
                            ),
                            root_cause_hint=(
                                "先確認 NACK 是 address、write-data、read 終止，還是來源欄位缺失；"
                                "只有 address/data NACK 才進一步檢查供電、reset、busy 與 command。"
                            ),
                        )
                    )
                    break

                if g.direction != f.direction:
                    divergences.append(
                        DivergencePoint(
                            tx_index=idx + 1,
                            golden_tx=g,
                            failing_tx=f,
                            mismatch_type="DIRECTION_MISMATCH",
                            description=f"Direction mismatch: Golden={g.direction.value}, Failing={f.direction.value}",
                            root_cause_hint="讀寫方向位元不同步。",
                        )
                    )
                    break

                if g.data_bytes != f.data_bytes:
                    divergences.append(
                        DivergencePoint(
                            tx_index=idx + 1,
                            golden_tx=g,
                            failing_tx=f,
                            mismatch_type="DATA_MISMATCH",
                            description=f"Data payload divergence on 0x{g.address_7bit:02X}: Golden={g.hex_dump}, Failing={f.hex_dump}",
                            root_cause_hint="資料內容不一致，檢查暫存器初始值或 EEPROM 儲存內容是否受損。",
                        )
                    )
                    break

        is_id = len(divergences) == 0
        summary = (
            "Golden and Failing traces are 100% identical in protocol sequence."
            if is_id
            else f"Found {len(divergences)} divergence point(s). First mismatch at Transaction #{divergences[0].tx_index}."
        )

        return WaveformDiffReport(
            is_identical=is_id,
            total_compared=max_len,
            divergence_points=divergences,
            summary=summary,
            golden_first_tx=g_txs[0] if g_txs else None,
            failing_first_tx=f_txs[0] if f_txs else None,
        )

    @classmethod
    def create_comparison_figure(
        cls,
        diff_report: WaveformDiffReport,
        title: str = "Golden vs Failing Trace Waveform Comparison",
    ) -> go.Figure:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=False,
            vertical_spacing=0.12,
            subplot_titles=("Golden (Normal Board) Waveform", "Failing (Defective Board) Waveform"),
        )

        reconstructor = I2CWaveformReconstructor(default_clock_khz=100.0)

        if diff_report.is_identical:
            if diff_report.golden_first_tx:
                g_wave = reconstructor.reconstruct_transaction_waveform(diff_report.golden_first_tx)
                fig.add_trace(
                    go.Scatter(
                        x=g_wave.time_us,
                        y=g_wave.sda,
                        mode="lines",
                        line=dict(shape="hv", color="#00CC96", width=2),
                        name="Golden SDA",
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=g_wave.time_us,
                        y=g_wave.scl,
                        mode="lines",
                        line=dict(shape="hv", color="#FFFF00", width=2),
                        name="Golden SCL",
                    ),
                    row=1,
                    col=1,
                )
            if diff_report.failing_first_tx or diff_report.golden_first_tx:
                target_tx = diff_report.failing_first_tx
                if target_tx is None:
                    target_tx = diff_report.golden_first_tx
                if target_tx is None:
                    raise RuntimeError("identical diff report has no source transaction")
                f_wave = reconstructor.reconstruct_transaction_waveform(target_tx)
                fig.add_trace(
                    go.Scatter(
                        x=f_wave.time_us,
                        y=f_wave.sda,
                        mode="lines",
                        line=dict(shape="hv", color="#00CC96", width=2),
                        name="Failing (Identical) SDA",
                    ),
                    row=2,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=f_wave.time_us,
                        y=f_wave.scl,
                        mode="lines",
                        line=dict(shape="hv", color="#FFFF00", width=2),
                        name="Failing (Identical) SCL",
                    ),
                    row=2,
                    col=1,
                )
        else:
            if diff_report.divergence_points and diff_report.divergence_points[0].golden_tx:
                g_tx = diff_report.divergence_points[0].golden_tx
                g_wave = reconstructor.reconstruct_transaction_waveform(g_tx)
                fig.add_trace(
                    go.Scatter(
                        x=g_wave.time_us,
                        y=g_wave.sda,
                        mode="lines",
                        line=dict(shape="hv", color="#00CC96", width=2),
                        name="Golden SDA",
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=g_wave.time_us,
                        y=g_wave.scl,
                        mode="lines",
                        line=dict(shape="hv", color="#FFFF00", width=2),
                        name="Golden SCL",
                    ),
                    row=1,
                    col=1,
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=[0, 10],
                        y=[1, 1],
                        mode="lines",
                        line=dict(dash="dot", color="#7F7F7F"),
                        name="No Transaction (Terminated)",
                    ),
                    row=1,
                    col=1,
                )

            if diff_report.divergence_points and diff_report.divergence_points[0].failing_tx:
                f_tx = diff_report.divergence_points[0].failing_tx
                f_wave = reconstructor.reconstruct_transaction_waveform(f_tx)
                fig.add_trace(
                    go.Scatter(
                        x=f_wave.time_us,
                        y=f_wave.sda,
                        mode="lines",
                        line=dict(shape="hv", color="#EF553B", width=2),
                        name="Failing SDA",
                    ),
                    row=2,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=f_wave.time_us,
                        y=f_wave.scl,
                        mode="lines",
                        line=dict(shape="hv", color="#FFA15A", width=2),
                        name="Failing SCL",
                    ),
                    row=2,
                    col=1,
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=[0, 10],
                        y=[1, 1],
                        mode="lines",
                        line=dict(dash="dot", color="#7F7F7F"),
                        name="No Transaction (Missing)",
                    ),
                    row=2,
                    col=1,
                )

        fig.update_layout(
            title=dict(text=f"<b>{title}</b>", font=dict(size=15, color="#FFFFFF")),
            template="plotly_dark",
            height=450,
            margin=dict(l=40, r=20, t=50, b=30),
        )
        return fig
