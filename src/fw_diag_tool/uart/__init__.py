"""UART Serial Crash Dump & ARM HardFault Analyzer Module."""

from .models import ARMHardFaultReport, KernelPanicReport, UARTReport
from .parser import UARTCrashParser
from .reporter import UARTReporter
from .symptom_db import SYMPTOM_DB, MatchedSymptom, UARTSymptom, classify_symptoms
from .timing import UARTTimingAnalysis, analyze_uart_timing

__all__ = [
    "SYMPTOM_DB",
    "ARMHardFaultReport",
    "KernelPanicReport",
    "MatchedSymptom",
    "UARTCrashParser",
    "UARTReport",
    "UARTReporter",
    "UARTSymptom",
    "UARTTimingAnalysis",
    "analyze_uart_timing",
    "classify_symptoms",
]
