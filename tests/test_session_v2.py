"""Session v2 schema, migration, atomic-write, and Fault Arena fixture tests."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from fw_diag_tool.fault_arena import FaultArenaFixtures
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.session.session_manager import SessionDocument, SessionManager
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.uart.parser import UARTCrashParser


class TestSessionV2Schema:
    def test_version_alias_is_normalized_without_keyerror(self):
        document = SessionManager.deserialize_session('{"version":"2.0","config":{},"report":{}}')

        assert document.schema_version == "2.0"

    def test_saved_payload_has_v2_top_level_fields(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        filepath = mgr.save_session("v2-schema", {"transactions": []})
        payload = json.loads(filepath.read_text(encoding="utf-8"))

        assert payload["schema_version"] == "2.0"
        assert isinstance(payload["tool_version"], str) and payload["tool_version"]
        assert payload["capture_sha256"] is None
        assert payload["board_profile_name"] is None
        assert payload["config"] == {}
        assert payload["report"] == {"transactions": []}
        assert payload["notes"] == ""

    def test_serialize_session_includes_all_required_fields(self):
        text = SessionManager.serialize_session(
            "serialized",
            {"report": {"count": 1}},
            capture_sha256="deadbeef",
            board_profile_name="YV4",
            config={"smbus_timeout_ms": 25.0},
            notes="synthetic case",
        )
        payload = json.loads(text)

        assert payload["schema_version"] == "2.0"
        assert payload["capture_sha256"] == "deadbeef"
        assert payload["board_profile_name"] == "YV4"
        assert payload["config"]["smbus_timeout_ms"] == 25.0
        assert payload["notes"] == "synthetic case"
        assert payload["report"] == {"report": {"count": 1}}

    def test_load_round_trips_report_and_metadata(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        report = {"anomaly_count": 3, "tool": "fw-diag"}
        filepath = mgr.save_session(
            "round-trip",
            report,
            capture_sha256=hashlib.sha256(b"capture").hexdigest(),
            board_profile_name="board-a",
            notes="keep original capture separately",
        )

        assert mgr.load_session(filepath) == report
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        assert raw["capture_sha256"] == hashlib.sha256(b"capture").hexdigest()
        assert raw["board_profile_name"] == "board-a"

    def test_load_document_round_trips_all_v2_fields(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        filepath = mgr.save_session(
            "round-trip-document",
            {"anomaly_count": 3},
            provenance={"input_name": "capture.csv"},
            capture_sha256="deadbeef",
            board_profile_name="board-a",
            config={"smbus_timeout_ms": 25.0},
            notes="keep the source capture separately",
        )

        document = mgr.load_document(filepath)

        assert isinstance(document, SessionDocument)
        assert document.schema_version == "2.0"
        assert document.name == "round-trip-document"
        assert document.capture_sha256 == "deadbeef"
        assert document.board_profile_name == "board-a"
        assert document.config == {"smbus_timeout_ms": 25.0}
        assert document.report == {"anomaly_count": 3}
        assert document.notes == "keep the source capture separately"
        assert document.provenance == {"input_name": "capture.csv"}

    def test_list_sessions_reports_schema_version(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        mgr.save_session("listed", {"ok": True})
        sessions = mgr.list_sessions()

        assert len(sessions) == 1
        assert sessions[0]["version"] == "2.0"


class TestSessionV1Migration:
    @staticmethod
    def _write_v1(path: Path, *, provenance: dict | None = None) -> Path:
        payload = {
            "version": "1.0",
            "created_at": "2025-01-01T00:00:00Z",
            "name": "legacy",
            "data": {"transactions": [1, 2, 3]},
        }
        if provenance is not None:
            payload["provenance"] = provenance
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_load_v1_migrates_to_v2_in_memory(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        filepath = self._write_v1(tmp_path / "legacy.fwsession.json")

        data = mgr.load_session(filepath)

        assert data == {"transactions": [1, 2, 3]}
        # The file itself must stay untouched (migration happens in memory).
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        assert raw["version"] == "1.0"
        assert "schema_version" not in raw

    def test_v1_provenance_sha_maps_to_capture_sha256(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        filepath = self._write_v1(
            tmp_path / "legacy.fwsession.json",
            provenance={
                "input_sha256": "abc123",
                "board_profile_name": "yv4",
                "smbus_timeout_ms": 25.0,
                "input_mode": "upload",
                "input_name": "capture.csv",
                "custom_key": "kept-in-provenance",
            },
        )

        migrated = mgr.migrate_v1(json.loads(filepath.read_text(encoding="utf-8")))

        assert migrated["schema_version"] == "2.0"
        assert migrated["capture_sha256"] == "abc123"
        assert migrated["board_profile_name"] == "yv4"
        assert migrated["config"] == {
            "smbus_timeout_ms": 25.0,
            "input_mode": "upload",
            "input_name": "capture.csv",
        }
        assert migrated["_v1_provenance"]["custom_key"] == "kept-in-provenance"
        assert migrated["_migrated_from"] == "1.0"

    def test_migrate_v1_rejects_non_mapping_data(self):
        with pytest.raises(TypeError, match="session data"):
            SessionManager.migrate_v1({"version": "1.0", "data": [1, 2]})

    def test_unsupported_versions_still_raise(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        bad = tmp_path / "bad.fwsession.json"
        bad.write_text('{"version": "9.9", "data": {}}', encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported session version"):
            mgr.load_session(bad)


class TestAtomicWrite:
    def test_save_leaves_no_temporary_files(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        filepath = mgr.save_session("atomic", {"ok": True})

        assert filepath.exists()
        leftovers = [p for p in tmp_path.iterdir() if p.name != filepath.name]
        assert leftovers == []

    def test_replace_existing_file_atomically(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        first = mgr.save_session("overwrite", {"generation": 1})
        second = mgr.save_session("overwrite", {"generation": 2})

        # Distinct files (timestamped names), each internally consistent.
        assert first != second
        for path in (first, second):
            raw = json.loads(path.read_text(encoding="utf-8"))
            assert raw["report"]["generation"] in (1, 2)

    def test_serialization_failure_does_not_touch_disk(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        before = sorted(p.name for p in tmp_path.iterdir())
        with pytest.raises((TypeError, ValueError)):
            mgr.save_session("nan", {"value": float("nan")})
        after = sorted(p.name for p in tmp_path.iterdir())

        assert before == after == []


class TestBackwardCompatibleBehavior:
    def test_legacy_test_contract_save_and_load(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        data = {"transactions": [1, 2, 3], "anomaly_count": 0}
        filepath = mgr.save_session("test_analysis", data)

        assert filepath.exists()
        assert mgr.load_session(filepath) == data

    def test_safe_name_and_provenance_still_enforced(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        filepath = mgr.save_session("../Board Capture / A", {"count": 1}, provenance={"k": "v"})

        assert "/" not in filepath.name
        assert mgr.load_session(filepath) == {"count": 1}
        assert json.loads(filepath.read_text(encoding="utf-8"))["provenance"] == {"k": "v"}


class TestFaultArenaFixtureRegistry:
    def test_registry_lists_all_cases(self):
        cases = FaultArenaFixtures.list_cases()

        assert len(cases) == 30
        assert [c.case_id for c in cases] == [f"{i:02d}" for i in range(1, 31)]
        kinds = {c.kind for c in cases}
        assert kinds <= {"i2c", "pcie", "spi", "uart", "mctp"}

    def test_lookup_by_id_and_case_label(self):
        assert FaultArenaFixtures.get_case("03").case_id == "03"
        assert FaultArenaFixtures.get_case("Case 07").case_id == "07"
        with pytest.raises(KeyError):
            FaultArenaFixtures.get_case("99")

    def test_generate_is_deterministic_and_nonempty(self):
        for case_id in ("01", "10", "20", "30"):
            first = FaultArenaFixtures.generate(case_id)
            assert first
            assert first == FaultArenaFixtures.generate(case_id)

    def test_generate_all_covers_every_case(self):
        generated = FaultArenaFixtures.generate_all()

        assert set(generated) == {f"{i:02d}" for i in range(1, 31)}
        assert all(text.strip() for text in generated.values())

    def test_write_all_creates_files(self, tmp_path: Path):
        written = FaultArenaFixtures.write_all(tmp_path)

        assert len(written) == 30
        for path in written:
            assert path.exists() and path.stat().st_size > 0

    def test_unknown_case_lookup_raises_keyerror(self):
        with pytest.raises(KeyError, match="unknown Fault Arena case"):
            FaultArenaFixtures.get_case("no-such-case")


class TestSessionManagerValidation:
    def test_provenance_may_not_shadow_top_level_capture_fields(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        with pytest.raises(ValueError, match="capture_sha256"):
            mgr.save_session("shadowed", {}, provenance={"capture_sha256": "x"})

    def test_non_string_capture_sha256_rejected(self, tmp_path: Path):
        mgr = SessionManager(session_dir=tmp_path)
        with pytest.raises(TypeError, match="capture_sha256"):
            mgr.save_session("bad-sha", {}, capture_sha256=123)  # type: ignore[arg-type]

    def test_serialize_rejects_session_that_cannot_be_loaded(self, monkeypatch):
        monkeypatch.setattr(SessionManager, "MAX_SESSION_BYTES", 512)

        with pytest.raises(ValueError, match="512-byte safety limit"):
            SessionManager.serialize_session("too-large", {"payload": "x" * 512})

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
    def test_session_directory_and_file_are_private(self, tmp_path: Path):
        session_dir = tmp_path / "sessions"
        mgr = SessionManager(session_dir=session_dir)

        filepath = mgr.save_session("private", {"ok": True})

        assert stat.S_IMODE(session_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(filepath.stat().st_mode) == 0o600


EXPECTED_I2C_CODES = {
    "01": {"I2C_ADDR_NACK"},
    "02": {"I2C_DATA_NACK"},
    "03": {"I2C_SMBUS_TIMEOUT"},
    "04": {"I2C_EEPROM_PAGE_ROLLOVER"},
    "05": {"I2C_ADDR_NACK", "I2C_MUX_MULTI_CHANNEL"},
}


class TestFaultArenaCasesParse:
    @pytest.mark.parametrize("case_id", ["01", "02", "03", "04", "05", "06"])
    def test_i2c_cases_decode_through_engine(self, case_id: str):
        csv_text = FaultArenaFixtures.generate(case_id)
        engine = I2CDiagnosticEngine(eeprom_profile="24C02")
        report = engine.analyze_csv_content(csv_text)

        codes = {issue.code for issue in report.issues}
        if case_id in EXPECTED_I2C_CODES:
            assert EXPECTED_I2C_CODES[case_id] <= codes
        else:
            summaries = [t.semantic_summary or "" for t in report.transactions]
            assert any("VOUT_TRIM" in s and "-0.25" in s for s in summaries)
            assert any("READ_VOUT" in s and "= 12.0 V" in s for s in summaries)

    def test_case_04_uses_24c02_page_profile_for_rollover(self):
        report = I2CDiagnosticEngine(eeprom_profile="24C02").analyze_csv_content(
            FaultArenaFixtures.generate("04")
        )

        rollover_transactions = [
            tx for tx in report.transactions if tx.decoded_values.get("rollover_hazard") is True
        ]

        assert len(rollover_transactions) == 1
        decoded = rollover_transactions[0].decoded_values
        assert decoded["offset"] == 0x06
        assert decoded["page_size"] == 8
        assert decoded["payload_len"] == 4
        assert decoded["evidence"] == "explicit-profile"
        assert any(issue.code == "I2C_EEPROM_PAGE_ROLLOVER" for issue in report.issues)

    def test_case_06_metadata_matches_signed_decode(self):
        case = FaultArenaFixtures.get_case("06")
        report = I2CDiagnosticEngine(eeprom_profile="24C02").analyze_csv_content(
            FaultArenaFixtures.generate("06")
        )

        summaries = [tx.semantic_summary or "" for tx in report.transactions]
        trim_transaction = next(tx for tx in report.transactions if tx.command_name == "VOUT_TRIM")
        vout_transaction = next(
            tx
            for tx in report.transactions
            if tx.command_name == "READ_VOUT" and "value" in tx.decoded_values
        )
        assert case.title == ("PMBus VOUT_TRIM Signed Two's-Complement (-0.25 V; READ_VOUT 12.0 V)")
        assert "127" not in case.title
        assert trim_transaction.decoded_values["value"] == -0.25
        assert vout_transaction.decoded_values["value"] == 12.0
        assert any("VOUT_TRIM = -0.25 V" in summary for summary in summaries)
        assert any("READ_VOUT = 12.0 V" in summary for summary in summaries)

    @pytest.mark.parametrize(
        ("case_id", "expected_aer", "expect_degraded"),
        [
            ("07", set(), True),
            ("08", {"CompTimeout"}, False),
            ("09", {"MalformedTLP"}, False),
            ("10", {"PoisonedTLP"}, False),
        ],
    )
    def test_pcie_cases_decode_link_and_aer(
        self, case_id: str, expected_aer: set[str], expect_degraded: bool
    ):
        bdf, raw = PCIeAnalyzer.parse_lspci_text(FaultArenaFixtures.generate(case_id))
        cfg = PCIeAnalyzer.decode_config_space(raw, bdf)

        assert cfg.link_info is not None
        assert cfg.link_info.is_degraded is expect_degraded
        assert cfg.aer_analysis is not None
        active = {
            e.short_code for e in cfg.aer_analysis.uncorr_errors if e.is_active and not e.is_masked
        }
        assert active == expected_aer

    def test_case_07_represents_gen4_x16_to_gen1_x1_degradation(self):
        bdf, raw = PCIeAnalyzer.parse_lspci_text(FaultArenaFixtures.generate("07"))
        cfg = PCIeAnalyzer.decode_config_space(raw, bdf)

        assert cfg.link_info is not None
        assert cfg.link_info.max_speed_code == 4
        assert cfg.link_info.max_speed_str == "16.0 GT/s (Gen4)"
        assert cfg.link_info.max_width == 16
        assert cfg.link_info.current_speed_code == 1
        assert cfg.link_info.current_speed_str == "2.5 GT/s (Gen1)"
        assert cfg.link_info.current_width == 1
        assert cfg.link_info.is_degraded is True

    def test_spi_missing_wren_flags_unknown_wel_state(self):
        report = SPIDiagnosticEngine().analyze_csv_content(FaultArenaFixtures.generate("11"))
        codes = {a.code for a in report.anomalies}
        assert "SPI_WEL_STATE_UNKNOWN" in codes or "SPI_WRITE_NO_WREN" in codes

    def test_spi_page_wraparound_starts_with_wren(self):
        report = SPIDiagnosticEngine().analyze_csv_content(FaultArenaFixtures.generate("12"))
        opcodes = [t.opcode_name for t in report.transactions]

        assert opcodes[0].startswith("Write Enable")
        assert any(op.startswith("Page Program") for op in opcodes[1:])
        assert any(a.code == "SPI_PAGE_PROGRAM_WRAP" for a in report.anomalies)

    @pytest.mark.parametrize("case_id", ["13", "14"])
    def test_spi_jedec_line_fault_detected(self, case_id: str):
        report = SPIDiagnosticEngine().analyze_csv_content(FaultArenaFixtures.generate(case_id))

        assert any(a.code == "SPI_JEDEC_LINE_FAULT" for a in report.anomalies)

    def test_kernel_null_pointer_parsed_as_x86_panic(self):
        report = UARTCrashParser().parse_kernel_panic(FaultArenaFixtures.generate("15"))

        assert report.architecture == "x86_64"
        assert report.faulting_address is not None
        assert report.faulting_func == "probe_driver"

    @pytest.mark.parametrize(
        ("case_id", "flag"),
        [
            ("16", "UFSR.DIVBYZERO"),
            ("17", "UFSR.UNALIGNED"),
            ("18", "BFSR.IMPRECISERR"),
        ],
    )
    def test_hardfault_flag_decoded(self, case_id: str, flag: str):
        report = UARTCrashParser().parse_arm_hardfault(FaultArenaFixtures.generate(case_id))

        assert any(flag in f for f in report.fault_flags)

    def test_mctp_sequence_error_visible_in_packets(self):
        report = ServerMgmtParser.parse_text_dump(FaultArenaFixtures.generate("19"))
        sequences = [pkt.pkt_seq for pkt in report.mctp_packets]

        assert sequences == [0, 2], "second packet must carry the out-of-order sequence 2"
        assert len(report.mctp_messages) == 1
        assert report.mctp_messages[0].is_complete is False
        assert report.mctp_messages[0].error == "sequence mismatch: expected 1, got 2"

    def test_ipmb_checksum_corruption_detected(self):
        report = ServerMgmtParser.parse_text_dump(FaultArenaFixtures.generate("20"))
        frames = [(f.checksum1_valid, f.checksum2_valid) for f in report.ipmb_frames]

        assert frames[0] == (True, True), "baseline request frame must be valid"
        assert frames[1][0] is False, "response checksum-1 must fail"
