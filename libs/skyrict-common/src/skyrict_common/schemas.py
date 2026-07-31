"""Standardized API response envelopes.

Every API response from Skyrict services uses these schemas for consistency.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata included in list responses."""

    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")

    @classmethod
    def create(cls, *, total: int, page: int, page_size: int) -> PaginationMeta:
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(total=total, page=page, page_size=page_size, total_pages=total_pages)


class ResponseEnvelope(BaseModel, Generic[T]):
    """Standard success response wrapper.

    Usage:
        return ResponseEnvelope(data=user, message="User retrieved successfully")
    """

    success: bool = Field(default=True, description="Whether the request succeeded")
    data: T | None = Field(default=None, description="Response payload")
    message: str | None = Field(default=None, description="Human-readable message")
    meta: PaginationMeta | None = Field(default=None, description="Pagination metadata (list endpoints only)")


class ErrorDetail(BaseModel):
    """Single error detail."""

    field: str | None = Field(default=None, description="Field that caused the error, if applicable")
    message: str = Field(..., description="Error message")
    code: str = Field(..., description="Machine-readable error code")


class ErrorResponse(BaseModel):
    """Standard error response wrapper.

    Usage:
        raise HTTPException(status_code=400, detail=ErrorResponse(...).model_dump())
    """

    success: bool = Field(default=False, description="Always false for errors")
    error: ErrorDetail = Field(..., description="Error details")
    request_id: str | None = Field(default=None, description="Request ID for tracing")


class ListResponse(BaseModel, Generic[T]):
    """Standard list response with pagination.

    Usage:
        return ListResponse(data=users, meta=pagination_meta)
    """

    success: bool = Field(default=True)
    data: list[T] = Field(default_factory=list, description="List of items")
    meta: PaginationMeta = Field(..., description="Pagination metadata")
