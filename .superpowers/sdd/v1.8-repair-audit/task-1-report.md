# Task 1 — Registered Route Registry

## Status

Implemented and verified. Commit: pending.

## Changes

- Added `fw_diag_tool.gui.route_registry` with registration and slug-resolution helpers.
- `gui/app.py` now registers every `st.Page` from the navigation structure before creating `st.navigation`.
- Dashboard quick links resolve the slug to the registered `st.Page`; unknown slugs retain the caption fallback.
- Added a runtime-context regression test proving a string slug is rejected while the registered page object succeeds.
- `PAGE_INDEX` and all existing page callables remain unchanged.

## Verification

- RED observed before implementation: test collection failed because `route_registry` did not exist.
- `uv run pytest -q tests/test_dashboard_enhanced.py`: 10 passed.
- `uv run ruff check src/fw_diag_tool/gui/app.py src/fw_diag_tool/gui/pages/dashboard_ui.py src/fw_diag_tool/gui/route_registry.py tests/test_dashboard_enhanced.py`: passed.
- `uv run mypy src/fw_diag_tool/gui/app.py src/fw_diag_tool/gui/pages/dashboard_ui.py src/fw_diag_tool/gui/route_registry.py`: passed.

## Concerns

The registry is populated when `gui.app` builds the navigation. Dashboard-only imports without app startup continue to use the existing caption fallback for unresolved slugs.
