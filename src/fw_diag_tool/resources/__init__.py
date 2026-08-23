"""Packaged sample captures used by the GUI."""

from importlib.resources import files


def load_i2c_sample() -> str:
    """Return the built-in I2C/PMBus analyzer CSV sample."""
    return files(__package__).joinpath("saleae_normal_pmbus_eeprom.csv").read_text(encoding="utf-8")


def load_spi_sample() -> str:
    """Return the built-in SPI Flash analyzer CSV sample."""
    return files(__package__).joinpath("spi_w25q128_sample.csv").read_text(encoding="utf-8")


__all__ = ["load_i2c_sample", "load_spi_sample"]
