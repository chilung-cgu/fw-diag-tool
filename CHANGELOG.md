# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-08-23

### Added
- Saleae Raw Digital CSV edge analyzer (Time,SCL,SDA) with true SCL clock period and stretch timing
- Board Profile schema supporting YAML/JSON server motherboard topologies (buses, muxes, devices)
- Hunt-Szymanski dynamic sequence alignment in Waveform Diff with retry detection and dropped transaction markers
- Session v2 schema with SHA-256 capture hashing, board profile metadata, and automated v1 migration
- Fault Arena 20-case fixture generators with in-GUI one-click automated diagnosis
- CLI options: --board-profile for hardware topology and --fail-on for CI/CD gates
- MkDocs search documentation configuration (mkdocs.yml) and in-app chapter reading expanders
- SPI Flash sample CSV bundled for offline practice in Web GUI

### Fixed
- Fixed false 360 kHz / 0% jitter metrics by requiring explicit duration or raw digital edge evidence
- Corrected I2C Read-final controller NACK semantics as valid bus termination
- Added SPI Flash BUSY (WIP=1) and WREN/Reset dual-command interlock tracking
- Fixed UART Panic signature recognition for ARM64 and RISC-V kernel dumps
- Guarded PCIe 64-byte short dump from parsing non-existent extended capabilities
- Sanitized rich Markdown report rendering in Web GUI and replaced external links with in-page expanders

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
