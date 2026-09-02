# Adversarial Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the five adversarial-review findings without silent fallback, shell/source injection, topology loss, false-positive diagnostics, stale GUI artifacts, or machine-unreadable CLI output.

**Architecture:** Keep `BoardProfile` as the topology source of truth, but make downstream Linux I2C bus identity explicit instead of inventing it. Split D-Bus mock generation into validated input normalization, deterministic object mapping, and a real `dbus-next` service; keep the Bash choice only as a safely quoted launcher for that service. Preserve existing public entry points where practical, and lock every repaired contract with a regression test written before production changes.

**Tech Stack:** Python 3.10+, Pydantic 2, dbus-next, Typer, Rich, Streamlit, pytest, Ruff, mypy, MkDocs

**Spec:** `docs/superpowers/plans/2026-09-02-phase1-log-patterns-expansion.md`, `docs/superpowers/plans/2026-09-02-phase2-em-dts-bridge.md`, and `docs/superpowers/plans/2026-09-02-phase3-em-dbus-mock-generator.md`, amended by the verified adversarial-review findings against commits `d9ca8da..dd34349`.

## Global Constraints

- Work only on branch `codex/fix-adversarial-review`; do not push, merge, amend, or force-update history.
- Follow strict red-green-refactor TDD for every behavior change: write the named failing test, run only that test and observe the expected failure, write the smallest production change, then rerun the focused test.
- A test that passes before the production change does not prove the bug and must be corrected before implementation begins.
- Python remains compatible with Python 3.10 and uses `from __future__ import annotations` where the surrounding module already does.
- Do not guess physical bus numbers. Entity-Manager output for a downstream MUX device requires an explicit `downstream_bus_num`; missing mapping is an actionable `ValueError`.
- Generated source must never interpolate unescaped board or device text into Bash or Python syntax. Dynamic values enter generated Python only through Python literals produced by `repr()` or `pprint.pformat()`.
- Generated mock scripts must own `xyz.openbmc_project.FWDiagMock`, export every advertised object, and fail non-zero when the bus connection, name acquisition, or export fails. Never suppress these failures with `|| true`.
- `--format json` stdout is raw JSON parseable by `json.loads`; `--format dts` stdout is raw DTS. `--format both` requires an output directory and produces two separate artifacts.
- GUI output metadata comes from the generated artifact, not the current selector. Any input or format change invalidates the prior artifact.
- Keep each task in its own Conventional Commit after its focused tests and relevant static checks pass.
- Do not edit unrelated pre-existing code or fix the separately observed date-parser issue in `src/fw_diag_tool/log/parser.py`.
- Final gates are `uv run pytest tests/ --tb=no -q`, `uv run ruff check .`, `uv run mypy src/fw_diag_tool`, `uv run python -m compileall -q src`, and `uv run mkdocs build --strict`.

---

## File Map and Responsibility Boundaries

- `src/fw_diag_tool/em/mock_gen.py`: strict EM JSON parsing, deterministic mock-object mapping, safe Python literal generation, and real D-Bus daemon source generation.
- `pyproject.toml` and `uv.lock`: declare and lock `dbus-next`, the runtime used by generated mock daemons.
- `src/fw_diag_tool/board_profile.py`: model explicit downstream Linux adapter numbers on MUX channels and validate their uniqueness.
- `src/fw_diag_tool/em/bridge.py`: translate direct, MUX, and downstream devices without flattening or inventing topology.
- `src/fw_diag_tool/codegen/dts_gen.py`: render one controller containing direct children and zero or more MUX children; retain the old one-MUX API as a compatibility wrapper.
- `src/fw_diag_tool/log/patterns.py`: match only actual failure language for the five over-broad patterns.
- `src/fw_diag_tool/gui/pages/em_builder_ui.py`: bind displayed/downloaded script content and metadata to one immutable generation key.
- `src/fw_diag_tool/cli.py`: provide artifact-safe stdout/file behavior and narrow user-input exceptions.
- `docs/chapters/ch11_board_profile.md`, `docs/chapters/ch25_em_builder.md`, and `README.md`: document the explicit MUX mapping, real D-Bus dependency, and CLI output contract.

### Task 1: Strict EM JSON Parsing and Collision-Free Mock Mapping

**Files:**

- Modify: `src/fw_diag_tool/em/mock_gen.py:17-167`
- Test: `tests/test_em_mock_gen.py`

**Interfaces:**

- Consumes: JSON text following the Entity-Manager root shape `{Name, Probe, Exposes}`.
- Produces: `EMMockGenerator.parse_em_json(json_text: str) -> EMBoardConfig` with non-lossy integer validation.
- Produces: `EMMockGenerator._build_mock_objects(config: EMBoardConfig) -> list[dict[str, Any]]`; both script generators must consume this single mapping.
- Preserves: `EMMockGenerator._get_sensor_mapping(dev)` as the category-to-interface mapping helper.

- [x] **Step 1: Write failing parser-contract tests**

Append these tests to `tests/test_em_mock_gen.py`:

```python
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"Exposes": {}}, "Exposes must be a JSON array"),
        ({"Exposes": ["not-an-object"]}, "Exposes[0] must be a JSON object"),
        ({"Exposes": [{"Name": "T", "Type": "TMP75", "Address": "0x48"}]}, "Bus"),
        ({"Exposes": [{"Name": "T", "Type": "TMP75", "Bus": True, "Address": "0x48"}]}, "Bus must be an integer"),
        ({"Exposes": [{"Name": "T", "Type": "TMP75", "Bus": 1.5, "Address": "0x48"}]}, "Bus must be an integer"),
        ({"Exposes": [{"Name": "T", "Type": "TMP75", "Bus": 1, "Address": "0x78"}]}, "Address must be a non-reserved"),
    ],
)
def test_parse_em_json_rejects_malformed_contract(payload: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        EMMockGenerator.parse_em_json(json.dumps(payload))
```

- [x] **Step 2: Run the parser tests and verify red**

Run:

```bash
uv run pytest tests/test_em_mock_gen.py::test_parse_em_json_rejects_malformed_contract -v
```

Expected: at least the mapping, non-object item, boolean, float, or out-of-range cases fail because the current parser silently skips or coerces them.

- [x] **Step 3: Add strict integer and shape helpers, then use them in `parse_em_json`**

Add this helper above `EMMockGenerator` and replace the permissive defaults in `parse_em_json`:

```python
def _parse_int_field(value: Any, *, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError(f"{path} must be an integer")
    try:
        parsed = int(value, 0) if isinstance(value, str) else value
    except ValueError as exc:
        raise ValueError(f"{path} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        if path.endswith("Address"):
            raise ValueError(f"{path} must be a non-reserved 7-bit I2C address (0x08..0x77)")
        raise ValueError(f"{path} must be between {minimum} and {maximum}")
    return parsed
```

Use these exact parser rules:

```python
if "Exposes" not in data:
    raise ValueError("Entity-Manager configuration is missing Exposes")
exposes_list = data["Exposes"]
if not isinstance(exposes_list, list):
    raise TypeError("Exposes must be a JSON array")

for idx, item in enumerate(exposes_list):
    path = f"Exposes[{idx}]"
    if not isinstance(item, dict):
        raise TypeError(f"{path} must be a JSON object")
    for field_name in ("Name", "Type", "Bus", "Address"):
        if field_name not in item:
            raise ValueError(f"{path} is missing {field_name}")
    bus = _parse_int_field(item["Bus"], path=f"{path}.Bus", minimum=0, maximum=65535)
    address = _parse_int_field(
        item["Address"], path=f"{path}.Address", minimum=0x08, maximum=0x77
    )
```

- [x] **Step 4: Run focused parser tests and existing valid parser tests**

Run:

```bash
uv run pytest tests/test_em_mock_gen.py -k 'parse_em_json' -v
```

Expected: all selected tests pass.

- [x] **Step 5: Write failing category and sanitized-name collision tests**

Append:

```python
def test_mock_mapping_skips_mux_instead_of_inventing_temperature_sensor() -> None:
    config = EMMockGenerator.parse_em_json(json.dumps({
        "Name": "MuxBoard",
        "Probe": "TRUE",
        "Exposes": [
            {"Name": "Main Mux", "Type": "PCA9548", "Bus": 1, "Address": "0x70"}
        ],
    }))
    assert EMMockGenerator._build_mock_objects(config) == []


def test_mock_mapping_disambiguates_sanitized_path_collisions() -> None:
    template = get_template("TMP75")
    assert template is not None
    config = EMBoardConfig(board_name="B", devices=[
        EMDeviceEntry(template=template, bus=1, address=0x48, name="CPU Temp"),
        EMDeviceEntry(template=template, bus=2, address=0x48, name="CPU-Temp"),
    ])
    paths = [obj["path"] for obj in EMMockGenerator._build_mock_objects(config)]
    assert len(paths) == len(set(paths)) == 2
    assert paths[0].endswith("/CPU_Temp_b1_a48")
    assert paths[1].endswith("/CPU_Temp_b2_a48")
```

- [x] **Step 6: Run the mapping tests and verify red**

Run:

```bash
uv run pytest tests/test_em_mock_gen.py -k 'skips_mux or sanitized_path_collision' -v
```

Expected: FAIL because MUX currently falls back to a temperature sensor and colliding sanitized names produce identical paths.

- [x] **Step 7: Add one deterministic object builder**

Change `_infer_category` so explicit MUX tokens return `"mux"`. Change `_get_sensor_mapping` so `gpio` and `mux` return `None`. Add `_build_mock_objects` that first counts sanitized base names, then suffixes every colliding base with bus/address:

```python
@classmethod
def _build_mock_objects(cls, config: EMBoardConfig) -> list[dict[str, Any]]:
    supported = [(dev, cls._get_sensor_mapping(dev)) for dev in config.devices]
    supported = [(dev, mapping) for dev, mapping in supported if mapping is not None]
    base_counts: dict[str, int] = {}
    for dev, _ in supported:
        base = _sanitize_name(dev.name)
        base_counts[base] = base_counts.get(base, 0) + 1

    objects: list[dict[str, Any]] = []
    for dev, mapping in supported:
        assert mapping is not None
        base = _sanitize_name(dev.name)
        component = f"{base}_b{dev.bus}_a{dev.address:02x}" if base_counts[base] > 1 else base
        sensor_kind = "inventory" if not mapping["is_sensor"] else mapping["kind"]
        prefix = (
            "/xyz/openbmc_project/inventory/system/board"
            if sensor_kind == "inventory"
            else f"/xyz/openbmc_project/sensors/{sensor_kind}"
        )
        objects.append({
            "name": dev.name,
            "chip": dev.template.chip_name,
            "category": dev.template.category.lower(),
            "bus": dev.bus,
            "address": f"0x{dev.address:02x}",
            "path": f"{prefix}/{component}",
            "unit": mapping["unit"],
            "value": mapping["value"],
            "is_sensor": mapping["is_sensor"],
        })
    return objects
```

Update `_get_sensor_mapping` to return a `kind` value (`temperature`, `fan_tach`, `power`, or `voltage`) rather than constructing its own final path. Do not keep two path-building implementations.

- [x] **Step 8: Run focused tests, static checks, and commit**

Run:

```bash
uv run pytest tests/test_em_mock_gen.py -v
uv run ruff check src/fw_diag_tool/em/mock_gen.py tests/test_em_mock_gen.py
uv run mypy src/fw_diag_tool/em/mock_gen.py
git add src/fw_diag_tool/em/mock_gen.py tests/test_em_mock_gen.py
git commit -m "fix(em): validate mock inputs and prevent path collisions"
```

Expected: tests and checks pass; one commit is created.

### Task 2: Generate a Real, Injection-Safe D-Bus Service

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/fw_diag_tool/em/mock_gen.py:170-319`
- Modify: `src/fw_diag_tool/cli.py:2076-2121`
- Modify: `src/fw_diag_tool/gui/pages/em_builder_ui.py:427-471`
- Modify: `src/fw_diag_tool/i18n/domains/gui.py`
- Modify: `docs/chapters/ch25_em_builder.md`
- Create: `tests/fixtures/em_mock_sample.json`
- Test: `tests/test_em_mock_gen.py`
- Test: `tests/test_cli_log_em.py`

**Interfaces:**

- Produces: `EMMockGenerator.generate_python_mock(config) -> str`, a standalone daemon using `dbus_next.aio.MessageBus`.
- Preserves: `EMMockGenerator.generate_busctl_script(config) -> str`, but its output becomes a Bash launcher containing the same Python daemon in a single-quoted heredoc; it no longer claims that `busctl set-property` creates objects.
- Generated daemon requests `xyz.openbmc_project.FWDiagMock`, exports each path, and runs until interrupted. A one-shot mode is intentionally omitted because exported objects disappear when their owning process exits.

- [x] **Step 1: Write failing syntax and source-injection tests**

Append:

```python
@pytest.mark.parametrize("board_name", ['Board"\\\nraise RuntimeError("INJECTED")#', "Board'''evil"])
def test_generated_python_is_valid_and_treats_board_name_as_data(board_name: str) -> None:
    config = EMBoardConfig(board_name=board_name, devices=[])
    script = EMMockGenerator.generate_python_mock(config)
    compile(script, "<generated-mock>", "exec")
    assert "BOARD_NAME = " + repr(board_name) in script


def test_generated_python_uses_python_booleans_not_json_tokens(
    sample_board_config: EMBoardConfig,
) -> None:
    script = EMMockGenerator.generate_python_mock(sample_board_config)
    compile(script, "<generated-mock>", "exec")
    assert "'is_sensor': True" in script
    assert '"is_sensor": true' not in script


def test_generated_bash_does_not_execute_device_text(
    sample_board_config: EMBoardConfig,
    tmp_path: Path,
) -> None:
    sample_board_config.devices[0].name = 'FRU"; echo INJECTED; #'
    script_path = tmp_path / "mock.sh"
    script_path.write_text(EMMockGenerator.generate_busctl_script(sample_board_config))
    result = subprocess.run(["bash", "-n", str(script_path)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "<<'PYTHON_MOCK'" in script_path.read_text()
```

Add `from pathlib import Path` and `import subprocess` to the test module.

- [x] **Step 2: Run the syntax and injection tests and verify red**

Run:

```bash
uv run pytest tests/test_em_mock_gen.py -k 'generated_python or generated_bash' -v
```

Expected: FAIL because JSON booleans are invalid Python and unescaped values currently enter source syntax.

- [x] **Step 3: Add the runtime dependency and refresh the lock**

Add this item to `[project].dependencies`:

```toml
    "dbus-next>=0.2.3,<1.0.0",
```

Run:

```bash
uv lock
uv sync --all-extras
```

Expected: `pyproject.toml` and `uv.lock` contain `dbus-next`; sync exits zero.

Create `tests/fixtures/em_mock_sample.json` with this exact content so later smoke tests never depend on an unspecified local file:

```json
{
  "Exposes": [
    {
      "Address": "0x48",
      "Bus": 1,
      "Name": "Inlet_Temp",
      "Type": "TMP75"
    },
    {
      "Address": "0x50",
      "Bus": 1,
      "Name": "Baseboard_FRU",
      "Type": "EEPROM"
    }
  ],
  "Name": "Mock_Test_Board",
  "Probe": "TRUE"
}
```

- [x] **Step 4: Write the failing service-ownership contract test**

Append:

```python
def test_generated_python_owns_name_and_exports_objects(
    sample_board_config: EMBoardConfig,
) -> None:
    script = EMMockGenerator.generate_python_mock(sample_board_config)
    assert "await bus.request_name(MOCK_SERVICE)" in script
    assert "bus.export(obj['path'], interface)" in script
    assert "ServiceInterface" in script
    assert "busctl set-property" not in script
    assert "|| true" not in script
```

- [x] **Step 5: Run the ownership test and verify red**

Run:

```bash
uv run pytest tests/test_em_mock_gen.py::test_generated_python_owns_name_and_exports_objects -v
```

Expected: FAIL because current output only writes properties to a service that does not exist.

- [x] **Step 6: Replace generated Python with a real `dbus-next` daemon**

Use `pprint.pformat(objects, sort_dicts=True, width=100)` for `MOCK_OBJECTS` and `repr(config.board_name)` for `BOARD_NAME`. The generated source must contain these concrete interfaces:

The generated script must not include `from __future__ import annotations`; `dbus-next` reads the literal return annotations (`"d"` and `"s"`) as D-Bus signatures at class-definition time.

```python
from dbus_next import BusType
from dbus_next.aio import MessageBus
from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property


class SensorValueInterface(ServiceInterface):
    def __init__(self, value: float, unit: str) -> None:
        super().__init__(SENSOR_VALUE_INTF)
        self._value = value
        self._unit = unit

    @dbus_property(access=PropertyAccess.READWRITE)
    def Value(self) -> "d":
        return self._value

    @Value.setter
    def Value(self, value: "d") -> None:
        self._value = value

    @dbus_property(access=PropertyAccess.READ)
    def Unit(self) -> "s":
        return self._unit


class BoardInterface(ServiceInterface):
    def __init__(self, pretty_name: str) -> None:
        super().__init__(BOARD_INTF)
        self._pretty_name = pretty_name

    @dbus_property(access=PropertyAccess.READWRITE)
    def PrettyName(self) -> "s":
        return self._pretty_name

    @PrettyName.setter
    def PrettyName(self, value: "s") -> None:
        self._pretty_name = value
```

The generated async setup must be:

```python
async def publish_mock_objects() -> MessageBus:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    for obj in MOCK_OBJECTS:
        interface = (
            SensorValueInterface(float(obj["value"]), str(obj["unit"]))
            if obj["is_sensor"]
            else BoardInterface(str(obj["name"]))
        )
        bus.export(obj["path"], interface)
    await bus.request_name(MOCK_SERVICE)
    return bus
```

Catch connection/name/export errors only in generated `main()`, print one error to stderr, and return 1. Do not catch exceptions inside `publish_mock_objects()`.

- [x] **Step 7: Make Bash output a quoted launcher for the exact Python daemon**

Build the Bash output only from fixed shell lines plus the already-generated Python source:

```python
python_source = cls.generate_python_mock(config)
return "\n".join([
    "#!/bin/bash",
    "set -euo pipefail",
    "python3 - \"$@\" <<'PYTHON_MOCK'",
    python_source.rstrip("\n"),
    "PYTHON_MOCK",
    "",
])
```

No board name or device field may appear in a shell command outside the quoted heredoc.

- [x] **Step 8: Update CLI and GUI labels without changing command names**

Keep CLI values `bash` and `python`. Set the CLI help text to `Output format: bash launcher or python daemon (default: bash)`. Change GUI radio options to `Bash launcher` and `Python daemon`. Keep the existing translation key names and use these exact values:

```python
"em_mock_format": {
    "zh-TW": "輸出格式：Bash launcher 或 Python daemon",
    "en-US": "Output format: Bash launcher or Python daemon",
},
```

Add this exact paragraph to `docs/chapters/ch25_em_builder.md`:

```markdown
產生的 Mock 是長時間執行的 D-Bus service，不是一次性的 `busctl set-property` 指令。它會取得 `xyz.openbmc_project.FWDiagMock` bus name 並 export sensor/inventory objects；執行環境必須安裝 `dbus-next`，且 D-Bus policy 必須允許該 process 連線、取得名稱與匯出物件。任一動作失敗時程式會以非零狀態結束，不會顯示假成功。
```

- [x] **Step 9: Run focused tests and commit**

Run:

```bash
uv run pytest tests/test_em_mock_gen.py tests/test_cli_log_em.py -k 'mock' -v
uv run ruff check src/fw_diag_tool/em/mock_gen.py src/fw_diag_tool/cli.py src/fw_diag_tool/gui/pages/em_builder_ui.py tests/test_em_mock_gen.py
uv run mypy src/fw_diag_tool/em/mock_gen.py
uv run mkdocs build --strict
git add pyproject.toml uv.lock src/fw_diag_tool/em/mock_gen.py src/fw_diag_tool/cli.py src/fw_diag_tool/gui/pages/em_builder_ui.py src/fw_diag_tool/i18n/domains/gui.py docs/chapters/ch25_em_builder.md tests/fixtures/em_mock_sample.json tests/test_em_mock_gen.py tests/test_cli_log_em.py
git commit -m "fix(em): generate an owned D-Bus mock service safely"
```

Expected: tests, syntax checks, type checks, and MkDocs build pass.

### Task 3: Make MUX-to-Entity-Manager Bus Identity Explicit

**Files:**

- Modify: `src/fw_diag_tool/board_profile.py:292-396`
- Modify: `src/fw_diag_tool/em/bridge.py:26-103`
- Modify: `docs/chapters/ch11_board_profile.md`
- Test: `tests/test_board_profile.py`
- Test: `tests/test_em_bridge.py`
- Test: `tests/test_cli_log_em.py`

**Interfaces:**

- Produces: `MuxChannel.downstream_bus_num: int | None`.
- `EMBridge.from_board_profile()` maps direct devices and MUX chips to the parent `bus_num`; it maps downstream devices to `downstream_bus_num`.
- `EMBridge.from_board_profile()` raises `ValueError` when a populated channel lacks `downstream_bus_num`; DTS generation does not require this field.

- [x] **Step 1: Write failing BoardProfile validation tests**

Add to `tests/test_board_profile.py`:

```python
def test_mux_channel_accepts_explicit_downstream_bus_num() -> None:
    profile = BoardProfile.from_text(REPRESENTATIVE_PROFILE_YAML.replace(
        "- channel: 0\n",
        "- channel: 0\n            downstream_bus_num: 10\n",
        1,
    ))
    assert profile.i2c_buses[0].muxes[0].channels[0].downstream_bus_num == 10


def test_board_profile_rejects_duplicate_downstream_bus_numbers() -> None:
    text = MULTI_CHANNEL_PROFILE_WITH_DOWNSTREAM_BUSES.replace(
        "downstream_bus_num: 11", "downstream_bus_num: 10"
    )
    with pytest.raises(SchemaError, match="duplicate downstream_bus_num: 10"):
        BoardProfile.from_text(text)
```

Define this complete constant in the same test file; do not derive these values in production code:

```python
MULTI_CHANNEL_PROFILE_WITH_DOWNSTREAM_BUSES = """
board_name: Explicit-Mux-Buses
version: "1.0"
i2c_buses:
  - bus_num: 3
    speed_mode: fast
    muxes:
      - address_7bit: 0x70
        name: main-mux
        category: mux
        protocol: I2C
        compatible: nxp,pca9548
        register_width: 8
        channels:
          - channel: 0
            downstream_bus_num: 10
            devices:
              - address_7bit: 0x48
                name: inlet-temp
                category: temperature
                protocol: I2C
                compatible: ti,tmp75
                register_width: 8
          - channel: 1
            downstream_bus_num: 11
            devices:
              - address_7bit: 0x48
                name: outlet-temp
                category: temperature
                protocol: I2C
                compatible: ti,tmp75
                register_width: 8
"""
```

- [x] **Step 2: Run the model tests and verify red**

Run:

```bash
uv run pytest tests/test_board_profile.py -k 'downstream_bus' -v
```

Expected: FAIL because `MuxChannel` forbids the unknown field.

- [x] **Step 3: Add and validate `downstream_bus_num`**

Add to `MuxChannel`:

```python
downstream_bus_num: int | None = None

@field_validator("downstream_bus_num", mode="before")
@classmethod
def _validate_downstream_bus_num(cls, value: Any) -> int | None:
    if value is None:
        return None
    bus_num = _parse_int(value, "downstream_bus_num")
    if not 0 <= bus_num <= 0xFFFF:
        raise ValueError("downstream_bus_num must be between 0 and 65535")
    return bus_num
```

Extend `BoardProfile._validate_bus_numbers()` with a second set. Reject a `downstream_bus_num` that duplicates a parent `bus_num` or another downstream bus. The error text must be `duplicate downstream_bus_num: <number>`.

- [x] **Step 4: Write failing EMBridge topology tests**

Update `SAMPLE_BOARD_WITH_MUX_YAML` in `tests/test_em_bridge.py` so channel 0 uses bus 10 and channel 1 uses bus 11. Then add:

```python
def test_from_board_profile_preserves_downstream_bus_identity() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_WITH_MUX_YAML)
    config = EMBridge.from_board_profile(profile)
    dev_map = {dev.name: dev for dev in config.devices}
    assert dev_map["PCA9548_Mux"].bus == 3
    assert dev_map["DIMM0_SPD"].bus == 10
    assert dev_map["DIMM1_SPD"].bus == 11


def test_from_board_profile_rejects_populated_mux_channel_without_linux_bus() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_WITH_MUX_YAML.replace(
        "            downstream_bus_num: 10\n", ""
    ))
    with pytest.raises(
        ValueError,
        match=r"MUX PCA9548_Mux channel 0 requires downstream_bus_num for Entity-Manager",
    ):
        EMBridge.from_board_profile(profile)
```

- [x] **Step 5: Run EMBridge tests and verify red**

Run:

```bash
uv run pytest tests/test_em_bridge.py -k 'downstream_bus_identity or without_linux_bus' -v
```

Expected: the preserved-identity test fails because current code flattens both channels to bus 3; the missing-mapping test fails because current code does not reject it.

- [x] **Step 6: Use explicit channel bus numbers in `EMBridge.from_board_profile`**

Replace the downstream loop with:

```python
for channel in mux.channels:
    if channel.devices and channel.downstream_bus_num is None:
        raise ValueError(
            f"MUX {mux.name} channel {channel.channel} requires downstream_bus_num "
            "for Entity-Manager generation"
        )
    for dev in channel.devices:
        assert channel.downstream_bus_num is not None
        all_entries.append(cls._create_device_entry(dev, channel.downstream_bus_num))
```

Do not add private pseudo-bus numbering or put non-standard MUX fields into Entity-Manager `Exposes`.

- [x] **Step 7: Add the documented example fail-fast CLI test**

Add to `tests/test_cli_log_em.py`:

```python
def test_cli_em_generate_json_requires_explicit_mux_downstream_bus_mapping() -> None:
    result = runner.invoke(
        app,
        ["em", "generate", "examples/data/board_yv4.yaml", "--format", "json"],
    )
    assert result.exit_code == 2
    assert "requires downstream_bus_num" in result.output
```

Add this exact paragraph to `docs/chapters/ch11_board_profile.md`:

```markdown
`downstream_bus_num` 是 MUX channel 對應到 Linux runtime I2C adapter 的明確編號。DTS 產生只需要 parent bus、MUX address 與 channel，因此可以省略；Entity-Manager 的 `Bus` 欄位則必須填入實際 adapter number。工具不會猜測此值：只要 populated channel 缺少 `downstream_bus_num`，`fw-diag em generate --format json` 就會停止並指出 MUX 與 channel。請在目標板上依 `/sys/bus/i2c/devices` 或 `i2cdetect -l` 的實際結果填入，不能直接複製另一塊板的編號。
```

- [x] **Step 8: Run focused tests, static checks, docs, and commit**

Run:

```bash
uv run pytest tests/test_board_profile.py tests/test_em_bridge.py tests/test_cli_log_em.py -k 'downstream or mux' -v
uv run ruff check src/fw_diag_tool/board_profile.py src/fw_diag_tool/em/bridge.py tests/test_board_profile.py tests/test_em_bridge.py
uv run mypy src/fw_diag_tool/board_profile.py src/fw_diag_tool/em/bridge.py
uv run mkdocs build --strict
git add src/fw_diag_tool/board_profile.py src/fw_diag_tool/em/bridge.py docs/chapters/ch11_board_profile.md tests/test_board_profile.py tests/test_em_bridge.py tests/test_cli_log_em.py
git commit -m "fix(em): preserve explicit mux downstream bus identity"
```

Expected: all selected checks pass and existing non-MUX BoardProfiles remain valid.

### Task 4: Render Direct Devices and Every MUX in DTS

**Files:**

- Modify: `src/fw_diag_tool/codegen/dts_gen.py`
- Modify: `src/fw_diag_tool/em/bridge.py:106-170`
- Create: `tests/fixtures/board_profile_direct.yaml`
- Test: `tests/test_dts_gen.py`
- Test: `tests/test_codegen_hardening.py`
- Test: `tests/test_em_bridge.py`

**Interfaces:**

- Produces: `DeviceTreeGenerator.generate_i2c_bus(bus_num: int, direct_devices: list[dict[str, Any]], muxes: list[dict[str, Any]], clock_frequency: int = 400000) -> str`.
- Preserves: `generate_dts_from_topology(...)` as a compatibility wrapper that creates one MUX descriptor and delegates to `generate_i2c_bus`.
- `EMBridge.to_dts()` converts every `bus.devices` item and every item in `bus.muxes`; it never creates a MUX when `bus.muxes` is empty.

- [x] **Step 1: Write failing renderer topology tests**

Add to `tests/test_dts_gen.py`:

```python
def test_generate_i2c_bus_without_mux_renders_direct_children_only() -> None:
    dts = DeviceTreeGenerator.generate_i2c_bus(
        bus_num=1,
        direct_devices=[{"addr": 0x48, "name": "temp", "compatible": "ti,tmp75"}],
        muxes=[],
    )
    assert "temp@48" in dts
    assert "i2c-mux@" not in dts


def test_generate_i2c_bus_renders_direct_devices_and_all_muxes() -> None:
    dts = DeviceTreeGenerator.generate_i2c_bus(
        bus_num=3,
        direct_devices=[{"addr": 0x48, "name": "local-temp", "compatible": "ti,tmp75"}],
        muxes=[
            {"addr": 0x70, "compatible": "nxp,pca9548", "channels": [
                {"channel": 0, "devices": [{"addr": 0x50, "name": "fru-a", "compatible": "atmel,24c64"}]}
            ]},
            {"addr": 0x71, "compatible": "nxp,pca9548", "channels": [
                {"channel": 1, "devices": [{"addr": 0x50, "name": "fru-b", "compatible": "atmel,24c64"}]}
            ]},
        ],
    )
    assert "local-temp@48" in dts
    assert dts.count("i2c-mux@") == 2
    assert "i2c-mux@70" in dts
    assert "i2c-mux@71" in dts
    assert "fru-a@50" in dts
    assert "fru-b@50" in dts
```

- [x] **Step 2: Run renderer tests and verify red**

Run:

```bash
uv run pytest tests/test_dts_gen.py -k 'generate_i2c_bus' -v
```

Expected: FAIL with `AttributeError` because `generate_i2c_bus` does not exist.

- [x] **Step 3: Implement the multi-MUX renderer and delegate the old API**

Use existing `_parse_int`, `_validate_address`, `_validate_node_name`, and `_validate_compatible` helpers. `generate_i2c_bus` must:

1. Open `&i2c<bus>`, emit status and `clock-frequency` once.
2. Render every direct device at four-space indentation.
3. Render every MUX at four-space indentation and only its declared channels.
4. Validate duplicate direct/MUX parent addresses and duplicate addresses per MUX channel.
5. Close the controller exactly once.

Add this normalization helper so direct devices and downstream devices share one validation path:

```python
@classmethod
def _normalize_device(
    cls,
    device: Any,
    *,
    path: str,
) -> tuple[int, str, str]:
    if not isinstance(device, dict):
        raise TypeError(f"{path} must be a mapping")
    if "addr" not in device:
        raise ValueError(f"{path} is missing addr")
    address = cls._validate_address(f"{path}.addr", device["addr"])
    name = cls._validate_node_name(device.get("name", "device"))
    compatible = cls._validate_compatible(device.get("compatible", ""))
    return address, name, compatible
```

Implement `generate_i2c_bus` with this exact control flow:

```python
@classmethod
def generate_i2c_bus(
    cls,
    *,
    bus_num: int,
    direct_devices: list[dict[str, Any]],
    muxes: list[dict[str, Any]],
    clock_frequency: int = 400000,
) -> str:
    bus = cls._parse_int("bus_num", bus_num)
    if not 0 <= bus <= 0xFFFF:
        raise ValueError("bus_num must be between 0 and 65535")
    frequency = cls._parse_int("clock_frequency", clock_frequency)
    if not 1 <= frequency <= 0xFFFFFFFF:
        raise ValueError("clock_frequency must be between 1 and 0xFFFFFFFF")
    if not isinstance(direct_devices, list):
        raise TypeError("direct_devices must be a list of mappings")
    if not isinstance(muxes, list):
        raise TypeError("muxes must be a list of mappings")

    normalized_direct = [
        cls._normalize_device(device, path=f"direct_devices[{index}]")
        for index, device in enumerate(direct_devices)
    ]
    normalized_muxes: list[tuple[int, str, list[tuple[int, list[tuple[int, str, str]]]]]] = []
    parent_addresses = {address for address, _, _ in normalized_direct}

    for mux_index, mux in enumerate(muxes):
        path = f"muxes[{mux_index}]"
        if not isinstance(mux, dict):
            raise TypeError(f"{path} must be a mapping")
        mux_address = cls._validate_address(f"{path}.addr", mux.get("addr"))
        mux_compatible = cls._validate_compatible(mux.get("compatible", ""))
        if mux_address in parent_addresses:
            raise ValueError(f"duplicate I2C address 0x{mux_address:02X} on parent bus {bus}")
        parent_addresses.add(mux_address)
        raw_channels = mux.get("channels", [])
        if not isinstance(raw_channels, list):
            raise TypeError(f"{path}.channels must be a list of mappings")

        normalized_channels: list[tuple[int, list[tuple[int, str, str]]]] = []
        seen_channels: set[int] = set()
        for channel_index, channel in enumerate(raw_channels):
            channel_path = f"{path}.channels[{channel_index}]"
            if not isinstance(channel, dict):
                raise TypeError(f"{channel_path} must be a mapping")
            channel_num = cls._parse_int(
                f"{channel_path}.channel", channel.get("channel", 0)
            )
            if not 0 <= channel_num <= 7:
                raise ValueError(f"{channel_path}.channel must be between 0 and 7")
            if channel_num in seen_channels:
                raise ValueError(f"duplicate MUX channel {channel_num} in {path}")
            seen_channels.add(channel_num)
            raw_devices = channel.get("devices", [])
            if not isinstance(raw_devices, list):
                raise TypeError(f"{channel_path}.devices must be a list of mappings")
            normalized_devices = [
                cls._normalize_device(device, path=f"{channel_path}.devices[{device_index}]")
                for device_index, device in enumerate(raw_devices)
            ]
            addresses = [address for address, _, _ in normalized_devices]
            if len(addresses) != len(set(addresses)):
                raise ValueError(f"duplicate I2C address on MUX channel {channel_num}")
            normalized_channels.append((channel_num, normalized_devices))
        normalized_muxes.append((mux_address, mux_compatible, normalized_channels))

    lines = [
        "// SPDX-License-Identifier: GPL-2.0+ or MIT",
        f"&i2c{bus} {{",
        '    status = "okay";',
        f"    clock-frequency = <{frequency}>;",
        "",
    ]
    for address, name, compatible in normalized_direct:
        lines.extend([
            f"    {name}@{address:x} {{",
            f'        compatible = "{compatible}";',
            f"        reg = <0x{address:02x}>;",
            "    };",
            "",
        ])
    for mux_address, mux_compatible, channels in normalized_muxes:
        lines.extend([
            f"    i2c-mux@{mux_address:x} {{",
            f'        compatible = "{mux_compatible}";',
            f"        reg = <0x{mux_address:02x}>;",
            "        #address-cells = <1>;",
            "        #size-cells = <0>;",
            "        i2c-mux-idle-disconnect;",
            "",
        ])
        for channel_num, devices in channels:
            lines.extend([
                f"        i2c@{channel_num} {{",
                "            #address-cells = <1>;",
                "            #size-cells = <0>;",
                f"            reg = <{channel_num}>;",
                "",
            ])
            for address, name, compatible in devices:
                lines.extend([
                    f"            {name}@{address:x} {{",
                    f'                compatible = "{compatible}";',
                    f"                reg = <0x{address:02x}>;",
                    "            };",
                    "",
                ])
            lines.extend(["        };", ""])
        lines.extend(["    };", ""])
    lines.extend(["};", ""])
    return "\n".join(lines)
```

Delegate the compatibility API as follows:

```python
return cls.generate_i2c_bus(
    bus_num=bus_num,
    direct_devices=[],
    muxes=[{
        "addr": mux_addr,
        "compatible": mux_compatible,
        "channels": [
            {"channel": channel, "devices": channel_devices}
            for channel, channel_devices in grouped_devices.items()
        ],
    }],
    clock_frequency=clock_frequency,
)
```

Preserve current validation messages covered by `tests/test_codegen_hardening.py` wherever the old API is used.

- [x] **Step 4: Run renderer and compatibility tests**

Run:

```bash
uv run pytest tests/test_dts_gen.py tests/test_codegen_hardening.py -k 'dts' -v
```

Expected: all selected tests pass.

- [x] **Step 5: Write failing EMBridge multi-MUX tests**

Add this exact fixture to `tests/test_em_bridge.py`:

```python
SAMPLE_BOARD_WITH_TWO_MUXES_YAML = """
board_name: Multi_Mux_Board
version: "1.0"
i2c_buses:
  - bus_num: 3
    speed_mode: fast
    devices:
      - address_7bit: 0x48
        name: local-temp
        category: temperature
        protocol: I2C
        compatible: ti,tmp75
        register_width: 8
    muxes:
      - address_7bit: 0x70
        name: mux-a
        category: mux
        protocol: I2C
        compatible: nxp,pca9548
        register_width: 8
        channels:
          - channel: 0
            devices:
              - address_7bit: 0x50
                name: fru-a
                category: fru
                protocol: I2C
                compatible: atmel,24c64
                register_width: 8
      - address_7bit: 0x71
        name: mux-b
        category: mux
        protocol: I2C
        compatible: nxp,pca9548
        register_width: 8
        channels:
          - channel: 1
            devices:
              - address_7bit: 0x50
                name: fru-b
                category: fru
                protocol: I2C
                compatible: atmel,24c64
                register_width: 8
"""
```

Then add:

```python
def test_to_dts_preserves_direct_devices_and_all_muxes() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_WITH_TWO_MUXES_YAML)
    dts = EMBridge.to_dts(profile)
    assert "local-temp@48" in dts
    assert dts.count("i2c-mux@") == 2
    assert "i2c-mux@70" in dts
    assert "i2c-mux@71" in dts


def test_to_dts_without_mux_does_not_invent_mux() -> None:
    profile = BoardProfile.from_text(SAMPLE_BOARD_PROFILE_YAML)
    dts = EMBridge.to_dts(profile, bus_num=1)
    assert "i2c-mux@" not in dts
```

Create `tests/fixtures/board_profile_direct.yaml` with this exact direct-only profile for Task 8 CLI smoke tests:

```yaml
board_name: Direct_Test_Board
version: "1.0"
i2c_buses:
  - bus_num: 1
    speed_mode: standard
    devices:
      - address_7bit: 0x48
        name: inlet-temp
        category: Temperature Sensor
        protocol: I2C
        compatible: ti,tmp75
        register_width: 8
```

- [x] **Step 6: Run bridge DTS tests and verify red**

Run:

```bash
uv run pytest tests/test_em_bridge.py -k 'all_muxes or does_not_invent_mux' -v
```

Expected: current code omits the direct child in a MUX bus, ignores the second MUX, and invents `i2c-mux@70` on direct-only buses.

- [x] **Step 7: Make `EMBridge.to_dts` build the complete descriptor**

For each selected bus, build:

```python
direct_devices = [
    {"addr": dev.address_7bit, "name": _dts_name(dev.name), "compatible": dev.compatible}
    for dev in bus.devices
]
muxes = [
    {
        "addr": mux.address_7bit,
        "compatible": mux.compatible,
        "channels": [
            {
                "channel": channel.channel,
                "devices": [
                    {"addr": dev.address_7bit, "name": _dts_name(dev.name), "compatible": dev.compatible}
                    for dev in channel.devices
                ],
            }
            for channel in mux.channels
        ],
    }
    for mux in bus.muxes
]
```

Call `DeviceTreeGenerator.generate_i2c_bus(...)`. Add `_dts_name(name: str) -> str` once; normalize whitespace and underscores to `-`, lowercase the result, and let `DeviceTreeGenerator` validate the remaining characters.

- [x] **Step 8: Run focused tests, static checks, and commit**

Run:

```bash
uv run pytest tests/test_dts_gen.py tests/test_codegen_hardening.py tests/test_em_bridge.py -v
uv run ruff check src/fw_diag_tool/codegen/dts_gen.py src/fw_diag_tool/em/bridge.py tests/test_dts_gen.py tests/test_em_bridge.py
uv run mypy src/fw_diag_tool/codegen/dts_gen.py src/fw_diag_tool/em/bridge.py
git add src/fw_diag_tool/codegen/dts_gen.py src/fw_diag_tool/em/bridge.py tests/fixtures/board_profile_direct.yaml tests/test_dts_gen.py tests/test_codegen_hardening.py tests/test_em_bridge.py
git commit -m "fix(dts): preserve direct and multi-mux topology"
```

Expected: focused suites and checks pass.

### Task 5: Tighten Log Patterns with Negative Controls

**Files:**

- Modify: `src/fw_diag_tool/log/patterns.py:336-407`
- Test: `tests/test_phase1_log_patterns.py`

**Interfaces:**

- Preserves pattern IDs: `IPMID_TIMEOUT`, `SYSTEMD_SERVICE_FAILED`, `JOURNAL_DISK_FULL`, `EMMC_IO_ERROR`, and `NFSROOT_MOUNT_FAIL`.
- Changes only matching precision; severity, subsystem, triage hint, and positive examples remain stable.

- [x] **Step 1: Write one parameterized failing negative-control test**

Append:

```python
@pytest.mark.parametrize(
    "log",
    [
        "Sep 02 01:00:00 bmc ipmid[200]: Host command timeout configured to 30 seconds",
        "Sep 02 01:00:01 bmc systemd[1]: demo.service: Main process exited, code=exited, status=0/SUCCESS",
        "Sep 02 02:00:00 bmc systemd-journald[50]: Vacuuming done, freed 16.0M of archived journals",
        "Sep 02 02:00:01 bmc systemd-journald[50]: Suppressed 12 messages from demo.service",
        "[ 600.0] mmcblk0: retrying command after retune",
        "[ 700.0] NFS: sending mount request for 192.0.2.10:/srv/root",
    ],
)
def test_expanded_patterns_ignore_normal_status_lines(log: str) -> None:
    report = LogParser.parse_log_text(log)
    assert report.summary.total_events == 0
```

Add `import pytest` to the test module.

- [x] **Step 2: Run the negative controls and verify red**

Run:

```bash
uv run pytest tests/test_phase1_log_patterns.py::test_expanded_patterns_ignore_normal_status_lines -v
```

Expected: all six cases currently produce false-positive events.

- [x] **Step 3: Replace only the five over-broad regular expressions**

Use these regex contracts:

```python
# IPMID_TIMEOUT
r"ipmid.*:\s*(?:Timed out waiting for|command timed out|no response from host)"

# SYSTEMD_SERVICE_FAILED
r"systemd\[\d+\]:\s*\S+\.service:\s*(?:Main process exited.*status=(?!0/SUCCESS\b)|Failed with result|entered failed state)"

# JOURNAL_DISK_FULL
r"systemd-journald.*:\s*(?:Failed to write entry.*No space left on device|No space left on device)"

# EMMC_IO_ERROR
r"mmcblk\d+:\s*(?:error\b|timed out\b|I/O error\b|failed to send\b)"

# NFSROOT_MOUNT_FAIL
r"NFS:.*(?:mount.*failed|No route to host|Connection refused)"
```

Keep `re.IGNORECASE`. Do not combine lifecycle/status messages into failure patterns merely because they contain words such as `timeout`, `request`, `retrying`, or `suppressed`.

- [x] **Step 4: Run positive and negative pattern tests**

Run:

```bash
uv run pytest tests/test_phase1_log_patterns.py -v
```

Expected: all original positive cases and all new negative controls pass.

- [x] **Step 5: Run log regression tests, static checks, and commit**

Run:

```bash
uv run pytest tests/test_log_parser.py tests/test_log_models.py tests/test_phase1_log_patterns.py -v
uv run ruff check src/fw_diag_tool/log/ tests/test_phase1_log_patterns.py
uv run mypy src/fw_diag_tool/log/
git add src/fw_diag_tool/log/patterns.py tests/test_phase1_log_patterns.py
git commit -m "fix(log): reject benign OpenBMC status messages"
```

Expected: all checks pass.

### Task 6: Invalidate Stale GUI Mock Artifacts

**Files:**

- Modify: `src/fw_diag_tool/gui/pages/em_builder_ui.py:402-471`
- Test: `tests/test_em_builder_ui.py:314-342`

**Interfaces:**

- Produces: `_mock_generation_key(board_name: str, probe_expression: str, format_name: str, devices: list[EMDeviceEntry]) -> tuple[object, ...]`.
- Stores: `st.session_state["em_mock_artifact"]` as `{"key": key, "content": str, "format": "bash" | "python"}`.
- Removes: legacy `em_mock_script` state after migration; no display path may infer metadata from the current radio value.

- [x] **Step 1: Write a failing pure helper test for input identity**

Import `_mock_generation_key` in `tests/test_em_builder_ui.py` and add:

```python
def test_mock_generation_key_changes_with_format_and_devices() -> None:
    devices = list(_get_default_sample_devices())
    bash_key = _mock_generation_key("Board", "TRUE", "bash", devices)
    python_key = _mock_generation_key("Board", "TRUE", "python", devices)
    changed_devices = list(devices)
    changed_devices[0] = EMDeviceEntry(
        template=devices[0].template,
        bus=devices[0].bus,
        address=devices[0].address,
        name="Changed_Name",
    )
    assert bash_key != python_key
    assert bash_key != _mock_generation_key("Board", "TRUE", "bash", changed_devices)
```

Import `EMDeviceEntry` from `fw_diag_tool.em.models`.

- [x] **Step 2: Run the helper test and verify red**

Run:

```bash
uv run pytest tests/test_em_builder_ui.py::test_mock_generation_key_changes_with_format_and_devices -v
```

Expected: FAIL with `ImportError` because the helper does not exist.

- [x] **Step 3: Add the immutable key helper**

Implement:

```python
def _mock_generation_key(
    board_name: str,
    probe_expression: str,
    format_name: str,
    devices: list[EMDeviceEntry],
) -> tuple[object, ...]:
    device_key = tuple(
        (dev.name, dev.template.em_type, dev.bus, dev.address, dev.power_state)
        for dev in devices
    )
    return (board_name, probe_expression, format_name, device_key)
```

- [x] **Step 4: Write the failing AppTest stale-format test**

Extend the mock-mode AppTest:

```python
def test_apptest_em_mock_format_change_invalidates_generated_artifact() -> None:
    at = AppTest.from_function(_mock_mode_with_devices_app, default_timeout=15).run()
    generate = next(button for button in at.button if "產生 D-Bus Mock" in button.label)
    generate.click().run()
    assert any(code.language == "bash" for code in at.code)

    format_radio = next(radio for radio in at.radio if "輸出格式" in radio.label)
    format_radio.set_value("Python daemon").run()

    assert not at.code
    assert not at.download_button
```

If the translated label differs, select the format radio by checking that its options contain `Python daemon`; do not select by list index.

- [x] **Step 5: Run the AppTest and verify red**

Run:

```bash
uv run pytest tests/test_em_builder_ui.py::test_apptest_em_mock_format_change_invalidates_generated_artifact -v
```

Expected: FAIL because the old Bash content remains while metadata changes to Python.

- [x] **Step 6: Store content and metadata as one artifact and invalidate on mismatch**

Before rendering a saved artifact, calculate the current key. If the saved key differs, remove it:

```python
format_name = "bash" if "Bash" in str(format_choice) else "python"
current_key = _mock_generation_key(board_name, probe_expr, format_name, devices_list)
artifact = st.session_state.get("em_mock_artifact")
if artifact is not None and artifact["key"] != current_key:
    st.session_state.pop("em_mock_artifact", None)
    artifact = None
```

On generation, store `key`, `content`, and `format` together. When rendering, derive language, file suffix, and MIME only from `artifact["format"]`. Never read `em_mock_fmt_select` for an already-generated artifact.

- [x] **Step 7: Run GUI tests, static checks, and commit**

Run:

```bash
uv run pytest tests/test_em_builder_ui.py -v
uv run ruff check src/fw_diag_tool/gui/pages/em_builder_ui.py tests/test_em_builder_ui.py
uv run mypy src/fw_diag_tool/gui/pages/em_builder_ui.py
git add src/fw_diag_tool/gui/pages/em_builder_ui.py tests/test_em_builder_ui.py
git commit -m "fix(gui): invalidate stale mock generator artifacts"
```

Expected: all tests and checks pass.

### Task 7: Make CLI Generation Output Artifact-Safe

**Files:**

- Modify: `src/fw_diag_tool/cli.py:2008-2073`
- Modify: `README.md`
- Modify: `docs/chapters/ch25_em_builder.md`
- Test: `tests/test_cli_log_em.py:336-386`

**Interfaces:**

- `fw-diag em generate PROFILE --format json` writes exactly one JSON document to stdout when `--out` is absent.
- `fw-diag em generate PROFILE --format dts` writes raw DTS to stdout when `--out` is absent.
- `fw-diag em generate PROFILE --format both --out DIRECTORY` writes `entity-manager.json` and `device-tree.dts` in that existing directory.
- `--format both` without `--out`, or with a non-directory path, exits 2 without partial output.

- [x] **Step 1: Strengthen the JSON stdout test so it fails on Rich decoration**

Replace the stdout portion of `test_cli_em_generate_json` with:

```python
result = runner.invoke(app, ["em", "generate", str(profile_file), "--format", "json"])
assert result.exit_code == 0
payload = json.loads(result.stdout)
assert payload["Name"] == "TestServer_V1"
assert payload["Exposes"][0]["Type"] == "TMP75"
```

- [x] **Step 2: Run the JSON stdout test and verify red**

Run:

```bash
uv run pytest tests/test_cli_log_em.py::test_cli_em_generate_json -v
```

Expected: FAIL with `json.JSONDecodeError` because Rich Panel borders and title surround the JSON.

- [x] **Step 3: Write failing `both` artifact contract tests**

Replace the old concatenation assertions in `test_cli_em_generate_both_and_invalid` and add:

```python
def test_cli_em_generate_both_requires_output_directory(tmp_path: Path) -> None:
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(SAMPLE_BOARD_PROFILE)
    missing_out = runner.invoke(app, ["em", "generate", str(profile_file), "-f", "both"])
    assert missing_out.exit_code == 2
    assert "requires --out DIRECTORY" in missing_out.output

    output_dir = tmp_path / "artifacts"
    output_dir.mkdir()
    result = runner.invoke(
        app,
        ["em", "generate", str(profile_file), "-f", "both", "-o", str(output_dir)],
    )
    assert result.exit_code == 0
    assert json.loads((output_dir / "entity-manager.json").read_text())["Name"] == "TestServer_V1"
    assert "&i2c1" in (output_dir / "device-tree.dts").read_text()


def test_cli_em_generate_both_rejects_file_output_without_partial_write(tmp_path: Path) -> None:
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(SAMPLE_BOARD_PROFILE)
    output_file = tmp_path / "combined.txt"
    result = runner.invoke(
        app,
        ["em", "generate", str(profile_file), "-f", "both", "-o", str(output_file)],
    )
    assert result.exit_code == 2
    assert not output_file.exists()
```

- [x] **Step 4: Run the `both` tests and verify red**

Run:

```bash
uv run pytest tests/test_cli_log_em.py -k 'generate_both' -v
```

Expected: FAIL because current command concatenates JSON and DTS and accepts a single file/stdout.

- [x] **Step 5: Separate data stdout from human status output**

Use `typer.echo(output_text)` for single-format stdout; do not wrap data in `Panel`. Keep Rich errors for invalid input. Handle `both` before generation:

```python
if fmt == "both":
    if output_file is None:
        console.print("[bold red]Error: --format both requires --out DIRECTORY.[/]")
        raise typer.Exit(code=2)
    if not output_file.is_dir():
        console.print("[bold red]Error: --out must be an existing directory for --format both.[/]")
        raise typer.Exit(code=2)
```

Generate both strings in memory before writing either file. Then write:

```python
(output_file / "entity-manager.json").write_text(em_json + "\n", encoding="utf-8")
(output_file / "device-tree.dts").write_text(dts_content.rstrip("\n") + "\n", encoding="utf-8")
```

If either generation step raises, write neither artifact. Existing-directory requirement avoids silently creating a misspelled output location.

- [x] **Step 6: Narrow the mock command parser exception boundary**

Replace `except Exception` around EM input parsing with:

```python
except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
```

This prevents programming errors from being mislabeled as user JSON errors.

- [x] **Step 7: Update CLI documentation**

Document three copy-pasteable commands:

```bash
uv run fw-diag em generate profile.yaml --format json > entity-manager.json
uv run fw-diag em generate profile.yaml --format dts > device-tree.dts
mkdir -p generated && uv run fw-diag em generate profile.yaml --format both --out generated
```

State that JSON/DTS stdout contains artifact bytes only, while `both` never concatenates unlike formats.

- [x] **Step 8: Run CLI tests, static checks, docs, and commit**

Run:

```bash
uv run pytest tests/test_cli_log_em.py -v
uv run ruff check src/fw_diag_tool/cli.py tests/test_cli_log_em.py
uv run mypy src/fw_diag_tool/cli.py
uv run mkdocs build --strict
git add src/fw_diag_tool/cli.py tests/test_cli_log_em.py README.md docs/chapters/ch25_em_builder.md
git commit -m "fix(cli): emit machine-readable generation artifacts"
```

Expected: CLI tests, static checks, and documentation build pass.

### Task 8: Full Regression, Generated-Artifact Smoke Tests, and Review Gate

**Files:**

- Modify only if a preceding test exposes a defect in the five approved scopes.
- Test: all repository tests and generated artifacts.

**Interfaces:**

- Consumes: commits from Tasks 1-7.
- Produces: verification evidence and a clean reviewable branch; no merge or push.

- [x] **Step 1: Generate representative artifacts into a temporary directory**

Run:

```bash
tmp_dir=$(mktemp -d)
uv run fw-diag em mock tests/fixtures/em_mock_sample.json --format python --output "$tmp_dir/mock.py"
uv run fw-diag em mock tests/fixtures/em_mock_sample.json --format bash --output "$tmp_dir/mock.sh"
uv run python -m py_compile "$tmp_dir/mock.py"
bash -n "$tmp_dir/mock.sh"
```

Expected: both syntax checks exit zero. This step does not claim a live OpenBMC system-bus test.

- [x] **Step 2: Verify raw CLI artifact behavior**

Run:

```bash
uv run fw-diag em generate tests/fixtures/board_profile_direct.yaml --format json > "$tmp_dir/em.json"
uv run python -m json.tool "$tmp_dir/em.json" >/dev/null
uv run fw-diag em generate tests/fixtures/board_profile_direct.yaml --format dts > "$tmp_dir/board.dts"
rg -n '^&i2c[0-9]+ \{' "$tmp_dir/board.dts"
```

Expected: JSON parses and DTS contains at least one controller node.

- [x] **Step 3: Run the full automated gates**

Run:

```bash
uv run pytest tests/ --tb=no -q
uv run ruff check .
uv run mypy src/fw_diag_tool
uv run python -m compileall -q src
uv run mkdocs build --strict
git diff --check
```

Expected: every command exits zero. If a command fails, apply `superpowers:systematic-debugging`, fix only the demonstrated regression, and rerun the failing command followed by this complete gate list.

- [x] **Step 4: Run adversarial review before any merge decision**

Dispatch two read-only reviewers after all gates pass:

1. One reviewer checks contract coverage against this plan and the original three phase plans.
2. One reviewer performs adversarial security/topology review, including hostile names, malformed JSON, duplicate sanitized names, multi-MUX topology, benign log lines, GUI state changes, and CLI piping.

Neither reviewer may edit files. Any finding must include severity, exact file/line, reproduction, and a minimal fix recommendation.

- [x] **Step 5: Report branch state and stop**

Run:

```bash
git status --short --branch
git log --oneline --decorate origin/main..HEAD
```

Expected: branch is `codex/fix-adversarial-review`; only intentional changes exist. Report local verification separately from live OpenBMC D-Bus runtime verification, remote CI, merge, and push status. Do not merge or push without explicit authorization.

---

## Acceptance Matrix

| Review finding | Failing-test gate | Minimal implementation | Final evidence |
|---|---|---|---|
| Mock Python JSON booleans and source injection | Tasks 1-2 syntax, hostile-name, collision tests | Strict parser, `pprint.pformat`, `repr`, quoted heredoc | `py_compile`, `bash -n`, focused pytest |
| Mock service does not exist and errors are hidden | Task 2 ownership contract | `dbus-next` service owns name and exports interfaces; no `|| true` | Generated-source tests; live bus explicitly remains environment-dependent |
| EMBridge flattens channels and DTS loses/invents topology | Tasks 3-4 explicit-bus and multi-MUX tests | `downstream_bus_num`, fail-fast EM conversion, complete DTS renderer | BoardProfile, bridge, DTS, and CLI suites |
| Log patterns flag normal lifecycle messages | Task 5 negative controls | Five narrowed regexes only | Positive plus negative parser suite |
| GUI displays stale content with current metadata | Task 6 AppTest state transition | Immutable artifact key and metadata | Full EM Builder AppTest |
| CLI JSON is decorated and `both` is concatenated | Task 7 parse and two-artifact tests | Raw stdout; directory-only `both` | `json.loads`, CLI suite, shell redirection smoke test |

## Plan Self-Review Record

- Spec coverage: all five requested repair areas map to Tasks 1-7; Task 8 covers full regression and second review.
- Scope boundary: the pre-existing date parser false positive and unrelated refactors are explicitly excluded.
- Placeholder scan: no deferred markers, cross-task shorthand, or unnamed error-handling steps remain.
- Type consistency: `downstream_bus_num`, `_build_mock_objects`, `_mock_generation_key`, and `generate_i2c_bus` use the same names and signatures in tests and implementations.
- Safety boundary: no bus number is inferred; a missing runtime mapping produces a deterministic error.
- Evidence boundary: generated-source syntax can be verified locally; actual system-bus ownership requires a host with D-Bus permissions and is not implied by unit tests.

---

## Completion Record (2026-09-02)

| Remediation scope | Implementation evidence |
|---|---|
| Strict parsing and collision-free mock mapping | `525f9cb`, `3afab8e` |
| Injection-safe, owned D-Bus daemon and launcher | `40ada5a`, `25d8db7` |
| Explicit MUX-to-Entity-Manager bus identity | `a458ab3` |
| Direct and multi-MUX DTS topology | `64e061d` |
| Log negative controls | `8f91183` |
| GUI artifact identity and stale-state invalidation | `bbd50f0`, `2e2a6c2`, `4cf43c5`, `507571c`, `f204614`, `4bcddac`, `b06d4e9` |
| Raw CLI output and atomic artifact rollback | `b2158aa`, `c112fee`, `4d3a4b4`, `650a2a9`, `0678b6f` |

- [x] Fresh full-suite evidence: `uv run pytest` completed with 1518 passed; `uv run ruff check .`, `uv run mypy src/`, and `uv run mkdocs build --strict` all exited zero.
- [x] Generated-artifact evidence: Python/Bash mock files passed `py_compile` and `bash -n`; generated JSON passed `json.tool`; generated DTS contained `&i2c1`.
- [x] Independent read-only review evidence: contract/plan coverage and adversarial security/topology review both reported approval; no files were edited by reviewers.
- [x] Branch gate: HEAD is `c59f028` on `codex/fix-adversarial-review`; merge, push, remote CI, and live D-Bus runtime verification remain intentionally unperformed.

Evidence note: every task checkbox above is marked complete from committed implementation/test artifacts. The red-phase commands are historical TDD evidence and were not replayed by reverting the committed tree during this final acceptance.
