"""add forfeit_input to matches

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-22 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Walkover marker: 1 = input1 forfeited, 2 = input2 forfeited, NULL = no forfeit.
    op.add_column("matches", sa.Column("forfeit_input", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "forfeit_input")
