PCI_CAP_ID_PM = 0x01
PCI_CAP_ID_AGP = 0x02
PCI_CAP_ID_VPD = 0x03
PCI_CAP_ID_SLOTID = 0x04
PCI_CAP_ID_MSI = 0x05
PCI_CAP_ID_CHSWP = 0x06
PCI_CAP_ID_PCIX = 0x07
PCI_CAP_ID_HT = 0x08
PCI_CAP_ID_VNDR = 0x09
PCI_CAP_ID_DBG = 0x0A
PCI_CAP_ID_CCRC = 0x0B
PCI_CAP_ID_SHPC = 0x0C
PCI_CAP_ID_SSVID = 0x0D
PCI_CAP_ID_AGP3 = 0x0E
PCI_CAP_ID_SECDEV = 0x0F
PCI_CAP_ID_EXP = 0x10
PCI_CAP_ID_MSIX = 0x11
PCI_CAP_ID_SATA = 0x12
PCI_CAP_ID_AF = 0x13
PCI_CAP_ID_EA = 0x14
PCI_CAP_ID_FPB = 0x15

PCI_CAP_NAMES = {
    PCI_CAP_ID_PM: "Power Management (PM)",
    PCI_CAP_ID_AGP: "AGP",
    PCI_CAP_ID_VPD: "Vital Product Data (VPD)",
    PCI_CAP_ID_SLOTID: "Slot Identification",
    PCI_CAP_ID_MSI: "Message Signalled Interrupts (MSI)",
    PCI_CAP_ID_CHSWP: "CompactPCI HotSwap",
    PCI_CAP_ID_PCIX: "PCI-X",
    PCI_CAP_ID_HT: "HyperTransport",
    PCI_CAP_ID_VNDR: "Vendor Specific",
    PCI_CAP_ID_DBG: "Debug Port",
    PCI_CAP_ID_CCRC: "CompactPCI Central Resource Control",
    PCI_CAP_ID_SHPC: "Standard Hot-Plug Controller",
    PCI_CAP_ID_SSVID: "Subsystem Vendor/Device ID",
    PCI_CAP_ID_AGP3: "AGP 8x",
    PCI_CAP_ID_SECDEV: "Secure Device",
    PCI_CAP_ID_EXP: "PCI Express (PCIe)",
    PCI_CAP_ID_MSIX: "MSI-X",
    PCI_CAP_ID_SATA: "SATA Configuration",
    PCI_CAP_ID_AF: "Advanced Features (AF)",
    PCI_CAP_ID_EA: "Enhanced Allocation (EA)",
    PCI_CAP_ID_FPB: "Flattening Portal Bridge (FPB)",
}

PCI_EXT_CAP_ID_AER = 0x0001
PCI_EXT_CAP_ID_VC = 0x0002
PCI_EXT_CAP_ID_DSN = 0x0003
PCI_EXT_CAP_ID_PWR = 0x0004
PCI_EXT_CAP_ID_RCLINK = 0x0005
PCI_EXT_CAP_ID_RCINT = 0x0006
PCI_EXT_CAP_ID_RCECC = 0x0007
PCI_EXT_CAP_ID_MFVC = 0x0008
PCI_EXT_CAP_ID_VC9 = 0x0009
PCI_EXT_CAP_ID_RCRB = 0x000A
PCI_EXT_CAP_ID_VNDR = 0x000B
PCI_EXT_CAP_ID_CAC = 0x000C
PCI_EXT_CAP_ID_ACS = 0x000D
PCI_EXT_CAP_ID_ARI = 0x000E
PCI_EXT_CAP_ID_ATS = 0x000F
PCI_EXT_CAP_ID_SRIOV = 0x0010
PCI_EXT_CAP_ID_MRIOV = 0x0011
PCI_EXT_CAP_ID_MCAST = 0x0012
PCI_EXT_CAP_ID_PRI = 0x0013
PCI_EXT_CAP_ID_REBAR = 0x0015
PCI_EXT_CAP_ID_DPA = 0x0016
PCI_EXT_CAP_ID_TPH = 0x0017
PCI_EXT_CAP_ID_LTR = 0x0018
PCI_EXT_CAP_ID_SECPCI = 0x0019
PCI_EXT_CAP_ID_PMUX = 0x001A
PCI_EXT_CAP_ID_PASID = 0x001B
PCI_EXT_CAP_ID_LNR = 0x001C
PCI_EXT_CAP_ID_DPC = 0x001D
PCI_EXT_CAP_ID_L1SS = 0x001E
PCI_EXT_CAP_ID_PTM = 0x001F
PCI_EXT_CAP_ID_MPCI = 0x0020
PCI_EXT_CAP_ID_FRSQ = 0x0021
PCI_EXT_CAP_ID_RTR = 0x0022
PCI_EXT_CAP_ID_DOE = 0x002E
PCI_EXT_CAP_ID_IDE = 0x0030

PCI_EXT_CAP_NAMES = {
    PCI_EXT_CAP_ID_AER: "Advanced Error Reporting (AER)",
    PCI_EXT_CAP_ID_VC: "Virtual Channel (VC)",
    PCI_EXT_CAP_ID_DSN: "Device Serial Number (DSN)",
    PCI_EXT_CAP_ID_PWR: "Power Budgeting",
    PCI_EXT_CAP_ID_RCLINK: "Root Complex Link Declaration",
    PCI_EXT_CAP_ID_RCINT: "Root Complex Internal Link Control",
    PCI_EXT_CAP_ID_RCECC: "Root Complex Event Collector Endpoint Association",
    PCI_EXT_CAP_ID_MFVC: "Multi-Function Virtual Channel",
    PCI_EXT_CAP_ID_VC9: "Virtual Channel 9",
    PCI_EXT_CAP_ID_RCRB: "Root Complex Register Block",
    PCI_EXT_CAP_ID_VNDR: "Vendor-Specific Extended Capability (VSEC)",
    PCI_EXT_CAP_ID_CAC: "Configuration Access Correlation",
    PCI_EXT_CAP_ID_ACS: "Access Control Services (ACS)",
    PCI_EXT_CAP_ID_ARI: "Alternative Routing-ID Interpretation (ARI)",
    PCI_EXT_CAP_ID_ATS: "Address Translation Services (ATS)",
    PCI_EXT_CAP_ID_SRIOV: "Single Root I/O Virtualization (SR-IOV)",
    PCI_EXT_CAP_ID_MRIOV: "Multi-Root I/O Virtualization (MR-IOV)",
    PCI_EXT_CAP_ID_MCAST: "Multicast",
    PCI_EXT_CAP_ID_PRI: "Page Request Interface (PRI)",
    PCI_EXT_CAP_ID_REBAR: "Resizable BAR (REBAR)",
    PCI_EXT_CAP_ID_DPA: "Dynamic Power Allocation (DPA)",
    PCI_EXT_CAP_ID_TPH: "TLP Processing Hints (TPH)",
    PCI_EXT_CAP_ID_LTR: "Latency Tolerance Reporting (LTR)",
    PCI_EXT_CAP_ID_SECPCI: "Secondary PCI Express",
    PCI_EXT_CAP_ID_PMUX: "Protocol Multiplexing (PMUX)",
    PCI_EXT_CAP_ID_PASID: "Process Address Space ID (PASID)",
    PCI_EXT_CAP_ID_LNR: "LN Requester (LNR)",
    PCI_EXT_CAP_ID_DPC: "Downstream Port Containment (DPC)",
    PCI_EXT_CAP_ID_L1SS: "L1 PM Substates (L1SS)",
    PCI_EXT_CAP_ID_PTM: "Precision Time Measurement (PTM)",
    PCI_EXT_CAP_ID_MPCI: "M-PCIe",
    PCI_EXT_CAP_ID_FRSQ: "Function Readiness Status (FRS)",
    PCI_EXT_CAP_ID_RTR: "Readiness Time Reporting (RTR)",
    PCI_EXT_CAP_ID_DOE: "Data Object Exchange (DOE)",
    PCI_EXT_CAP_ID_IDE: "Integrity & Data Encryption (IDE)",
}

AER_UNCORR_BITS = {
    4: ("Data Link Protocol Error", "DLP"),
    5: ("Surprise Down Error", "SurpriseDown"),
    12: ("Poisoned TLP Received", "PoisonedTLP"),
    13: ("Flow Control Protocol Error", "FCP"),
    14: ("Completion Timeout", "CompTimeout"),
    15: ("Completer Abort", "CompAbort"),
    16: ("Unexpected Completion", "UnexpComp"),
    17: ("Receiver Overflow", "RxOverflow"),
    18: ("Malformed TLP", "MalformedTLP"),
    19: ("ECRC Error", "ECRC"),
    20: ("Unsupported Request Error", "UR"),
    21: ("ACS Violation", "ACSViolation"),
    22: ("Uncorrectable Internal Error", "UncorrIntErr"),
    23: ("MC Blocked TLP", "MCBlockedTLP"),
    24: ("AtomicOp Egress Blocked", "AtomicOpBlocked"),
    25: ("TLP Prefix Blocked Error", "TLPPrefixBlocked"),
    26: ("Poisoned TLP Egress Blocked", "PoisonedEgressBlocked"),
}

AER_CORR_BITS = {
    0: ("Receiver Error", "RxErr"),
    6: ("Bad TLP", "BadTLP"),
    7: ("Bad DLLP", "BadDLLP"),
    8: ("Replay Number Rollover", "ReplayNumRollover"),
    12: ("Replay Timer Timeout", "ReplayTimeout"),
    13: ("Advisory Non-Fatal Error", "AdvisoryNonFatal"),
    14: ("Corrected Internal Error", "CorrIntErr"),
    15: ("Header Log Overflow", "HdrLogOverflow"),
}

PCI_BASE_CLASSES = {
    0x00: "Unclassified / Legacy Device",
    0x01: "Mass Storage Controller",
    0x02: "Network Controller",
    0x03: "Display Controller",
    0x04: "Multimedia Device",
    0x05: "Memory Controller",
    0x06: "Bridge Device",
    0x07: "Simple Communication Controller",
    0x08: "Generic System Peripheral",
    0x09: "Input Device Controller",
    0x0A: "Docking Station",
    0x0B: "Processor",
    0x0C: "Serial Bus Controller",
    0x0D: "Wireless Controller",
    0x0E: "Intelligent I/O Controller",
    0x0F: "Satellite Communication Controller",
    0x10: "Encryption/Decryption Controller",
    0x11: "Data Acquisition & Signal Processing Controller",
    0x12: "Processing Accelerator",
    0x13: "Non-Essential Instrumentation",
    0xFF: "Unassigned / Vendor Specific",
}