"""backfill a personal club for every club-less user

Clubs are the (now implicit) ownership/permission unit: a user with no club
cannot organise tournaments. New accounts get a personal club at registration;
this migration backfills the same for pre-existing accounts that never created
one, so the implicit-club model holds for the whole user base.

Idempotent: it only touches users that have no ``users_x_clubs`` row, so
re-running is a no-op once every user owns a club.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-19 16:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # One personal club (named after the user) + an OWNER membership for every
    # account that currently belongs to no club.
    op.execute(
        """
        DO $$
        DECLARE
            r RECORD;
            cid bigint;
        BEGIN
            FOR r IN
                SELECT u.id, u.name
                FROM users u
                WHERE NOT EXISTS (
                    SELECT 1 FROM users_x_clubs uc WHERE uc.user_id = u.id
                )
            LOOP
                INSERT INTO clubs (name, created)
                VALUES (r.name, NOW())
                RETURNING id INTO cid;

                INSERT INTO users_x_clubs (club_id, user_id, relation)
                VALUES (cid, r.id, 'OWNER');
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    # No-op: auto-created personal clubs are indistinguishable from
    # user-created ones, so there is nothing safe to remove on downgrade.
    pass
