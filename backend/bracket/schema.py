from sqlalchemy import Column, ForeignKey, Integer, String, Table, UniqueConstraint, func
from sqlalchemy.orm import declarative_base  # type: ignore[attr-defined]
from sqlalchemy.sql.sqltypes import BigInteger, Boolean, DateTime, Enum, Float, Text

Base = declarative_base()
metadata = Base.metadata
DateTimeTZ = DateTime(timezone=True)

clubs = Table(
    "clubs",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
)

tournaments = Table(
    "tournaments",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("start_time", DateTimeTZ, nullable=False),
    Column("club_id", BigInteger, ForeignKey("clubs.id"), index=True, nullable=False),
    Column("dashboard_public", Boolean, nullable=False),
    Column("logo_path", String, nullable=True),
    Column("dashboard_endpoint", String, nullable=True, index=True, unique=True),
    Column("players_can_be_in_multiple_teams", Boolean, nullable=False, server_default="f"),
    Column("auto_assign_courts", Boolean, nullable=False, server_default="f"),
    Column("duration_minutes", Integer, nullable=False, server_default="15"),
    Column("margin_minutes", Integer, nullable=False, server_default="5"),
    Column(
        "status",
        Enum(
            "OPEN",
            "ARCHIVED",
            name="tournament_status",
        ),
        nullable=False,
        server_default="OPEN",
        index=True,
    ),
    # Individual tournament (one team = one player). Gate for the rating system.
    Column("is_individual", Boolean, nullable=False, server_default="f"),
    # NULL = not rated. FK to a global rating category.
    Column("rating_category_id", BigInteger, ForeignKey("rating_categories.id"), nullable=True),
    # Monotonic ordering assigned at settlement (sort truth within a category).
    Column("settled_seq", BigInteger, nullable=True),
    Column("settled_at", DateTimeTZ, nullable=True),
    # Set when the owner requests settlement while seeds are still PENDING; the
    # tournament then waits in the admin "批准并结算" queue. NULL once settled.
    Column("settlement_requested_at", DateTimeTZ, nullable=True),
    # Manual placement for the public showcase page: a JSON array of team ids in
    # finishing order. NULL = derive the placement from the scores.
    Column("showcase_ranking", Text, nullable=True),
)

stages = Table(
    "stages",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), index=True, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="false"),
)

stage_items = Table(
    "stage_items",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", Text, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("stage_id", BigInteger, ForeignKey("stages.id"), index=True, nullable=False),
    Column("team_count", Integer, nullable=False),
    Column("ranking_id", BigInteger, ForeignKey("rankings.id"), nullable=False),
    Column(
        "type",
        Enum(
            "SINGLE_ELIMINATION",
            "ROUND_ROBIN",
            name="stage_type",
        ),
        nullable=False,
    ),
)

stage_item_inputs = Table(
    "stage_item_inputs",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("slot", Integer, nullable=False),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), index=True, nullable=False),
    Column(
        "stage_item_id",
        BigInteger,
        ForeignKey("stage_items.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    ),
    Column("team_id", BigInteger, ForeignKey("teams.id"), nullable=True),
    Column("winner_from_stage_item_id", BigInteger, ForeignKey("stage_items.id"), nullable=True),
    Column("winner_position", Integer, nullable=True),
    Column("points", Float, nullable=False, server_default="0"),
    Column("wins", Integer, nullable=False, server_default="0"),
    Column("draws", Integer, nullable=False, server_default="0"),
    Column("losses", Integer, nullable=False, server_default="0"),
    UniqueConstraint("stage_item_id", "team_id"),
    UniqueConstraint("stage_item_id", "winner_from_stage_item_id", "winner_position"),
)

rounds = Table(
    "rounds",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", Text, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("is_draft", Boolean, nullable=False),
    Column("stage_item_id", BigInteger, ForeignKey("stage_items.id"), nullable=False),
)


matches = Table(
    "matches",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("start_time", DateTimeTZ, nullable=True),
    Column("duration_minutes", Integer, nullable=True),
    Column("margin_minutes", Integer, nullable=True),
    Column("custom_duration_minutes", Integer, nullable=True),
    Column("custom_margin_minutes", Integer, nullable=True),
    Column("round_id", BigInteger, ForeignKey("rounds.id"), nullable=False),
    Column("stage_item_input1_id", BigInteger, ForeignKey("stage_item_inputs.id"), nullable=True),
    Column("stage_item_input2_id", BigInteger, ForeignKey("stage_item_inputs.id"), nullable=True),
    Column("stage_item_input1_conflict", Boolean, nullable=False),
    Column("stage_item_input2_conflict", Boolean, nullable=False),
    Column(
        "stage_item_input1_winner_from_match_id",
        BigInteger,
        ForeignKey("matches.id"),
        nullable=True,
    ),
    Column(
        "stage_item_input2_winner_from_match_id",
        BigInteger,
        ForeignKey("matches.id"),
        nullable=True,
    ),
    Column("court_id", BigInteger, ForeignKey("courts.id"), nullable=True),
    Column("stage_item_input1_score", Integer, nullable=False),
    Column("stage_item_input2_score", Integer, nullable=False),
    Column("position_in_schedule", Integer, nullable=True),
    Column("games", Text, nullable=True),
    Column("best_of", Integer, nullable=False, server_default="3"),
    Column("forfeit_input", Integer, nullable=True),
)

teams = Table(
    "teams",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), index=True, nullable=False),
    Column("active", Boolean, nullable=False, index=True, server_default="t"),
    Column("elo_score", Float, nullable=False, server_default="0"),
    Column("wins", Integer, nullable=False, server_default="0"),
    Column("draws", Integer, nullable=False, server_default="0"),
    Column("losses", Integer, nullable=False, server_default="0"),
    Column("logo_path", String, nullable=True),
    Column("sort_order", Integer, nullable=False, server_default="0"),
)

players = Table(
    "players",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", String, nullable=False, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), index=True, nullable=False),
    Column("elo_score", Float, nullable=False),
    Column("wins", Integer, nullable=False),
    Column("draws", Integer, nullable=False),
    Column("losses", Integer, nullable=False),
    Column("active", Boolean, nullable=False, index=True, server_default="t"),
)

users = Table(
    "users",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("email", String, nullable=True, index=True, unique=True),
    Column("name", String, nullable=False),
    Column("password_hash", String, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column(
        "account_type",
        Enum(
            "REGULAR",
            "DEMO",
            name="account_type",
        ),
        nullable=False,
    ),
    # Site admin: maintains rating categories and reviews initial ratings.
    Column("is_admin", Boolean, nullable=False, server_default="f"),
    # Bumped on a password change; tokens issued under an older generation stop
    # authenticating (see check_jwt_and_get_user).
    Column("token_version", BigInteger, nullable=False, server_default="0"),
)

users_x_clubs = Table(
    "users_x_clubs",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("club_id", BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column(
        "relation",
        Enum(
            "OWNER",
            "COLLABORATOR",
            name="user_x_club_relation",
        ),
        nullable=False,
        default="OWNER",
    ),
)

players_x_teams = Table(
    "players_x_teams",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("player_id", BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("team_id", BigInteger, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
)

courts = Table(
    "courts",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("name", Text, nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), nullable=False, index=True),
)

rankings = Table(
    "rankings",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    Column("tournament_id", BigInteger, ForeignKey("tournaments.id"), nullable=False, index=True),
    Column("position", Integer, nullable=False),
    Column("win_points", Float, nullable=False),
    Column("draw_points", Float, nullable=False),
    Column("loss_points", Float, nullable=False),
    Column("add_score_points", Boolean, nullable=False),
)

# --- Cross-tournament rating system (CanadaChinaTT) ---

rating_categories = Table(
    "rating_categories",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column("key", String, nullable=False, unique=True),
    Column("name", String, nullable=False),
    Column("algorithm", String, nullable=False, server_default="chinatt"),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
)

player_ratings = Table(
    "player_ratings",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column(
        "category_id",
        BigInteger,
        ForeignKey("rating_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("initial_rating", Integer, nullable=False),
    Column("current_rating", Integer, nullable=False),
    Column(
        "status",
        Enum(
            "PENDING",
            "ACTIVE",
            name="player_rating_status",
        ),
        nullable=False,
        server_default="PENDING",
    ),
    Column("approved_by", BigInteger, ForeignKey("users.id"), nullable=True),
    Column("approved_at", DateTimeTZ, nullable=True),
    Column("matches_played", Integer, nullable=False, server_default="0"),
    Column("last_updated", DateTimeTZ, nullable=False, server_default=func.now()),
    UniqueConstraint("category_id", "user_id"),
)

rating_events = Table(
    "rating_events",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column(
        "category_id",
        BigInteger,
        ForeignKey("rating_categories.id"),
        nullable=False,
        index=True,
    ),
    # RESTRICT: ledger rows must not dangle when upstream rows are deleted.
    Column("match_id", BigInteger, ForeignKey("matches.id", ondelete="RESTRICT"), nullable=False),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("opponent_id", BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column(
        "tournament_id",
        BigInteger,
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    Column("rating_before", Integer, nullable=False),
    Column("rating_after", Integer, nullable=False),
    Column("delta", Integer, nullable=False),
    Column(
        "result",
        Enum(
            "W",
            "L",
            name="rating_event_result",
        ),
        nullable=False,
    ),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
)

teams_x_users = Table(
    "teams_x_users",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column("team_id", BigInteger, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column(
        "tournament_id",
        BigInteger,
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    UniqueConstraint("team_id"),
    UniqueConstraint("tournament_id", "user_id"),
)

user_trusted_managers = Table(
    "user_trusted_managers",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("manager_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "manager_id"),
)

tournament_scorers = Table(
    "tournament_scorers",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column(
        "tournament_id",
        BigInteger,
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    UniqueConstraint("tournament_id", "user_id"),
)

tournament_favorites = Table(
    "tournament_favorites",
    metadata,
    Column("id", BigInteger, primary_key=True, index=True, autoincrement=True),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column(
        "tournament_id",
        BigInteger,
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("created", DateTimeTZ, nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "tournament_id"),
)
