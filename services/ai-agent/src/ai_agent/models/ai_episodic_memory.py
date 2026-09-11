"""ai_episodic_memory - query-response pairs with 90-day TTL.

Stores every query-response interaction for contextual recall. Embeddings and
vector search are deferred to SKY-60 (chat citations) - this table only
persists the text and metadata for now.

Rows expire after 90 days and are cleaned up by the hourly sweep job. The
``expires_at`` column is set at insert time and indexed for efficient cleanup
deletion.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_agent.models.base import Base


class AiEpisodicMemoryModel(Base):
    """One query-response pair for episodic recall (90-day TTL)."""

    __tablename__ = "ai_episodic_memory"
    __table_args__ = (
        Index("idx_episodic_memory_tenant_created", "tenant_id", text("created_at DESC")),
        Index("idx_episodic_memory_expires", "expires_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_summary: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now() + interval '90 days'"),
    )
    # Timestamp of the compaction pass that summarized this row into semantic
    # facts (SKY-90). NULL until the weekly compaction job folds the row's
    # essence into ai_semantic_memory; compacted rows no longer enter recall.
    # Indexed (partial, WHERE compacted_at IS NULL) in migration 0020.
    compacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
