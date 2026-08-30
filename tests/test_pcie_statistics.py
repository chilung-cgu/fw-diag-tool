from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fw_diag_tool.pcie.constants import PCI_BASE_CLASSES
from fw_diag_tool.pcie.models import (
    AERAnalysisResult,
    AERCorrectableError,
    AERUncorrectableError,
    DmesgAEREvent,
    HeaderType,
    PCIeConfigSpace,
    PCIeLinkInfo,
)
from fw_diag_tool.pcie.reporter import PCIeReporter
from fw_diag_tool.pcie.statistics import PCIeStatistics, compute_pcie_statistics


def _create_config_space(
    bdf: str = "0000:01:00.0",
    vendor_id: int = 0x10DE,
    device_id: int = 0x1DB4,
    base_class: int = 0x03,
    class_name: str = "Display Controller",
    link_info: PCIeLinkInfo | None = None,
    aer_analysis: AERAnalysisResult | None = None,
) -> PCIeConfigSpace:
    return PCIeConfigSpace(
        raw_data=bytes(256),
        bdf=bdf,
        vendor_id=vendor_id,
        device_id=device_id,
        base_class=base_class,
        class_name=class_name,
        header_type=HeaderType.TYPE_0_ENDPOINT,
        link_info=link_info,
        aer_analysis=aer_analysis,
    )


def test_empty_configs_and_events() -> None:
    stats = compute_pcie_statistics([])
    assert stats.device_count == 0
    assert stats.total_aer_errors == 0
    assert stats.uncorrectable_count == 0
    assert stats.correctable_count == 0
    assert stats.error_rate_per_sec is None
    assert stats.link_degradation_count == 0
    assert stats.topology_summary == {}
    assert stats.link_speed_distribution == {}


def test_none_arguments() -> None:
    stats = compute_pcie_statistics(None, None)
    assert stats.device_count == 0
    assert stats.total_aer_errors == 0
    assert stats.error_rate_per_sec is None


def test_single_device_clean() -> None:
    link = PCIeLinkInfo(
        max_speed_code=4,
        max_speed_str="16.0 GT/s (Gen4)",
        max_width=16,
        current_speed_code=4,
        current_speed_str="16.0 GT/s (Gen4)",
        current_width=16,
        is_degraded=False,
    )
    cfg = _create_config_space(link_info=link)
    stats = compute_pcie_statistics([cfg])
    assert stats.device_count == 1
    assert stats.total_aer_errors == 0
    assert stats.uncorrectable_count == 0
    assert stats.correctable_count == 0
    assert stats.link_degradation_count == 0
    assert stats.topology_summary == {"Display Controller": 1}
    assert stats.link_speed_distribution == {"Gen4": 1}


def test_multi_device_topology() -> None:
    devices = [
        _create_config_space(bdf="0000:00:01.0", base_class=0x06, class_name="Bridge Device"),
        _create_config_space(bdf="0000:00:02.0", base_class=0x06, class_name="Bridge Device"),
        _create_config_space(bdf="0000:01:00.0", base_class=0x02, class_name="Network Controller"),
        _create_config_space(bdf="0000:02:00.0", base_class=0x01, class_name="Mass Storage Controller"),
        _create_config_space(bdf="0000:03:00.0", base_class=0x12, class_name="Processing Accelerator"),
    ]
    stats = compute_pcie_statistics(devices)
    assert stats.device_count == 5
    assert stats.topology_summary == {
        "Bridge Device": 2,
        "Network Controller": 1,
        "Mass Storage Controller": 1,
        "Processing Accelerator": 1,
    }


def test_aer_error_counting_from_config_space() -> None:
    aer = AERAnalysisResult(
        offset=0x100,
        uncorr_status_raw=0x00040020,
        uncorr_mask_raw=0,
        uncorr_severity_raw=0x00040000,
        corr_status_raw=0x00000041,
        corr_mask_raw=0,
        cap_control_raw=0,
        header_log_raw=[0, 0, 0, 0],
        uncorr_errors=[
            AERUncorrectableError(bit_pos=18, name="Malformed TLP", short_code="MalformedTLP", is_active=True, is_masked=False, severity="Fatal"),
            AERUncorrectableError(bit_pos=5, name="Surprise Down", short_code="SurpriseDown", is_active=True, is_masked=False, severity="Non-Fatal"),
            AERUncorrectableError(bit_pos=4, name="Data Link Protocol", short_code="DLP", is_active=False, is_masked=False, severity="Fatal"),
        ],
        corr_errors=[
            AERCorrectableError(bit_pos=0, name="Receiver Error", short_code="RxErr", is_active=True, is_masked=False),
            AERCorrectableError(bit_pos=6, name="Bad TLP", short_code="BadTLP", is_active=True, is_masked=False),
            AERCorrectableError(bit_pos=7, name="Bad DLLP", short_code="BadDLLP", is_active=False, is_masked=False),
        ],
    )
    cfg = _create_config_space(aer_analysis=aer)
    stats = compute_pcie_statistics([cfg])
    assert stats.uncorrectable_count == 2
    assert stats.correctable_count == 2
    assert stats.total_aer_errors == 4


def test_dmesg_aer_counting() -> None:
    events = [
        DmesgAEREvent(
            timestamp="100.123456",
            bdf="0000:01:00.0",
            severity="Uncorrected (Fatal)",
            error_name="MalformedTLP",
            tlp_header=None,
            raw_line="raw line 1",
            root_cause_guide="guide 1",
        ),
        DmesgAEREvent(
            timestamp="102.123456",
            bdf="0000:01:00.0",
            severity="Uncorrected (Non-Fatal)",
            error_name="CompTimeout",
            tlp_header=None,
            raw_line="raw line 2",
            root_cause_guide="guide 2",
        ),
        DmesgAEREvent(
            timestamp="104.123456",
            bdf="0000:01:00.0",
            severity="Correctable",
            error_name="BadTLP",
            tlp_header=None,
            raw_line="raw line 3",
            root_cause_guide="guide 3",
        ),
    ]
    stats = compute_pcie_statistics([], dmesg_events=events)
    assert stats.device_count == 0
    assert stats.uncorrectable_count == 2
    assert stats.correctable_count == 1
    assert stats.total_aer_errors == 3


def test_dmesg_error_rate_calculation() -> None:
    events = [
        DmesgAEREvent(timestamp="10.000000", bdf="0000:01:00.0", severity="Correctable", error_name="BadTLP", tlp_header=None, raw_line="line 1", root_cause_guide=""),
        DmesgAEREvent(timestamp="15.000000", bdf="0000:01:00.0", severity="Correctable", error_name="BadTLP", tlp_header=None, raw_line="line 2", root_cause_guide=""),
        DmesgAEREvent(timestamp="20.000000", bdf="0000:01:00.0", severity="Correctable", error_name="BadTLP", tlp_header=None, raw_line="line 3", root_cause_guide=""),
        DmesgAEREvent(timestamp="30.000000", bdf="0000:01:00.0", severity="Correctable", error_name="BadTLP", tlp_header=None, raw_line="line 4", root_cause_guide=""),
    ]
    # duration = 30.0 - 10.0 = 20.0 seconds, 4 events => 4 / 20.0 = 0.2 errors/sec
    stats = compute_pcie_statistics([], dmesg_events=events)
    assert stats.error_rate_per_sec == pytest.approx(0.2, rel=1e-3)


def test_dmesg_error_rate_single_event_or_same_timestamp() -> None:
    single_event = [
        DmesgAEREvent(timestamp="124.582910", bdf="0000:01:00.0", severity="Fatal", error_name="MalformedTLP", tlp_header=None, raw_line="", root_cause_guide=""),
    ]
    stats_single = compute_pcie_statistics([], dmesg_events=single_event)
    assert stats_single.error_rate_per_sec is None

    same_ts_events = [
        DmesgAEREvent(timestamp="124.582910", bdf="0000:01:00.0", severity="Fatal", error_name="MalformedTLP", tlp_header=None, raw_line="", root_cause_guide=""),
        DmesgAEREvent(timestamp="124.582910", bdf="0000:01:00.0", severity="Fatal", error_name="CompTimeout", tlp_header=None, raw_line="", root_cause_guide=""),
    ]
    stats_same = compute_pcie_statistics([], dmesg_events=same_ts_events)
    assert stats_same.error_rate_per_sec is None


def test_dmesg_error_rate_missing_or_invalid_timestamps() -> None:
    events = [
        DmesgAEREvent(timestamp=None, bdf="0000:01:00.0", severity="Fatal", error_name="MalformedTLP", tlp_header=None, raw_line="", root_cause_guide=""),
        DmesgAEREvent(timestamp="invalid_ts", bdf="0000:01:00.0", severity="Fatal", error_name="MalformedTLP", tlp_header=None, raw_line="", root_cause_guide=""),
    ]
    stats = compute_pcie_statistics([], dmesg_events=events)
    assert stats.error_rate_per_sec is None


def test_link_degradation_counting() -> None:
    devices = [
        _create_config_space(
            bdf="0000:01:00.0",
            link_info=PCIeLinkInfo(
                max_speed_code=4, max_width=16, current_speed_code=3, current_width=8, is_degraded=True
            ),
        ),
        _create_config_space(
            bdf="0000:02:00.0",
            link_info=PCIeLinkInfo(
                max_speed_code=4, max_width=16, current_speed_code=4, current_width=16, is_degraded=False
            ),
        ),
        _create_config_space(
            bdf="0000:03:00.0",
            link_info=PCIeLinkInfo(
                max_speed_code=5, max_width=16, current_speed_code=5, current_width=8, is_degraded=True
            ),
        ),
        _create_config_space(bdf="0000:04:00.0", link_info=None),
    ]
    stats = compute_pcie_statistics(devices)
    assert stats.device_count == 4
    assert stats.link_degradation_count == 2


def test_link_speed_distribution() -> None:
    devices = [
        _create_config_space(link_info=PCIeLinkInfo(current_speed_code=1)),
        _create_config_space(link_info=PCIeLinkInfo(current_speed_code=2)),
        _create_config_space(link_info=PCIeLinkInfo(current_speed_code=3)),
        _create_config_space(link_info=PCIeLinkInfo(current_speed_code=3)),
        _create_config_space(link_info=PCIeLinkInfo(current_speed_code=4)),
        _create_config_space(link_info=PCIeLinkInfo(current_speed_code=5)),
        _create_config_space(link_info=PCIeLinkInfo(current_speed_code=6)),
        _create_config_space(link_info=PCIeLinkInfo(current_speed_code=0, current_speed_str="8.0 GT/s (Gen3)")),
    ]
    stats = compute_pcie_statistics(devices)
    assert stats.link_speed_distribution == {
        "Gen1": 1,
        "Gen2": 1,
        "Gen3": 3,
        "Gen4": 1,
        "Gen5": 1,
        "Gen6": 1,
    }


def test_combined_configs_and_dmesg_events() -> None:
    aer = AERAnalysisResult(
        offset=0x100,
        uncorr_status_raw=0x00040000,
        uncorr_mask_raw=0,
        uncorr_severity_raw=0x00040000,
        corr_status_raw=0x00000001,
        corr_mask_raw=0,
        cap_control_raw=0,
        header_log_raw=[0, 0, 0, 0],
        uncorr_errors=[
            AERUncorrectableError(bit_pos=18, name="Malformed TLP", short_code="MalformedTLP", is_active=True, is_masked=False, severity="Fatal"),
        ],
        corr_errors=[
            AERCorrectableError(bit_pos=0, name="Receiver Error", short_code="RxErr", is_active=True, is_masked=False),
        ],
    )
    cfg = _create_config_space(aer_analysis=aer)
    events = [
        DmesgAEREvent(timestamp="10.0", bdf="0000:01:00.0", severity="Fatal", error_name="CompTimeout", tlp_header=None, raw_line="", root_cause_guide=""),
        DmesgAEREvent(timestamp="20.0", bdf="0000:01:00.0", severity="Correctable", error_name="BadTLP", tlp_header=None, raw_line="", root_cause_guide=""),
    ]
    stats = compute_pcie_statistics([cfg], dmesg_events=events)
    assert stats.device_count == 1
    assert stats.uncorrectable_count == 2  # 1 from config + 1 from dmesg
    assert stats.correctable_count == 2    # 1 from config + 1 from dmesg
    assert stats.total_aer_errors == 4
    assert stats.error_rate_per_sec == pytest.approx(0.2, rel=1e-3)


def test_reporter_format_statistics() -> None:
    stats = PCIeStatistics(
        device_count=2,
        total_aer_errors=3,
        uncorrectable_count=2,
        correctable_count=1,
        error_rate_per_sec=0.25,
        link_degradation_count=1,
        topology_summary={"Display Controller": 1, "Network Controller": 1},
        link_speed_distribution={"Gen4": 1, "Gen3": 1},
    )
    md = PCIeReporter.format_statistics(stats)
    assert "## PCIe 統計摘要（PCIe Statistics Summary）" in md
    assert "- **裝置總數（Device Count）**: `2`" in md
    assert "- **AER 錯誤總數（Total AER Errors）**: `3`" in md
    assert "- **錯誤發生率（Error Rate）**: `0.2500 次/秒（errors/sec）`" in md
    assert "- **連線降級數量（Link Degradation Count）**: `1`" in md
    assert "顯示控制器（Display Controller）: `1`" in md
    assert "網路控制器（Network Controller）: `1`" in md
    assert "`Gen4`: `1`" in md
    assert "`Gen3`: `1`" in md


def test_frozen_dataclass_immutability() -> None:
    stats = PCIeStatistics(device_count=1)
    with pytest.raises(FrozenInstanceError):
        stats.device_count = 2  # type: ignore[misc]


def test_device_class_fallback_when_class_name_empty() -> None:
    cfg1 = _create_config_space(base_class=0x01, class_name="")
    cfg2 = _create_config_space(base_class=0xFE, class_name="")
    stats = compute_pcie_statistics([cfg1, cfg2])
    assert PCI_BASE_CLASSES[0x01] in stats.topology_summary
    assert "Unknown Class (0xFE)" in stats.topology_summary
