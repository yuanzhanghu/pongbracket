"""drop tournament_join_requests

The join-request / approval workflow is gone: a logged-in user joins an
individual tournament instantly (no owner approval, no rejection), so the
``tournament_join_requests`` table and its ``join_request_status`` enum are no
longer written or read by anything.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-20 14:30:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tournament_join_requests")
    op.execute("DROP TYPE IF EXISTS join_request_status")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_join_requests (
            id BIGSERIAL PRIMARY KEY,
            tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR NOT NULL DEFAULT 'PENDING',
            linked_team_id BIGINT REFERENCES teams(id) ON DELETE SET NULL,
            trust_creator BOOLEAN NOT NULL DEFAULT FALSE,
            created TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT tournament_join_requests_tournament_id_user_id_key
                UNIQUE (tournament_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tournament_join_requests_tournament_id "
        "ON tournament_join_requests (tournament_id)"
    )
