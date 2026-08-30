"""Packaged sample captures used by the GUI."""

from importlib.resources import files

_I2C_SAMPLE_FILES = {
    "builtin-decoded": "saleae_normal_pmbus_eeprom.csv",
    "split-decoded": "i2c_split_decoded.csv",
    "raw-100khz": "i2c_raw_100khz.csv",
    "text-trace": "i2c_text_trace.log",
    "address-nack": "i2c_address_nack.csv",
    "failing-nack": "i2c_failing_nack.csv",
    "golden": "i2c_golden.csv",
}

_WAVEFORM_DIFF_SAMPLE_FILES = {
    "golden": "i2c_golden.csv",
    "failing": "i2c_failing_nack.csv",
}

_UART_SAMPLE_FILES = {
    "kernel-panic": "kernel_panic_nvme.log",
    "hardfault": "arm_hardfault_stm32.log",
}

_MCTP_SAMPLE_FILES = {
    "mctp-pldm": "mctp_pldm_sample.hex",
    "ipmb": "ipmb_sample.hex",
}

_PCIE_DMESG_SAMPLE_FILE = "pcie_aer_dmesg.log"
_PCIE_LSPCI_SAMPLE_FILE = "pcie_aer_lspci.txt"


def load_i2c_sample(sample: str = "builtin-decoded") -> str:
    """Return a packaged I2C teaching capture."""
    try:
        filename = _I2C_SAMPLE_FILES[sample]
    except KeyError as exc:
        supported = ", ".join(sorted(_I2C_SAMPLE_FILES))
        raise ValueError(f"unknown I2C sample {sample!r}; choose one of: {supported}") from exc
    return files(__package__).joinpath(filename).read_text(encoding="utf-8")


def load_spi_sample() -> str:
    """Return the built-in SPI Flash analyzer CSV sample."""
    return files(__package__).joinpath("spi_w25q128_sample.csv").read_text(encoding="utf-8")


def load_waveform_diff_samples() -> tuple[str, str]:
    """Return the packaged Golden and Failing traces used by Page 3."""
    resource_files = files(__package__)
    return (
        resource_files.joinpath(_WAVEFORM_DIFF_SAMPLE_FILES["golden"]).read_text(encoding="utf-8"),
        resource_files.joinpath(_WAVEFORM_DIFF_SAMPLE_FILES["failing"]).read_text(encoding="utf-8"),
    )


def load_pcie_dmesg_sample() -> str:
    """Return the packaged Linux dmesg AER teaching sample."""
    return files(__package__).joinpath(_PCIE_DMESG_SAMPLE_FILE).read_text(encoding="utf-8")


def load_pcie_lspci_sample() -> str:
    """Return the packaged lspci Config Space teaching sample."""
    return files(__package__).joinpath(_PCIE_LSPCI_SAMPLE_FILE).read_text(encoding="utf-8")


def load_uart_sample(sample: str = "kernel-panic") -> str:
    """Return a packaged UART kernel panic or HardFault sample log."""
    try:
        filename = _UART_SAMPLE_FILES[sample]
    except KeyError as exc:
        supported = ", ".join(sorted(_UART_SAMPLE_FILES))
        raise ValueError(f"unknown UART sample {sample!r}; choose one of: {supported}") from exc
    return files(__package__).joinpath(filename).read_text(encoding="utf-8")


def load_mctp_sample(sample: str = "mctp-pldm") -> str:
    """Return a packaged MCTP/PLDM or IPMB sample dump."""
    try:
        filename = _MCTP_SAMPLE_FILES[sample]
    except KeyError as exc:
        supported = ", ".join(sorted(_MCTP_SAMPLE_FILES))
        raise ValueError(f"unknown MCTP sample {sample!r}; choose one of: {supported}") from exc
    return files(__package__).joinpath(filename).read_text(encoding="utf-8")


__all__ = [
    "load_i2c_sample",
    "load_mctp_sample",
    "load_pcie_dmesg_sample",
    "load_pcie_lspci_sample",
    "load_spi_sample",
    "load_uart_sample",
    "load_waveform_diff_samples",
]
