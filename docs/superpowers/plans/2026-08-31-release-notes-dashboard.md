# Release Notes Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a package-safe, bilingual, cumulative release-notes manifest and Dashboard presentation that accurately reports v1.7.0 and prevents future version/document drift.

**Architecture:** A validated JSON resource is the single structured source for GUI release notes. A small typed loader validates schema, ordering, bilingual fields, safe local routes, and resource loading; the Dashboard renders the loader output and degrades visibly on malformed data. Human-readable CHANGELOG/README remain public documents and are tied to the manifest by release-contract tests.

**Tech Stack:** Python 3.10+, stdlib `dataclasses`/`json`/`importlib.resources`, Streamlit, pytest, uv, MkDocs.

**Spec:** `docs/superpowers/specs/2026-08-31-release-notes-dashboard-design.md`

## Global Constraints

- Python >= 3.10 compatibility; all commands use `uv run`.
- Traditional Chinese (zh-TW) UI and English (en-US) translations are both required.
- No runtime network calls, external URLs, arbitrary HTML, or user tracking.
- `releases` is descending by stable semantic version; it contains at most 100 entries, and versions/highlight IDs are unique.
- Each bilingual field contains both `zh-TW` and `en-US`; text is 1–500 characters and rejects HTML, external URL schemes, and standalone LaTeX delimiters; categories are limited to `field_rca`, `evidence_replay`, `teaching`, `team`, `quality`, `ux`.
- Page routes are safe lower-case slugs and are filtered against `PAGE_INDEX`; document paths are repository-relative and reject absolute/`..` paths.
- Dataclasses are frozen; malformed resource data raises `ReleaseNotesError` and GUI shows a localized warning instead of silently using stale text.
- `pyproject.toml`, `uv.lock`, manifest head, and CHANGELOG head must agree; run `uv lock --check` before any future release tag.
- Do not rewrite or move the existing `v1.7.0` tag; do not push or merge from this plan.
- New production behavior follows TDD: write and observe a failing test before implementation.
- Before each commit, run the task-scoped tests plus `ruff`/`mypy` applicable to changed Python files.

## Execution Handoff Gate

- Stop after this plan is committed; do not create the SDD ledger, write the first RED test, dispatch an implementer, or edit production code until the user has switched the execution model.
- After the user resumes, invoke `superpowers:subagent-driven-development`, run `scripts/sdd-workspace docs/superpowers/plans/2026-08-31-release-notes-dashboard.md`, create `.superpowers/sdd/release-notes-dashboard/progress.md`, and only then begin Task 1 Step 1.

## File Map

- `src/fw_diag_tool/resources/release_notes.json`: versioned structured release data, v1.0.0–v1.7.0, packaged as a resource.
- `src/fw_diag_tool/release_notes.py`: immutable models, schema validation, semantic-version ordering, and resource loader.
- `src/fw_diag_tool/gui/pages/dashboard_ui.py`: thin localized release-note rendering and explicit unavailable fallback.
- `src/fw_diag_tool/i18n/domains/gui.py`: bilingual labels/status/CTA strings without embedded historical version numbers.
- `CHANGELOG.md`: human-readable v1.7.0 section at the top.
- `README.md`: current version and v1.7.0 highlight references.
- `tests/test_release_notes.py`: loader, schema, resource, release-contract, and packaging-facing tests.
- `tests/test_dashboard_health_enhanced.py`: Dashboard release-note rendering and malformed-resource behavior.
- `tests/test_packaging.py`: resource inclusion/load assertion for built wheel.
- `.superpowers/sdd/release-notes-dashboard/progress.md`: append-only execution ledger created by `scripts/sdd-workspace` (git-ignored SDD artifact; never commit it).

### Task 1: Release Notes Models and Validated Resource

**Files:**
- Create: `tests/test_release_notes.py`
- Create: `src/fw_diag_tool/release_notes.py`
- Create: `src/fw_diag_tool/resources/release_notes.json`

**Interfaces:**
- Produces `ReleaseHighlight` frozen dataclass with `id: str`, `category: str`, `protocols: tuple[str, ...]`, `title: Mapping[str, str]`, `summary: Mapping[str, str]`, `page: str | None`, `doc: str | None`.
- Produces `ReleaseNote` frozen dataclass with `version: str`, `date: str`, `source_ref: str`, `summary: Mapping[str, str]`, `highlights: tuple[ReleaseHighlight, ...]`.
- Produces `ReleaseNotesError(ValueError)`.
- Produces `parse_release_notes(payload: Mapping[str, object]) -> tuple[ReleaseNote, ...]` and `load_release_notes() -> tuple[ReleaseNote, ...]`.
- Produces `localized_text(mapping: Mapping[str, str], locale: str) -> str`, with fallback order `locale`, `zh-TW`, then `en-US`.

- [ ] **Step 1: Write the failing loader and resource tests**

  Add tests with these concrete assertions and a local `valid_payload()` factory that returns a complete one-release mapping. Build each invalid case by copying that mapping and changing exactly one field, so each parameterized failure tests one contract rule rather than fixture setup:

  ```python
  def test_packaged_history_is_descending_and_starts_at_current_version():
      notes = load_release_notes()
      assert notes[0].version == __version__ == "1.7.0"
      assert [note.version for note in notes] == [
          "1.7.0",
          "1.6.0",
          "1.5.0",
          "1.4.0",
          "1.3.0",
          "1.2.0",
          "1.1.1",
          "1.1.0",
          "1.0.0",
      ]


  def test_models_are_frozen():
      note = load_release_notes()[0]
      with pytest.raises(FrozenInstanceError):
          note.version = "9.9.9"


  @pytest.mark.parametrize(
      "payload_factory",
      [
          missing_schema,
          wrong_schema,
          duplicate_version,
          duplicate_highlight,
          ascending_versions,
          missing_english,
          unsafe_doc,
          unsafe_page,
          invalid_category,
          overlong_text,
      ],
  )
  def test_invalid_manifest_is_rejected(payload_factory):
      with pytest.raises(ReleaseNotesError):
          parse_release_notes(payload_factory())
  ```

  Define `missing_schema()`, `wrong_schema()`, `duplicate_version()`, `duplicate_highlight()`, `ascending_versions()`, `missing_english()`, `unsafe_doc()`, `unsafe_page()`, `invalid_category()`, and `overlong_text()` as small factories using `copy.deepcopy(valid_payload())`; add direct cases for an HTML/external-URL summary, more than 12 highlights, more than 100 releases, and duplicate JSON keys passed through the resource loader; assert all shipped highlights have both locales and safe fields.
  Also assert `localized_text({"zh-TW": "繁中", "en-US": "English"}, "ja-JP") == "繁中"`, and that a mapping with only `en-US` falls back to its first available value without raising `KeyError`.

- [ ] **Step 2: Run the new tests and verify the expected RED state**

  Run:

  ```bash
  uv run pytest tests/test_release_notes.py -q
  ```

  Expected: collection/import failure because `fw_diag_tool.release_notes` and the packaged JSON do not yet exist. Fix only test syntax/fixture errors if the failure is unrelated; do not add production code before the missing-module failure is observed.

- [ ] **Step 3: Implement immutable models and strict parser**

  Implement the exact public interfaces above. Validate `schema_version == 1`, top-level `releases` is a non-empty list with at most 100 entries, dates with both `^\\d{4}-\\d{2}-\\d{2}$` and `date.fromisoformat()`, stable versions matching `^[0-9]+\\.[0-9]+\\.[0-9]+$`, descending order using numeric `(major, minor, patch)` tuples, unique versions/highlight IDs, required bilingual non-empty strings of 1–500 characters, and reject HTML tags, external URL schemes, or standalone LaTeX delimiters in text. Validate allowed categories, a protocols list whose entries are unique members of `I2C`, `SPI`, `UART`, `PCIe`, or `MCTP` (the list may be empty for cross-cutting highlights), safe page slugs with `^[a-z0-9]+(?:-[a-z0-9]+)*$`, `source_ref` as a relative `CHANGELOG.md#x.y.z` reference, and doc paths relative to `docs/` that end in `.md` and contain no absolute path, `..`, or backslash component. Read the resource with `importlib.resources.files(...).joinpath(...).read_text(encoding="utf-8")`, reject duplicate JSON object keys, convert JSON/IO/schema failures to `ReleaseNotesError`, copy mappings into immutable `MappingProxyType` values, and copy lists into tuples before constructing frozen dataclasses.

  Keep the implementation boundary explicit: `_require_mapping()` and `_require_text_map()` reject wrong runtime types; `_parse_version()` returns a numeric `(major, minor, patch)` tuple; `_reject_duplicate_keys()` is passed as `object_pairs_hook` to `json.loads`; and `localized_text()` never indexes an unverified locale directly. `load_release_notes()` catches `OSError`, `UnicodeError`, `json.JSONDecodeError`, duplicate-key errors, and `ReleaseNotesError`, re-raising one contextual `ReleaseNotesError` without silently returning an empty tuple.

- [ ] **Step 4: Add v1.0.0–v1.7.0 resource data from verified release history**

  Populate every release with a date, source reference, bilingual summary, and at least one concrete highlight. v1.7.0 must cover PCIe/MCTP topology, SPI chip DB, UART symptom DB, interactive stats charts, and integration/coverage work; v1.6.0 must cover protocol statistics, CSV export, and unified report; v1.5.0 must cover CLI diff/correlation/session/i18n/dashboard work. Earlier entries must match the corresponding existing CHANGELOG headings and may summarize the already published feature sections without inventing new features. Use only local commit/CHANGELOG evidence.

- [ ] **Step 5: Run loader tests and static checks to verify GREEN**

  Run:

  ```bash
  uv run pytest tests/test_release_notes.py -q
  uv run ruff check src/fw_diag_tool/release_notes.py tests/test_release_notes.py
  uv run mypy src/fw_diag_tool/release_notes.py
  ```

  Expected: all loader/resource tests pass with exit code 0 and no lint/type errors.

- [ ] **Step 6: Commit the self-contained loader deliverable**

  ```bash
  git add src/fw_diag_tool/release_notes.py src/fw_diag_tool/resources/release_notes.json tests/test_release_notes.py
  git commit -m "feat(release): add validated cumulative release notes manifest"
  ```

### Task 2: Dashboard Cumulative Release-Notes UX and i18n

**Files:**
- Modify: `src/fw_diag_tool/gui/pages/dashboard_ui.py`
- Modify: `src/fw_diag_tool/i18n/domains/gui.py`
- Modify: `tests/test_dashboard_health_enhanced.py`
- Test: `tests/test_release_notes.py` (loader remains the fixture/API source)

**Interfaces:**
- Consumes `load_release_notes()`, `ReleaseNote`, `ReleaseNotesError`, and `PAGE_INDEX`.
- Produces `_render_release_notes() -> None` and `_render_release_card(note: ReleaseNote, locale: str) -> None`; `render()` calls `_render_release_notes()` exactly once in place of the hard-coded v1.5.0 block.

- [ ] **Step 1: Write failing Dashboard behavior tests**

  Add focused tests around `_render_release_notes()` using the repository's existing Streamlit AppTest style (or a `MagicMock` capture only where AppTest cannot inspect a container): assert the default view contains v1.7.0, v1.6.0, and v1.5.0 cards, the title/expander labels contain no hard-coded historical version, the history selectbox contains every manifest version, and switching the global registry between `zh-TW` and `en-US` changes the title and CTA labels. Add a malformed-loader test that monkeypatches `dashboard_ui.load_release_notes` to raise `ReleaseNotesError`, captures `st.warning`, and asserts the helper returns without propagating the exception.

- [ ] **Step 2: Run the focused Dashboard tests to verify RED**

  ```bash
  uv run pytest tests/test_dashboard_health_enhanced.py -k release_notes -q
  ```

  Expected: FAIL because `_render_release_notes()` is absent and existing i18n still contains the stale v1.5.0 text.

- [ ] **Step 3: Add bilingual i18n keys without historical versions**

  Add `whats_new_title`, `whats_new_current_version`, `whats_new_history_label`, `whats_new_history_select`, `whats_new_category`, `whats_new_protocols`, `whats_new_open_page`, `whats_new_read_doc`, `whats_new_unavailable`, and category labels for all six allowed categories, each with `zh-TW` and `en-US`. The title must be version-neutral; format only runtime values such as `{version}` and `{date}`.

- [ ] **Step 4: Implement the thin Dashboard renderer**

  Import the typed loader and `PAGE_INDEX`; snapshot `get_global_registry().get_locale()` once at the start of the helper and use a pure `localized_text(mapping, locale)` fallback chain for manifest content. Render the version-neutral title, current installed version caption, latest `notes[:3]` in `st.columns`, and one non-nested `st.expander` containing a selectbox over all versions and the selected note's details. Resolve a manifest `page` only by exact lookup in `PAGE_INDEX`, pass its existing registered URL to `_render_quick_link`, and show a validated `doc` only as a plain `st.caption` path when no page CTA is available; do not create nested expanders, interpolate manifest content into raw HTML, or build Markdown URLs from manifest strings. Catch only `ReleaseNotesError`, call localized `st.warning`, and return. Warn when `__version__` is absent from otherwise valid history. Remove the old hard-coded v1.5.0 Markdown block and change `_render_quick_link`'s fallback to plain caption text rather than an interpolated Markdown URL.

  Keep the helper's control flow equivalent to:

  ```python
  def _render_release_notes() -> None:
      locale = get_global_registry().get_locale()
      try:
          notes = load_release_notes()
      except ReleaseNotesError:
          st.warning(t("whats_new_unavailable", domain="gui"))
          return
      st.subheader(t("whats_new_title", domain="gui"))
      st.caption(t("whats_new_current_version", domain="gui", version=__version__))
      for note in notes[:3]:
          _render_release_card(note, locale)
      with st.expander(t("whats_new_history_label", domain="gui")):
          selected = st.selectbox(
              t("whats_new_history_select", domain="gui"),
              [note.version for note in notes],
          )
          _render_release_card(next(note for note in notes if note.version == selected), locale)
  ```

  Implement `_render_release_card(note: ReleaseNote, locale: str) -> None` as the single card/detail renderer; it must use `st.write`/`st.caption` for manifest text, emit at most one page CTA or doc caption per highlight, and never call `st.expander`.

- [ ] **Step 5: Run Dashboard/AppTest and static checks to verify GREEN**

  ```bash
  uv run pytest tests/test_dashboard_health_enhanced.py tests/test_dashboard_enhanced.py -q
  uv run ruff check src/fw_diag_tool/gui/pages/dashboard_ui.py src/fw_diag_tool/i18n/domains/gui.py tests/test_dashboard_health_enhanced.py
  uv run mypy src/fw_diag_tool/gui/pages/dashboard_ui.py
  ```

- [ ] **Step 6: Commit the Dashboard deliverable**

  ```bash
  git add src/fw_diag_tool/gui/pages/dashboard_ui.py src/fw_diag_tool/i18n/domains/gui.py tests/test_dashboard_health_enhanced.py
  git commit -m "feat(gui): show cumulative localized release history"
  ```

### Task 3: v1.7.0 Public Documents and Release Consistency Contract

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `tests/test_release_notes.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Consumes `load_release_notes()` and project metadata.
- Produces tests that fail if the package version, manifest head, CHANGELOG head, README current-version marker, or manifest-to-heading version set diverge.

- [ ] **Step 1: Write failing release-contract tests**

  Replace the top-level `import tomllib` in `tests/test_packaging.py` with a Python 3.10-compatible shim (`try: import tomllib` / `except ModuleNotFoundError: import tomli as tomllib`). Then add tests that parse the `version = "..."` project declaration with a small regular expression and assert: manifest first version equals project version; the `fw-diag-tool` package entry in `uv.lock` equals project version; first `CHANGELOG.md` heading equals project version; every manifest version has a matching unique `## [x.y.z]` heading; each `source_ref` version matches its manifest entry; README's explicit current-version marker and first highlights heading contain `v{project_version}` without treating historical sections as current; and the wheel archive contains `fw_diag_tool/resources/release_notes.json`. Add a test that loads the manifest through `importlib.resources` from the installed package path, not the source path.

  Use anchored expressions such as `^version\\s*=\\s*["']([^"']+)["']` within the `[project]` block and `^##\\s+\\[([^]]+)\\]` for CHANGELOG headings; do not use a repository-wide `"v1.7.0" in readme` assertion. Parse the lock entry with `name = "fw-diag-tool"` followed immediately by its `version`, and run the isolated subprocess with `cwd=tmp_path` so the source checkout cannot satisfy the import accidentally.

- [ ] **Step 2: Run contract tests to verify RED**

  ```bash
  uv run pytest tests/test_release_notes.py tests/test_packaging.py -k "contract or release or manifest" -q
  ```

  Expected: FAIL because CHANGELOG/README are stale and the release resource assertion is not yet present.

- [ ] **Step 3: Add the verified v1.7.0 CHANGELOG section**

  Insert `## [1.7.0] - 2026-08-30` before v1.6.0. Describe only features evidenced by commit `9bbc2c4` and existing tests: PCIe/MCTP topology, SPI Flash chip DB, UART symptom DB, Plotly stats charts, and integration/session/reporter coverage. Do not state a test count as a timeless product capability; if mentioning the local run, label it as verification evidence in the commit-era section.

- [ ] **Step 4: Update README's current version and highlights**

  Change the introductory current-version marker and the immediately following highlights heading/content to v1.7.0, retaining existing useful links and tables. Do not rewrite unrelated historical feature descriptions in this task.

- [ ] **Step 5: Extend packaging assertions and run GREEN checks**

  Assert the JSON resource exists in the wheel and can be parsed by `load_release_notes()` from an isolated no-source-checkout install. Run:

  ```bash
  uv run pytest tests/test_release_notes.py tests/test_packaging.py -q
  uv run ruff check tests/test_release_notes.py tests/test_packaging.py
  uv lock --check
  ```

- [ ] **Step 6: Commit the release-contract deliverable**

  ```bash
  git add CHANGELOG.md README.md tests/test_release_notes.py tests/test_packaging.py
  git commit -m "docs(release): record v1.7.0 and enforce metadata parity"
  ```

### Task 4: Documentation Navigation and Resource Verification

**Files:**
- Modify: `docs/chapters/ch16_dashboard.md` (document cumulative release-notes behavior and evidence boundary)
- Modify: `tests/test_docs.py` (add the focused link/heading assertion)
- Inspect: `mkdocs.yml` (confirm the existing `chapters/ch16_dashboard.md` Dashboard nav entry; no change is expected)

**Interfaces:**
- Consumes the actual Dashboard behavior and manifest contract from Tasks 1–3.
- Produces a source/package documentation trail explaining latest-three cards, full history, and unavailable fallback.

- [ ] **Step 1: Write a failing docs assertion for the new behavior**

  Add a focused assertion that `docs/chapters/ch16_dashboard.md` contains the release-history section, `v1.7.0`, and the exact concepts "累積歷史" / "cumulative history" and "證據邊界" / "evidence boundary"; parse `mkdocs.yml` and assert `chapters/ch16_dashboard.md` is present in the existing nav entry.

- [ ] **Step 2: Run the docs test to verify RED**

  ```bash
  uv run pytest tests/test_docs.py -k dashboard -q
  ```

- [ ] **Step 3: Update the dashboard chapter with case-first instructions**

  Explain what a user sees, how to expand full history, how to switch locale, what a page CTA and a document-path caption mean, and why the manifest is local release metadata rather than a live update service. State that the three-card view is a convenience summary, not evidence that a target board received an update. Keep Markdown lists/tables/code blocks separated by blank lines per MkDocs rules and link only to existing relative chapter paths.

- [ ] **Step 4: Run docs and packaging verification**

  ```bash
  uv run pytest tests/test_docs.py tests/test_packaging.py -q
  uv run mkdocs build --strict
  git diff --check
  ```

- [ ] **Step 5: Commit the documentation deliverable**

  ```bash
  git add docs/chapters/ch16_dashboard.md tests/test_docs.py
  git commit -m "docs(gui): explain cumulative release history"
  ```

### Task 5: Full Verification and Adversarial Release Review

**Files:**
- No planned production edits; only test fixes if a prior task's contract is demonstrably incomplete.

**Interfaces:**
- Consumes all prior task outputs and the append-only SDD ledger.
- Produces fresh local evidence and a review package; no push/merge/tag mutation.

- [ ] **Step 1: Run the focused release/UI gate**

  ```bash
  uv run --locked --extra pdf pytest tests/test_release_notes.py tests/test_dashboard_health_enhanced.py tests/test_dashboard_enhanced.py tests/test_packaging.py tests/test_docs.py -q
  ```

- [ ] **Step 2: Run static and docs gates**

  ```bash
  uv run ruff check src/fw_diag_tool/release_notes.py src/fw_diag_tool/gui/pages/dashboard_ui.py src/fw_diag_tool/i18n/domains/gui.py tests/test_release_notes.py tests/test_dashboard_health_enhanced.py tests/test_packaging.py
  uv run mypy src/fw_diag_tool/release_notes.py src/fw_diag_tool/gui/pages/dashboard_ui.py
  uv run mkdocs build --strict
  uv lock --check
  git diff --check
  ```

- [ ] **Step 3: Run the complete suite and record exact output**

  ```bash
  uv run --locked --extra pdf pytest -q
  ```

  Record exit code, passed/failed count, and elapsed time in the ledger; do not copy a prior baseline claim.

- [ ] **Step 4: Dispatch final adversarial code review**

  Review the complete branch for schema bypasses, malformed-resource behavior, unsafe routes, stale v1.5.0 strings, wheel loading, i18n completeness, Streamlit nested-expander/API compatibility, and docs consistency. Include all deferred P0/P1 findings from the prior v1.7 audit as explicitly out of scope.

- [ ] **Step 5: Verify final Git state and report boundaries**

  ```bash
  git status --short --branch
  git log --oneline --decorate -8
  git diff main...HEAD --stat
  ```

  Report branch/commits and fresh local gates. Do not claim release/tag/remote readiness until a separate authorized push and remote CI verification occurs.
