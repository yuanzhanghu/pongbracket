"""add per-game scores and best_of to matches

Revision ID: f1a2b3c4d5e6
Revises: c1ab44651e79
Create Date: 2026-06-07 20:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "f1a2b3c4d5e6"
down_revision: str | None = "c1ab44651e79"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Per-game scores as a JSON string, e.g. "[[11,9],[11,7],[9,11],[11,6]]".
    op.add_column("matches", sa.Column("games", sa.Text(), nullable=True))
    # Best-of format for the match (3 = best of 3 / first to 2 games, 5 = best of 5, ...).
    op.add_column(
        "matches", sa.Column("best_of", sa.Integer(), server_default="3", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("matches", "best_of")
    op.drop_column("matches", "games")
