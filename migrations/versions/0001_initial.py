"""initial durable schema: research_tasks, evidence, claims, task_events

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-11

@spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

_TASK_STATUS = sa.Enum(
    "queued",
    "running",
    "partial",
    "completed",
    "failed",
    "cancel_requested",
    "cancelled",
    name="task_status",
    native_enum=False,
    length=32,
)
_EVENT_TYPE = sa.Enum(
    "task.created",
    "stage.started",
    "search.completed",
    "evidence.extracted",
    "claim.verified",
    "progress",
    "task.partial",
    "task.completed",
    "task.failed",
    "task.cancelled",
    name="event_type",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "research_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("budget_max_sources", sa.Integer(), nullable=False),
        sa.Column("status", _TASK_STATUS, nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_research_tasks_idempotency_key"
        ),
    )
    op.create_index(
        "ix_research_tasks_status", "research_tasks", ["status"]
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_task_id", "evidence", ["task_id"])
    op.create_index(
        "ix_evidence_task_canonical", "evidence", ["task_id", "canonical_url"]
    )

    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_task_id", "claims", ["task_id"])

    op.create_table(
        "claim_evidence",
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("claim_id", "evidence_id"),
    )

    op.create_table(
        "task_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", _EVENT_TYPE, nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", "sequence", name="uq_task_events_task_sequence"
        ),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])
    op.create_index(
        "ix_task_events_task_sequence", "task_events", ["task_id", "sequence"]
    )


def downgrade() -> None:
    op.drop_index("ix_task_events_task_sequence", table_name="task_events")
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")
    op.drop_table("claim_evidence")
    op.drop_index("ix_claims_task_id", table_name="claims")
    op.drop_table("claims")
    op.drop_index("ix_evidence_task_canonical", table_name="evidence")
    op.drop_index("ix_evidence_task_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_research_tasks_status", table_name="research_tasks")
    op.drop_table("research_tasks")
