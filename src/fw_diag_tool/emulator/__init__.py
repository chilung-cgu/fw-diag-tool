"""Virtual Hardware Device Emulators for offline testing and driver validation."""

from .eeprom import VirtualEEPROM24C64
from .lm75 import VirtualLM75
from .spi_flash import VirtualSPIFlashW25Q128

__all__ = ["VirtualEEPROM24C64", "VirtualLM75", "VirtualSPIFlashW25Q128"]
