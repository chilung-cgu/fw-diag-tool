from fw_diag_tool.pcie.parser import PCIeAnalyzer
from fw_diag_tool.pcie.reporter import PCIeReporter


def test_pcie_link_degradation_detection():
    # Construct a dummy 256-byte config space with PCIe Cap at 0x40
    raw = bytearray(256)
    # Vendor/Dev: 0x10EE / 0x7024
    raw[0:4] = bytes([0xEE, 0x10, 0x24, 0x70])
    # Status: Cap list present (0x0010)
    raw[6] = 0x10
    # Cap pointer -> 0x40
    raw[0x34] = 0x40
    # Cap ID: 0x10 (PCIe Cap), Next: 0x00
    raw[0x40] = 0x10
    raw[0x41] = 0x00
    # Link Capabilities (Offset 0x40 + 12 = 0x4C): Max Gen4 (4), Width x16 (16 << 4 = 0x100) -> 0x00000104
    raw[0x4C] = 0x04
    raw[0x4D] = 0x01
    # Link Status (Offset 0x40 + 18 = 0x52): Operating at Gen3 (3), Width x8 (8 << 4 = 0x80) -> 0x0083
    raw[0x52] = 0x83
    raw[0x53] = 0x00

    cfg = PCIeAnalyzer.decode_config_space(bytes(raw), bdf="0000:01:00.0")
    assert cfg.link_info is not None
    assert cfg.link_info.max_speed_str == "16.0 GT/s (Gen4)"
    assert cfg.link_info.max_width == 16
    assert cfg.link_info.current_speed_str == "8.0 GT/s (Gen3)"
    assert cfg.link_info.current_width == 8
    assert cfg.link_info.is_degraded is True
    assert "PCIe Link Degraded" in cfg.link_info.degradation_reason
    md = PCIeReporter.to_markdown(cfg)
    assert "DEGRADED" in md

def test_multi_lspci_parsing():
    text = """0000:00:00.0 Host bridge: Intel Corporation Device 1234
00: 86 80 34 12 06 00 10 00 00 00 00 06 00 00 00 00
10: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
20: 00 00 00 00 00 00 00 00 00 00 00 00 86 80 34 12
30: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

0000:01:00.0 Processing accelerators: Xilinx Corporation Device 7024
00: ee 10 24 70 06 00 10 00 01 00 80 12 00 00 00 00
10: 0c 00 00 f0 00 00 00 00 00 00 00 00 00 00 00 00
20: 00 00 00 00 00 00 00 00 00 00 00 00 ee 10 24 70
30: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
"""
    devices = PCIeAnalyzer.parse_multi_lspci_text(text)
    assert len(devices) == 2
    assert devices[0].vendor_id == 0x8086
    assert devices[1].vendor_id == 0x10EE