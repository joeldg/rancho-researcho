"""add durable FindAll task metadata and candidates

Revision ID: 0003_findall_candidates
Revises: 0002_claim_verification_result
Create Date: 2026-07-11

@spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_findall_candidates"
down_revision = "0002_claim_verification_result"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_tasks",
        sa.Column(
            "task_type", sa.String(length=32), nullable=False, server_default="research"
        ),
    )
    op.add_column(
        "research_tasks", sa.Column("output_schema", sa.JSON(), nullable=True)
    )
    op.create_index("ix_research_tasks_task_type", "research_tasks", ["task_type"])
    op.create_table(
        "candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidates_task_id", "candidates", ["task_id"])
    op.create_table(
        "candidate_evidence",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_id", "evidence_id"),
    )


def downgrade() -> None:
    op.drop_table("candidate_evidence")
    op.drop_index("ix_candidates_task_id", table_name="candidates")
    op.drop_table("candidates")
    op.drop_index("ix_research_tasks_task_type", table_name="research_tasks")
    op.drop_column("research_tasks", "output_schema")
    op.drop_column("research_tasks", "task_type")
