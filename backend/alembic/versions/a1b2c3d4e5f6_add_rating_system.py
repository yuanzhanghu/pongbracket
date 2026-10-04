"""add cross-tournament rating system (CanadaChinaTT)

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-18 20:15:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "a1b2c3d4e5f6"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Site admin flag.
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), server_default="f", nullable=False)
    )

    # Global rating categories (not owned by any club).
    op.create_table(
        "rating_categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("algorithm", sa.String(), server_default="chinatt", nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_rating_categories_id", "rating_categories", ["id"])

    # Seed the default category.
    op.execute(
        "INSERT INTO rating_categories (key, name, algorithm) "
        "VALUES ('CanadaChinaTT', '加华积分', 'chinatt')"
    )

    # Tournament columns.
    op.add_column(
        "tournaments",
        sa.Column("is_individual", sa.Boolean(), server_default="f", nullable=False),
    )
    op.add_column(
        "tournaments", sa.Column("rating_category_id", sa.BigInteger(), nullable=True)
    )
    op.add_column("tournaments", sa.Column("settled_seq", sa.BigInteger(), nullable=True))
    op.add_column(
        "tournaments", sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "tournaments_rating_category_id_fkey",
        "tournaments",
        "rating_categories",
        ["rating_category_id"],
        ["id"],
    )

    # Per-account rating in a category (ledger head).
    op.create_table(
        "player_ratings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("initial_rating", sa.Integer(), nullable=False),
        sa.Column("current_rating", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACTIVE", name="player_rating_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matches_played", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["rating_categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "user_id"),
    )
    op.create_index("ix_player_ratings_id", "player_ratings", ["id"])
    op.create_index("ix_player_ratings_category_id", "player_ratings", ["category_id"])

    # Append-only ledger of per-match rating changes.
    op.create_table(
        "rating_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_id", sa.BigInteger(), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("rating_before", sa.Integer(), nullable=False),
        sa.Column("rating_after", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("result", sa.Enum("W", "L", name="rating_event_result"), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["rating_categories.id"]),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opponent_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rating_events_id", "rating_events", ["id"])
    op.create_index("ix_rating_events_category_id", "rating_events", ["category_id"])
    op.create_index("ix_rating_events_tournament_id", "rating_events", ["tournament_id"])

    # Team <-> account binding (individual tournaments, 1:1).
    op.create_table(
        "teams_x_users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id"),
        sa.UniqueConstraint("tournament_id", "user_id"),
    )
    op.create_index("ix_teams_x_users_id", "teams_x_users", ["id"])

    # Join requests.
    op.create_table(
        "tournament_join_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", name="join_request_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("linked_team_id", sa.BigInteger(), nullable=True),
        sa.Column("trust_creator", sa.Boolean(), server_default="f", nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tournament_id", "user_id"),
    )
    op.create_index("ix_tournament_join_requests_id", "tournament_join_requests", ["id"])
    op.create_index(
        "ix_tournament_join_requests_tournament_id", "tournament_join_requests", ["tournament_id"]
    )

    # Trusted manager lists.
    op.create_table(
        "user_trusted_managers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("manager_id", sa.BigInteger(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "manager_id"),
    )
    op.create_index("ix_user_trusted_managers_id", "user_trusted_managers", ["id"])

    # Tournament scorers.
    op.create_table(
        "tournament_scorers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tournament_id", "user_id"),
    )
    op.create_index("ix_tournament_scorers_id", "tournament_scorers", ["id"])
    op.create_index("ix_tournament_scorers_tournament_id", "tournament_scorers", ["tournament_id"])


def downgrade() -> None:
    op.drop_table("tournament_scorers")
    op.drop_table("user_trusted_managers")
    op.drop_table("tournament_join_requests")
    op.drop_table("teams_x_users")
    op.drop_table("rating_events")
    op.drop_table("player_ratings")
    op.drop_constraint("tournaments_rating_category_id_fkey", "tournaments", type_="foreignkey")
    op.drop_column("tournaments", "settled_at")
    op.drop_column("tournaments", "settled_seq")
    op.drop_column("tournaments", "rating_category_id")
    op.drop_column("tournaments", "is_individual")
    op.drop_table("rating_categories")
    op.drop_column("users", "is_admin")
    for enum_name in ("player_rating_status", "rating_event_result", "join_request_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
