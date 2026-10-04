"""add teams.sort_order

Persists a manual display/seed order for teams. Non-rated tournaments order their
teams by this column (reorderable with up/down arrows on the teams page); the same
order seeds round-robin groups. Backfilled per tournament by creation order.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-01 09:30:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE teams ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0")
    op.execute(
        """
        UPDATE teams t
        SET sort_order = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY tournament_id ORDER BY created, id
            ) AS rn
            FROM teams
        ) sub
        WHERE t.id = sub.id
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE teams DROP COLUMN IF EXISTS sort_order")
