# Phase 2: Entity-Manager & Device Tree Bridge via BoardProfile

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish BoardProfile as the single source of truth across the firmware development toolchain, enabling bidirectional-compatible generation of OpenBMC Entity-Manager (EM) JSON configurations and Linux Device Tree (.dts) fragments without duplicate schema declarations.

**Architecture:** Create `EMBridge` in `src/fw_diag_tool/em/bridge.py` that translates `BoardProfile` data structures into `EMBoardConfig` (for Entity-Manager JSON generation via `EMBuilder`) and `DeviceTreeGenerator` node entries (for kernel DTS generation). Expose this bridge via the `fw-diag em generate` CLI command in `src/fw_diag_tool/cli.py` and integrate into documentation.

**Tech Stack:** Python 3.10+, dataclasses, Pydantic (BoardProfile), DeviceTreeGenerator, EMBuilder, Typer, pytest

**Spec:** This plan is self-contained. The design conforms to OpenBMC Entity-Manager schemas and Linux kernel device tree bindings for I2C and multiplexers.

## Global Constraints

- Python >= 3.10 (use `from __future__ import annotations`)
- Zero-LaTeX rule: Do not use inline LaTeX or LaTeX syntax. Use plain Unicode symbols (`->`, `°C`, `Ω`, `µs`, `V`, `W`).
- Maintain frozen dataclasses, classmethod helpers, and explicit type annotations.
- No new external dependencies; reuse existing `BoardProfile`, `EMBuilder`, `DeviceTreeGenerator`.
- CLI commands must use Typer and output structured tables / messages with Rich.
- All tests must pass: run `uv run pytest tests/test_em_bridge.py tests/test_cli_log_em.py -v`.
- Linting and static typing: run `uv run ruff check .` and `uv run mypy src/fw_diag_tool`.

---

### Task 1: Core Bridge Module (`EMBridge`)

**Files:**
- Create: `src/fw_diag_tool/em/bridge.py`
- Modify: `src/fw_diag_tool/em/__init__.py`
- Test: `tests/test_em_bridge.py`

**Interfaces:**
- Consumes: `BoardProfile`, `I2CBusInfo`, `I2CDeviceInfo`, `MuxInfo` from `fw_diag_tool.board_profile`
- Consumes: `EMBoardConfig`, `EMDeviceEntry`, `EMDeviceTemplate`, `DEVICE_TEMPLATES`, `get_template` from `fw_diag_tool.em`
- Consumes: `DeviceTreeGenerator` from `fw_diag_tool.codegen.dts_gen`
- Produces: `EMBridge` class exporting:
  - `from_board_profile(cls, profile: BoardProfile, bus_num: int | None = None) -> EMBoardConfig`
  - `to_em_json(cls, profile: BoardProfile, bus_num: int | None = None, indent: int = 2) -> str`
  - `to_dts(cls, profile: BoardProfile, bus_num: int | None = None) -> str`

- [x] **Step 1: Write unit tests for `EMBridge`** (`tests/test_em_bridge.py`)
- [x] **Step 2: Implement `EMBridge`** (`src/fw_diag_tool/em/bridge.py`)
- [x] **Step 3: Export `EMBridge` from package root** (`src/fw_diag_tool/em/__init__.py`)
- [x] **Step 4: Verify test suite and types**

---

### Task 2: CLI Integration for `fw-diag em generate`

**Files:**
- Modify: `src/fw_diag_tool/cli.py`
- Test: `tests/test_cli_log_em.py`

**Command Specification:**
```bash
fw-diag em generate <PROFILE_PATH> [--bus <BUS_NUM>] [--format json|dts|both] [--out <OUTPUT_FILE>]
```

- [x] **Step 1: Implement `generate_em_or_dts` CLI command** (`src/fw_diag_tool/cli.py`)
- [x] **Step 2: Add CLI test cases in `tests/test_cli_log_em.py`**
- [x] **Step 3: Verify CLI behavior with tests**

---

## Verification & Acceptance Checklist

1. **Unit & Integration Tests:**
   ```bash
   uv run pytest tests/test_em_bridge.py tests/test_cli_log_em.py -v
   ```
2. **CLI Verification:**
   ```bash
   uv run fw-diag em generate examples/sample_board_profile.yaml -f json
   uv run fw-diag em generate examples/sample_board_profile.yaml -f dts
   uv run fw-diag em generate examples/sample_board_profile.yaml -f both
   ```
3. **Code Quality:**
   ```bash
   uv run ruff check src/fw_diag_tool/em/bridge.py src/fw_diag_tool/cli.py
   uv run mypy src/fw_diag_tool/em/bridge.py src/fw_diag_tool/cli.py
   ```

---

## Completion Record (2026-09-02)

- [x] Core bridge and CLI implementation: `d9ca8da`, `a458ab3`, `64e061d`, and `dd34349` cover BoardProfile translation, explicit MUX bus identity, direct/multi-MUX DTS rendering, exports, and CLI integration.
- [x] Fresh final evidence: `uv run pytest` completed with 1518 passed; `uv run ruff check .`, `uv run mypy src/`, and `uv run mkdocs build --strict` all exited zero.
- [x] Artifact smoke evidence: `fw-diag em generate` produced JSON parseable by `json.tool` and DTS containing `&i2c1`; both formats were generated separately without concatenation.
- Evidence boundary: the generated DTS/JSON checks are local static artifacts; physical I2C adapter numbering and target-board runtime behavior remain environment-dependent.
