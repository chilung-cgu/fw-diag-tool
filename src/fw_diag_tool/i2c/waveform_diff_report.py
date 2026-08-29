"""Traditional-Chinese presentation for I2C waveform diff results.

The diff engine deliberately keeps stable English strings for CLI/API users and
documentation contracts.  This module is the user-facing adapter used by the
GUI: it puts a short zh-TW explanation first, keeps protocol tokens intact,
and records which evidence was actually compared.
"""

from __future__ import annotations

import re

from .models import I2CDirection, I2CTransaction
from .waveform_diff import WaveformDiffReport

_DIFF_TYPE_ZH = {
    "NACK_MISMATCH": "ACK／NACK 結果不一致（NACK_MISMATCH）",
    "ADDRESS_MISMATCH": "位址不一致（ADDRESS_MISMATCH）",
    "DIRECTION_MISMATCH": "讀寫方向不一致（DIRECTION_MISMATCH）",
    "DATA_MISMATCH": "資料 Payload 不一致（DATA_MISMATCH）",
    "RETRY_SEQUENCE": "重試序列不一致（RETRY_SEQUENCE）",
    "DROPPED_TRANSACTION": "交易遺失（DROPPED_TRANSACTION）",
    "UNEXPECTED_EXTRA_TX": "多出非預期交易（UNEXPECTED_EXTRA_TX）",
    "PHASE_SHIFT": "交易相位偏移（PHASE_SHIFT）",
}

_SUMMARY_RE = re.compile(
    r"^Found (?P<count>\d+) divergence point\(s\)\. "
    r"First mismatch at Transaction #(?P<tx>\d+)\.$"
)
_ADDRESS_RE = re.compile(
    r"^Address mismatch: Golden sent (?P<golden>0x[0-9A-Fa-f]+), "
    r"Failing sent (?P<failing>0x[0-9A-Fa-f]+)$"
)
_ACK_RE = re.compile(
    r"^ACK outcome mismatch on (?P<address>0x[0-9A-Fa-f]+): "
    r"Golden=(?P<golden>[^,]+), Failing=(?P<failing>[^.]+)\. "
    r"A final controller NACK on a read is treated as normal termination\.$"
)
_DIRECTION_RE = re.compile(
    r"^Direction mismatch: Golden=(?P<golden>[^,]+), Failing=(?P<failing>.+)$"
)
_DATA_RE = re.compile(
    r"^Data payload divergence on (?P<address>0x[0-9A-Fa-f]+): "
    r"Golden=(?P<golden>[^,]+), Failing=(?P<failing>.+)$"
)
_DROPPED_RE = re.compile(
    r"^Dropped Transaction: golden transaction #(?P<tx>\d+) to (?P<address>0x[0-9A-Fa-f]+) "
    r"was not observed in the failing trace\.$"
)
_RETRY_RE = re.compile(
    r"^Retry Sequence: failing transaction #(?P<failed>\d+) failed; the same command is retried "
    r"at transaction #(?P<retry>\d+)\.$"
)
_FAILED_ATTEMPT_RE = re.compile(
    r"^Failing transaction #(?P<tx>\d+) is a failed attempt for golden transaction #(?P<golden>\d+)\.$"
)
_EXTRA_RE = re.compile(
    r"^Failing trace has unexpected extra transaction #(?P<tx>\d+) to "
    r"(?P<address>0x[0-9A-Fa-f]+) (?P<direction>.+)$"
)
_PHASE_RE = re.compile(
    r"^Phase Shift: transaction alignment moved by (?P<offset>[+-]\d+) "
    r"after an insertion or dropped transaction\.$"
)

_INSUFFICIENT_EVIDENCE_ZH = {
    (
        "both golden and failing traces contain no transactions; "
        "protocol identity cannot be established."
    ): "Golden 與 Failing trace 都沒有 transaction，無法建立協定一致性。",
    (
        "at least one trace contains source/parser errors; "
        "protocol identity and waveform equivalence cannot be established."
    ): "至少一份 trace 含有來源／解析器錯誤，無法建立協定一致性或波形等價性。",
    (
        "at least one trace has unknown ACK or incomplete transaction framing; "
        "protocol identity cannot be established."
    ): "至少一份 trace 的 ACK 未知或交易框架不完整，無法建立協定一致性。",
}


def localize_diff_type(value: str) -> str:
    """Return a zh-TW mismatch label while preserving the stable code."""
    return _DIFF_TYPE_ZH.get(value, value)


def localize_diff_summary(value: str) -> str:
    """Translate the engine summary without hiding its canonical wording."""
    if value == "Golden and Failing traces are 100% identical in protocol sequence.":
        return f"Golden 與 Failing trace 的協定序列完全一致。（{value}）"
    match = _SUMMARY_RE.fullmatch(value)
    if match:
        return (
            f"找到 {match.group('count')} 個分歧點；第一個差異在第 {match.group('tx')} 筆交易。"
            f"（{value}）"
        )
    if value.startswith("Insufficient evidence: "):
        reason = value.removeprefix("Insufficient evidence: ")
        localized_reason = _INSUFFICIENT_EVIDENCE_ZH.get(reason, reason)
        return f"證據不足：{localized_reason}（{value}）"
    return value


def _direction_text(value: str) -> str:
    return {
        I2CDirection.READ.value: "READ（讀取）",
        I2CDirection.WRITE.value: "WRITE（寫入）",
    }.get(value, value)


def localize_diff_description(value: str) -> str:
    """Translate known diff symptoms and retain addresses/ACK outcomes."""
    match = _ADDRESS_RE.fullmatch(value)
    if match:
        return (
            f"Golden 送出 {match.group('golden')}，Failing 送出 {match.group('failing')}；"
            f"兩份 trace 的目標位址不同。（{value}）"
        )
    match = _ACK_RE.fullmatch(value)
    if match:
        return (
            f"位址 {match.group('address')} 的 ACK 結果不一致：Golden={match.group('golden')}、"
            f"Failing={match.group('failing')}。Read 的最後一個 controller NACK 屬於正常結束，"
            f"不直接視為 target failure。（{value}）"
        )
    match = _DIRECTION_RE.fullmatch(value)
    if match:
        return (
            f"讀寫方向不一致：Golden={_direction_text(match.group('golden'))}、"
            f"Failing={_direction_text(match.group('failing'))}。（{value}）"
        )
    match = _DATA_RE.fullmatch(value)
    if match:
        return (
            f"位址 {match.group('address')} 的資料 Payload 不一致："
            f"Golden={match.group('golden')}、Failing={match.group('failing')}。（{value}）"
        )
    match = _DROPPED_RE.fullmatch(value)
    if match:
        return (
            f"Golden 的交易 #{match.group('tx')}（位址 {match.group('address')}）沒有在 Failing trace 中觀察到。"
            f"（{value}）"
        )
    match = _RETRY_RE.fullmatch(value)
    if match:
        return (
            f"Failing 的交易 #{match.group('failed')} 失敗後，在交易 #{match.group('retry')} 重試同一 command。"
            f"（{value}）"
        )
    match = _FAILED_ATTEMPT_RE.fullmatch(value)
    if match:
        return (
            f"Failing 的交易 #{match.group('tx')} 是 Golden 交易 #{match.group('golden')} 的失敗嘗試。"
            f"（{value}）"
        )
    match = _EXTRA_RE.fullmatch(value)
    if match:
        return (
            f"Failing 多出交易 #{match.group('tx')}（位址 {match.group('address')}，"
            f"{_direction_text(match.group('direction'))}）。（{value}）"
        )
    match = _PHASE_RE.fullmatch(value)
    if match:
        return (
            f"交易對齊在插入或遺失交易後偏移 {match.group('offset')}。"
            f"（{value}）"
        )
    return value


def localize_diff_hint(value: str) -> str:
    """Keep existing Chinese hints and provide a readable fallback."""
    if value.startswith(("檢查", "先確認", "將")):
        return value
    return f"排查提示：{value}"


def _tx_summary(tx: I2CTransaction | None) -> str:
    if tx is None:
        return "（無對應交易）"
    direction = tx.direction.value if isinstance(tx.direction, I2CDirection) else str(tx.direction)
    address = (
        f"0x{tx.address_7bit:02X}" if getattr(tx, "address_available", True) else "未知位址"
    )
    data = getattr(tx, "hex_dump", "-") or "-"
    return f"交易 #{tx.id}；位址 {address}；方向 {_direction_text(direction)}；資料 {data}"


def format_waveform_diff_markdown(
    report: WaveformDiffReport,
    *,
    golden_name: str = "Golden",
    failing_name: str = "Failing",
) -> str:
    """Build a portable, evidence-bounded Markdown diff report for the GUI."""
    lines = [
        "# I2C 雙波形差分診斷報告（I2C Waveform Diff Diagnostic Report）",
        "",
        "## 輸入與證據範圍（Input & Evidence Scope）",
        f"- **Golden（正常）輸入**：`{golden_name}`",
        f"- **Failing（故障）輸入**：`{failing_name}`",
        f"- **比較交易數（Compared Transactions）**：`{report.total_compared}`",
        "- **分析方法**：比較解碼後的 I2C transaction 欄位；不是類比電壓或原始 SCL/SDA edge 的 pass/fail 量測。",
        "",
        "## 差分摘要（Diff Summary）",
        f"- **判定**：{('協定序列一致' if report.is_identical else '發現差異或證據不足')}",
        f"- **摘要**：{localize_diff_summary(report.summary)}",
        "",
    ]
    if not report.divergence_points:
        lines.append(
            "未產生可列出的分歧點；若摘要指出證據不足，請補充 ACK、時間戳或完整 STOP/START 邊界。"
        )
    else:
        lines.append("## 分歧點（Divergence Points）")
        for index, point in enumerate(report.divergence_points, 1):
            lines.extend(
                [
                    f"### {index}. 交易 #{point.tx_index}：{localize_diff_type(point.mismatch_type)}",
                    f"- **現象描述**：{localize_diff_description(point.description)}",
                    f"- **排查建議**：{localize_diff_hint(point.root_cause_hint)}",
                    f"- **Golden 交易**：{_tx_summary(point.golden_tx)}",
                    f"- **Failing 交易**：{_tx_summary(point.failing_tx)}",
                ]
            )
            if point.alignment_offset is not None:
                lines.append(f"- **對齊偏移（Alignment Offset）**：`{point.alignment_offset:+d}`")
            lines.append("")

    lines.extend(
        [
            "## 解讀限制（Interpretation Limits）",
            "- 差分結果只回答兩份輸入的解碼交易是否一致；它不能單獨證明實體層電壓、上拉電阻、雜訊或裝置根因。",
            "- 請保留原始 capture、analyzer 設定與這份報告，並用 datasheet、driver log 及重現測試確認下一步。",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "format_waveform_diff_markdown",
    "localize_diff_description",
    "localize_diff_hint",
    "localize_diff_summary",
    "localize_diff_type",
]
