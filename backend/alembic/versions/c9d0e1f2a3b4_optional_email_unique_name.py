"""optional email, unique user name

Users may register without an email address (some don't want to share one
with the site), so ``users.email`` becomes nullable. The display name takes
over as the login identifier, so it must be unique: existing duplicates are
renamed by appending ``(id)`` (keeping the oldest account's name untouched)
before a case-insensitive unique index is created.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-11 12:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN email DROP NOT NULL")
    # Rename duplicate names (case-insensitive), keeping the oldest account as-is.
    op.execute(
        """
        UPDATE users u
        SET name = u.name || ' (' || u.id || ')'
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY LOWER(name) ORDER BY id) AS rn
            FROM users
        ) d
        WHERE d.id = u.id AND d.rn > 1
        """
    )
    op.execute("CREATE UNIQUE INDEX ix_users_name_lower ON users (LOWER(name))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_name_lower")
    # Rows with NULL email cannot be restored; leave the column nullable.
