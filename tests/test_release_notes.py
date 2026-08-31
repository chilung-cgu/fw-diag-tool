import copy
from dataclasses import FrozenInstanceError
from importlib.resources import files

import pytest

from fw_diag_tool import __version__
from fw_diag_tool.release_notes import (
    ReleaseNotesError,
    load_release_notes,
    localized_text,
    parse_release_notes,
)


def valid_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "releases": [
            {
                "version": "1.0.0",
                "date": "2026-08-23",
                "source_ref": "CHANGELOG.md#1.0.0",
                "summary": {"zh-TW": "初版", "en-US": "Initial release"},
                "highlights": [
                    {
                        "id": "i2c-engine",
                        "category": "field_rca",
                        "protocols": ["I2C"],
                        "title": {"zh-TW": "I2C 引擎", "en-US": "I2C engine"},
                        "summary": {"zh-TW": "波形分析", "en-US": "Waveform analysis"},
                        "page": "i2c-diagnosis",
                        "doc": "chapters/ch01_i2c.md",
                    }
                ],
            }
        ],
    }


def _changed(path: tuple[str, ...], value: object) -> dict[str, object]:
    payload = copy.deepcopy(valid_payload())
    target: object = payload
    for key in path[:-1]:
        target = target[key] if isinstance(target, dict) else target[int(key)]
    if isinstance(target, dict):
        target[path[-1]] = value
    else:
        target[int(path[-1])] = value
    return payload


def missing_schema():
    payload = copy.deepcopy(valid_payload())
    del payload["schema_version"]
    return payload


def wrong_schema():
    return _changed(("schema_version",), 2)


def duplicate_version():
    payload = copy.deepcopy(valid_payload())
    payload["releases"].append(copy.deepcopy(payload["releases"][0]))
    return payload


def duplicate_highlight():
    payload = copy.deepcopy(valid_payload())
    release = payload["releases"][0]
    release["highlights"].append(copy.deepcopy(release["highlights"][0]))
    return payload


def duplicate_global_highlight():
    payload = copy.deepcopy(valid_payload())
    second = copy.deepcopy(payload["releases"][0])
    second["version"] = "0.9.0"
    second["source_ref"] = "CHANGELOG.md#0.9.0"
    payload["releases"].append(second)
    return payload


def ascending_versions():
    payload = copy.deepcopy(valid_payload())
    payload["releases"][0]["version"] = "2.0.0"
    return payload


def missing_english():
    return _changed(("releases", "0", "summary"), {"zh-TW": "只有中文"})


def unsafe_doc():
    return _changed(("releases", "0", "highlights", "0", "doc"), "https://evil.test/x.md")


def unsafe_page():
    return _changed(("releases", "0", "highlights", "0", "page"), "../private")


def invalid_category():
    return _changed(("releases", "0", "highlights", "0", "category"), "Unknown")


def overlong_text():
    return _changed(("releases", "0", "summary", "en-US"), "x" * 501)


def test_packaged_history_is_descending_and_starts_at_current_version():
    notes = load_release_notes()
    assert notes[0].version == __version__ == "1.7.0"
    assert [note.version for note in notes] == [
        "1.7.0", "1.6.0", "1.5.0", "1.4.0", "1.3.0", "1.2.0", "1.1.1", "1.1.0", "1.0.0"
    ]


def test_manifest_is_available_as_a_package_resource():
    resource = files("fw_diag_tool.resources").joinpath("release_notes.json")
    assert resource.is_file()
    assert load_release_notes()[0].version == __version__


def test_models_are_frozen():
    note = load_release_notes()[0]
    with pytest.raises(FrozenInstanceError):
        note.version = "9.9.9"


@pytest.mark.parametrize(
    "payload_factory",
    [missing_schema, wrong_schema, duplicate_version, duplicate_highlight, duplicate_global_highlight, ascending_versions,
     missing_english, unsafe_doc, unsafe_page, invalid_category, overlong_text],
)
def test_invalid_manifest_is_rejected(payload_factory):
    with pytest.raises(ReleaseNotesError):
        parse_release_notes(payload_factory())


def test_additional_manifest_constraints():
    for field, value in [
        (("releases", "0", "summary", "en-US"), "<b>bad</b>"),
        (("releases", "0", "summary", "en-US"), "https://external.test"),
        (("releases", "0", "summary", "en-US"), "bad $x$"),
    ]:
        with pytest.raises(ReleaseNotesError):
            parse_release_notes(_changed(field, value))
    many = copy.deepcopy(valid_payload())
    many["releases"][0]["highlights"] = many["releases"][0]["highlights"] * 13
    with pytest.raises(ReleaseNotesError):
        parse_release_notes(many)
    too_many = copy.deepcopy(valid_payload())
    too_many["releases"] = [copy.deepcopy(valid_payload()["releases"][0]) for _ in range(101)]
    with pytest.raises(ReleaseNotesError):
        parse_release_notes(too_many)


def test_localized_text_fallbacks():
    assert localized_text({"zh-TW": "繁中", "en-US": "English"}, "ja-JP") == "繁中"
    assert localized_text({"en-US": "English"}, "ja-JP") == "English"


def test_shipped_highlights_are_bilingual_and_safe():
    for note in load_release_notes():
        assert note.summary.keys() >= {"zh-TW", "en-US"}
        for highlight in note.highlights:
            assert highlight.title.keys() >= {"zh-TW", "en-US"}
            assert highlight.summary.keys() >= {"zh-TW", "en-US"}
            assert highlight.page is None or ".." not in highlight.page
            assert highlight.doc is None or not highlight.doc.startswith("/")


def test_duplicate_json_keys_are_rejected(monkeypatch):
    import fw_diag_tool.release_notes as module

    monkeypatch.setattr(module, "files", lambda package: _Resource("{\"schema_version\":1,\"schema_version\":1}"))
    with pytest.raises(ReleaseNotesError):
        module.load_release_notes()


class _Resource:
    def __init__(self, text: str):
        self.text = text

    def joinpath(self, _name: str):
        return self

    def read_text(self, encoding: str):
        assert encoding == "utf-8"
        return self.text
