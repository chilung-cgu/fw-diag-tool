from fw_diag_tool.codegen.driver_gen import I2CDriverCodeGenerator
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.models import AckType, I2CDirection, I2CTransaction
from fw_diag_tool.i2c.timing_charts import I2CTimingCharts
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor


def test_waveform_reconstruction_and_plotly():
    tx = I2CTransaction(
        id=1,
        start_time=0.001,
        end_time=0.0012,
        address_7bit=0x50,
        address_8bit=0xA0,
        direction=I2CDirection.WRITE,
        data_bytes=[0x00, 0x12, 0x34],
        address_ack=AckType.ACK,
        has_stop=True,
    )
    reconstructor = I2CWaveformReconstructor(default_clock_khz=100.0)
    wave_data = reconstructor.reconstruct_transaction_waveform(tx)
    assert len(wave_data.time_us) > 50
    assert len(wave_data.scl) == len(wave_data.time_us)
    assert len(wave_data.sda) == len(wave_data.time_us)
    ann_types = [a.annotation_type for a in wave_data.annotations]
    assert "START" in ann_types
    assert "ADDRESS" in ann_types
    assert "DATA" in ann_types
    assert "ACK" in ann_types
    assert "STOP" in ann_types

    # Plotly figure creation
    fig = reconstructor.create_plotly_figure(wave_data, title="Test Waveform")
    assert fig is not None
    assert len(fig.data) >= 3


def test_driver_code_generator():
    snippets = I2CDriverCodeGenerator.generate_all_snippets(
        addr_7bit=0x50, reg_offset=0x10, data_bytes=[0xAB, 0xCD], is_read=False, bus_num=2
    )
    assert "Linux Userspace (i2c-dev)" in snippets
    assert "0x50" in snippets["Linux Userspace (i2c-dev)"]
    assert "i2ctransfer -y 2 w3@0x50 0x10 0xAB 0xCD" in snippets["OpenBMC / Linux CLI (i2c-tools)"]
    assert " -f " not in snippets["OpenBMC / Linux CLI (i2c-tools)"]
    assert "HAL_I2C_Mem_Write" in snippets["STM32 HAL C Driver"]
    assert "0xAB, 0xCD" in snippets["STM32 HAL C Driver"]
    assert "Wire.beginTransmission(0x50)" in snippets["Arduino / Wire.h"]
    assert "Wire.write(0xAB);" in snippets["Arduino / Wire.h"]
    assert "Wire.write(0xCD);" in snippets["Arduino / Wire.h"]


def test_timing_charts_and_health_radar():
    csv_data = """Time,Packet ID,Address,Read/Write,Data,ACK/NACK
0.001,0,0x50,Write,0x00 0x12,ACK
0.002,1,0x48,Read,0x19 0x00,ACK
"""
    engine = I2CDiagnosticEngine()
    report = engine.analyze_csv_content(csv_data)
    fig_hist = I2CTimingCharts.create_frequency_distribution(report)
    assert fig_hist is not None
    fig_timeline = I2CTimingCharts.create_bus_activity_timeline(report)
    assert fig_timeline is not None
    health_df = I2CTimingCharts.get_device_health_summary(report)
    assert not health_df.empty
    assert "0x50" in list(health_df["Slave Address"])
