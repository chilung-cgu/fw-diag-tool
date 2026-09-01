from dataclasses import FrozenInstanceError

import pytest

from fw_diag_tool import uart
from fw_diag_tool.uart import MatchedSymptom, UARTSymptom, classify_symptoms
from fw_diag_tool.uart.models import CrashType, UARTReport
from fw_diag_tool.uart.reporter import UARTReporter


def test_database_has_expected_categories_and_entries() -> None:
    from fw_diag_tool.uart import SYMPTOM_DB

    assert len(SYMPTOM_DB) >= 35
    assert {
        "kernel_panic",
        "watchdog",
        "oom",
        "filesystem",
        "driver_probe",
        "hardware_error",
        "boot_failure",
        "security_violation",
        "memory_error",
    } <= {symptom.category for symptom in SYMPTOM_DB}


def test_symptom_is_frozen_and_has_bilingual_fields() -> None:
    symptom = UARTSymptom(
        pattern=r"panic",
        category="kernel_panic",
        severity="critical",
        description_zh="核心崩潰",
        description_en="Kernel panic",
        suggested_action_zh="檢查 call trace",
        suggested_action_en="Inspect the call trace",
    )
    assert symptom.severity == "critical"
    with pytest.raises(FrozenInstanceError):
        symptom.category = "other"  # type: ignore[misc]


def test_classify_matches_case_insensitively_with_one_based_line_numbers() -> None:
    matches = classify_symptoms(["normal", "KERNEL PANIC - not syncing", "done"])
    assert matches
    assert matches[0].line_number == 2
    assert matches[0].matched_line == "KERNEL PANIC - not syncing"
    assert matches[0].symptom.category == "kernel_panic"
    assert matches[0].symptom.severity == "critical"


def test_classify_returns_all_patterns_on_same_line() -> None:
    matches = classify_symptoms(["Kernel panic: Oops: out of memory"])
    categories = {match.symptom.category for match in matches}
    assert {"kernel_panic", "oom"} <= categories


def test_classify_preserves_duplicate_lines_and_order() -> None:
    matches = classify_symptoms(["watchdog timeout", "watchdog timeout"])
    assert len(matches) >= 2
    assert {match.line_number for match in matches} == {1, 2}
    assert [match.line_number for match in matches] == sorted(
        match.line_number for match in matches
    )


def test_classify_empty_and_unmatched_lines() -> None:
    assert classify_symptoms([]) == []
    assert classify_symptoms(["boot complete", "all good"]) == []


@pytest.mark.parametrize(
    ("line", "category"),
    [
        ("watchdog: hard lockup detected", "watchdog"),
        ("oom-killer invoked", "oom"),
        ("EXT4-fs error (device mmcblk0)", "filesystem"),
        ("i2c probe failed with error -121", "driver_probe"),
        ("EDAC: uncorrectable ECC error", "hardware_error"),
        ("No bootable device", "boot_failure"),
        ("avc: denied { read }", "security_violation"),
        ("segmentation fault", "memory_error"),
    ],
)
def test_classify_representative_boot_failure_patterns(line: str, category: str) -> None:
    assert any(match.symptom.category == category for match in classify_symptoms([line]))


def test_matched_symptom_is_frozen() -> None:
    match = classify_symptoms(["BUG: unable to handle page fault"])[0]
    assert isinstance(match, MatchedSymptom)
    with pytest.raises(FrozenInstanceError):
        match.line_number = 99  # type: ignore[misc]


def test_reporter_includes_symptom_classification_section() -> None:
    report = UARTReport(
        crash_type=CrashType.GENERIC_LOG,
        summary_title="Generic",
        raw_log_lines=1,
    )
    markdown = UARTReporter.to_markdown(report, lines=["No bootable device"])
    assert "## UART 症狀分類（UART Symptom Classification）" in markdown
    assert "boot_failure" in markdown
    assert "No bootable device" in markdown


def test_reporter_symptom_section_handles_no_matches() -> None:
    report = UARTReport(
        crash_type=CrashType.GENERIC_LOG,
        summary_title="Generic",
        raw_log_lines=1,
    )
    markdown = UARTReporter.to_markdown(report, lines=["boot complete"])
    assert "## UART 症狀分類（UART Symptom Classification）" in markdown
    assert "未偵測到症狀" in markdown


def test_public_exports_include_symptom_api() -> None:
    assert "UARTSymptom" in uart.__all__
    assert "MatchedSymptom" in uart.__all__
    assert "SYMPTOM_DB" in uart.__all__
    assert "classify_symptoms" in uart.__all__
