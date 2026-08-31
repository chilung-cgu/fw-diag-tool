# Final adversarial review fix report

## Scope

- Normalized every non-null `doc` value in `src/fw_diag_tool/resources/release_notes.json` to a path relative to `docs/`.
- Corrected the historical `1.1.0` document name to the shipped `chapters/ch01_i2c_pmbus.md`.
- Added a regression test proving shipped documentation paths use `chapters/` and resolve to files under `docs/`.
- Parser contract and unrelated documentation files were not changed.

## Verification

- RED: the new regression test failed on the pre-fix `docs/chapters/...` value.
- GREEN: `uv run pytest tests/test_release_notes.py -q` — 19 passed.
- `uv run pytest tests/test_docs.py -q -k 'not local_markdown_links_resolve'` — 8 passed, 1 deselected.
- `uv run pytest tests/test_packaging.py::test_release_manifest_and_documentation_contract -q` — 1 passed.
- `uv run ruff check .` — passed.
- `git diff --check` — passed.

## Environment limitation

`mkdocs build --strict` could not run because `mkdocs` is not installed in this environment. The existing `test_local_markdown_links_resolve` also reports a pre-existing false positive from `docs/superpowers/plans/2026-08-31-release-notes-dashboard.md` (`[^"']+` parsed as a link target); that file was outside this fix scope.
