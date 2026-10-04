"""add showcase_ranking to tournaments

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f7
Create Date: 2026-08-23 10:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "b7c8d9e0f1a2"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Manual correction of the placement shown on the public showcase page, as a JSON
    # array of team ids in finishing order, e.g. "[12,7,9]". NULL = show the standings
    # the scores produce. Needed because a drop-in evening is often called before every
    # match has been played, so the table's own standings are not the real result.
    op.add_column("tournaments", sa.Column("showcase_ranking", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tournaments", "showcase_ranking")
