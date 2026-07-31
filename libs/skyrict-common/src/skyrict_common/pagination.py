"""Pagination utilities for list endpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaginationParams:
    """Parsed pagination parameters from query string."""

    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size

    @classmethod
    def create(cls, page: int | None = None, page_size: int | None = None) -> PaginationParams:
        """Create from optional query params with validation."""
        p = max(1, page or 1)
        ps = max(1, min(100, page_size or 20))
        return cls(page=p, page_size=ps)
