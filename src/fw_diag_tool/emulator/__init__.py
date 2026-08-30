"""Virtual Hardware Device Emulators for offline testing and driver validation."""

from .eeprom import VirtualEEPROM24C64
from .i2c_mux import VirtualPCA9548A
from .ina219 import VirtualINA219
from .lm75 import VirtualLM75
from .spi_flash import VirtualSPIFlashW25Q128

__all__ = [
    "VirtualEEPROM24C64",
    "VirtualINA219",
    "VirtualLM75",
    "VirtualPCA9548A",
    "VirtualSPIFlashW25Q128",
]
