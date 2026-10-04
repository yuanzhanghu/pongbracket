from sqlalchemy import func

from bracket.database import database
from bracket.logic.tournaments import sql_delete_tournament_completely
from bracket.models.db.account import UserAccountType
from bracket.models.db.rating import AdminUserRatings
from bracket.models.db.user import User, UserInDB, UserInsertable, UserPublic, UserToUpdate
from bracket.schema import users
from bracket.sql.clubs import get_clubs_for_user_id, sql_delete_club
from bracket.sql.tournaments import sql_get_tournaments
from bracket.utils.db import fetch_one_parsed
from bracket.utils.id_types import ClubId, TournamentId, UserId
from bracket.utils.types import assert_some


def normalize_email(email: str | None) -> str | None:
    """Email addresses are case-insensitive in practice; normalise so lookups and
    uniqueness checks don't depend on how the user typed their address. An empty
    address normalises to None (email is optional)."""
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized if normalized != "" else None


async def get_user_access_to_tournament(tournament_id: TournamentId, user_id: UserId) -> bool:
    query = """
        SELECT DISTINCT t.id
        FROM users_x_clubs
        JOIN tournaments t ON t.club_id = users_x_clubs.club_id
        WHERE user_id = :user_id
        """
    result = await database.fetch_all(query=query, values={"user_id": user_id})
    return tournament_id in {tournament["id"] for tournament in result}


async def get_which_clubs_has_user_access_to(user_id: UserId) -> set[ClubId]:
    query = """
        SELECT club_id
        FROM users_x_clubs
        WHERE user_id = :user_id
        """
    result = await database.fetch_all(query=query, values={"user_id": user_id})
    return {club["club_id"] for club in result}


async def get_user_access_to_club(club_id: ClubId, user_id: UserId) -> bool:
    return club_id in await get_which_clubs_has_user_access_to(user_id)


async def update_user(user_id: UserId, user: UserToUpdate) -> None:
    query = """
        UPDATE users
        SET name = :name, email = :email
        WHERE id = :user_id
        """
    await database.execute(
        query=query,
        values={
            "user_id": user_id,
            "name": user.name.strip(),
            "email": normalize_email(user.email),
        },
    )


async def update_user_account_type(user_id: UserId, account_type: UserAccountType) -> None:
    query = """
        UPDATE users
        SET account_type = :account_type
        WHERE id = :user_id
        """
    await database.execute(
        query=query, values={"user_id": user_id, "account_type": account_type.value}
    )


async def update_user_password(user_id: UserId, password_hash: str) -> None:
    """Also retires every access token issued so far: they carry the generation
    they were signed under, and bumping it makes them fail authentication."""
    query = """
        UPDATE users
        SET password_hash = :password_hash, token_version = token_version + 1
        WHERE id = :user_id
        """
    await database.execute(query=query, values={"user_id": user_id, "password_hash": password_hash})


async def get_user_token_version(user_id: UserId) -> int | None:
    """The generation a user's tokens must carry to be accepted. None if the user
    is gone, which no token can match."""
    query = """
        SELECT token_version
        FROM users
        WHERE id = :user_id
        """
    version = await database.fetch_val(query=query, values={"user_id": user_id})
    return int(version) if version is not None else None


async def get_user_by_id(user_id: UserId) -> UserPublic | None:
    query = """
        SELECT *
        FROM users
        WHERE id = :user_id
        """
    result = await database.fetch_one(query=query, values={"user_id": user_id})
    return UserPublic.model_validate(dict(result._mapping)) if result is not None else None


async def get_all_users_with_ratings() -> list[AdminUserRatings]:
    # Demo accounts are auto-generated (demo-<uuid>) and short-lived, so they
    # are excluded from the admin user list. Only ACTIVE (approved) ratings are
    # included — PENDING seeds live in the settlement review queue instead.
    query = """
        SELECT u.id AS user_id, u.name, pr.category_id, pr.current_rating
        FROM users u
        LEFT JOIN player_ratings pr ON pr.user_id = u.id AND pr.status = 'ACTIVE'
        WHERE u.account_type != 'DEMO'
        ORDER BY lower(u.name), u.id
        """
    result = await database.fetch_all(query=query)
    users_by_id: dict[int, AdminUserRatings] = {}
    for row in result:
        mapping = row._mapping
        entry = users_by_id.get(mapping["user_id"])
        if entry is None:
            entry = AdminUserRatings(user_id=mapping["user_id"], name=mapping["name"])
            users_by_id[mapping["user_id"]] = entry
        if mapping["category_id"] is not None:
            entry.ratings[mapping["category_id"]] = mapping["current_rating"]
    return list(users_by_id.values())


async def get_expired_demo_users() -> list[UserPublic]:
    query = """
        SELECT *
        FROM users
        WHERE account_type='DEMO'
        AND created <= NOW() - INTERVAL '30 minutes'
        """
    result = await database.fetch_all(query=query)
    return [UserPublic.model_validate(demo_user) for demo_user in result]


async def create_user(user: UserInsertable) -> User:
    query = """
        INSERT INTO users (email, name, password_hash, created, account_type)
        VALUES (:email, :name, :password_hash, :created, :account_type)
        RETURNING *
        """
    result = await database.fetch_one(
        query=query,
        values={
            "password_hash": user.password_hash,
            # Strip here rather than at each call site so the CLI and any other
            # writer can't reintroduce whitespace-padded, unfindable names.
            "name": user.name.strip(),
            "email": normalize_email(user.email),
            "created": user.created,
            "account_type": user.account_type.value,
        },
    )
    return User.model_validate(dict(assert_some(result)._mapping))


async def delete_user(user_id: UserId) -> None:
    query = """
        DELETE FROM users
        WHERE id = :user_id
        """
    await database.fetch_one(query=query, values={"user_id": user_id})


async def check_whether_email_is_in_use(email: str | None) -> bool:
    normalized = normalize_email(email)
    if normalized is None:
        return False
    query = """
        SELECT id
        FROM users
        WHERE LOWER(email) = :email
        """
    result = await database.fetch_one(query=query, values={"email": normalized})
    return result is not None


async def check_whether_name_is_in_use(name: str, exclude_user_id: UserId | None = None) -> bool:
    query = """
        SELECT id
        FROM users
        WHERE LOWER(BTRIM(name)) = LOWER(:name)
        AND (CAST(:exclude_id AS BIGINT) IS NULL OR id != CAST(:exclude_id AS BIGINT))
        """
    result = await database.fetch_one(
        query=query, values={"name": name.strip(), "exclude_id": exclude_user_id}
    )
    return result is not None


async def get_user(email: str) -> UserInDB | None:
    normalized = normalize_email(email)
    if normalized is None:
        # Never match the NULL emails of accounts registered without one.
        return None
    return await fetch_one_parsed(
        database,
        UserInDB,
        users.select().where(func.lower(users.c.email) == normalized),
    )


async def get_user_by_login(login: str) -> UserInDB | None:
    """Resolve a login identifier that may be either an email address or a
    (unique, case-insensitively matched) user name."""
    # BTRIM the stored values too: legacy rows were saved with surrounding
    # whitespace (e.g. "Jenny "), which made them unfindable by name.
    query = """
        SELECT *
        FROM users
        WHERE LOWER(BTRIM(email)) = LOWER(:login) OR LOWER(BTRIM(name)) = LOWER(:login)
        LIMIT 1
        """
    result = await database.fetch_one(query=query, values={"login": login.strip()})
    return UserInDB.model_validate(dict(result._mapping)) if result is not None else None


async def delete_user_and_owned_clubs(user_id: UserId) -> None:
    for club in await get_clubs_for_user_id(user_id):
        for tournament in await sql_get_tournaments((club.id,), None):
            await sql_delete_tournament_completely(tournament.id)

        await sql_delete_club(club.id)

    await delete_user(user_id)
