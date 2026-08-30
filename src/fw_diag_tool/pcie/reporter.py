from __future__ import annotations

import re

from .models import DmesgAEREvent, HeaderType, PCIeConfigSpace

_ROOT_CAUSE_GUIDE_ZH = {
    "Completion Timeout (CTO): Requester did not receive completion in time.": "完成逾時（Completion Timeout；CTO）：請求端（Requester）未在期限內收到 completion。",
    "Unsupported Request (UR): Target received unsupported or out-of-range TLP.": "不支援請求（Unsupported Request；UR）：目標端（Target）收到不支援或超出範圍的 TLP。",
    "Malformed TLP: Violation of Transaction Layer packet framing or length.": "格式錯誤 TLP（Malformed TLP）：違反 Transaction Layer 封包框架或長度規則。",
    "Poisoned TLP: Data parity or error bit EP is set in received TLP.": "毒化 TLP（Poisoned TLP）：收到的 TLP 設定資料同位元或 EP 錯誤位元。",
    "Surprise Down: PCIe Link went down unexpectedly without software handshake.": "意外斷線（Surprise Down）：PCIe Link 未經軟體交握便意外中斷。",
    "Receiver Error: Physical layer 8b/10b or 128b/130b decode error or framing error.": "接收器錯誤（Receiver Error）：Physical Layer 發生 8b/10b 或 128b/130b 解碼／框架錯誤。",
    "Bad TLP: LCRC check failed in Data Link layer, triggering replay.": "錯誤 TLP（Bad TLP）：Data Link Layer 的 LCRC 檢查失敗，已觸發 replay。",
}
_LINK_DEGRADED_RE = re.compile(
    r"^PCIe Link Degraded: Operating at (?P<current>.+) x(?P<current_width>\d+) "
    r"\(Max Capable: (?P<maximum>.+) x(?P<maximum_width>\d+)\)$"
)
_AER_TRUNCATED_RE = re.compile(
    r"^AER capability at (?P<offset>0x[0-9A-Fa-f]+) is truncated: "
    r"the (?P<size>0x[0-9A-Fa-f]+)-byte AER structure is not fully present in the source dump$"
)
_DEVICE_DUMP_RE = re.compile(
    r"^Device dump could not be decoded: (?P<detail>.+?) "
    r"The source bytes were not interpreted as a clean config space\.?$"
)
_COMMAND_REGISTER_BIT_RE = re.compile(
    r"^Command Register Bit (?P<bit>\d+) \((?P<field>[A-Za-z0-9_.]+)\) is 0\.?$"
)
_TLP_FALLBACK_RE = re.compile(r"^TLP Fmt:(?P<fmt>0x[0-9A-Fa-f]+) Type:(?P<type>0x[0-9A-Fa-f]+)$")
_SEVERITY_PAIR_RE = re.compile(r"^(?P<outer>[^()]+) \((?P<inner>[^()]+)\)$")

_ERROR_NAME_ZH = {
    "Data Link Protocol Error": "資料鏈結協定錯誤（Data Link Protocol Error）",
    "DLP": "資料鏈結協定錯誤（DLP；Data Link Protocol）",
    "Surprise Down Error": "意外斷線錯誤（Surprise Down Error）",
    "SurpriseDown": "意外斷線錯誤（SurpriseDown）",
    "Poisoned TLP Received": "收到 Poisoned TLP（Poisoned TLP Received）",
    "PoisonedTLP": "收到 Poisoned TLP（PoisonedTLP）",
    "Flow Control Protocol Error": "流量控制協定錯誤（Flow Control Protocol Error）",
    "FCP": "流量控制協定錯誤（FCP；Flow Control Protocol）",
    "Completion Timeout": "完成逾時（Completion Timeout）",
    "CompTimeout": "完成逾時（CompTimeout；Completion Timeout）",
    "Completer Abort": "完成端中止（Completer Abort）",
    "CompAbort": "完成端中止（CompAbort；Completer Abort）",
    "Unexpected Completion": "非預期 Completion（Unexpected Completion）",
    "UnexpComp": "非預期 Completion（UnexpComp）",
    "Receiver Overflow": "接收器溢位（Receiver Overflow）",
    "RxOverflow": "接收器溢位（RxOverflow；Receiver Overflow）",
    "Malformed TLP": "封包格式錯誤（Malformed TLP）",
    "ECRC Error": "ECRC 錯誤（ECRC Error）",
    "ECRC": "ECRC 錯誤（ECRC）",
    "Unsupported Request Error": "不支援請求錯誤（Unsupported Request Error）",
    "UR": "不支援請求錯誤（UR；Unsupported Request）",
    "ACS Violation": "ACS 違規（ACS Violation）",
    "ACSViolation": "ACS 違規（ACSViolation）",
    "Uncorrectable Internal Error": "不可修正內部錯誤（Uncorrectable Internal Error）",
    "UncorrIntErr": "不可修正內部錯誤（UncorrIntErr）",
    "MC Blocked TLP": "MC Blocked TLP（被封鎖的 TLP；MC Blocked TLP）",
    "MCBlockedTLP": "MC Blocked TLP（被封鎖的 TLP；MCBlockedTLP）",
    "AtomicOp Egress Blocked": "AtomicOp 輸出被封鎖（AtomicOp Egress Blocked）",
    "AtomicOpBlocked": "AtomicOp 輸出被封鎖（AtomicOpBlocked）",
    "TLP Prefix Blocked Error": "TLP Prefix 被封鎖（TLP Prefix Blocked Error）",
    "TLPPrefixBlocked": "TLP Prefix 被封鎖（TLPPrefixBlocked）",
    "Poisoned TLP Egress Blocked": "Poisoned TLP 輸出被封鎖（Poisoned TLP Egress Blocked）",
    "PoisonedEgressBlocked": "Poisoned TLP 輸出被封鎖（PoisonedEgressBlocked）",
    "Receiver Error": "接收器錯誤（Receiver Error）",
    "RxErr": "接收器錯誤（RxErr；Receiver Error）",
    "Bad DLLP": "DLLP 錯誤（Bad DLLP）",
    "BadDLLP": "DLLP 錯誤（BadDLLP）",
    "Bad TLP": "LCRC 錯誤（Bad TLP）",
    "BadTLP": "LCRC 錯誤（BadTLP）",
    "Replay Number Rollover": "重播序號回繞（Replay Number Rollover）",
    "ReplayNumRollover": "重播序號回繞（ReplayNumRollover）",
    "Replay Timer Timeout": "重播計時器逾時（Replay Timer Timeout）",
    "ReplayTimeout": "重播計時器逾時（ReplayTimeout）",
    "Advisory Non-Fatal Error": "建議性非致命錯誤（Advisory Non-Fatal Error）",
    "AdvisoryNonFatal": "建議性非致命錯誤（AdvisoryNonFatal；Advisory Non-Fatal Error）",
    "Corrected Internal Error": "已修正內部錯誤（Corrected Internal Error）",
    "CorrIntErr": "已修正內部錯誤（CorrIntErr；Corrected Internal Error）",
    "Header Log Overflow": "標頭記錄溢位（Header Log Overflow）",
    "HdrLogOverflow": "標頭記錄溢位（HdrLogOverflow；Header Log Overflow）",
    "MalformedTLP": "封包格式錯誤（MalformedTLP）",
    "CompletionTimeout": "完成逾時（CompletionTimeout）",
    "ReceiverError": "接收器錯誤（ReceiverError）",
    "Memory Space Disabled": "記憶體空間未啟用（Memory Space Disabled）",
    "Bus Master Disabled": "匯流排主控未啟用（Bus Master Disabled）",
}

_CLASS_NAME_ZH = {
    "Unclassified / Legacy Device": "未分類／舊式裝置（Unclassified / Legacy Device）",
    "Mass Storage Controller": "大量儲存控制器（Mass Storage Controller）",
    "Network Controller": "網路控制器（Network Controller）",
    "Display Controller": "顯示控制器（Display Controller）",
    "Multimedia Device": "多媒體裝置（Multimedia Device）",
    "Memory Controller": "記憶體控制器（Memory Controller）",
    "Bridge Device": "橋接裝置（Bridge Device）",
    "Simple Communication Controller": "簡易通訊控制器（Simple Communication Controller）",
    "Generic System Peripheral": "一般系統週邊（Generic System Peripheral）",
    "Input Device Controller": "輸入裝置控制器（Input Device Controller）",
    "Docking Station": "擴充底座（Docking Station）",
    "Processor": "處理器（Processor）",
    "Serial Bus Controller": "序列匯流排控制器（Serial Bus Controller）",
    "Wireless Controller": "無線控制器（Wireless Controller）",
    "Intelligent I/O Controller": "智慧型 I/O 控制器（Intelligent I/O Controller）",
    "Satellite Communication Controller": "衛星通訊控制器（Satellite Communication Controller）",
    "Encryption/Decryption Controller": "加解密控制器（Encryption/Decryption Controller）",
    "Data Acquisition & Signal Processing Controller": "資料擷取與訊號處理控制器（Data Acquisition & Signal Processing Controller）",
    "Processing Accelerator": "處理加速器（Processing Accelerator）",
    "Non-Essential Instrumentation": "非必要儀器（Non-Essential Instrumentation）",
    "Unassigned / Vendor Specific": "未指定／廠商專屬（Unassigned / Vendor Specific）",
}

_HEADER_TYPE_ZH = {
    HeaderType.TYPE_0_ENDPOINT.name: "端點裝置（TYPE_0_ENDPOINT）",
    HeaderType.TYPE_1_BRIDGE.name: "橋接裝置（TYPE_1_BRIDGE）",
    HeaderType.TYPE_2_CARDBUS.name: "CardBus 裝置（TYPE_2_CARDBUS）",
    HeaderType.UNKNOWN.name: "未知（UNKNOWN）",
}

_CAPABILITY_NAME_ZH = {
    "Power Management (PM)": "電源管理（Power Management；PM）",
    "Vital Product Data (VPD)": "重要產品資料（Vital Product Data；VPD）",
    "Slot Identification": "插槽識別（Slot Identification）",
    "Message Signalled Interrupts (MSI)": "訊息觸發中斷（Message Signalled Interrupts；MSI）",
    "AGP": "AGP（加速繪圖埠；AGP）",
    "PCI-X": "PCI-X 匯流排（PCI-X）",
    "HyperTransport": "HyperTransport 高速互連匯流排（HyperTransport）",
    "CompactPCI HotSwap": "CompactPCI 熱插拔（CompactPCI HotSwap）",
    "CompactPCI Central Resource Control": "CompactPCI 中央資源控制（CompactPCI Central Resource Control）",
    "AGP 8x": "AGP 8x 加速繪圖埠（AGP 8x）",
    "Vendor Specific": "廠商專屬（Vendor Specific）",
    "Debug Port": "除錯埠（Debug Port）",
    "Standard Hot-Plug Controller": "標準熱插拔控制器（Standard Hot-Plug Controller）",
    "Subsystem Vendor/Device ID": "子系統廠商／裝置 ID（Subsystem Vendor/Device ID）",
    "Secure Device": "安全裝置（Secure Device）",
    "PCI Express (PCIe)": "PCI Express（PCIe）",
    "MSI-X": "MSI-X（訊息觸發中斷擴充；MSI-X）",
    "SATA Configuration": "SATA 設定（SATA Configuration）",
    "Advanced Features (AF)": "進階功能（Advanced Features；AF）",
    "Enhanced Allocation (EA)": "增強配置（Enhanced Allocation；EA）",
    "Flattening Portal Bridge (FPB)": "Flattening Portal Bridge（FPB）",
    "Advanced Error Reporting (AER)": "進階錯誤回報（Advanced Error Reporting；AER）",
    "Virtual Channel (VC)": "虛擬通道（Virtual Channel；VC）",
    "Device Serial Number (DSN)": "裝置序號（Device Serial Number；DSN）",
    "Power Budgeting": "電源預算（Power Budgeting）",
    "Root Complex Link Declaration": "Root Complex Link 宣告（Root Complex Link Declaration）",
    "Root Complex Internal Link Control": "Root Complex 內部 Link 控制（Root Complex Internal Link Control）",
    "Root Complex Event Collector Endpoint Association": "Root Complex 事件收集器 Endpoint 關聯（Root Complex Event Collector Endpoint Association）",
    "Multi-Function Virtual Channel": "多功能虛擬通道（Multi-Function Virtual Channel）",
    "Virtual Channel 9": "虛擬通道 9（Virtual Channel 9）",
    "Root Complex Register Block": "Root Complex 暫存器區塊（Root Complex Register Block）",
    "Vendor-Specific Extended Capability (VSEC)": "廠商專屬延伸 Capability（Vendor-Specific Extended Capability；VSEC）",
    "Configuration Access Correlation": "設定存取關聯（Configuration Access Correlation）",
    "Access Control Services (ACS)": "存取控制服務（Access Control Services；ACS）",
    "Alternative Routing-ID Interpretation (ARI)": "替代路由識別碼解讀（Alternative Routing-ID Interpretation；ARI）",
    "Address Translation Services (ATS)": "位址轉譯服務（Address Translation Services；ATS）",
    "Single Root I/O Virtualization (SR-IOV)": "單一根 I/O 虛擬化（Single Root I/O Virtualization；SR-IOV）",
    "Multi-Root I/O Virtualization (MR-IOV)": "多重根 I/O 虛擬化（Multi-Root I/O Virtualization；MR-IOV）",
    "Multicast": "多點傳送（Multicast）",
    "Page Request Interface (PRI)": "頁面請求介面（Page Request Interface；PRI）",
    "Resizable BAR (REBAR)": "可調整 BAR（Resizable BAR；REBAR）",
    "Dynamic Power Allocation (DPA)": "動態電源配置（Dynamic Power Allocation；DPA）",
    "TLP Processing Hints (TPH)": "TLP 處理提示（TLP Processing Hints；TPH）",
    "Latency Tolerance Reporting (LTR)": "延遲容忍度回報（Latency Tolerance Reporting；LTR）",
    "Secondary PCI Express": "次要 PCI Express（Secondary PCI Express）",
    "Protocol Multiplexing (PMUX)": "協定多工（Protocol Multiplexing；PMUX）",
    "Process Address Space ID (PASID)": "程序位址空間識別碼（Process Address Space ID；PASID）",
    "LN Requester (LNR)": "LN Requester（LN 請求端；LNR）",
    "Downstream Port Containment (DPC)": "下游埠隔離（Downstream Port Containment；DPC）",
    "L1 PM Substates (L1SS)": "L1 電源管理子狀態（L1 PM Substates；L1SS）",
    "Precision Time Measurement (PTM)": "精密時間量測（Precision Time Measurement；PTM）",
    "M-PCIe": "M-PCIe（M-PCIe）",
    "Function Readiness Status (FRS)": "函式就緒狀態（Function Readiness Status；FRS）",
    "Readiness Time Reporting (RTR)": "就緒時間回報（Readiness Time Reporting；RTR）",
    "Data Object Exchange (DOE)": "資料物件交換（Data Object Exchange；DOE）",
    "Integrity & Data Encryption (IDE)": "完整性與資料加密（Integrity & Data Encryption；IDE）",
}

_CAPABILITY_FIELD_ZH = {
    "device_type": "裝置類型（device_type）",
    "cap_version": "Capability 版本（cap_version）",
    "dev_ctl": "裝置控制（dev_ctl）",
    "dev_sta": "裝置狀態（dev_sta）",
    "max_payload_size": "最大 Payload 大小（max_payload_size）",
    "max_read_request_size": "最大讀取請求大小（max_read_request_size）",
    "max_link_speed": "最大 Link 速率（max_link_speed）",
    "max_link_width": "最大 Link 寬度（max_link_width）",
    "current_link_speed": "目前 Link 速率（current_link_speed）",
    "current_link_width": "目前 Link 寬度（current_link_width）",
    "is_link_degraded": "Link 是否降級（is_link_degraded）",
    "link_retrain": "連線重新訓練（Link retrain；link_retrain）",
    "is_64bit": "是否 64-bit（is_64bit）",
    "enabled": "是否啟用（enabled）",
    "multiple_msg_enable": "多重訊息啟用數（multiple_msg_enable）",
    "multiple_msg_capable": "多重訊息支援數（multiple_msg_capable）",
    "function_mask": "函式遮罩（function_mask）",
    "table_size": "表格大小（table_size）",
    "evidence": "證據狀態（evidence）",
    "message": "訊息（message）",
    "aer_summary": "AER 摘要（aer_summary）",
    "active_fatal": "作用中致命錯誤數（active_fatal）",
    "active_nonfatal": "作用中非致命錯誤數（active_nonfatal）",
    "active_correctable": "作用中可修正錯誤數（active_correctable）",
}

_CAPABILITY_VALUE_ZH = {
    "PCI Express Endpoint": "PCIe 終端裝置（PCI Express Endpoint）",
    "Legacy PCI Express Endpoint": "舊式 PCIe 終端裝置（Legacy PCI Express Endpoint）",
    "Root Port of PCI Express Root Complex": "PCIe Root Complex 根埠（Root Port of PCI Express Root Complex）",
    "Upstream Port of PCI Express Switch": "PCIe Switch 上游埠（Upstream Port of PCI Express Switch）",
    "Downstream Port of PCI Express Switch": "PCIe Switch 下游埠（Downstream Port of PCI Express Switch）",
    "PCI Express to PCI/PCI-X Bridge": "PCIe 至 PCI/PCI-X 橋接器（PCI Express to PCI/PCI-X Bridge）",
    "PCI/PCI-X to PCI Express Bridge": "PCI/PCI-X 至 PCIe 橋接器（PCI/PCI-X to PCI Express Bridge）",
    "Root Complex Integrated Endpoint": "Root Complex 整合終端（Root Complex Integrated Endpoint）",
    "Root Complex Event Collector": "Root Complex 事件收集器（Root Complex Event Collector）",
}

_TLP_TYPE_ZH = {
    "MRd (Memory Read 3DW)": "記憶體讀取 3DW（MRd；Memory Read 3DW）",
    "MRd (Memory Read 4DW)": "記憶體讀取 4DW（MRd；Memory Read 4DW）",
    "MRdLk (Memory Read Lock 3DW)": "記憶體鎖定讀取 3DW（MRdLk；Memory Read Lock 3DW）",
    "MRdLk (Memory Read Lock 4DW)": "記憶體鎖定讀取 4DW（MRdLk；Memory Read Lock 4DW）",
    "MWr (Memory Write 3DW)": "記憶體寫入 3DW（MWr；Memory Write 3DW）",
    "MWr (Memory Write 4DW)": "記憶體寫入 4DW（MWr；Memory Write 4DW）",
    "IORd (I/O Read)": "I/O 讀取（IORd；I/O Read）",
    "IOWr (I/O Write)": "I/O 寫入（IOWr；I/O Write）",
    "CfgRd0 (Config Read Type 0)": "設定空間讀取 Type 0（CfgRd0；Config Read Type 0）",
    "CfgWr0 (Config Write Type 0)": "設定空間寫入 Type 0（CfgWr0；Config Write Type 0）",
    "CfgRd1 (Config Read Type 1)": "設定空間讀取 Type 1（CfgRd1；Config Read Type 1）",
    "CfgWr1 (Config Write Type 1)": "設定空間寫入 Type 1（CfgWr1；Config Write Type 1）",
    "Cpl (Completion without Data)": "無資料完成（Cpl；Completion without Data）",
    "CplD (Completion with Data)": "含資料完成（CplD；Completion with Data）",
    "CplLk (Completion Lock without Data)": "無資料完成鎖定（CplLk；Completion Lock without Data）",
    "CplDLk (Completion Lock with Data)": "含資料完成鎖定（CplDLk；Completion Lock with Data）",
    "Msg (Message routed to RC)": "路由至 RC 的訊息（Msg；Message routed to RC）",
    "MsgD (Message with Data routed to RC)": "含資料且路由至 RC 的訊息（MsgD；Message with Data routed to RC）",
}


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _localize_root_cause(value: str | None) -> str:
    if not value:
        return ""
    if "\n" in value:
        return "\n".join(_localize_root_cause(line) for line in value.splitlines())
    if _LINK_DEGRADED_RE.fullmatch(value):
        return _localize_link_reason(value)
    translated = _ROOT_CAUSE_GUIDE_ZH.get(value)
    if translated:
        return translated
    if value.startswith("【Root Cause 排查建議】"):
        return value.replace("【Root Cause 排查建議】", "【根因排查建議（Root Cause）】", 1)
    if value.startswith("Linux Kernel AER error event: "):
        token = value.removeprefix("Linux Kernel AER error event: ")
        return f"Linux Kernel AER 事件：{_localize_error_name(token)}"
    if value.startswith("Specific error flag: "):
        token = value.removeprefix("Specific error flag: ")
        return f"特定錯誤旗標：{_localize_error_name(token)}"
    match = _COMMAND_REGISTER_BIT_RE.fullmatch(value)
    if match:
        return f"Command Register Bit {match.group('bit')}（{match.group('field')}）為 0。"
    if value.startswith("Root Cause: "):
        return f"根因：{value.removeprefix('Root Cause: ')}（原始：{value}）"
    if _contains_cjk(value):
        return value
    return f"根因排查指引（原始：{value}）"


def _localize_data_quality_issue(value: str) -> str:
    match = _DEVICE_DUMP_RE.fullmatch(value)
    if match:
        return (
            f"裝置 dump 無法解碼：{match.group('detail')}；來源 bytes 未被解讀為有效 "
            f"PCIe Configuration Space。（原始：{value}）"
        )
    if value.startswith("Device dump could not be decoded: "):
        detail = value.removeprefix("Device dump could not be decoded: ")
        return f"裝置 dump 無法解碼：{detail}（原始：{value}）"
    match = _AER_TRUNCATED_RE.fullmatch(value)
    if match:
        return (
            f"AER Capability 位於 {match.group('offset')}；來源 dump 只有部分結構，"
            f"未包含完整 {match.group('size')} bytes。（原始：{value}）"
        )
    if _contains_cjk(value):
        return value
    return f"資料品質問題（原始：{value}）"


def _localize_class_name(value: str) -> str:
    if not value:
        return ""
    if value in _CLASS_NAME_ZH:
        return _CLASS_NAME_ZH[value]
    match = re.fullmatch(r"Unknown Class (0x[0-9A-Fa-f]+)", value)
    if match:
        return f"未知類別（{value}）"
    if _contains_cjk(value):
        return value
    return f"未知類別（{value}）"


def _localize_header_type(value: HeaderType | str) -> str:
    raw = value.name if isinstance(value, HeaderType) else str(value)
    if raw in _HEADER_TYPE_ZH:
        return _HEADER_TYPE_ZH[raw]
    if _contains_cjk(raw):
        return raw
    return f"未知標頭類型（{raw}）"


def _localize_capability_name(value: str) -> str:
    if not value:
        return ""
    if value in _CAPABILITY_NAME_ZH:
        return _CAPABILITY_NAME_ZH[value]
    match = re.fullmatch(r"Unknown Cap \((0x[0-9A-Fa-f]+)\)", value)
    if match:
        return f"未知 Capability（{value}）"
    match = re.fullmatch(r"Extended Cap (0x[0-9A-Fa-f]+)", value)
    if match:
        return f"未知延伸 Capability（{value}）"
    if _contains_cjk(value):
        return value
    return f"未知 Capability（{value}）"


def _localize_tlp_type(value: str) -> str:
    if value in _TLP_TYPE_ZH:
        return _TLP_TYPE_ZH[value]
    match = _TLP_FALLBACK_RE.fullmatch(value)
    if match:
        return f"未知 TLP 類型（{value}）"
    if _contains_cjk(value):
        return value
    return f"未知 TLP 類型（{value}）"


def _localize_field_name(value: str) -> str:
    if value in _CAPABILITY_FIELD_ZH:
        return _CAPABILITY_FIELD_ZH[value]
    if _contains_cjk(value):
        return value
    return f"欄位（{value}）"


def _localize_decoded_value(key: str, value: object) -> str:
    if isinstance(value, dict):
        parts = [
            f"{_localize_field_name(str(item_key))}: "
            f"{_localize_decoded_value(str(item_key), item_value)}"
            for item_key, item_value in value.items()
        ]
        return "；".join(parts)
    if isinstance(value, bool):
        return f"{'是' if value else '否'}（{value}）"
    if isinstance(value, (int, float)):
        return str(value)
    if key == "message":
        return _localize_data_quality_issue(str(value))
    value_text = str(value)
    if value_text in _CAPABILITY_VALUE_ZH:
        return _CAPABILITY_VALUE_ZH[value_text]
    if value_text.startswith("Unknown ("):
        return f"未知值（{value_text}）"
    if key == "evidence" and value_text == "truncated":
        return "截斷（truncated）"
    if key in {"max_link_speed", "current_link_speed"} or re.fullmatch(
        r"(?:0x[0-9A-Fa-f]+|x\d+|\d+(?:\.\d+)? GT/s \(Gen\d+\))", value_text
    ):
        return value_text
    if _contains_cjk(value_text):
        return value_text
    return f"未知值（{value_text}）"


def _localize_decoded_info(info: dict[str, object]) -> str:
    return (
        "；".join(
            f"{_localize_field_name(str(key))}: {_localize_decoded_value(str(key), value)}"
            for key, value in info.items()
        )
        or "無資料（N/A）"
    )


def _localize_severity(value: str) -> str:
    direct = {
        "Fatal": "致命（Fatal）",
        "Non-Fatal": "非致命（Non-Fatal）",
        "Correctable": "可修正（Correctable）",
        "Uncorrected": "未修正（Uncorrected）",
    }
    if value in direct:
        return direct[value]
    match = _SEVERITY_PAIR_RE.fullmatch(value)
    if match:
        outer = direct.get(match.group("outer"), match.group("outer"))
        inner = direct.get(match.group("inner"), match.group("inner"))
        return f"{outer}／{inner}（{value}）"
    if _contains_cjk(value):
        return value
    return f"未知嚴重度（{value}）"


def _localize_error_name(value: str) -> str:
    if value in _ERROR_NAME_ZH:
        return _ERROR_NAME_ZH[value]
    if _contains_cjk(value):
        return value
    return f"未知 AER 錯誤（{value}）"


def _localize_link_reason(value: str) -> str:
    match = _LINK_DEGRADED_RE.fullmatch(value)
    if not match:
        if _contains_cjk(value):
            return value
        return f"PCIe Link 降級原因（原始：{value}）"
    return (
        f"PCIe Link 降級：目前 {match.group('current')} x{match.group('current_width')}，"
        f"最大能力 {match.group('maximum')} x{match.group('maximum_width')}"
    )


class PCIeReporter:
    @staticmethod
    def localize_class_name(value: str) -> str:
        """Return a Chinese-first PCI class label for GUI and CLI callers."""
        return _localize_class_name(value)

    @staticmethod
    def localize_header_type(value: HeaderType | str) -> str:
        """Return a Chinese-first configuration-space header type label."""
        return _localize_header_type(value)

    @staticmethod
    def localize_link_reason(value: str) -> str:
        """Return a Chinese-first link health explanation for GUI callers."""
        return _localize_link_reason(value)

    @staticmethod
    def to_markdown(cfg: PCIeConfigSpace) -> str:
        lines: list[str] = []
        bdf_str = cfg.bdf or "N/A"
        lines.append(f"# PCIe 診斷報告（PCIe Diagnostic Report；BDF: {bdf_str}）\n")
        if cfg.data_quality_issues:
            lines.append("## 資料品質限制（Data Quality Limitations）")
            lines.extend(
                f"- {_localize_data_quality_issue(issue)}" for issue in cfg.data_quality_issues
            )
            lines.append("")
            if len(cfg.raw_data) < 64:
                lines.extend(
                    [
                        "## 解碼狀態（Decode Status）",
                        "- 來源資料不足以建立 PCIe Configuration Space；以下不填入預設的 0 值，避免誤判為硬體回報。",
                        "- 請提供至少 64 bytes 的完整 hex dump，再重新執行分析。",
                        "",
                    ]
                )
                return "\n".join(lines)
        lines.append("## 1. 裝置識別與基礎設定（Device Identification & Base Configuration）")
        lines.append(
            f"- **廠商 ID／裝置 ID（Vendor ID／Device ID）**: "
            f"`0x{cfg.vendor_id:04X}` / `0x{cfg.device_id:04X}`"
        )
        class_name = (
            _localize_class_name(cfg.class_name) if cfg.class_name else "未知類別（Unavailable）"
        )
        lines.append(
            f"- **類別碼（Class Code）**: `0x{cfg.base_class:02X}{cfg.sub_class:02X}{cfg.prog_if:02X}` "
            f"({class_name})"
        )
        lines.append(f"- **修訂識別碼（Revision ID）**: `0x{cfg.revision_id:02X}`")
        lines.append(
            f"- **標頭類型（Header Type）**: `{_localize_header_type(cfg.header_type)}` "
            f"（多功能（Multi-Function）: `{cfg.is_multi_function}`）"
        )
        lines.append(
            f"- **命令暫存器（Command Register）**: `0x{cfg.command:04X}` "
            f"（MSE: `{bool(cfg.command & 0x02)}`, BME: `{bool(cfg.command & 0x04)}`, "
            f"IOSE: `{bool(cfg.command & 0x01)}`）"
        )
        lines.append(
            f"- **狀態暫存器（Status Register）**: `0x{cfg.status:04X}` "
            f"（CapList: `{bool(cfg.status & 0x10)}`, MasterDataParity: `{bool(cfg.status & 0x8000)}`）"
        )
        lines.append("")

        if cfg.link_info:
            lines.append(
                "## 2. PCIe 連線協商與速率／寬度健康度（PCIe Link Negotiation & Speed/Width Health）"
            )
            lines.append(
                f"- **最大能力（Maximum Capable）**: "
                f"`{cfg.link_info.max_speed_str} x{cfg.link_info.max_width}`"
            )
            lines.append(
                f"- **協商狀態（Negotiated Status）**: "
                f"`{cfg.link_info.current_speed_str} x{cfg.link_info.current_width}`"
            )
            if cfg.link_info.is_degraded:
                lines.append(
                    f"- **連線健康度（Link Health）**: `🚨 已降級（DEGRADED）` "
                    f"({_localize_link_reason(cfg.link_info.degradation_reason)})"
                )
                lines.append(
                    f"\n```text\n{_localize_root_cause(cfg.link_info.root_cause_guide)}\n```\n"
                )
            else:
                lines.append(
                    "- **連線健康度（Link Health）**: `✔ 最佳（OPTIMAL）` （以設計的最大能力運作）"
                )
            lines.append("")

        if cfg.header_type == HeaderType.TYPE_0_ENDPOINT:
            lines.append("## 3. 基礎位址暫存器（Base Address Registers；BAR 0 - 5）")
            lines.append(
                "| BAR 索引（BAR Index） | 類型（Type） | 64-bit | 可預取（Prefetchable） | "
                "基礎位址（Base Address） | 原始十六進位（Raw Hex） |"
            )
            lines.append("|---|---|---|---|---|---|")
            for bar in cfg.bars:
                type_str = "I/O 空間（I/O Space）" if bar.is_io else "記憶體空間（Memory Space）"
                lines.append(
                    f"| BAR{bar.index} | {type_str} | {bar.is_64bit} | {bar.is_prefetchable} | `0x{bar.base_address:016X}` | `0x{bar.raw_value:08X}` |"
                )
            lines.append("")
        elif cfg.header_type == HeaderType.TYPE_1_BRIDGE and cfg.bridge_bus:
            b = cfg.bridge_bus
            lines.append("## 3. 第 1 類 PCI 橋接器設定（Type 1 PCI-to-PCI Bridge Configuration）")
            lines.append(
                f"- **主要／次要／從屬匯流排（Primary／Secondary／Subordinate Bus）**: "
                f"`{b.primary_bus}` / `{b.secondary_bus}` / `{b.subordinate_bus}`"
            )
            lines.append(
                f"- **記憶體視窗（Memory Window）**: `0x{b.mem_base:08X}` - `0x{b.mem_limit:08X}`"
            )
            lines.append(
                f"- **可預取記憶體視窗（Prefetchable Memory Window）**: "
                f"`0x{b.pref_mem_base:08X}` - `0x{b.pref_mem_limit:08X}`"
            )
            lines.append(
                f"- **I/O 視窗（I/O Window）**: `0x{b.io_base:04X}` - `0x{b.io_limit:04X}`"
            )
            lines.append("")

        lines.append("## 4. 標準 PCI Capabilities（Standard PCI Capabilities；0x34 Linked List）")
        if cfg.standard_capabilities:
            lines.append(
                "| 位移（Offset） | 能力 ID（Cap ID） | 名稱（Name） | 下一個位移（Next Offset） | "
                "關鍵參數（Key Parameters） |"
            )
            lines.append("|---|---|---|---|---|")
            for cap in cfg.standard_capabilities:
                info_summary = _localize_decoded_info(cap.decoded_info)
                lines.append(
                    f"| `0x{cap.offset:02X}` | `0x{cap.cap_id:02X}` | "
                    f"{_localize_capability_name(cap.name)} | `0x{cap.next_offset:02X}` | "
                    f"{info_summary} |"
                )
        else:
            lines.append("*找不到標準 Capabilities（No Standard Capabilities found.）*")
        lines.append("")

        lines.append(
            "## 5. PCI Express 延伸 Capabilities（Extended Capabilities；0x100 Linked List）"
        )
        if cfg.extended_capabilities:
            lines.append(
                "| 位移（Offset） | 延伸能力 ID（Ext Cap ID） | 版本（Version） | 名稱（Name） | "
                "下一個位移（Next Offset） |"
            )
            lines.append("|---|---|---|---|---|")
            for ext in cfg.extended_capabilities:
                lines.append(
                    f"| `0x{ext.offset:03X}` | `0x{ext.ext_cap_id:04X}` | v{ext.version} | "
                    f"{_localize_capability_name(ext.name)} | `0x{ext.next_offset:03X}` |"
                )
        else:
            lines.append("*找不到延伸 Capabilities（No Extended Capabilities found.）*")
        lines.append("")

        lines.append("## 6. AER（Advanced Error Reporting）深入分析（In-Depth Analysis）")
        if cfg.aer_analysis:
            aer = cfg.aer_analysis
            lines.append(f"- **AER 能力位移（AER Capability Offset）**: `0x{aer.offset:03X}`")
            lines.append(
                f"- **不可修正錯誤狀態／遮罩／嚴重度（Uncorrectable Error Status / Mask / Severity）**: "
                f"`0x{aer.uncorr_status_raw:08X}` / `0x{aer.uncorr_mask_raw:08X}` / "
                f"`0x{aer.uncorr_severity_raw:08X}`"
            )
            lines.append(
                f"- **可修正錯誤狀態／遮罩（Correctable Error Status / Mask）**: "
                f"`0x{aer.corr_status_raw:08X}` / `0x{aer.corr_mask_raw:08X}`"
            )
            lines.append(
                f"- **作用中的不可修正錯誤（Active Uncorrectable Errors）**: "
                f"致命（Fatal）: `{aer.active_uncorr_fatal_count}`、"
                f"非致命（Non-Fatal）: `{aer.active_uncorr_nonfatal_count}`"
            )
            lines.append(
                f"- **作用中的可修正錯誤（Active Correctable Errors）**: `{aer.active_corr_count}`"
            )
            lines.append("")

            active_uncorr = [e for e in aer.uncorr_errors if e.is_active]
            if active_uncorr:
                lines.append(
                    "### 作用中的不可修正錯誤與根因指引（Active Uncorrectable Errors & Root Cause Guidance）"
                )
                for err in active_uncorr:
                    masked_tag = "（已遮罩；MASKED）" if err.is_masked else ""
                    lines.append(
                        f"#### [{_localize_severity(err.severity)}] {_localize_error_name(err.name)}"
                        f"（Bit {err.bit_pos}）{masked_tag}"
                    )
                    if err.root_cause_guide:
                        lines.append(
                            f"\n```text\n{_localize_root_cause(err.root_cause_guide)}\n```\n"
                        )
                lines.append("")

            active_corr = [e for e in aer.corr_errors if e.is_active]
            if active_corr:
                lines.append("### 作用中的可修正錯誤（Active Correctable Errors）")
                for corr_err in active_corr:
                    masked_tag = "（已遮罩；MASKED）" if corr_err.is_masked else ""
                    lines.append(
                        f"#### {_localize_error_name(corr_err.name)}（Bit {corr_err.bit_pos}）{masked_tag}"
                    )
                    if corr_err.root_cause_guide:
                        lines.append(
                            f"\n```text\n{_localize_root_cause(corr_err.root_cause_guide)}\n```\n"
                        )
                lines.append("")

            if aer.decoded_tlp:
                tlp = aer.decoded_tlp
                lines.append("### 故障交易 TLP Header Log 解碼（Faulting Transaction）")
                raw_dw = list(tlp.raw_dw[:4])
                raw_dw_text = " ".join(
                    f"0x{word:08X}" if isinstance(word, int) else "n/a" for word in raw_dw
                )
                if len(raw_dw) < 4:
                    raw_dw_text += " " + " ".join("n/a" for _ in range(4 - len(raw_dw)))
                lines.append(f"- **原始 DW[0..3]（Raw DW[0..3]）**: `{raw_dw_text}`")
                lines.append(
                    f"- **TLP 封包類型（TLP Packet Type）**: `{_localize_tlp_type(tlp.type_name)}` "
                    f"（Fmt: `0x{tlp.fmt:X}`, Type: `0x{tlp.type_:02X}`）"
                )
                lines.append(f"- **長度（Length）**: `{tlp.length}` DW（{tlp.length * 4} Bytes）")
                lines.append(
                    f"- **流量類別（Traffic Class；TC）**: `{tlp.tc}`、"
                    f"**摘要（Digest；TD）**: `{tlp.td}`、"
                    f"**毒化（Poisoned；EP）**: `{tlp.ep}`"
                )
                if tlp.requester_id is not None:
                    req_b = (tlp.requester_id >> 8) & 0xFF
                    req_df = tlp.requester_id & 0xFF
                    tag_text = f"0x{tlp.tag:02X}" if isinstance(tlp.tag, int) else "n/a"
                    lines.append(
                        f"- **Requester ID（請求端識別碼）**: `0x{tlp.requester_id:04X}` "
                        f"（匯流排（Bus）:{req_b:02X}, 裝置（Dev）:{req_df >> 3:02X}, "
                        f"函式（Func）:{req_df & 0x7:X}）、**標籤（Tag）**: `{tag_text}`"
                        f"（原始欄位 Tag**: `{tag_text}`）"
                    )
                if tlp.address is not None:
                    lines.append(f"- **Target Address（目標位址）**: `0x{tlp.address:016X}`")
                if tlp.completer_id is not None:
                    lines.append(
                        f"- **Completer ID（完成端識別碼）**: `0x{tlp.completer_id:04X}`、"
                        f"**Completion Status（完成狀態）**: `{tlp.completion_status}`"
                    )
                lines.append("")
        else:
            lines.append(
                "*找不到 AER Extended Capability（Configuration Space 未偵測到 AER Extended Capability）。*\n"
            )
        return "\n".join(lines)

    @staticmethod
    def format_dmesg_events(events: list[DmesgAEREvent]) -> str:
        if not events:
            return (
                "dmesg 中找不到 PCIe AER 錯誤事件（No PCIe AER error events found in dmesg log.）"
            )
        lines = ["# Linux 核心 dmesg AER 診斷報告（Linux Kernel dmesg AER Diagnostic Report）\n"]
        for idx, ev in enumerate(events, 1):
            ts_str = f"[{ev.timestamp}] " if ev.timestamp else ""
            lines.append(
                f"## 事件 {idx}（Event {idx}）：{ts_str}裝置 {ev.bdf} - "
                f"{_localize_error_name(ev.error_name)} "
                f"（{_localize_severity(ev.severity)}）"
            )
            lines.append(f"- **原始日誌（Raw Log）**: `{ev.raw_line}`")
            if ev.tlp_header:
                lines.append(f"- **擷取到的 TLP Header（Captured TLP Header）**: `{ev.tlp_header}`")
            lines.append(f"\n```text\n{_localize_root_cause(ev.root_cause_guide)}\n```\n")
        return "\n".join(lines)
