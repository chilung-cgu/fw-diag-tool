from __future__ import annotations

from fw_diag_tool.bundle import create_diagnostic_bundle, read_bundle_manifest


def test_bundle_without_raw_capture(tmp_path):
    reports = ["# Report A\ncontent"]
    path = create_diagnostic_bundle(tmp_path, reports=reports, configs=['{"key": "val"}'])
    assert path.exists()
    assert path.suffix == ".zip"
    assert "fw-diag-bundle" in path.name

    manifest = read_bundle_manifest(path)
    assert manifest.includes_raw_capture is False
    assert len(manifest.files) == 2
    assert all(f["name"].startswith(("reports/", "configs/")) for f in manifest.files)


def test_bundle_with_explicit_raw_capture(tmp_path):
    path = create_diagnostic_bundle(
        tmp_path,
        reports=["# R"],
        raw_captures=[("trace.csv", b"Time,SCL\n")],
    )
    manifest = read_bundle_manifest(path)
    assert manifest.includes_raw_capture is True
    assert any(f["name"] == "raw/trace.csv" for f in manifest.files)
