import pytest
from fw_diag_tool.spi.engine import SPIDiagnosticEngine
from fw_diag_tool.spi.models import SPIOpcode, SPISeverity
from fw_diag_tool.spi.parser import SPIParser
from fw_diag_tool.spi.reporter import SPIReporter

def test_spi_jedec_id_and_wren_program():
    # Simulated SPI trace:
    # 1. Read JEDEC ID (0x9F -> 0xEF 0x40 0x18 Winbond W25Q128)
    # 2. Write Enable (0x06)
    # 3. Page Program (0x02 0x00 0x10 0x00, 4 bytes data)
    csv_data = """Time [s],MOSI,MISO,Enable
0.0001,0x9F,0x00,0
0.0002,0x00,0xEF,0
0.0003,0x00,0x40,0
0.0004,0x00,0x18,0
0.0005,0x00,0x00,1
0.0010,0x06,0x00,0
0.0011,0x00,0x00,1
0.0020,0x02,0x00,0
0.0021,0x00,0x00,0
0.0022,0x10,0x00,0
0.0023,0x00,0x00,0
0.0024,0xAA,0x00,0
0.0025,0xBB,0x00,0
0.0026,0xCC,0x00,0
0.0027,0xDD,0x00,0
0.0028,0x00,0x00,1
"""
    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert report.summary.total_transactions == 3
    assert report.summary.detected_flash_chip == "Winbond W25Q128 (128 Mbit / 16 MB)"
    assert report.summary.write_count == 1
    assert report.summary.anomaly_count == 0
    md = SPIReporter.to_markdown(report)
    assert "Winbond W25Q128" in md

def test_spi_write_without_wren_anomaly():
    # Page program issued directly without 0x06
    csv_data = """Time [s],MOSI,MISO,Enable
0.0010,0x02,0x00,0
0.0011,0x00,0x00,0
0.0012,0x00,0x00,0
0.0013,0x00,0x00,0
0.0014,0x55,0x00,0
0.0015,0x00,0x00,1
"""
    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert report.summary.anomaly_count == 1
    assert report.anomalies[0].code == "SPI_WRITE_NO_WREN"
    assert report.anomalies[0].severity == SPISeverity.CRITICAL

def test_spi_page_program_wrap_around_hazard():
    # Program starting at offset 0xF0 with 30 bytes (> 256 page wrap)
    mosi_bytes = [0x06]
    tx1_csv = "0.001,0x06,0x00,0\n0.002,0x00,0x00,1\n"
    tx2_rows = ["0.010,0x02,0x00,0", "0.011,0x00,0x00,0", "0.012,0x00,0x00,0", "0.013,0xF0,0x00,0"]
    for i in range(30):
        tx2_rows.append(f"0.0{20+i},0x{i:02X},0x00,0")
    tx2_rows.append("0.060,0x00,0x00,1")
    csv_data = "Time [s],MOSI,MISO,Enable\n" + tx1_csv + "\n".join(tx2_rows)

    engine = SPIDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    assert any(a.code == "SPI_PAGE_PROGRAM_WRAP" for a in report.anomalies)