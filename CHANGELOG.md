# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-08-23

### Added
- I2C / SMBus / PMBus waveform reconstruction engine with SCL/SDA digital overlay
- PCIe Config Space parser with AER TLP Header Log decoding and Link degradation detection
- SPI NOR Flash protocol decoder with JEDEC ID lookup and WREN state machine tracking
- UART Crash Dump analyzer for Linux Kernel Panic and ARM Cortex-M HardFault
- MCTP (DSP0236/DSP0240 PLDM/SPDM) and IPMB server management protocol decoders
- Device Tree (.dts) auto-generator for Linux/OpenBMC BSP development
- C Header code generator producing MISRA-oriented RMW bitfield templates
- Multi-platform I2C driver snippet generator (Linux/OpenBMC/STM32 HAL/Arduino)
- Golden vs Failing Waveform Diff engine for A/B hardware comparison
- Virtual device emulators: EEPROM 24C64, LM75 temperature sensor, W25Q128 SPI Flash
- Fuzzing test generator for parser stress testing
- Session state persistence (.fwsession JSON)
- Interactive Streamlit Web GUI with 12 diagnostic pages and 20-case Fault Arena
- GitHub Actions CI/CD pipeline with Python 3.10-3.12 matrix testing
- Comprehensive Junior FW Engineer guide (docs/JUNIOR_FW_GUIDE.md)

### Fixed
- MCTP DSP0236 header version detection and SOM=0 payload offset alignment
- IPMB Response NetFn odd/even masking and Completion Code extraction
- ARM HardFault BFARVALID bit linkage preventing stale address false positives
- PMBus Linear16 signed two's complement handling for VOUT_TRIM negative values
- PMBus VOUT_MODE dynamic exponent update on Read transactions
- PCIe diagnostics AttributeError from stale property names
- PCIe Config TLP DW2 extended register number collision with BDF fields
- EEPROM page_size <= 0 division-by-zero crash guard
