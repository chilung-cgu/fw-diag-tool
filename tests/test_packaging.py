from __future__ import annotations

import shutil
import subprocess
import tarfile
import venv
from pathlib import Path
from zipfile import ZipFile

import pytest
import tomllib

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
