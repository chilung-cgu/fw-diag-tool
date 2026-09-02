import json

import pytest

from fw_diag_tool.board_profile import BoardProfile, SchemaError, load_board_profile

REPRESENTATIVE_PROFILE_YAML = """
board_name: YV4-CraterLake-reference
version: "1.0"
i2c_buses:
  - bus_num: 1
    speed_mode: fast-mode-plus
    devices:
      - address_7bit: 0x20
        name: board-gpio
        category: gpio-expander
        protocol: I2C
        compatible: nxp,pca9555
        register_width: 8
        registers:
          - name: output0
            offset: 0x02
            access: RW
        commands: []
    muxes:
      - address_7bit: 0x70
        name: board-mux
        category: i2c-mux
        protocol: I2C
        compatible: nxp,pca9548
        register_width: 8
        registers: []
        commands: []
        channels:
          - channel: 0
            devices:
              - address_7bit: 0x48
                name: inlet-temperature
                category: temperature-sensor
                protocol: I2C
                compatible: ti,tmp75
                register_width: 8
                registers:
                  - name: temperature
                    offset: 0x00
                    access: RO
                commands: []
          - channel: 1
            devices:
              - address_7bit: 0x48
                name: outlet-temperature
                category: temperature-sensor
                protocol: I2C
                compatible: ti,tmp75
                register_width: 8
                registers:
                  - name: temperature
                    offset: 0x00
                    access: RO
          - channel: 2
            devices:
              - address_7bit: 0x58
                name: system-vr
                category: power-controller
                protocol: PMBus
                compatible: infineon,xdpe12284
                register_width: 8
                registers: []
                commands:
                  - name: status-word
                    command_code: 0x79
          - channel: 3
            devices: []
          - channel: 4
            devices: []
          - channel: 5
            devices: []
          - channel: 6
            devices: []
          - channel: 7
            devices: []
"""

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


def test_loads_representative_yv4_craterlake_yaml_topology():
    profile = BoardProfile.from_yaml(REPRESENTATIVE_PROFILE_YAML)

    assert profile.board_name == "YV4-CraterLake-reference"
    assert profile.i2c_buses[0].speed_mode == "fast_plus"
    assert profile.i2c_buses[0].muxes[0].address_7bit == 0x70
    assert len(profile.i2c_buses[0].muxes[0].channels) == 8
    assert profile.i2c_buses[0].muxes[0].channels[0].devices[0].registers[0].offset == 0
    assert profile.i2c_buses[0].muxes[0].channels[2].devices[0].commands[0].code == 0x79


def test_loads_json_and_round_trips_normalized_mapping(tmp_path):
    source = json.dumps(profile_mapping())
    profile = BoardProfile.from_json(source)
    json_path = tmp_path / "board.json"
    json_path.write_text(source, encoding="utf-8")

    from_file = BoardProfile.from_file(json_path)
    assert from_file.to_dict() == profile.to_dict()
    assert load_board_profile(json_path).board_name == "test-board"


def test_load_board_profile_accepts_mapping_and_pathless_text():
    mapping = profile_mapping()
    assert load_board_profile(mapping).board_name == "test-board"
    assert load_board_profile(json.dumps(mapping), format="json").version == "1.0"


def test_same_address_is_allowed_on_different_mux_channels():
    profile = BoardProfile.from_mapping(profile_mapping())
    channels = profile.i2c_buses[0].muxes[0].channels
    assert channels[0].devices[0].address_7bit == channels[1].devices[0].address_7bit


@pytest.mark.parametrize(
    ("document", "format", "message"),
    [
        ('{"board_name": "broken",}', "json", "JSON syntax error"),
        (
            '{"board_name":"a","board_name":"b","version":"1.0","i2c_buses":[]}',
            "json",
            "JSON duplicate key",
        ),
        ("board_name: [broken\ni2c_buses: []", "yaml", "YAML syntax error"),
        (
            "board_name: test\nboard_name: duplicate\nversion: '1.0'\ni2c_buses: []",
            "yaml",
            "duplicate key",
        ),
        ("[]", "json", "root must be a mapping/object"),
        ("board_name: test\nversion: '1.0'\ni2c_buses: {}", "yaml", "valid list"),
    ],
)
def test_rejects_malformed_documents_with_schema_error(document, format, message):
    with pytest.raises(SchemaError, match=message):
        load_board_profile(document, format=format)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda data: data["i2c_buses"][0]["devices"][0].update(address_7bit=0x78), "address_7bit"),
        (lambda data: data["i2c_buses"][0]["devices"][0].update(address_7bit=0x07), "address_7bit"),
        (
            lambda data: data["i2c_buses"][0]["devices"][0].update(register_width=24),
            "register_width",
        ),
        (lambda data: data["i2c_buses"][0]["muxes"][0]["channels"][0].update(channel=8), "channel"),
        (
            lambda data: data["i2c_buses"][0]["muxes"][0]["channels"][0]["devices"].append(
                data["i2c_buses"][0]["muxes"][0]["channels"][0]["devices"][0].copy()
            ),
            "duplicate I2C address",
        ),
    ],
)
def test_rejects_invalid_nested_fields_without_uncaught_validation_error(mutator, message):
    data = profile_mapping()
    mutator(data)

    with pytest.raises(SchemaError, match=message):
        BoardProfile.from_mapping(data)


def test_rejects_duplicate_addresses_on_same_parent_bus():
    data = profile_mapping()
    duplicate = data["i2c_buses"][0]["devices"][0].copy()
    duplicate["name"] = "second-board-gpio"
    data["i2c_buses"][0]["devices"].append(duplicate)

    with pytest.raises(SchemaError, match="duplicate I2C address 0x20 on bus 1"):
        BoardProfile.from_mapping(data)


def test_rejects_mux_address_collision_with_direct_device():
    data = profile_mapping()
    data["i2c_buses"][0]["devices"][0]["address_7bit"] = 0x70

    with pytest.raises(SchemaError, match="duplicate I2C address 0x70 on bus 1"):
        BoardProfile.from_mapping(data)


def test_rejects_duplicate_channels_and_bus_numbers():
    duplicate_channel = profile_mapping()
    duplicate_channel["i2c_buses"][0]["muxes"][0]["channels"].append({"channel": 0, "devices": []})
    with pytest.raises(SchemaError, match="duplicate MUX channel 0"):
        BoardProfile.from_mapping(duplicate_channel)

    duplicate_bus = profile_mapping()
    duplicate_bus["i2c_buses"].append(duplicate_bus["i2c_buses"][0].copy())
    with pytest.raises(SchemaError, match="duplicate bus_num: 1"):
        BoardProfile.from_mapping(duplicate_bus)


def test_rejects_unknown_fields_and_register_offsets_beyond_width():
    unknown = profile_mapping()
    unknown["unexpected"] = True
    with pytest.raises(SchemaError, match="Extra inputs are not permitted"):
        BoardProfile.from_mapping(unknown)

    too_wide = profile_mapping()
    too_wide["i2c_buses"][0]["devices"][0]["registers"] = [{"name": "bad-offset", "offset": 0x100}]
    with pytest.raises(SchemaError, match="exceeds 8-bit"):
        BoardProfile.from_mapping(too_wide)


def profile_mapping():
    return {
        "board_name": "test-board",
        "version": "1.0",
        "i2c_buses": [
            {
                "bus_num": 1,
                "speed_mode": "fast",
                "devices": [
                    {
                        "address_7bit": "0x20",
                        "name": "board-gpio",
                        "category": "gpio-expander",
                        "protocol": "I2C",
                        "compatible": "nxp,pca9555",
                        "register_width": 8,
                        "registers": [],
                        "commands": [],
                    }
                ],
                "muxes": [
                    {
                        "address_7bit": "0x70",
                        "name": "mux",
                        "category": "i2c-mux",
                        "protocol": "I2C",
                        "compatible": "nxp,pca9548",
                        "register_width": "8",
                        "channels": [
                            {
                                "channel": "0",
                                "devices": [
                                    {
                                        "address_7bit": "0x50",
                                        "name": "eeprom",
                                        "category": "memory",
                                        "protocol": "I2C",
                                        "compatible": "atmel,24c64",
                                        "register_width": 8,
                                        "registers": [
                                            {
                                                "name": "data",
                                                "address": "0x00",
                                                "access": "rw",
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                "channel": 1,
                                "devices": [
                                    {
                                        "address_7bit": "0x50",
                                        "name": "second-eeprom",
                                        "category": "memory",
                                        "protocol": "I2C",
                                        "compatible": "atmel,24c64",
                                        "register_width": 8,
                                        "registers": [],
                                        "commands": [],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_engine_uses_board_profile_for_device_mapping():
    from fw_diag_tool.i2c.engine import I2CDiagnosticEngine

    profile = load_board_profile(REPRESENTATIVE_PROFILE_YAML)
    engine = I2CDiagnosticEngine(board_profile=profile)
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x20,Write,,ACK
0.0011,0,,Write,0x02,ACK
0.0012,0,,Write,0xAA,ACK
"""
    report = engine.analyze_csv_content(csv_data)
    tx = report.transactions[0]
    assert tx.device_name == "board-gpio"
    assert tx.identity_confidence == "board-profile"
    assert tx.device_category == "gpio-expander"


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
