"""Validated, immutable release-note manifest models."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from types import MappingProxyType


class ReleaseNotesError(ValueError):
    """Raised when release-note resource data violates its schema."""


@dataclass(frozen=True)
class ReleaseHighlight:
    id: str
    category: str
    protocols: tuple[str, ...]
    title: Mapping[str, str]
    summary: Mapping[str, str]
    page: str | None
    doc: str | None


@dataclass(frozen=True)
class ReleaseNote:
    version: str
    date: str
    source_ref: str
    summary: Mapping[str, str]
    highlights: tuple[ReleaseHighlight, ...]


_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SOURCE_RE = re.compile(r"^CHANGELOG\.md#([0-9]+\.[0-9]+\.[0-9]+)$")
_DOC_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[^\\]+\.md$")
_PROTOCOLS = {"I2C", "SPI", "UART", "PCIe", "MCTP"}
_CATEGORIES = {"field_rca", "evidence_replay", "teaching", "team", "quality", "ux"}
_HTML_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"(?:https?|ftp|file|javascript):", re.IGNORECASE)


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ReleaseNotesError(f"{field} must be an object")
    return value


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 500:
        raise ReleaseNotesError(f"{field} must be 1-500 characters")
    if _HTML_RE.search(value) or _URL_RE.search(value) or ("$" in value):
        raise ReleaseNotesError(f"{field} contains unsafe text")
    return value


def _require_text_map(value: object, field: str) -> Mapping[str, str]:
    mapping = _require_mapping(value, field)
    if set(mapping) != {"zh-TW", "en-US"}:
        raise ReleaseNotesError(f"{field} must contain zh-TW and en-US")
    result: dict[str, str] = {}
    for locale in ("zh-TW", "en-US"):
        result[locale] = _require_text(mapping[locale], f"{field}.{locale}")
    return MappingProxyType(result)


def _parse_version(value: object, field: str = "version") -> tuple[int, int, int]:
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise ReleaseNotesError(f"{field} must be semantic numeric version")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseNotesError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_highlight(value: object, index: int) -> ReleaseHighlight:
    item = _require_mapping(value, f"highlights[{index}]")
    required = {"id", "category", "protocols", "title", "summary", "page", "doc"}
    if set(item) != required:
        raise ReleaseNotesError(f"highlights[{index}] fields mismatch")
    ident = _require_text(item["id"], f"highlights[{index}].id")
    category = item["category"]
    if not isinstance(category, str) or category not in _CATEGORIES:
        raise ReleaseNotesError(f"invalid category: {category!r}")
    protocols = item["protocols"]
    if not isinstance(protocols, list) or any(p not in _PROTOCOLS for p in protocols) or len(set(protocols)) != len(protocols):
        raise ReleaseNotesError("protocols must be unique allowed entries")
    page = item["page"]
    if page is not None and (not isinstance(page, str) or not _SLUG_RE.fullmatch(page)):
        raise ReleaseNotesError("invalid page slug")
    doc = item["doc"]
    if doc is not None and (not isinstance(doc, str) or not _DOC_RE.fullmatch(doc) or ".." in doc.split("/") or doc.startswith("/")):
        raise ReleaseNotesError("invalid doc path")
    return ReleaseHighlight(ident, category, tuple(protocols), _require_text_map(item["title"], "title"), _require_text_map(item["summary"], "summary"), page, doc)


def parse_release_notes(payload: Mapping[str, object]) -> tuple[ReleaseNote, ...]:
    root = _require_mapping(payload, "payload")
    if set(root) != {"schema_version", "releases"} or root.get("schema_version") != 1:
        raise ReleaseNotesError("unsupported or missing schema_version")
    releases = root["releases"]
    if not isinstance(releases, list) or not releases or len(releases) > 100:
        raise ReleaseNotesError("releases must contain 1-100 entries")
    notes: list[ReleaseNote] = []
    seen_versions: set[str] = set()
    seen_highlight_ids: set[str] = set()
    previous: tuple[int, int, int] | None = None
    for idx, value in enumerate(releases):
        item = _require_mapping(value, f"releases[{idx}]")
        required = {"version", "date", "source_ref", "summary", "highlights"}
        if set(item) != required:
            raise ReleaseNotesError(f"releases[{idx}] fields mismatch")
        version = item["version"]
        parsed = _parse_version(version, f"releases[{idx}].version")
        if not isinstance(version, str) or version in seen_versions or (previous is not None and parsed >= previous):
            raise ReleaseNotesError("versions must be unique and descending")
        seen_versions.add(version)
        previous = parsed
        datestr = item["date"]
        if not isinstance(datestr, str) or not _DATE_RE.fullmatch(datestr):
            raise ReleaseNotesError("invalid date")
        try:
            date.fromisoformat(datestr)
        except ValueError as exc:
            raise ReleaseNotesError("invalid date") from exc
        source_ref = item["source_ref"]
        if not isinstance(source_ref, str) or _SOURCE_RE.fullmatch(source_ref) is None or source_ref.rsplit("#", 1)[1] != version:
            raise ReleaseNotesError("invalid source_ref")
        highlights_value = item["highlights"]
        if not isinstance(highlights_value, list) or not highlights_value or len(highlights_value) > 12:
            raise ReleaseNotesError("highlights must contain 1-12 entries")
        highlights = tuple(_parse_highlight(v, i) for i, v in enumerate(highlights_value))
        ids = [h.id for h in highlights]
        if len(set(ids)) != len(ids):
            raise ReleaseNotesError("duplicate highlight id")
        if seen_highlight_ids.intersection(ids):
            raise ReleaseNotesError("duplicate highlight id")
        seen_highlight_ids.update(ids)
        notes.append(ReleaseNote(version, datestr, source_ref, _require_text_map(item["summary"], "summary"), highlights))
    return tuple(notes)


def load_release_notes() -> tuple[ReleaseNote, ...]:
    try:
        text = files("fw_diag_tool.resources").joinpath("release_notes.json").read_text(encoding="utf-8")
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        return parse_release_notes(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ReleaseNotesError) as exc:
        if isinstance(exc, ReleaseNotesError) and str(exc).startswith("Unable to load"):
            raise
        raise ReleaseNotesError(f"Unable to load release notes: {exc}") from exc


def localized_text(mapping: Mapping[str, str], locale: str) -> str:
    for key in (locale, "zh-TW", "en-US"):
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return next(iter(mapping.values()))
