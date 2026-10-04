"""add users.token_version

Access tokens are stateless JWTs, so a password change used to leave every token
issued before it working until it expired — a year, now. Each token carries the
generation it was issued under; bumping the column invalidates all of them.

Revision ID: a1b2c3d4e5f7
Revises: d0e1f2a3b4c5
Create Date: 2026-08-22 12:40:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "a1b2c3d4e5f7"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version BIGINT NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS token_version")
