from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HeaderType(Enum):
    TYPE_0_ENDPOINT = 0
    TYPE_1_BRIDGE = 1
    TYPE_2_CARDBUS = 2
    UNKNOWN = -1

@dataclass
class BARInfo:
    index: int
    raw_value: int
    is_io: bool
    is_64bit: bool = False
    is_prefetchable: bool = False
    base_address: int = 0
    size: int | None = None

@dataclass
class BridgeBusInfo:
    primary_bus: int
    secondary_bus: int
    subordinate_bus: int
    secondary_latency_timer: int
    io_base: int
    io_limit: int
    mem_base: int
    mem_limit: int
    pref_mem_base: int
    pref_mem_limit: int

@dataclass
class StandardCapability:
    cap_id: int
    name: str
    offset: int
    next_offset: int
    raw_bytes: bytes
    decoded_info: dict[str, Any] = field(default_factory=dict)

@dataclass
class ExtendedCapability:
    ext_cap_id: int
    version: int
    name: str
    offset: int
    next_offset: int
    raw_bytes: bytes
    decoded_info: dict[str, Any] = field(default_factory=dict)

@dataclass
class TLPHeaderDecoded:
    fmt: int
    type_: int
    length: int
    is_3dw: bool
    is_4dw: bool
    has_data: bool
    tc: int
    td: bool
    ep: bool
    attr: int
    type_name: str
    requester_id: int | None = None
    tag: int | None = None
    completer_id: int | None = None
    completion_status: int | None = None
    address: int | None = None
    first_dw_be: int | None = None
    last_dw_be: int | None = None
    raw_dw: list[int] = field(default_factory=list)

@dataclass
class AERUncorrectableError:
    bit_pos: int
    name: str
    short_code: str
    is_active: bool
    is_masked: bool
    severity: str
    root_cause_guide: str | None = None

@dataclass
class AERCorrectableError:
    bit_pos: int
    name: str
    short_code: str
    is_active: bool
    is_masked: bool
    root_cause_guide: str | None = None

@dataclass
class AERAnalysisResult:
    offset: int
    uncorr_status_raw: int
    uncorr_mask_raw: int
    uncorr_severity_raw: int
    corr_status_raw: int
    corr_mask_raw: int
    cap_control_raw: int
    header_log_raw: list[int]
    root_error_status_raw: int | None = None
    error_source_id_raw: int | None = None
    uncorr_errors: list[AERUncorrectableError] = field(default_factory=list)
    corr_errors: list[AERCorrectableError] = field(default_factory=list)
    decoded_tlp: TLPHeaderDecoded | None = None
    active_uncorr_fatal_count: int = 0
    active_uncorr_nonfatal_count: int = 0
    active_corr_count: int = 0

@dataclass
class PCIeConfigSpace:
    raw_data: bytes
    bdf: str | None = None
    vendor_id: int = 0
    device_id: int = 0
    command: int = 0
    status: int = 0
    revision_id: int = 0
    prog_if: int = 0
    sub_class: int = 0
    base_class: int = 0
    class_name: str = ""
    cache_line_size: int = 0
    latency_timer: int = 0
    header_type: HeaderType = HeaderType.UNKNOWN
    is_multi_function: bool = False
    bist: int = 0
    subsystem_vendor_id: int | None = None
    subsystem_device_id: int | None = None
    bars: list[BARInfo] = field(default_factory=list)
    expansion_rom_bar: int | None = None
    bridge_bus: BridgeBusInfo | None = None
    interrupt_pin: int = 0
    interrupt_line: int = 0
    capabilities_ptr: int = 0
    standard_capabilities: list[StandardCapability] = field(default_factory=list)
    extended_capabilities: list[ExtendedCapability] = field(default_factory=list)
    aer_analysis: AERAnalysisResult | None = None

@dataclass
class DmesgAEREvent:
    timestamp: str | None
    bdf: str
    severity: str
    error_name: str
    tlp_header: str | None
    raw_line: str
    root_cause_guide: str