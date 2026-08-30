"""Tests for the PCIe Before/After diff engine."""

from __future__ import annotations

import pytest

from fw_diag_tool.pcie.diff import PCIeDiffEngine, PCIeDiffResult
from fw_diag_tool.pcie.models import (
    AERAnalysisResult,
    AERCorrectableError,
    AERUncorrectableError,
    HeaderType,
    PCIeConfigSpace,
    PCIeLinkInfo,
)


def _make_pcie_config(
    vendor_id: int = 0x10EE,
    device_id: int = 0x7024,
    link_speed: str = "8.0 GT/s",
    link_width: int = 8,
    is_degraded: bool = False,
    uncorr_errors: list[str] | None = None,
    corr_errors: list[str] | None = None,
    inactive_errors: list[str] | None = None,
    quality_issues: list[str] | None = None,
    has_link_info: bool = True,
    has_aer: bool = True,
) -> PCIeConfigSpace:
    link_info = (
        PCIeLinkInfo(
            current_speed_str=link_speed,
            current_width=link_width,
            is_degraded=is_degraded,
        )
        if has_link_info
        else None
    )

    aer_analysis = None
    if has_aer:
        uncorr_list = [
            AERUncorrectableError(
                bit_pos=i,
                name=name,
                short_code=name[:4],
                is_active=True,
                is_masked=False,
                severity="Fatal",
            )
            for i, name in enumerate(uncorr_errors or [])
        ]
        corr_list = [
            AERCorrectableError(
                bit_pos=i,
                name=name,
                short_code=name[:4],
                is_active=True,
                is_masked=False,
            )
            for i, name in enumerate(corr_errors or [])
        ]
        for i, name in enumerate(inactive_errors or []):
            uncorr_list.append(
                AERUncorrectableError(
                    bit_pos=100 + i,
                    name=name,
                    short_code="INACT",
                    is_active=False,
                    is_masked=False,
                    severity="NonFatal",
                )
            )
        aer_analysis = AERAnalysisResult(
            offset=0x100,
            uncorr_status_raw=0,
            uncorr_mask_raw=0,
            uncorr_severity_raw=0,
            corr_status_raw=0,
            corr_mask_raw=0,
            cap_control_raw=0,
            header_log_raw=[],
            uncorr_errors=uncorr_list,
            corr_errors=corr_list,
        )

    return PCIeConfigSpace(
        raw_data=b"\x00" * 256,
        vendor_id=vendor_id,
        device_id=device_id,
        header_type=HeaderType.TYPE_0_ENDPOINT,
        link_info=link_info,
        aer_analysis=aer_analysis,
        data_quality_issues=list(quality_issues or []),
    )


def test_pcie_diff_identical() -> None:
    cfg1 = _make_pcie_config(
        uncorr_errors=["Completion Timeout"],
        corr_errors=["Receiver Error"],
        quality_issues=["AER truncated"],
    )
    cfg2 = _make_pcie_config(
        uncorr_errors=["Completion Timeout"],
        corr_errors=["Receiver Error"],
        quality_issues=["AER truncated"],
    )

    result = PCIeDiffEngine.compare(cfg1, cfg2)
    assert isinstance(result, PCIeDiffResult)
    assert result.is_identical is True
    assert result.vendor_changed is False
    assert result.device_changed is False
    assert result.link_degradation_changed is False
    assert result.baseline_link_summary == "8.0 GT/s x8"
    assert result.candidate_link_summary == "8.0 GT/s x8"
    assert result.new_aer_errors == []
    assert result.resolved_aer_errors == []
    assert result.common_aer_errors == ["Completion Timeout", "Receiver Error"]
    assert result.new_quality_issues == []
    assert result.resolved_quality_issues == []
    assert "完全一致" in result.summary


def test_pcie_diff_vendor_and_device_changed() -> None:
    cfg1 = _make_pcie_config(vendor_id=0x10EE, device_id=0x7024)
    cfg2 = _make_pcie_config(vendor_id=0x8086, device_id=0x1572)

    result = PCIeDiffEngine.compare(cfg1, cfg2)
    assert result.is_identical is False
    assert result.vendor_changed is True
    assert result.device_changed is True
    assert "Vendor ID 變更（0x10EE -> 0x8086）" in result.summary
    assert "Device ID 變更（0x7024 -> 0x1572）" in result.summary


def test_pcie_diff_aer_errors() -> None:
    cfg1 = _make_pcie_config(
        uncorr_errors=["Poisoned TLP", "Completion Timeout"],
        corr_errors=["Receiver Error"],
    )
    cfg2 = _make_pcie_config(
        uncorr_errors=["Completion Timeout", "Malformed TLP"],
        corr_errors=["Bad TLP"],
    )

    result = PCIeDiffEngine.compare(cfg1, cfg2)
    assert result.is_identical is False
    assert result.new_aer_errors == ["Bad TLP", "Malformed TLP"]
    assert result.resolved_aer_errors == ["Poisoned TLP", "Receiver Error"]
    assert result.common_aer_errors == ["Completion Timeout"]
    assert "新增 2 項 AER 錯誤" in result.summary
    assert "修復 2 項 AER 錯誤" in result.summary


def test_pcie_diff_aer_inactive_ignored() -> None:
    cfg1 = _make_pcie_config(
        uncorr_errors=["Completion Timeout"],
        inactive_errors=["Poisoned TLP"],
    )
    cfg2 = _make_pcie_config(
        uncorr_errors=["Completion Timeout"],
        inactive_errors=["Malformed TLP"],
    )

    result = PCIeDiffEngine.compare(cfg1, cfg2)
    assert result.is_identical is True
    assert result.new_aer_errors == []
    assert result.resolved_aer_errors == []
    assert result.common_aer_errors == ["Completion Timeout"]


def test_pcie_diff_link_degradation_change() -> None:
    cfg1 = _make_pcie_config(is_degraded=False)
    cfg2 = _make_pcie_config(is_degraded=True)

    result = PCIeDiffEngine.compare(cfg1, cfg2)
    assert result.is_identical is False
    assert result.link_degradation_changed is True
    assert "Link 降級狀態變更（正常 -> 已降級）" in result.summary


def test_pcie_diff_link_speed_change() -> None:
    cfg1 = _make_pcie_config(link_speed="8.0 GT/s", link_width=16)
    cfg2 = _make_pcie_config(link_speed="16.0 GT/s", link_width=16)

    result = PCIeDiffEngine.compare(cfg1, cfg2)
    assert result.is_identical is False
    assert result.link_degradation_changed is False
    assert result.baseline_link_summary == "8.0 GT/s x16"
    assert result.candidate_link_summary == "16.0 GT/s x16"
    assert "Link 狀態變更（8.0 GT/s x16 -> 16.0 GT/s x16）" in result.summary


def test_pcie_diff_quality_issues() -> None:
    cfg1 = _make_pcie_config(quality_issues=["AER capability truncated"])
    cfg2 = _make_pcie_config(quality_issues=["Command register MSE is 0"])

    result = PCIeDiffEngine.compare(cfg1, cfg2)
    assert result.is_identical is False
    assert result.new_quality_issues == ["Command register MSE is 0"]
    assert result.resolved_quality_issues == ["AER capability truncated"]
    assert "新增 1 項品質問題" in result.summary
    assert "修復 1 項品質問題" in result.summary


def test_pcie_diff_none_fields() -> None:
    cfg1 = _make_pcie_config(has_link_info=False, has_aer=False)
    cfg2 = _make_pcie_config(has_link_info=False, has_aer=False)

    result = PCIeDiffEngine.compare(cfg1, cfg2)
    assert result.is_identical is True
    assert result.baseline_link_summary == "N/A"
    assert result.candidate_link_summary == "N/A"
    assert result.new_aer_errors == []
    assert result.resolved_aer_errors == []
    assert result.common_aer_errors == []


def test_pcie_diff_type_error() -> None:
    cfg = _make_pcie_config()
    with pytest.raises(TypeError, match="PCIeConfigSpace"):
        PCIeDiffEngine.compare("invalid", cfg)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="PCIeConfigSpace"):
        PCIeDiffEngine.compare(cfg, None)  # type: ignore[arg-type]
