"""Stable exception types for input and resource-boundary failures."""

from __future__ import annotations

from typing import Any


class InputFormatError(ValueError):
    """Input could not be parsed according to the selected format."""


class ResourceLimitError(ValueError):
    """Input or analysis output exceeded a configured resource limit."""

    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        limit: int | None = None,
        observed: int | None = None,
    ) -> None:
        super().__init__(message)
        self.resource = resource
        self.limit = limit
        self.observed = observed

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": type(self).__name__,
            "message": str(self),
            "resource": self.resource,
            "limit": self.limit,
            "observed": self.observed,
        }


class AmbiguousProtocolError(ValueError):
    """A frame could match multiple protocols; the caller must disambiguate."""

    def __init__(
        self,
        message: str,
        *,
        candidates: list[str] | None = None,
        line_number: int | None = None,
        raw_hex: str | None = None,
    ) -> None:
        super().__init__(message)
        self.candidates = candidates or []
        self.line_number = line_number
        self.raw_hex = raw_hex

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": type(self).__name__,
            "message": str(self),
            "candidates": self.candidates,
            "line_number": self.line_number,
            "raw_hex": self.raw_hex,
        }


__all__ = ["AmbiguousProtocolError", "InputFormatError", "ResourceLimitError"]
