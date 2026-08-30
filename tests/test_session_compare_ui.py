"""Tests for Session A/B comparison GUI module."""

from __future__ import annotations

import json

import pytest

from fw_diag_tool.gui.pages.session_compare_ui import (
    _parse_session_payload,
    build_comparison_dataframe,
    format_session_comparison_markdown,
    get_sample_sessions,
    render,
)
from fw_diag_tool.session.comparator import compare_sessions


def test_render_is_callable() -> None:
    """render() 函式必須存在且可被呼叫。"""
    assert callable(render)


def test_parse_session_payload_supports_dict_str_bytes() -> None:
    """測試 _parse_session_payload 能正確解析 dict、str 與 bytes。"""
    sample_dict = {"name": "sess_1", "report": {"anomaly_count": 2}}
    parsed_from_dict = _parse_session_payload(sample_dict, default_name="fallback")
    assert parsed_from_dict["name"] == "sess_1"

    sample_str = json.dumps({"report": {"anomaly_count": 0}})
    parsed_from_str = _parse_session_payload(sample_str, default_name="custom_name")
    assert parsed_from_str["name"] == "custom_name"
    assert parsed_from_str["report"]["anomaly_count"] == 0

    sample_bytes = json.dumps({"name": "b_sess", "report": {"total_transactions": 10}}).encode(
        "utf-8"
    )
    parsed_from_bytes = _parse_session_payload(sample_bytes, default_name="fallback")
    assert parsed_from_bytes["name"] == "b_sess"


def test_parse_session_payload_invalid_inputs_raise_type_error() -> None:
    """測試非法輸入（非 dict/str/bytes 或 JSON 格式非 mapping）拋出 TypeError。"""
    with pytest.raises(TypeError):
        _parse_session_payload(12345, default_name="invalid")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        _parse_session_payload("[1, 2, 3]", default_name="invalid")


def test_build_comparison_dataframe_values() -> None:
    """測試 build_comparison_dataframe 產生的表格數值與 Delta 格式。"""
    baseline = {
        "name": "Base_v1",
        "config": {"protocol": "i2c"},
        "report": {"anomaly_count": 5, "total_transactions": 20},
    }
    candidate = {
        "name": "Cand_v2",
        "config": {"protocol": "i2c"},
        "report": {"anomaly_count": 1, "total_transactions": 25},
    }
    comparison = compare_sessions(baseline, candidate)
    df = build_comparison_dataframe(comparison, baseline, candidate)

    assert len(df) == 3
    # 檢查欄位名稱
    assert list(df.columns) == [
        "指標 / 項目（Metric）",
        "Baseline（基準）",
        "Candidate（待測）",
        "差異（Delta）",
    ]

    # 檢查各列內容
    rows = df.to_dict(orient="records")
    assert rows[0]["指標 / 項目（Metric）"] == "異常總數（Anomaly Count）"
    assert rows[0]["Baseline（基準）"] == "5"
    assert rows[0]["Candidate（待測）"] == "1"
    assert rows[0]["差異（Delta）"] == "-4"

    assert rows[1]["指標 / 項目（Metric）"] == "交易總數（Total Transactions）"
    assert rows[1]["Baseline（基準）"] == "20"
    assert rows[1]["Candidate（待測）"] == "25"
    assert rows[1]["差異（Delta）"] == "+5"

    assert rows[2]["指標 / 項目（Metric）"] == "協定（Protocol）"
    assert rows[2]["Baseline（基準）"] == "i2c"
    assert rows[2]["Candidate（待測）"] == "i2c"
    assert rows[2]["差異（Delta）"] == "一致（Same）"


def test_build_comparison_dataframe_protocol_changed() -> None:
    """測試跨協定比對時協定差異顯示變更。"""
    baseline = {
        "name": "Base_I2C",
        "config": {"protocol": "i2c"},
        "report": {"anomaly_count": 2, "total_transactions": 10},
    }
    candidate = {
        "name": "Cand_SPI",
        "config": {"protocol": "spi"},
        "report": {"anomaly_count": 2, "total_transactions": 10},
    }
    comparison = compare_sessions(baseline, candidate)
    df = build_comparison_dataframe(comparison, baseline, candidate)
    rows = df.to_dict(orient="records")
    assert rows[2]["差異（Delta）"] == "變更（Changed）"


def test_format_session_comparison_markdown() -> None:
    """測試 Markdown 報告格式與必要欄位。"""
    baseline, candidate = get_sample_sessions()
    comparison = compare_sessions(baseline, candidate)
    md = format_session_comparison_markdown(comparison, baseline, candidate)

    assert "# Session A/B 對比報告（Session Comparison Report）" in md
    assert "- **Baseline（基準）**: I2C Baseline (Golden/Before)" in md
    assert "- **Candidate（待測）**: I2C Candidate (Fixed/After)" in md
    assert "- **判定結果（Verdict）**: improved" in md
    assert "## 指標差異對比（Metric Deltas）" in md
    assert "## 分析摘要（Summary）" in md


def test_get_sample_sessions_and_comparison_verdict() -> None:
    """測試內建範例資料可直接執行並得到 improved 判定。"""
    baseline, candidate = get_sample_sessions()
    assert isinstance(baseline, dict)
    assert isinstance(candidate, dict)

    comparison = compare_sessions(baseline, candidate)
    assert comparison.verdict == "improved"
    assert comparison.metric_deltas["anomaly_count"] == -4
    assert comparison.metric_deltas["total_transactions"] == 4
    assert comparison.metric_deltas["protocol"]["changed"] is False
