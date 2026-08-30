"""PCIe Configuration Space Before/After Analysis and Diff Engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .models import PCIeConfigSpace, PCIeLinkInfo


@dataclass
class PCIeDiffResult:
    """Structured differences between two PCIe configuration space reports."""

    vendor_changed: bool = False
    device_changed: bool = False
    link_degradation_changed: bool = False
    baseline_link_summary: str = ""
    candidate_link_summary: str = ""
    new_aer_errors: list[str] = field(default_factory=list)
    resolved_aer_errors: list[str] = field(default_factory=list)
    common_aer_errors: list[str] = field(default_factory=list)
    new_quality_issues: list[str] = field(default_factory=list)
    resolved_quality_issues: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def is_identical(self) -> bool:
        """Return True if there are no differences in vendor, device, link, AER errors, or quality issues."""
        return (
            not self.vendor_changed
            and not self.device_changed
            and not self.link_degradation_changed
            and self.baseline_link_summary == self.candidate_link_summary
            and len(self.new_aer_errors) == 0
            and len(self.resolved_aer_errors) == 0
            and len(self.new_quality_issues) == 0
            and len(self.resolved_quality_issues) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor_changed": self.vendor_changed,
            "device_changed": self.device_changed,
            "link_degradation_changed": self.link_degradation_changed,
            "baseline_link_summary": self.baseline_link_summary,
            "candidate_link_summary": self.candidate_link_summary,
            "new_aer_errors": list(self.new_aer_errors),
            "resolved_aer_errors": list(self.resolved_aer_errors),
            "common_aer_errors": list(self.common_aer_errors),
            "new_anomalies": list(self.new_aer_errors),
            "resolved_anomalies": list(self.resolved_aer_errors),
            "common_anomalies": list(self.common_aer_errors),
            "new_quality_issues": list(self.new_quality_issues),
            "resolved_quality_issues": list(self.resolved_quality_issues),
            "summary": self.summary,
            "is_identical": self.is_identical,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class PCIeDiffEngine:
    """Compares baseline vs candidate PCIe configuration spaces."""

    @classmethod
    def _extract_aer_errors(cls, cfg: PCIeConfigSpace) -> set[str]:
        if not cfg.aer_analysis:
            return set()
        active_uncorr = {e.name for e in cfg.aer_analysis.uncorr_errors if e.is_active}
        active_corr = {e.name for e in cfg.aer_analysis.corr_errors if e.is_active}
        return active_uncorr | active_corr

    @classmethod
    def _format_link_summary(cls, link: PCIeLinkInfo | None) -> str:
        if link is None:
            return "N/A"
        return f"{link.current_speed_str} x{link.current_width}"

    @classmethod
    def compare(
        cls,
        baseline: PCIeConfigSpace,
        candidate: PCIeConfigSpace,
    ) -> PCIeDiffResult:
        if not isinstance(baseline, PCIeConfigSpace) or not isinstance(candidate, PCIeConfigSpace):
            raise TypeError("baseline and candidate must be PCIeConfigSpace instances")

        vendor_changed = baseline.vendor_id != candidate.vendor_id
        device_changed = baseline.device_id != candidate.device_id

        b_degraded = baseline.link_info.is_degraded if baseline.link_info else False
        c_degraded = candidate.link_info.is_degraded if candidate.link_info else False
        link_degradation_changed = b_degraded != c_degraded

        b_link_summary = cls._format_link_summary(baseline.link_info)
        c_link_summary = cls._format_link_summary(candidate.link_info)

        b_aer = cls._extract_aer_errors(baseline)
        c_aer = cls._extract_aer_errors(candidate)
        new_aer_errors = sorted(c_aer - b_aer)
        resolved_aer_errors = sorted(b_aer - c_aer)
        common_aer_errors = sorted(b_aer & c_aer)

        b_issues = set(baseline.data_quality_issues)
        c_issues = set(candidate.data_quality_issues)
        new_quality_issues = sorted(c_issues - b_issues)
        resolved_quality_issues = sorted(b_issues - c_issues)

        is_same = (
            not vendor_changed
            and not device_changed
            and not link_degradation_changed
            and b_link_summary == c_link_summary
            and not new_aer_errors
            and not resolved_aer_errors
            and not new_quality_issues
            and not resolved_quality_issues
        )

        if is_same:
            summary = "Baseline 與 Candidate PCIe 配置完全一致，未發現差異。"
        else:
            parts = []
            if vendor_changed:
                parts.append(
                    f"Vendor ID 變更（0x{baseline.vendor_id:04X} -> 0x{candidate.vendor_id:04X}）"
                )
            if device_changed:
                parts.append(
                    f"Device ID 變更（0x{baseline.device_id:04X} -> 0x{candidate.device_id:04X}）"
                )
            if link_degradation_changed:
                b_status = "已降級" if b_degraded else "正常"
                c_status = "已降級" if c_degraded else "正常"
                parts.append(f"Link 降級狀態變更（{b_status} -> {c_status}）")
            elif b_link_summary != c_link_summary:
                parts.append(f"Link 狀態變更（{b_link_summary} -> {c_link_summary}）")

            if new_aer_errors or resolved_aer_errors:
                parts.append(f"新增 {len(new_aer_errors)} 項 AER 錯誤")
                parts.append(f"修復 {len(resolved_aer_errors)} 項 AER 錯誤")

            if new_quality_issues or resolved_quality_issues:
                parts.append(f"新增 {len(new_quality_issues)} 項品質問題")
                parts.append(f"修復 {len(resolved_quality_issues)} 項品質問題")

            summary = f"PCIe 對比結果：{'，'.join(parts)}。"

        return PCIeDiffResult(
            vendor_changed=vendor_changed,
            device_changed=device_changed,
            link_degradation_changed=link_degradation_changed,
            baseline_link_summary=b_link_summary,
            candidate_link_summary=c_link_summary,
            new_aer_errors=new_aer_errors,
            resolved_aer_errors=resolved_aer_errors,
            common_aer_errors=common_aer_errors,
            new_quality_issues=new_quality_issues,
            resolved_quality_issues=resolved_quality_issues,
            summary=summary,
        )


__all__ = ["PCIeDiffEngine", "PCIeDiffResult"]
