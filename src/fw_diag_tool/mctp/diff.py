"""MCTP / IPMB Before/After Analysis and Diff Engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import ProtocolMode, ServerMgmtReport


@dataclass
class MCTPDiffResult:
    """Structured differences between two MCTP/IPMB server management reports."""

    message_count_delta: int = 0
    ipmb_frame_count_delta: int = 0
    error_count_delta: int = 0
    new_errors: list[str] = field(default_factory=list)
    resolved_errors: list[str] = field(default_factory=list)
    common_errors: list[str] = field(default_factory=list)
    new_warnings: list[str] = field(default_factory=list)
    resolved_warnings: list[str] = field(default_factory=list)
    common_warnings: list[str] = field(default_factory=list)
    protocol_mode_changed: bool = False
    baseline_protocol_mode: str = ""
    candidate_protocol_mode: str = ""
    summary: str = ""

    @property
    def is_identical(self) -> bool:
        """Return True if there are no differences in messages, frames, errors, warnings, or protocol mode."""
        return (
            self.message_count_delta == 0
            and self.ipmb_frame_count_delta == 0
            and len(self.new_errors) == 0
            and len(self.resolved_errors) == 0
            and len(self.new_warnings) == 0
            and len(self.resolved_warnings) == 0
            and not self.protocol_mode_changed
        )


class MCTPDiffEngine:
    """Compares baseline vs candidate MCTP/IPMB server management reports."""

    @classmethod
    def _extract_errors(cls, report: ServerMgmtReport) -> list[str]:
        if hasattr(report, "errors") and report.errors:
            return list(report.errors)
        if hasattr(report, "source_errors") and report.source_errors:
            return list(report.source_errors)
        return []

    @classmethod
    def _extract_warnings(cls, report: ServerMgmtReport) -> list[str]:
        if hasattr(report, "warnings") and report.warnings:
            return list(report.warnings)
        return []

    @classmethod
    def _extract_protocol_mode(cls, report: ServerMgmtReport) -> str:
        mode = getattr(report, "protocol_mode", ProtocolMode.AUTO)
        if hasattr(mode, "value"):
            return str(mode.value)
        return str(mode)

    @classmethod
    def compare(
        cls,
        baseline: ServerMgmtReport,
        candidate: ServerMgmtReport,
    ) -> MCTPDiffResult:
        if not isinstance(baseline, ServerMgmtReport) or not isinstance(
            candidate, ServerMgmtReport
        ):
            raise TypeError("baseline and candidate must be ServerMgmtReport instances")

        b_errors_list = cls._extract_errors(baseline)
        c_errors_list = cls._extract_errors(candidate)
        b_errors = set(b_errors_list)
        c_errors = set(c_errors_list)
        new_errors = sorted(c_errors - b_errors)
        resolved_errors = sorted(b_errors - c_errors)
        common_errors = sorted(b_errors & c_errors)
        error_delta = len(c_errors_list) - len(b_errors_list)

        b_warnings_list = cls._extract_warnings(baseline)
        c_warnings_list = cls._extract_warnings(candidate)
        b_warnings = set(b_warnings_list)
        c_warnings = set(c_warnings_list)
        new_warnings = sorted(c_warnings - b_warnings)
        resolved_warnings = sorted(b_warnings - c_warnings)
        common_warnings = sorted(b_warnings & c_warnings)

        b_msg_count = len(baseline.mctp_messages)
        c_msg_count = len(candidate.mctp_messages)
        msg_delta = c_msg_count - b_msg_count

        b_ipmb_count = len(baseline.ipmb_frames)
        c_ipmb_count = len(candidate.ipmb_frames)
        ipmb_delta = c_ipmb_count - b_ipmb_count

        b_proto = cls._extract_protocol_mode(baseline)
        c_proto = cls._extract_protocol_mode(candidate)
        protocol_mode_changed = b_proto != c_proto

        identical = (
            msg_delta == 0
            and ipmb_delta == 0
            and not new_errors
            and not resolved_errors
            and not new_warnings
            and not resolved_warnings
            and not protocol_mode_changed
        )

        if identical:
            summary = "Baseline 與 Candidate MCTP/IPMB 報告完全一致，未發現差異。"
        else:
            parts = []
            if msg_delta != 0:
                parts.append(f"MCTP 訊息數變化 {msg_delta:+d}（{b_msg_count} -> {c_msg_count}）")
            if ipmb_delta != 0:
                parts.append(f"IPMB 訊框數變化 {ipmb_delta:+d}（{b_ipmb_count} -> {c_ipmb_count}）")
            if protocol_mode_changed:
                parts.append(f"協定模式由 {b_proto} 變更為 {c_proto}")
            if new_errors:
                parts.append(f"新增 {len(new_errors)} 項錯誤")
            if resolved_errors:
                parts.append(f"修復 {len(resolved_errors)} 項錯誤")
            if new_warnings:
                parts.append(f"新增 {len(new_warnings)} 項警告")
            if resolved_warnings:
                parts.append(f"修復 {len(resolved_warnings)} 項警告")
            if not parts:
                parts.append("偵測到細微差異")
            summary = f"MCTP/IPMB 對比結果：{'，'.join(parts)}。"

        return MCTPDiffResult(
            message_count_delta=msg_delta,
            ipmb_frame_count_delta=ipmb_delta,
            error_count_delta=error_delta,
            new_errors=new_errors,
            resolved_errors=resolved_errors,
            common_errors=common_errors,
            new_warnings=new_warnings,
            resolved_warnings=resolved_warnings,
            common_warnings=common_warnings,
            protocol_mode_changed=protocol_mode_changed,
            baseline_protocol_mode=b_proto,
            candidate_protocol_mode=c_proto,
            summary=summary,
        )


__all__ = ["MCTPDiffEngine", "MCTPDiffResult"]

