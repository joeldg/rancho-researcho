"""Durable SQLAlchemy models for Phase 2 research tasks, evidence, and events."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rancho.db import Base


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
class TaskStatus(str, enum.Enum):
    """Explicit task lifecycle states; terminal states are marked below."""

    queued = "queued"
    running = "running"
    partial = "partial"
    completed = "completed"
    failed = "failed"
    cancel_requested = "cancel_requested"
    cancelled = "cancelled"


TERMINAL_STATES = frozenset(
    {TaskStatus.partial, TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled}
)


# @spec[RANCHO_ASYNC_RESEARCH.md#sse-and-events]
class EventType(str, enum.Enum):
    """The explicit set of emitted task event types (SSE event names)."""

    task_created = "task.created"
    stage_started = "stage.started"
    search_completed = "search.completed"
    evidence_extracted = "evidence.extracted"
    claim_verified = "claim.verified"
    progress = "progress"
    task_partial = "task.partial"
    task_completed = "task.completed"
    task_failed = "task.failed"
    task_cancelled = "task.cancelled"


def _status_enum() -> Enum:
    return Enum(TaskStatus, name="task_status", native_enum=False, length=32)


def _event_type_enum() -> Enum:
    return Enum(
        EventType,
        name="event_type",
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
claim_evidence = Table(
    "claim_evidence",
    Base.metadata,
    Column(
        "claim_id",
        ForeignKey("claims.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "evidence_id",
        ForeignKey("evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
class ResearchTask(Base):
    """A durable research task: the system of record for its lifecycle."""

    __tablename__ = "research_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    objective: Mapped[str] = mapped_column(Text)
    budget_max_sources: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[TaskStatus] = mapped_column(
        _status_enum(), default=TaskStatus.queued, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    events: Mapped[list[TaskEvent]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskEvent.sequence",
    )
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    claims: Mapped[list[Claim]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_research_tasks_idempotency_key"),
    )


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
class Evidence(Base):
    """Retained source evidence; claims must trace back to these rows."""

    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True
    )
    canonical_url: Mapped[str] = mapped_column(Text)
    original_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    task: Mapped[ResearchTask] = relationship(back_populates="evidence")

    __table_args__ = (
        Index("ix_evidence_task_canonical", "task_id", "canonical_url"),
    )


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
class Claim(Base):
    """A synthesized claim linked to the evidence that supports it."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped[ResearchTask] = relationship(back_populates="claims")
    evidence: Mapped[list[Evidence]] = relationship(secondary=claim_evidence)


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
class TaskEvent(Base):
    """A durable, monotonically sequenced event for a task."""

    __tablename__ = "task_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[EventType] = mapped_column(_event_type_enum())
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped[ResearchTask] = relationship(back_populates="events")

    __table_args__ = (
        UniqueConstraint(
            "task_id", "sequence", name="uq_task_events_task_sequence"
        ),
        Index("ix_task_events_task_sequence", "task_id", "sequence"),
    )
