from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Schema for error details."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Schema for error response."""

    error: ErrorDetail


__all__ = [
    "ErrorDetail",
    "ErrorResponse",
]

