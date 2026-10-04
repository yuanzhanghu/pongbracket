"""add tournaments.settlement_requested_at

Marks an individual rated tournament whose owner has requested settlement while
some participants' initial ratings are still PENDING. Such tournaments surface in
the admin "批准并结算" queue, where one action approves the seeds and settles in a
single transaction — the owner only ever presses "申请积分结算" once.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-20 12:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS settlement_requested_at "
        "TIMESTAMP WITH TIME ZONE NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tournaments DROP COLUMN IF EXISTS settlement_requested_at")
