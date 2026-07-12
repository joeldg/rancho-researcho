"""link scheduled monitor occurrences to tasks

Revision ID: 0005_monitor_automation
Revises: 0004_monitors

@spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_monitor_automation"
down_revision = "0004_monitors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("research_tasks") as batch:
        batch.add_column(sa.Column("monitor_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_research_tasks_monitor",
            "monitors",
            ["monitor_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint(
            "uq_monitor_scheduled_occurrence", ["monitor_id", "scheduled_for"]
        )
    op.create_index("ix_research_tasks_monitor_id", "research_tasks", ["monitor_id"])
    with op.batch_alter_table("monitor_runs") as batch:
        batch.add_column(
            sa.Column(
                "webhook_status",
                sa.String(32),
                nullable=False,
                server_default="not_required",
            )
        )
        batch.create_unique_constraint("uq_monitor_runs_task_id", ["task_id"])


def downgrade() -> None:
    with op.batch_alter_table("monitor_runs") as batch:
        batch.drop_constraint("uq_monitor_runs_task_id", type_="unique")
        batch.drop_column("webhook_status")
    op.drop_index("ix_research_tasks_monitor_id", table_name="research_tasks")
    with op.batch_alter_table("research_tasks") as batch:
        batch.drop_constraint("uq_monitor_scheduled_occurrence", type_="unique")
        batch.drop_constraint("fk_research_tasks_monitor", type_="foreignkey")
        batch.drop_column("scheduled_for")
        batch.drop_column("monitor_id")
