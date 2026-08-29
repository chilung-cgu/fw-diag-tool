import struct
import unittest

from fw_diag_tool.pcie import HeaderType, PCIeAnalyzer, PCIeReporter
from fw_diag_tool.resources import load_pcie_lspci_sample


class TestPCIeAnalyzer(unittest.TestCase):
    def setUp(self):
        # Build synthetic 4096-byte PCIe Config Space with AER, MSI, and PCIe Cap
        buf = bytearray(4096)

        # 0x00: Vendor ID = 0x10EE (Xilinx), Device ID = 0x7024
        struct.pack_into("<HH", buf, 0x00, 0x10EE, 0x7024)
        # 0x04: Command = 0x0006 (BME | MSE), Status = 0x0010 (Capabilities List)
        struct.pack_into("<HH", buf, 0x04, 0x0006, 0x0010)
        # 0x08: Rev ID = 0x01, Prog IF = 0x00, SubClass = 0x80, BaseClass = 0x12 (Processing Accelerator)
        struct.pack_into("<BBBB", buf, 0x08, 0x01, 0x00, 0x80, 0x12)
        # 0x0C: Header Type = 0x00 (Endpoint), BIST = 0
        struct.pack_into("<BBBB", buf, 0x0C, 0x10, 0x00, 0x00, 0x00)

        # 0x10: BAR0 64-bit Prefetchable Memory @ 0x80000000_00000000
        # Low DW = 0x0000000C (64-bit=1, Pref=1)
        struct.pack_into("<II", buf, 0x10, 0x0000000C, 0x80000000)

        # 0x2C: Subsystem Vendor = 0x10EE, Subsystem Device = 0x0007
        struct.pack_into("<HH", buf, 0x2C, 0x10EE, 0x0007)
        # 0x34: Cap Pointer = 0x40
        buf[0x34] = 0x40

        # Cap @ 0x40: MSI (ID=0x05), Next=0x60
        struct.pack_into("<BBH", buf, 0x40, 0x05, 0x60, 0x0081)  # MSI Enabled, 64-bit

        # Cap @ 0x60: PCIe Cap (ID=0x10), Next=0x00
        struct.pack_into("<BBH", buf, 0x60, 0x10, 0x00, 0x0002)  # Endpoint, Gen2
        # DevCtl (offset 0x68) = MPS 256B (bit 5:7 = 001b -> 0x0020)
        struct.pack_into("<HH", buf, 0x68, 0x0020, 0x0000)
        # LinkSta (offset 0x72) = x8 Gen3 (0x0083)
        struct.pack_into("<HH", buf, 0x70, 0x0000, 0x0083)

        # Ext Cap @ 0x100: AER (ID=0x0001, Ver=1, Next=0x180)
        ext_hdr = 0x0001 | (1 << 16) | (0x180 << 20)
        struct.pack_into("<I", buf, 0x100, ext_hdr)

        # AER Uncorr Status @ 0x104: Completion Timeout (bit 14 = 0x00004000) & Malformed TLP (bit 18 = 0x00040000)
        struct.pack_into("<I", buf, 0x104, 0x00044000)
        # AER Uncorr Mask @ 0x108: 0x00000000
        struct.pack_into("<I", buf, 0x108, 0x00000000)
        # AER Uncorr Severity @ 0x10C: Malformed is Fatal (bit 18 = 0x00040000), CTO is Non-Fatal (bit 14 = 0)
        struct.pack_into("<I", buf, 0x10C, 0x00040000)

        # AER Corr Status @ 0x110: Bad TLP (bit 6 = 0x00000040)
        struct.pack_into("<I", buf, 0x110, 0x00000040)

        # AER Header Log @ 0x11C - 0x128 (4 DWs)
        # DW0: 0x00000001 -> MRd 3DW, Length 1 DW
        # DW1: 0x0100000F -> Requester BDF 01:00.0, Tag 0, First BE = 0xF
        # DW2: 0xFE000000 -> Target Address 0xFE000000
        # DW3: 0x00000000
        struct.pack_into("<IIII", buf, 0x11C, 0x00000001, 0x0100000F, 0xFE000000, 0x00000000)

        # Ext Cap @ 0x180: DSN (ID=0x0003, Ver=1, Next=0x000)
        ext_hdr_dsn = 0x0003 | (1 << 16) | (0x000 << 20)
        struct.pack_into("<I", buf, 0x180, ext_hdr_dsn)

        self.raw_bytes = bytes(buf)

    def test_config_space_decoding(self):
        cfg = PCIeAnalyzer.decode_config_space(self.raw_bytes, bdf="0000:01:00.0")
        self.assertEqual(cfg.vendor_id, 0x10EE)
        self.assertEqual(cfg.device_id, 0x7024)
        self.assertEqual(cfg.header_type, HeaderType.TYPE_0_ENDPOINT)
        self.assertEqual(len(cfg.bars), 1)
        self.assertTrue(cfg.bars[0].is_64bit)
        self.assertEqual(cfg.bars[0].base_address, 0x8000000000000000)

    def test_capabilities(self):
        cfg = PCIeAnalyzer.decode_config_space(self.raw_bytes)
        cap_ids = [c.cap_id for c in cfg.standard_capabilities]
        self.assertIn(0x05, cap_ids)  # MSI
        self.assertIn(0x10, cap_ids)  # PCIe Cap

        ext_ids = [e.ext_cap_id for e in cfg.extended_capabilities]
        self.assertIn(0x0001, ext_ids)  # AER
        self.assertIn(0x0003, ext_ids)  # DSN

    def test_aer_analysis(self):
        cfg = PCIeAnalyzer.decode_config_space(self.raw_bytes)
        aer = cfg.aer_analysis
        self.assertIsNotNone(aer)
        assert aer is not None
        self.assertEqual(aer.active_uncorr_fatal_count, 1)  # Malformed TLP
        self.assertEqual(aer.active_uncorr_nonfatal_count, 1)  # CompTimeout
        self.assertEqual(aer.active_corr_count, 1)  # Bad TLP

        # Check Decoded TLP Header
        tlp = aer.decoded_tlp
        self.assertIsNotNone(tlp)
        assert tlp is not None
        self.assertEqual(tlp.type_name, "MRd (Memory Read 3DW)")
        self.assertEqual(tlp.length, 1)
        self.assertEqual(tlp.address, 0xFE000000)
        self.assertEqual(tlp.requester_id, 0x0100)

    def test_lspci_text_parsing(self):
        # Generate formatted lspci -xxxx text
        lines = ["0000:01:00.0 Processing accelerators: Xilinx Corporation Device 7024"]
        for offset in range(0, 512, 16):
            chunk = self.raw_bytes[offset : offset + 16]
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            lines.append(f"{offset:02x}: {hex_str}")
        lspci_dump = "\n".join(lines)

        bdf, parsed_data = PCIeAnalyzer.parse_lspci_text(lspci_dump)
        self.assertEqual(bdf, "0000:01:00.0")
        cfg = PCIeAnalyzer.decode_config_space(parsed_data, bdf)
        self.assertEqual(cfg.vendor_id, 0x10EE)

    def test_packaged_lspci_sample_preserves_offsets_and_decodes_aer(self):
        bdf, parsed_data = PCIeAnalyzer.parse_lspci_text(load_pcie_lspci_sample())

        self.assertEqual(bdf, "0000:01:00.0")
        self.assertEqual(len(parsed_data), 0x130)
        self.assertEqual(parsed_data[0x100:0x104], bytes.fromhex("01 00 01 00"))
        self.assertEqual(parsed_data[0x60:0x100], bytes(0xA0))

        cfg = PCIeAnalyzer.decode_config_space(parsed_data, bdf)
        self.assertEqual([cap.ext_cap_id for cap in cfg.extended_capabilities], [0x0001])
        self.assertIsNotNone(cfg.aer_analysis)
        assert cfg.aer_analysis is not None
        self.assertEqual(cfg.aer_analysis.active_uncorr_fatal_count, 1)
        self.assertIsNotNone(cfg.aer_analysis.decoded_tlp)

    def test_dmesg_parsing(self):
        dmesg_sample = """
[  124.582910] pcieport 0000:00:01.0: AER: Uncorrected (Fatal) error received: 0000:01:00.0
[  124.582915] pcieport 0000:00:01.0: PCIe Bus Error: severity=Uncorrected (Fatal), type=Transaction Layer, id=0010(Receiver ID)
[  124.582920] pcieport 0000:00:01.0:   device [10ee:7024] error status/mask=00040000/00000000
[  124.582922] pcieport 0000:00:01.0:    [18] MalformedTLP           (First)
[  124.582925] pcieport 0000:00:01.0:   TLP Header: 00000001 0100000f fe000000 00000000
"""
        events = PCIeAnalyzer.parse_dmesg_aer(dmesg_sample)
        self.assertTrue(len(events) >= 1)
        ev = events[0]
        self.assertEqual(ev.error_name, "Receiver ID")
        report = PCIeReporter.format_dmesg_events(events)
        self.assertIn("Linux Kernel dmesg AER Diagnostic Report", report)

    def test_markdown_report_generation(self):
        cfg = PCIeAnalyzer.decode_config_space(self.raw_bytes, bdf="0000:01:00.0")
        md = PCIeReporter.to_markdown(cfg)
        self.assertIn("PCIe Diagnostic Report", md)
        self.assertIn("Malformed TLP", md)
        self.assertIn("Completion Timeout", md)
        self.assertIn("BAR0", md)


if __name__ == "__main__":
    unittest.main()
