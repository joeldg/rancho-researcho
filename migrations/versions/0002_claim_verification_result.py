"""add verified final result to research tasks

Revision ID: 0002_claim_verification_result
Revises: 0001_initial
Create Date: 2026-07-11

@spec[RANCHO_CLAIM_VERIFICATION.md#requirements]
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_claim_verification_result"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_tasks", sa.Column("final_result", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("research_tasks", "final_result")
