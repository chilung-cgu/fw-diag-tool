from __future__ import annotations

import json
import re
import shutil
import subprocess
import tarfile
import venv
from pathlib import Path
from zipfile import ZipFile

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def built_artifacts(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required for isolated packaging tests")
    assert uv is not None
    output_dir = tmp_path_factory.mktemp("artifacts")
    subprocess.run(
        [uv, "build", "--out-dir", str(output_dir)],
        cwd=ROOT,
        check=True,
    )
    return next(output_dir.glob("*.whl")), next(output_dir.glob("*.tar.gz"))


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def test_release_manifest_and_documentation_contract() -> None:
    version = project_version()
    manifest = json.loads(
        (ROOT / "src/fw_diag_tool/resources/release_notes.json").read_text(encoding="utf-8")
    )
    releases = manifest["releases"]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^##\s+\[([^]]+)\]", changelog, re.MULTILINE)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    project_block = re.search(
        r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", (ROOT / "pyproject.toml").read_text()
    )
    assert project_block is not None
    declared = re.search(
        r"^version\s*=\s*[\"']([^\"']+)[\"']", project_block.group(1), re.MULTILINE
    )
    assert declared is not None and declared.group(1) == version
    assert releases[0]["version"] == version
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    lock_match = re.search(r'(?ms)^name = "fw-diag-tool"\s*\nversion = "([^"]+)"', lock)
    assert lock_match is not None and lock_match.group(1) == version
    assert headings[0] == version
    assert len(headings) == len(set(headings))
    assert {item["version"] for item in releases} == set(headings)
    assert all(item["source_ref"] == f"CHANGELOG.md#{item['version']}" for item in releases)
    assert f"目前版本 **v{version}**" in readme
    assert re.search(rf"^## .*v{re.escape(version)} .*Highlights", readme, re.MULTILINE)


def test_wheel_metadata_and_package_resources_are_versioned_and_included(built_artifacts) -> None:
    wheel, _ = built_artifacts
    version = project_version()

    assert wheel.name == f"fw_diag_tool-{version}-py3-none-any.whl"
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata_text = archive.read(metadata).decode("utf-8")

    assert f"Version: {version}" in metadata_text
    assert "fw_diag_tool/resources/saleae_normal_pmbus_eeprom.csv" in names
    assert "fw_diag_tool/resources/spi_w25q128_sample.csv" in names
    assert "fw_diag_tool/resources/i2c_golden.csv" in names
    assert "fw_diag_tool/resources/i2c_failing_nack.csv" in names
    assert "fw_diag_tool/resources/pcie_aer_dmesg.log" in names
    assert "fw_diag_tool/resources/pcie_aer_lspci.txt" in names
    assert "fw_diag_tool/resources/release_notes.json" in names
    assert "fw_diag_tool/docs/chapters/ch01_i2c_pmbus.md" in names


def test_isolated_wheel_exposes_gui_guide_without_source_checkout(
    built_artifacts, tmp_path: Path
) -> None:
    wheel, _ = built_artifacts
    environment = tmp_path / "wheel-env"
    venv.EnvBuilder(with_pip=True).create(environment)
    wheel_python = environment / "bin" / "python"
    if not wheel_python.exists():
        wheel_python = environment / "Scripts" / "python.exe"

    subprocess.run(
        [str(wheel_python), "-m", "pip", "install", "--no-deps", str(wheel)],
        cwd=tmp_path,
        check=True,
    )


def test_isolated_wheel_loads_release_notes_without_source_checkout(
    built_artifacts, tmp_path: Path
) -> None:
    wheel, _ = built_artifacts
    environment = tmp_path / "release-wheel-env"
    venv.EnvBuilder(with_pip=True).create(environment)
    wheel_python = environment / "bin" / "python"
    if not wheel_python.exists():
        wheel_python = environment / "Scripts" / "python.exe"
    subprocess.run(
        [str(wheel_python), "-m", "pip", "install", "--no-deps", str(wheel)],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        [
            str(wheel_python),
            "-c",
            "from fw_diag_tool.release_notes import load_release_notes; assert load_release_notes()[0].version == '2.0.0'",
        ],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        [
            str(wheel_python),
            "-c",
            (
                "from importlib.resources import files; "
                "guide = files('fw_diag_tool').joinpath('docs', 'chapters', 'ch01_i2c_pmbus.md'); "
                "assert guide.is_file() and 'I2C' in guide.read_text(encoding='utf-8')"
            ),
        ],
        cwd=tmp_path,
        check=True,
    )


def test_sdist_excludes_site_and_build_test_artifacts(built_artifacts) -> None:
    _, sdist = built_artifacts
    excluded = {
        "site",
        "build",
        "dist",
        "tests",
        "test-results",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "htmlcov",
        ".coverage",
        "coverage.xml",
        "junit.xml",
    }

    with tarfile.open(sdist) as archive:
        members = archive.getnames()

    assert all(not set(Path(member).parts) & excluded for member in members)
    assert any(member.endswith("/README.md") for member in members)
    assert any(member.endswith("/docs/chapters/ch01_i2c_pmbus.md") for member in members)
    assert any(member.endswith("/examples/demo_i2c_diag.py") for member in members)
    assert any(member.endswith("/src/fw_diag_tool/__init__.py") for member in members)
    assert any(member.endswith("/LICENSE") for member in members)
