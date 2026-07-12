"""add candidate reasoning and durable monitors

Revision ID: 0004_monitors
Revises: 0003_findall_candidates

@spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_monitors"
down_revision = "0003_findall_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column(
            "match_status", sa.String(16), nullable=False, server_default="matched"
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "reasoning",
            sa.Text(),
            nullable=False,
            server_default="Evidence-linked match.",
        ),
    )
    op.create_table(
        "monitors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("webhook_secret", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("idempotency_key", name="uq_monitors_idempotency_key"),
    )
    op.create_index("ix_monitors_next_run_at", "monitors", ["next_run_at"])
    op.create_table(
        "monitor_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("evidence_hashes", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("material_change", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitor_runs_monitor_id", "monitor_runs", ["monitor_id"])
    op.create_index("ix_monitor_runs_task_id", "monitor_runs", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_monitor_runs_task_id", table_name="monitor_runs")
    op.drop_index("ix_monitor_runs_monitor_id", table_name="monitor_runs")
    op.drop_table("monitor_runs")
    op.drop_index("ix_monitors_next_run_at", table_name="monitors")
    op.drop_table("monitors")
    op.drop_column("candidates", "reasoning")
    op.drop_column("candidates", "match_status")
