"""renumber teams.sort_order per tournament

Participants admitted into an individual tournament were inserted without a
sort_order, so they all fell back to the column default (0). Ties made the manual
up/down ordering pick the wrong neighbour. Renumber every tournament to 1..N by the
same (sort_order, id) key the teams listing sorts on, so the displayed order is
unchanged and only the duplicates are flattened.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-31 10:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE teams t
        SET sort_order = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY tournament_id ORDER BY sort_order, id
            ) AS rn
            FROM teams
        ) sub
        WHERE t.id = sub.id AND t.sort_order <> sub.rn
        """
    )


def downgrade() -> None:
    pass
