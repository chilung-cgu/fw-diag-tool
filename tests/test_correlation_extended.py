"""Tests for extended 5-protocol cross-correlation timeline and anomaly clustering."""

from __future__ import annotations

from types import SimpleNamespace

from fw_diag_tool.gui.pages.correlation_ui import (
    _build_timeline_chart,
    build_timeline_events,
    detect_cross_protocol_clusters,
    render,
)
from fw_diag_tool.gui.shared import analyze_mctp_input, analyze_pcie_input
from fw_diag_tool.mctp.models import IPMBFrame, MCTPMessage, ServerMgmtReport
from fw_diag_tool.pcie.models import (
    AERAnalysisResult,
    AERCorrectableError,
    AERUncorrectableError,
    DmesgAEREvent,
    PCIeConfigSpace,
    PCIeLinkInfo,
)
from fw_diag_tool.resources import (
    load_mctp_sample,
    load_pcie_sample,
)


def test_correlation_render_callable() -> None:
    assert callable(render)


def test_load_pcie_sample() -> None:
    lspci_txt = load_pcie_sample("lspci")
    assert "00:00.0" in lspci_txt or len(lspci_txt) > 50

    dmesg_txt = load_pcie_sample("dmesg")
    assert "AER" in dmesg_txt or "PCIe" in dmesg_txt

    mctp_hex = load_mctp_sample("mctp-pldm")
    assert len(mctp_hex) > 10


def test_build_timeline_events_pcie_dmesg_aer() -> None:
    dmesg_event = DmesgAEREvent(
        timestamp="0.015",
        bdf="0000:01:00.0",
        severity="Fatal",
        error_name="MalformedTLP",
        tlp_header="00 00 00 00",
        raw_line="raw dmesg line",
        root_cause_guide="Check TLP framing",
    )
    events = build_timeline_events(pcie_report=[dmesg_event])
    assert len(events) == 1
    assert events[0]["protocol"] == "PCIe"
    assert events[0]["timestamp"] == 0.015
    assert events[0]["anomaly"] is True
    assert "MalformedTLP" in events[0]["label"]


def test_build_timeline_events_pcie_config_space_with_link_and_aer() -> None:
    cfg = PCIeConfigSpace(
        raw_data=b"\x00" * 256,
        bdf="0000:02:00.0",
        vendor_id=0x10DE,
        device_id=0x2204,
        link_info=PCIeLinkInfo(
            max_speed_str="16.0 GT/s (Gen4)",
            max_width=16,
            current_speed_str="2.5 GT/s (Gen1)",
            current_width=4,
            is_degraded=True,
            degradation_reason="PCIe Link Degraded: Gen1 x4 (Max Gen4 x16)",
        ),
        aer_analysis=AERAnalysisResult(
            offset=0x100,
            uncorr_status_raw=0x00040000,
            uncorr_mask_raw=0,
            uncorr_severity_raw=0x00040000,
            corr_status_raw=0x00000001,
            corr_mask_raw=0,
            cap_control_raw=0,
            header_log_raw=[0, 0, 0, 0],
            uncorr_errors=[
                AERUncorrectableError(
                    bit_pos=18,
                    name="Malformed TLP",
                    short_code="MALF_TLP",
                    is_active=True,
                    is_masked=False,
                    severity="Fatal",
                )
            ],
            corr_errors=[
                AERCorrectableError(
                    bit_pos=0,
                    name="Receiver Error",
                    short_code="RCVR_ERR",
                    is_active=True,
                    is_masked=False,
                )
            ],
        ),
    )
    events = build_timeline_events(pcie_report=cfg)
    assert len(events) == 4  # Device Presence + Link Degraded + AER Uncorr + AER Corr
    dev_ev = next(e for e in events if "PCIe Dev" in e["label"])
    assert dev_ev["anomaly"] is False
    assert "0x10DE:0x2204" in dev_ev["label"]

    link_ev = next(e for e in events if "Link Degraded" in e["label"])
    assert link_ev["anomaly"] is True

    uncorr_ev = next(e for e in events if "AER Uncorr" in e["label"])
    assert uncorr_ev["anomaly"] is True

    corr_ev = next(e for e in events if "AER Corr" in e["label"])
    assert corr_ev["anomaly"] is True


def test_build_timeline_events_mctp_and_ipmb() -> None:
    msg_ok = MCTPMessage(
        src_eid=0x0A,
        dest_eid=0x08,
        msg_tag=1,
        msg_type=0x01,
        msg_type_name="PLDM",
        packets_count=1,
        payload=[0x00, 0x00],
        is_complete=True,
        summary="MCTP: EID 0x0A -> 0x08 [PLDM]",
    )
    msg_err = MCTPMessage(
        src_eid=0x0A,
        dest_eid=0x08,
        msg_tag=2,
        msg_type=0x01,
        msg_type_name="PLDM",
        packets_count=2,
        payload=[0x00],
        is_complete=False,
        error="sequence mismatch",
        summary="MCTP: Incomplete message",
    )
    ipmb_ok = IPMBFrame(
        rs_addr=0x20,
        netfn=0x06,
        netfn_name="App (Request)",
        rs_lun=0,
        checksum1_valid=True,
        rq_addr=0x81,
        rq_seq=1,
        rq_lun=0,
        cmd=0x01,
        cmd_name="Get Device ID",
        checksum2_valid=True,
        summary="IPMB: 0x81 -> 0x20 [App: Get Device ID]",
    )
    ipmb_corrupt = IPMBFrame(
        rs_addr=0x20,
        netfn=0x06,
        netfn_name="App (Request)",
        rs_lun=0,
        checksum1_valid=True,
        rq_addr=0x81,
        rq_seq=2,
        rq_lun=0,
        cmd=0x02,
        cmd_name="Cold Reset",
        checksum2_valid=False,
        summary="IPMB: 0x81 -> 0x20 [App: Cold Reset]",
    )
    report = ServerMgmtReport(
        mctp_messages=[msg_ok, msg_err],
        ipmb_frames=[ipmb_ok, ipmb_corrupt],
        source_errors=["malformed trailing bytes"],
    )
    events = build_timeline_events(mctp_report=report)
    assert len(events) == 5

    mctp_anomalies = [e for e in events if e["protocol"] == "MCTP" and e["anomaly"]]
    assert len(mctp_anomalies) == 3  # msg_err + ipmb_corrupt + source_error


def test_build_timeline_events_all_5_protocols_and_clustering() -> None:
    i2c_report = SimpleNamespace(
        transactions=[SimpleNamespace(start_time=0.001, address_7bit=0x50)],
        issues=[
            SimpleNamespace(
                title="Address NACK on 0x50",
                timestamp=0.0012,
            )
        ],
    )
    spi_report = SimpleNamespace(
        transactions=[SimpleNamespace(start_time=0.0015, opcode_name="Fast Read (0x0B)")],
        issues=[
            SimpleNamespace(
                title="SPI Flash Timeout",
                timestamp=0.0018,
            )
        ],
    )
    uart_report = SimpleNamespace(
        crash_type=SimpleNamespace(value="Kernel Panic"),
        summary_title="Kernel Panic in nvme_probe",
    )
    pcie_report = [
        DmesgAEREvent(
            timestamp="0.0020",
            bdf="0000:01:00.0",
            severity="Fatal",
            error_name="SurpriseDown",
            tlp_header=None,
            raw_line="",
            root_cause_guide="",
        )
    ]
    mctp_report = ServerMgmtReport(
        mctp_messages=[
            MCTPMessage(
                src_eid=0x0A,
                dest_eid=0x08,
                msg_tag=1,
                msg_type=0x01,
                msg_type_name="PLDM",
                packets_count=1,
                payload=[],
                is_complete=False,
                error="Dropped packet",
                summary="MCTP Dropped",
            )
        ]
    )

    events = build_timeline_events(
        i2c_report=i2c_report,
        spi_report=spi_report,
        uart_report=uart_report,
        pcie_report=pcie_report,
        mctp_report=mctp_report,
    )

    protocols_seen = {e["protocol"] for e in events}
    assert protocols_seen == {"I2C", "SPI", "UART", "PCIe", "MCTP"}

    # Detect clusters within 2ms window
    clusters = detect_cross_protocol_clusters(events, window_s=0.002)
    assert len(clusters) >= 1
    cluster_protos = clusters[0]["protocols"]
    assert len(cluster_protos) >= 2


def test_timeline_chart_all_5_protocols() -> None:
    events = [
        {"protocol": "I2C", "timestamp": 0.001, "label": "I2C Txn", "anomaly": False},
        {"protocol": "SPI", "timestamp": 0.002, "label": "SPI Read", "anomaly": False},
        {"protocol": "UART", "timestamp": 0.003, "label": "UART Crash", "anomaly": True},
        {"protocol": "PCIe", "timestamp": 0.004, "label": "PCIe AER Fatal", "anomaly": True},
        {"protocol": "MCTP", "timestamp": 0.005, "label": "MCTP Msg", "anomaly": False},
    ]
    fig = _build_timeline_chart(events)
    assert len(fig.data) == 5
    trace_names = {trace.name for trace in fig.data}
    assert trace_names == {"I2C", "SPI", "UART", "PCIe", "MCTP"}
    assert fig.layout.yaxis.ticktext == ("MCTP", "PCIe", "UART", "SPI", "I2C")


def test_analyze_pcie_and_mctp_helpers() -> None:
    pcie_sample = load_pcie_sample("lspci")
    pcie_devices = analyze_pcie_input(pcie_sample)
    assert len(pcie_devices) >= 1

    pcie_dmesg = load_pcie_sample("dmesg")
    pcie_events = analyze_pcie_input(pcie_dmesg)
    assert len(pcie_events) >= 1

    mctp_sample = load_mctp_sample("mctp-pldm")
    mctp_rep = analyze_mctp_input(mctp_sample)
    assert mctp_rep.total_frames >= 1
