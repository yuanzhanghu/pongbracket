"""remove swiss stage type and swiss_score columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-18 21:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # FK-safe purge of any existing SWISS data: matches -> stage_item_inputs ->
    # rounds -> stage_items, all scoped to SWISS stage items.
    op.execute(
        """
        DELETE FROM matches
        WHERE round_id IN (
            SELECT r.id FROM rounds r
            JOIN stage_items si ON si.id = r.stage_item_id
            WHERE si.type = 'SWISS'
        )
        """
    )
    op.execute(
        """
        DELETE FROM stage_item_inputs
        WHERE stage_item_id IN (SELECT id FROM stage_items WHERE type = 'SWISS')
        """
    )
    op.execute(
        """
        DELETE FROM rounds
        WHERE stage_item_id IN (SELECT id FROM stage_items WHERE type = 'SWISS')
        """
    )
    op.execute("DELETE FROM stage_items WHERE type = 'SWISS'")

    # Recreate the stage_type enum without SWISS.
    op.execute("ALTER TYPE stage_type RENAME TO stage_type_old")
    op.execute("CREATE TYPE stage_type AS ENUM ('SINGLE_ELIMINATION', 'ROUND_ROBIN')")
    op.execute(
        "ALTER TABLE stage_items ALTER COLUMN type TYPE stage_type USING type::text::stage_type"
    )
    op.execute("DROP TYPE stage_type_old")

    # Drop swiss_score columns.
    op.drop_column("teams", "swiss_score")
    op.drop_column("players", "swiss_score")


def downgrade() -> None:
    op.add_column(
        "teams",
        sa.Column("swiss_score", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "players",
        sa.Column("swiss_score", sa.Float(), server_default="0", nullable=False),
    )

    op.execute("ALTER TYPE stage_type RENAME TO stage_type_old")
    op.execute("CREATE TYPE stage_type AS ENUM ('SINGLE_ELIMINATION', 'SWISS', 'ROUND_ROBIN')")
    op.execute(
        "ALTER TABLE stage_items ALTER COLUMN type TYPE stage_type USING type::text::stage_type"
    )
    op.execute("DROP TYPE stage_type_old")
