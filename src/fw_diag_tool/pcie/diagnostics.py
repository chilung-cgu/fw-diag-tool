from __future__ import annotations

from typing import Any

from .models import PCIeConfigSpace

ROOT_CAUSE_GUIDES: dict[str, str] = {
    "CompTimeout": "Completion Timeout (CTO): Requester did not receive completion in time.",
    "Completion Timeout": "Completion Timeout (CTO): Requester did not receive completion in time.",
    "UR": "Unsupported Request (UR): Target received unsupported or out-of-range TLP.",
    "Unsupported Request": "Unsupported Request (UR): Target received unsupported or out-of-range TLP.",
    "MalformedTLP": "Malformed TLP: Violation of Transaction Layer packet framing or length.",
    "Malformed TLP": "Malformed TLP: Violation of Transaction Layer packet framing or length.",
    "PoisonedTLP": "Poisoned TLP: Data parity or error bit EP is set in received TLP.",
    "Poisoned TLP": "Poisoned TLP: Data parity or error bit EP is set in received TLP.",
    "SurpriseDown": "Surprise Down: PCIe Link went down unexpectedly without software handshake.",
    "Surprise Down": "Surprise Down: PCIe Link went down unexpectedly without software handshake.",
    "ReceiverError": "Receiver Error: Physical layer 8b/10b or 128b/130b decode error or framing error.",
    "Receiver Error": "Receiver Error: Physical layer 8b/10b or 128b/130b decode error or framing error.",
    "BadTLP": "Bad TLP: LCRC check failed in Data Link layer, triggering replay.",
    "Bad TLP": "Bad TLP: LCRC check failed in Data Link layer, triggering replay."
}


def get_root_cause_guide(error_name: str) -> str | None:
    for key, guide in ROOT_CAUSE_GUIDES.items():
        if key.lower() in error_name.lower():
            return guide
    return None


def diagnose_pcie_device(dev: PCIeConfigSpace) -> list[dict[str, Any]]:
    findings = []
    aer = getattr(dev, "aer_analysis", None) or getattr(dev, "aer", None)
    if aer:
        for err in aer.uncorr_errors:
            if err.is_active:
                findings.append({
                    "type": "AER_UNCORRECTABLE",
                    "severity": "CRITICAL" if err.severity == "Fatal" else "ERROR",
                    "name": err.name,
                    "guide": err.root_cause_guide or get_root_cause_guide(err.name)
                })
        for err in aer.corr_errors:
            if err.is_active:
                findings.append({
                    "type": "AER_CORRECTABLE",
                    "severity": "WARNING",
                    "name": err.name,
                    "guide": err.root_cause_guide or get_root_cause_guide(err.name)
                })

    mem_enable = bool(dev.command & (1 << 1))
    bus_master = bool(dev.command & (1 << 2))
    if not mem_enable:
        findings.append({
            "type": "CONFIG_WARNING",
            "severity": "INFO",
            "name": "Memory Space Disabled",
            "guide": "Command Register Bit 1 (MSE) is 0."
        })
    if not bus_master:
        findings.append({
            "type": "CONFIG_WARNING",
            "severity": "INFO",
            "name": "Bus Master Disabled",
            "guide": "Command Register Bit 2 (BME) is 0."
        })

    if dev.link_info and dev.link_info.is_degraded:
        findings.append({
            "type": "LINK_DEGRADED",
            "severity": "WARNING",
            "name": "PCIe Link Degraded",
            "guide": dev.link_info.degradation_reason + "\n" + dev.link_info.root_cause_guide
        })

    return findings
