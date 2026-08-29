from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .models import AckType, I2CAnalysisReport, I2CDirection, I2CTransaction
from .waveform import I2CWaveformReconstructor


@dataclass
class DivergencePoint:
    tx_index: int
    golden_tx: I2CTransaction | None
    failing_tx: I2CTransaction | None
    mismatch_type: str  # protocol, retry, dropped-transaction, or phase-shift classification
    description: str
    root_cause_hint: str
    golden_index: int | None = None
    failing_index: int | None = None
    alignment_offset: int | None = None


@dataclass
class WaveformDiffReport:
    is_identical: bool
    total_compared: int
    divergence_points: list[DivergencePoint] = field(default_factory=list)
    summary: str = ""
    golden_first_tx: I2CTransaction | None = None
    failing_first_tx: I2CTransaction | None = None
    alignment: list[tuple[int | None, int | None]] = field(default_factory=list)


class WaveformDiffEngine:
    # Compares Golden (Normal) vs Failing (Defective) I2C traces and pinpoints root divergence

    _SOURCE_LIMITATION_CODES = frozenset(
        {
            "I2C_UNKNOWN_EVENT_TYPE",
            "I2C_SEMANTIC_EVIDENCE_INCOMPLETE",
        }
    )

    _FAILED_ACK_OUTCOMES = frozenset(
        {
            "address_nack",
            "aggregate_nack",
            "data_nack",
        }
    )
    _MAX_ALIGNMENT_MATCHES = 2_000_000

    @classmethod
    def _has_source_limitation(cls, report: I2CAnalysisReport) -> bool:
        """Return whether parser/source evidence makes protocol identity unprovable."""
        if any(tx.source_error and tx.aggregate_ack == AckType.NONE for tx in report.transactions):
            return True
        return any(
            issue.code in cls._SOURCE_LIMITATION_CODES for issue in report.data_quality_issues
        )

    @staticmethod
    def _has_unprovable_protocol_evidence(report: I2CAnalysisReport) -> bool:
        """Return whether ACK/framing fields are too incomplete for identity claims."""
        for tx in report.transactions:
            if tx.aggregate_ack != AckType.NONE:
                # Aggregate ACK/NACK is intentionally compared as its own
                # outcome; do not reinterpret its per-byte NONE values here.
                continue
            if tx.address_ack in (AckType.NONE, None):
                return True
            if any(packet.ack in (AckType.NONE, None) for packet in tx.byte_packets):
                return True
            if not tx.has_stop and not tx.is_repeated_start:
                return True
        limitation_codes = {
            "I2C_ACK_UNAVAILABLE",
            "I2C_ADDRESS_UNAVAILABLE",
            "I2C_DIRECTION_UNAVAILABLE",
            "I2C_DATA_UNAVAILABLE",
            "I2C_TIMESTAMP_OUT_OF_ORDER",
        }
        for issue in report.data_quality_issues:
            if (
                issue.code == "I2C_ACK_UNAVAILABLE"
                and report.transactions
                and all(tx.aggregate_ack != AckType.NONE for tx in report.transactions)
            ):
                continue
            if issue.code in limitation_codes:
                return True
        return False

    @staticmethod
    def _ack_outcome(tx: I2CTransaction) -> str:
        """Return a comparison-safe ACK outcome, excluding normal read termination NACK."""
        if tx.address_ack == AckType.NACK:
            return "address_nack"
        if tx.aggregate_ack == AckType.NACK:
            return "aggregate_nack"
        if tx.aggregate_ack == AckType.ACK:
            return "aggregate_ack"
        if tx.has_unexpected_data_nack:
            return "data_nack"
        if tx.address_ack == AckType.NONE or any(
            packet.ack == AckType.NONE for packet in tx.byte_packets if not packet.is_address
        ):
            return "unknown"
        return "ok"

    @staticmethod
    def _protocol_key(tx: I2CTransaction) -> tuple[int, I2CDirection, tuple[int, ...]] | None:
        """Return fields safe for sequence alignment, excluding ACK and timing.

        A transaction with an unavailable address/direction or byte is not an
        alignment anchor.  Treating a partially captured packet as an exact
        key can turn a dropped packet into a false retry or a false match.
        """
        if (
            tx.source_error
            or not tx.address_available
            or not tx.direction_available
            or not isinstance(tx.direction, I2CDirection)
        ):
            return None
        if any(not packet.byte_available for packet in tx.byte_packets):
            return None
        return (tx.address_7bit, tx.direction, tuple(tx.data_bytes))

    @classmethod
    def _is_retry_attempt(cls, anchor: I2CTransaction, candidate: I2CTransaction) -> bool:
        """Return whether candidate is a failed same-command attempt."""
        anchor_key = cls._protocol_key(anchor)
        candidate_key = cls._protocol_key(candidate)
        if cls._ack_outcome(candidate) not in cls._FAILED_ACK_OUTCOMES:
            return False
        if anchor_key is not None and anchor_key == candidate_key:
            return True
        return (
            cls._ack_outcome(candidate) == "address_nack"
            and cls._same_endpoint(anchor, candidate)
            and not candidate.data_bytes
        )

    @staticmethod
    def _same_endpoint(golden: I2CTransaction, failing: I2CTransaction) -> bool:
        """Return whether two rows target the same address and direction."""
        return (
            golden.address_7bit == failing.address_7bit
            and golden.direction == failing.direction
        )

    @staticmethod
    def _next_position(
        positions: dict[object, list[int]],
        key: object,
        start: int,
        limit: int | None = None,
    ) -> int | None:
        """Find the first indexed occurrence in O(log n) time."""
        candidates = positions.get(key)
        if not candidates:
            return None
        offset = bisect_left(candidates, start)
        if offset >= len(candidates):
            return None
        candidate = candidates[offset]
        return candidate if limit is None or candidate < limit else None

    @classmethod
    def _next_distinct_anchor_limit(
        cls,
        failing_positions: dict[object, list[int]],
        failing_start: int,
        next_distinct_key: tuple[int, I2CDirection, tuple[int, ...]] | None,
    ) -> int | None:
        """Return the next expected command boundary in the failing trace."""
        if next_distinct_key is None:
            return None
        return cls._next_position(failing_positions, next_distinct_key, failing_start)

    @classmethod
    def _find_alignment_candidate(
        cls,
        golden: list[I2CTransaction],
        failing_positions: dict[object, list[int]],
        failing_ack_positions: dict[object, list[int]],
        golden_index: int,
        failing_start: int,
        previous_key: tuple[int, I2CDirection, tuple[int, ...]] | None,
        previous_was_paired: bool,
        next_distinct_key: tuple[int, I2CDirection, tuple[int, ...]] | None,
    ) -> int | None:
        """Find the best same-command failing transaction for one golden row."""
        golden_tx = golden[golden_index]
        key = cls._protocol_key(golden_tx)
        if key is None:
            return None
        first_same_key = cls._next_position(failing_positions, key, failing_start)
        if first_same_key is None:
            return None
        limit = cls._next_distinct_anchor_limit(
            failing_positions, failing_start, next_distinct_key
        )
        if (
            limit is not None
            and first_same_key >= limit
            and not (previous_was_paired and previous_key == next_distinct_key)
        ):
            return None
        if limit is None or first_same_key >= limit:
            limit = None
        ack_key = (key, cls._ack_outcome(golden_tx))
        exact_ack = cls._next_position(failing_ack_positions, ack_key, failing_start, limit)
        if exact_ack is not None:
            return exact_ack
        return first_same_key

    @classmethod
    def _build_exact_alignment(
        cls,
        golden: list[I2CTransaction],
        failing: list[I2CTransaction],
    ) -> list[tuple[int, int]] | None:
        """Build a longest exact protocol/ACK subsequence.

        Hunt--Szymanski keeps the common case near linear in the number of
        equal tokens.  A cap avoids allocating an unbounded match graph for a
        very long trace consisting almost entirely of one repeated command.
        """
        def token(tx: I2CTransaction, index: int, side: str) -> object:
            key = cls._protocol_key(tx)
            return (
                ("known", key, cls._ack_outcome(tx))
                if key is not None
                else ("unknown", side, index)
            )

        golden_tokens = [token(tx, index, "golden") for index, tx in enumerate(golden)]
        failing_tokens = [token(tx, index, "failing") for index, tx in enumerate(failing)]
        if golden_tokens == failing_tokens:
            return list(zip(range(len(golden)), range(len(failing))))
        if not golden_tokens or not failing_tokens:
            return []

        failing_positions: dict[object, list[int]] = {}
        for index, value in enumerate(failing_tokens):
            failing_positions.setdefault(value, []).append(index)
        edge_count = sum(len(failing_positions.get(value, ())) for value in golden_tokens)
        if edge_count > cls._MAX_ALIGNMENT_MATCHES:
            return None

        tails: list[int] = []
        tail_nodes: list[int] = []
        nodes: list[tuple[int, int, int]] = []
        for golden_index, value in enumerate(golden_tokens):
            for failing_index in reversed(failing_positions.get(value, ())):
                tail = bisect_left(tails, failing_index)
                if tail < len(tails) and tails[tail] == failing_index:
                    continue
                previous = tail_nodes[tail - 1] if tail else -1
                node = len(nodes)
                nodes.append((golden_index, failing_index, previous))
                if tail == len(tails):
                    tails.append(failing_index)
                    tail_nodes.append(node)
                else:
                    tails[tail] = failing_index
                    tail_nodes[tail] = node

        alignment: list[tuple[int, int]] = []
        node = tail_nodes[-1] if tail_nodes else -1
        while node >= 0:
            golden_index, failing_index, node = nodes[node]
            alignment.append((golden_index, failing_index))
        alignment.reverse()
        return alignment

    @staticmethod
    def _append_indexed_divergence(
        divergences: list[DivergencePoint],
        *,
        tx_index: int,
        golden_tx: I2CTransaction | None,
        failing_tx: I2CTransaction | None,
        mismatch_type: str,
        description: str,
        root_cause_hint: str,
        golden_index: int | None = None,
        failing_index: int | None = None,
        alignment_offset: int | None = None,
    ) -> None:
        divergences.append(
            DivergencePoint(
                tx_index=tx_index,
                golden_tx=golden_tx,
                failing_tx=failing_tx,
                mismatch_type=mismatch_type,
                description=description,
                root_cause_hint=root_cause_hint,
                golden_index=golden_index,
                failing_index=failing_index,
                alignment_offset=alignment_offset,
            )
        )

    @classmethod
    def compare_reports(
        cls,
        golden: I2CAnalysisReport,
        failing: I2CAnalysisReport,
    ) -> WaveformDiffReport:
        if not isinstance(golden, I2CAnalysisReport) or not isinstance(failing, I2CAnalysisReport):
            raise TypeError("golden and failing must be I2CAnalysisReport objects")
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

        if cls._has_source_limitation(golden) or cls._has_source_limitation(failing):
            return WaveformDiffReport(
                is_identical=False,
                total_compared=max_len,
                summary=(
                    "Insufficient evidence: at least one trace contains source/parser errors; "
                    "protocol identity and waveform equivalence cannot be established."
                ),
                golden_first_tx=g_txs[0] if g_txs else None,
                failing_first_tx=f_txs[0] if f_txs else None,
            )

        if cls._has_unprovable_protocol_evidence(golden) or cls._has_unprovable_protocol_evidence(
            failing
        ):
            return WaveformDiffReport(
                is_identical=False,
                total_compared=max_len,
                summary=(
                    "Insufficient evidence: at least one trace has unknown ACK or incomplete "
                    "transaction framing; protocol identity cannot be established."
                ),
                golden_first_tx=g_txs[0] if g_txs else None,
                failing_first_tx=f_txs[0] if f_txs else None,
            )

        failing_positions: dict[object, list[int]] = {}
        failing_ack_positions: dict[object, list[int]] = {}
        for failing_index, failing_tx in enumerate(f_txs):
            key = cls._protocol_key(failing_tx)
            if key is None:
                continue
            failing_positions.setdefault(key, []).append(failing_index)
            ack_key = (key, cls._ack_outcome(failing_tx))
            failing_ack_positions.setdefault(ack_key, []).append(failing_index)

        golden_keys = [cls._protocol_key(tx) for tx in g_txs]
        previous_keys: list[tuple[int, I2CDirection, tuple[int, ...]] | None] = [None] * len(
            g_txs
        )
        previous_key: tuple[int, I2CDirection, tuple[int, ...]] | None = None
        for index, key in enumerate(golden_keys):
            previous_keys[index] = previous_key
            if key is not None:
                previous_key = key
        next_distinct_keys: list[
            tuple[int, I2CDirection, tuple[int, ...]] | None
        ] = [None] * len(g_txs)
        nearest_key: tuple[int, I2CDirection, tuple[int, ...]] | None = None
        second_nearest_key: tuple[int, I2CDirection, tuple[int, ...]] | None = None
        for index in range(len(g_txs) - 1, -1, -1):
            key = golden_keys[index]
            if key is not None:
                next_distinct_keys[index] = (
                    nearest_key if nearest_key != key else second_nearest_key
                )
                if nearest_key != key:
                    second_nearest_key = nearest_key
                    nearest_key = key

        exact_alignment = cls._build_exact_alignment(g_txs, f_txs)
        exact_cursor = 0

        alignment: list[tuple[int | None, int | None]] = []
        golden_index = 0
        failing_index = 0
        last_pair_golden: int | None = None
        pending_phase_shift = False
        phase_start_golden: int | None = None
        had_structural_gap = False
        future_anchor_probe = 1

        def append_phase_shift(next_golden_index: int, next_failing_index: int | None) -> None:
            nonlocal pending_phase_shift, phase_start_golden
            if not pending_phase_shift:
                return
            marker_golden_index = (
                next_golden_index
                if next_failing_index is not None
                else (phase_start_golden if phase_start_golden is not None else next_golden_index)
            )
            golden_tx = (
                g_txs[marker_golden_index] if marker_golden_index < len(g_txs) else None
            )
            failing_tx = (
                f_txs[next_failing_index]
                if next_failing_index is not None and next_failing_index < len(f_txs)
                else None
            )
            offset = (
                next_failing_index - marker_golden_index
                if next_failing_index is not None
                else len(f_txs) - len(g_txs)
            )
            cls._append_indexed_divergence(
                divergences,
                tx_index=marker_golden_index + 1,
                golden_tx=golden_tx,
                failing_tx=failing_tx,
                mismatch_type="PHASE_SHIFT",
                description=(
                    "Phase Shift: transaction alignment moved by "
                    f"{offset:+d} after an insertion or dropped transaction."
                ),
                root_cause_hint=(
                    "確認 capture 是否遺失封包、Failing trace 是否包含 retry，並以時間戳與"
                    " repeated-START/STOP 邊界重新核對交易序列。"
                ),
                golden_index=marker_golden_index,
                failing_index=next_failing_index,
                alignment_offset=offset,
            )
            pending_phase_shift = False
            phase_start_golden = None

        def record_pair(pair_golden_index: int, pair_failing_index: int) -> None:
            alignment.append((pair_golden_index, pair_failing_index))
            append_phase_shift(pair_golden_index, pair_failing_index)

        def append_retry_or_extra(
            extra_index: int,
            anchor: I2CTransaction | None,
            *,
            allow_retry: bool,
            retry_successor: int | None = None,
        ) -> None:
            nonlocal pending_phase_shift, phase_start_golden, had_structural_gap
            extra = f_txs[extra_index]
            is_retry = bool(
                allow_retry and anchor is not None and cls._is_retry_attempt(anchor, extra)
            )
            mismatch_type = "RETRY_SEQUENCE" if is_retry else "UNEXPECTED_EXTRA_TX"
            description = (
                f"Retry Sequence: failing transaction #{extra.id} failed; the same command is retried at "
                f"transaction #{f_txs[retry_successor].id}."
                if is_retry and retry_successor is not None
                else (
                    f"Failing transaction #{extra.id} is a failed attempt for "
                    f"golden transaction #{anchor.id}."
                )
                if is_retry and anchor is not None
                else (
                    f"Failing trace has unexpected extra transaction #{extra.id} to "
                    f"0x{extra.address_7bit:02X} {extra.direction.value}"
                )
            )
            hint = (
                "將同一 command 的連續 NACK/重試次數與 driver timeout、retry budget 對照。"
                if is_retry
                else "檢查 retry、polling、背景裝置與兩份 capture 的起點是否一致。"
            )
            cls._append_indexed_divergence(
                divergences,
                tx_index=golden_index + 1,
                golden_tx=anchor,
                failing_tx=extra,
                mismatch_type=mismatch_type,
                description=description,
                root_cause_hint=hint,
                golden_index=golden_index if golden_index < len(g_txs) else last_pair_golden,
                failing_index=extra_index,
                alignment_offset=extra_index - golden_index,
            )
            alignment.append((None, extra_index))
            if not pending_phase_shift:
                phase_start_golden = golden_index
            pending_phase_shift = True
            had_structural_gap = True

        def append_dropped(tx_index: int) -> None:
            nonlocal pending_phase_shift, phase_start_golden, had_structural_gap
            dropped = g_txs[tx_index]
            cls._append_indexed_divergence(
                divergences,
                tx_index=tx_index + 1,
                golden_tx=dropped,
                failing_tx=None,
                mismatch_type="DROPPED_TRANSACTION",
                description=(
                    f"Dropped Transaction: golden transaction #{dropped.id} to 0x{dropped.address_7bit:02X} "
                    "was not observed in the failing trace."
                ),
                root_cause_hint=(
                    "確認 capture window、timeout/early-return、bus hang 與封包遺失；"
                    "不要把後續交易直接按原始 index 配對。"
                ),
                golden_index=tx_index,
                failing_index=None,
                alignment_offset=failing_index - tx_index,
            )
            alignment.append((tx_index, None))
            if not pending_phase_shift:
                phase_start_golden = tx_index
            pending_phase_shift = True
            had_structural_gap = True

        def compare_pair(pair_golden_index: int, pair_failing_index: int) -> None:
            g = g_txs[pair_golden_index]
            f = f_txs[pair_failing_index]
            tx_index = pair_golden_index + 1
            if g.address_7bit != f.address_7bit:
                cls._append_indexed_divergence(
                    divergences,
                    tx_index=tx_index,
                    golden_tx=g,
                    failing_tx=f,
                    mismatch_type="ADDRESS_MISMATCH",
                    description=(
                        f"Address mismatch: Golden sent 0x{g.address_7bit:02X}, "
                        f"Failing sent 0x{f.address_7bit:02X}"
                    ),
                    root_cause_hint="檢查晶片 Address Pin 硬體配置或驅動定址常數。",
                    golden_index=pair_golden_index,
                    failing_index=pair_failing_index,
                    alignment_offset=pair_failing_index - pair_golden_index,
                )
                return

            g_ack_outcome = cls._ack_outcome(g)
            f_ack_outcome = cls._ack_outcome(f)
            if g_ack_outcome != f_ack_outcome:
                cls._append_indexed_divergence(
                    divergences,
                    tx_index=tx_index,
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
                    golden_index=pair_golden_index,
                    failing_index=pair_failing_index,
                    alignment_offset=pair_failing_index - pair_golden_index,
                )
                return

            if g.direction != f.direction:
                cls._append_indexed_divergence(
                    divergences,
                    tx_index=tx_index,
                    golden_tx=g,
                    failing_tx=f,
                    mismatch_type="DIRECTION_MISMATCH",
                    description=(
                        f"Direction mismatch: Golden={g.direction.value}, "
                        f"Failing={f.direction.value}"
                    ),
                    root_cause_hint="讀寫方向位元不同步。",
                    golden_index=pair_golden_index,
                    failing_index=pair_failing_index,
                    alignment_offset=pair_failing_index - pair_golden_index,
                )
                return

            if g.data_bytes != f.data_bytes:
                cls._append_indexed_divergence(
                    divergences,
                    tx_index=tx_index,
                    golden_tx=g,
                    failing_tx=f,
                    mismatch_type="DATA_MISMATCH",
                    description=(
                        f"Data payload divergence on 0x{g.address_7bit:02X}: "
                        f"Golden={g.hex_dump}, Failing={f.hex_dump}"
                    ),
                    root_cause_hint=(
                        "資料內容不一致，檢查暫存器初始值或 EEPROM 儲存內容是否受損。"
                    ),
                    golden_index=pair_golden_index,
                    failing_index=pair_failing_index,
                    alignment_offset=pair_failing_index - pair_golden_index,
                )

        def has_later_anchor(current_golden_index: int) -> bool:
            nonlocal future_anchor_probe
            if failing_index >= len(f_txs):
                return False
            future_anchor_probe = max(future_anchor_probe, current_golden_index + 1)
            while future_anchor_probe < len(g_txs):
                key = golden_keys[future_anchor_probe]
                if key is not None and cls._next_position(
                    failing_positions, key, failing_index
                ) is not None:
                    return True
                future_anchor_probe += 1
            return False

        while golden_index < len(g_txs):
            candidate: int | None
            if exact_alignment is not None:
                while exact_cursor < len(exact_alignment) and (
                    exact_alignment[exact_cursor][0] < golden_index
                    or exact_alignment[exact_cursor][1] < failing_index
                ):
                    exact_cursor += 1
            exact_pair = (
                exact_alignment[exact_cursor]
                if exact_alignment is not None and exact_cursor < len(exact_alignment)
                else None
            )
            if exact_pair is not None and exact_pair[0] == golden_index:
                candidate = exact_pair[1]
            else:
                if (
                    exact_pair is not None
                    and exact_pair[1] >= failing_index
                    and exact_pair[0] > golden_index
                ):
                    same_endpoint = bool(
                        failing_index < len(f_txs)
                        and cls._same_endpoint(g_txs[golden_index], f_txs[failing_index])
                    )
                    current_key = cls._protocol_key(g_txs[golden_index])
                    later_same_index = (
                        cls._next_position(failing_positions, current_key, failing_index)
                        if current_key is not None
                        else None
                    )
                    later_same_key = (
                        later_same_index is not None and later_same_index > exact_pair[1]
                    )
                    remaining_differs = (len(g_txs) - golden_index) != (
                        len(f_txs) - failing_index
                    )
                    strong_future_anchor = (
                        current_key is not None
                        and later_same_index is None
                        and exact_alignment is not None
                        and len(exact_alignment) - exact_cursor >= 2
                    )
                    if not same_endpoint and (
                        remaining_differs
                        or later_same_key
                        or had_structural_gap
                        or strong_future_anchor
                    ):
                        append_dropped(golden_index)
                        golden_index += 1
                        continue
                candidate = cls._find_alignment_candidate(
                    g_txs,
                    failing_positions,
                    failing_ack_positions,
                    golden_index,
                    failing_index,
                    previous_keys[golden_index],
                    last_pair_golden == golden_index - 1,
                    next_distinct_keys[golden_index],
                )
            if candidate is not None:
                anchor = g_txs[golden_index]
                for extra_index in range(failing_index, candidate):
                    append_retry_or_extra(
                        extra_index,
                        anchor,
                        allow_retry=True,
                        retry_successor=candidate,
                    )
                record_pair(golden_index, candidate)
                compare_pair(golden_index, candidate)
                last_pair_golden = golden_index
                golden_index += 1
                failing_index = candidate + 1
                continue

            later_anchor = has_later_anchor(golden_index)
            remaining_golden = len(g_txs) - golden_index
            remaining_failing = len(f_txs) - failing_index
            same_endpoint = bool(
                failing_index < len(f_txs)
                and cls._same_endpoint(g_txs[golden_index], f_txs[failing_index])
            )
            if later_anchor and remaining_golden != remaining_failing:
                if same_endpoint and remaining_failing:
                    record_pair(golden_index, failing_index)
                    compare_pair(golden_index, failing_index)
                    last_pair_golden = golden_index
                    golden_index += 1
                    failing_index += 1
                    continue
                append_dropped(golden_index)
                golden_index += 1
                continue

            if remaining_golden != remaining_failing:
                if same_endpoint and remaining_failing:
                    record_pair(golden_index, failing_index)
                    compare_pair(golden_index, failing_index)
                    last_pair_golden = golden_index
                    golden_index += 1
                    failing_index += 1
                    continue
                if remaining_golden > remaining_failing:
                    append_dropped(golden_index)
                    golden_index += 1
                    continue
                append_retry_or_extra(
                    failing_index,
                    g_txs[last_pair_golden] if last_pair_golden is not None else None,
                    allow_retry=False,
                )
                failing_index += 1
                continue

            if (
                had_structural_gap
                and remaining_golden == remaining_failing
                and failing_index < len(f_txs)
                and not same_endpoint
            ):
                append_dropped(golden_index)
                golden_index += 1
                continue

            pair_count = min(remaining_golden, remaining_failing)
            for offset in range(pair_count):
                pair_golden_index = golden_index + offset
                pair_failing_index = failing_index + offset
                record_pair(pair_golden_index, pair_failing_index)
                compare_pair(pair_golden_index, pair_failing_index)
                last_pair_golden = pair_golden_index
            golden_index += pair_count
            failing_index += pair_count
            while golden_index < len(g_txs):
                append_dropped(golden_index)
                golden_index += 1
            while failing_index < len(f_txs):
                append_retry_or_extra(
                    failing_index,
                    g_txs[last_pair_golden] if last_pair_golden is not None else None,
                    allow_retry=False,
                )
                failing_index += 1
            break

        while failing_index < len(f_txs):
            append_retry_or_extra(
                failing_index,
                g_txs[last_pair_golden] if last_pair_golden is not None else None,
                allow_retry=False,
            )
            failing_index += 1

        if pending_phase_shift:
            append_phase_shift(golden_index, None)

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
            alignment=alignment,
        )

    @classmethod
    def create_comparison_figure(
        cls,
        diff_report: WaveformDiffReport,
        title: str = "Golden（正常）與 Failing（故障）波形比較（Waveform Comparison）",
    ) -> go.Figure:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=False,
            vertical_spacing=0.12,
            subplot_titles=(
                "Golden（正常板卡）波形（Golden Waveform）",
                "Failing（故障板卡）波形（Failing Waveform）",
            ),
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
                        name="Golden SDA（正常板卡 SDA）",
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
                        name="Golden SCL（正常板卡 SCL）",
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
                        name="Failing（一致）SDA（故障板卡 SDA）",
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
                        name="Failing（一致）SCL（故障板卡 SCL）",
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
                        name="Golden SDA（正常板卡 SDA）",
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
                        name="Golden SCL（正常板卡 SCL）",
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
                        name="沒有交易（No Transaction；已結束）",
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
                        name="Failing SDA（故障板卡 SDA）",
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
                        name="Failing SCL（故障板卡 SCL）",
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
                        name="沒有交易（No Transaction；缺少交易）",
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
