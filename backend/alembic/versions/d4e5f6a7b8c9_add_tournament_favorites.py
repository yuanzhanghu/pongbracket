"""add tournament_favorites (users follow/bookmark tournaments)

Lets any account follow tournaments it can view (its own, ones it joined, or
other public ones) independent of club membership, powering the home page's
"我关注的锦标赛" tab.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-19 18:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_favorites (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
            created TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, tournament_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tournament_favorites_tournament_id "
        "ON tournament_favorites (tournament_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tournament_favorites")
