from __future__ import annotations

import hashlib
import json
import os
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fw_diag_tool import __version__

BUNDLE_SUFFIX = ".fw-diag-bundle.zip"


@dataclass
class BundleManifest:
    """Privacy manifest for a diagnostic bundle."""

    schema_version: str = "1.0"
    tool_version: str = ""
    created_at: str = ""
    includes_raw_capture: bool = False
    files: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "created_at": self.created_at,
            "includes_raw_capture": self.includes_raw_capture,
            "files": self.files,
        }


def create_diagnostic_bundle(
    output_dir: Path | str,
    *,
    reports: list[str],
    configs: list[str] | None = None,
    raw_captures: list[tuple[str, bytes]] | None = None,
) -> Path:
    """Create a privacy-aware diagnostic bundle (.fw-diag-bundle.zip).

    Raw captures are only included when explicitly provided via raw_captures.
    The manifest records whether raw capture data is included.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    bundle_path = output_dir / f"diag_{timestamp}{BUNDLE_SUFFIX}"

    manifest = BundleManifest(
        tool_version=__version__,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        includes_raw_capture=bool(raw_captures),
    )

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, report in enumerate(reports):
            name = f"reports/report_{i}.md"
            zf.writestr(name, report)
            manifest.files.append(
                {"name": name, "sha256": hashlib.sha256(report.encode()).hexdigest()}
            )
        for i, config in enumerate(configs or []):
            name = f"configs/config_{i}.json"
            zf.writestr(name, config)
            manifest.files.append(
                {"name": name, "sha256": hashlib.sha256(config.encode()).hexdigest()}
            )
        for name, content in raw_captures or []:
            arcname = f"raw/{name}"
            zf.writestr(arcname, content)
            manifest.files.append({"name": arcname, "sha256": hashlib.sha256(content).hexdigest()})
        manifest_text = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n"
        zf.writestr("manifest.json", manifest_text)

    if os.name == "posix":
        os.chmod(bundle_path, 0o600)
    return bundle_path


def read_bundle_manifest(bundle_path: Path | str) -> BundleManifest:
    bundle_path = Path(bundle_path)
    with zipfile.ZipFile(bundle_path) as zf:
        manifest_text = zf.read("manifest.json").decode("utf-8")
    data = json.loads(manifest_text)
    return BundleManifest(**data)


__all__ = ["BundleManifest", "create_diagnostic_bundle", "read_bundle_manifest"]
