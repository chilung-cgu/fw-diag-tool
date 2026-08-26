"""Packaged sample captures used by the GUI."""

from importlib.resources import files

_I2C_SAMPLE_FILES = {
    "builtin-decoded": "saleae_normal_pmbus_eeprom.csv",
    "split-decoded": "i2c_split_decoded.csv",
    "raw-100khz": "i2c_raw_100khz.csv",
    "text-trace": "i2c_text_trace.log",
}


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


__all__ = ["load_i2c_sample", "load_spi_sample"]
