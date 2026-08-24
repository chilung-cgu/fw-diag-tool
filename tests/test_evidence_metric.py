from __future__ import annotations

from fw_diag_tool.evidence import EvidenceLevel, EvidenceMetric


def test_measured_metric_has_value_and_level():
    metric = EvidenceMetric.measured(
        400.0, sample_count=18, source="byte-duration", unit="kHz"
    )
    assert metric.is_available
    assert metric.value == 400.0
    assert metric.level == EvidenceLevel.MEASURED
    d = metric.to_dict()
    assert d["value"] == 400.0
    assert d["level"] == "Measured"


def test_unavailable_metric_has_null_value_and_reason():
    metric = EvidenceMetric.unavailable(
        reason="no bitrate or byte duration in input", unit="kHz"
    )
    assert not metric.is_available
    assert metric.value is None
    assert metric.level == EvidenceLevel.UNAVAILABLE
    assert metric.availability_reason == "no bitrate or byte duration in input"
    d = metric.to_dict()
    assert d["value"] is None
    assert d["availability_reason"] == "no bitrate or byte duration in input"
