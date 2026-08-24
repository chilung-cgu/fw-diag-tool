"""Property-based tests for parser robustness using Hypothesis."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from fw_diag_tool.errors import InputFormatError, ResourceLimitError
from fw_diag_tool.i2c.parser import I2CParser
from fw_diag_tool.mctp.models import ProtocolMode
from fw_diag_tool.mctp.parser import ServerMgmtParser
from fw_diag_tool.uart.parser import UARTCrashParser

# Limit text size to stay within parser resource limits.
csv_text = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    max_size=512,
)


@settings(max_examples=100, deadline=None)
@given(text=csv_text)
def test_i2c_parser_never_crashes_on_arbitrary_text(text: str) -> None:
    """I2C parser must either parse or raise InputFormat/ResourceLimit, never anything else."""
    try:
        I2CParser.parse_csv_string(text)
    except (InputFormatError, ResourceLimitError):
        pass


hex_line = st.text(
    alphabet="0123456789ABCDEFabcdef \t",
    max_size=128,
).filter(lambda s: s.strip())


@settings(max_examples=200, deadline=None)
@given(line=hex_line)
def test_mctp_parser_never_crashes_on_arbitrary_hex(line: str) -> None:
    """MCTP/IPMB parser must not crash on arbitrary hex input."""
    try:
        ServerMgmtParser.parse_text_dump(line, protocol_mode=ProtocolMode.AUTO)
    except (ValueError, TypeError):
        pass


uart_text = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    max_size=1024,
)


@settings(max_examples=50, deadline=None)
@given(text=uart_text)
def test_uart_parser_never_crashes_on_arbitrary_text(text: str) -> None:
    """UART parser must handle arbitrary log text without unexpected exceptions."""
    try:
        UARTCrashParser.parse_log_text(text)
    except (ValueError, TypeError):
        pass
