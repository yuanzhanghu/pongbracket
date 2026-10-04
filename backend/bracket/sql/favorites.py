from bracket.database import database
from bracket.models.db.tournament import Tournament
from bracket.utils.id_types import TournamentId, UserId


async def add_favorite(user_id: UserId, tournament_id: TournamentId) -> None:
    await database.execute(
        """
        INSERT INTO tournament_favorites (user_id, tournament_id)
        VALUES (:u, :t)
        ON CONFLICT (user_id, tournament_id) DO NOTHING
        """,
        {"u": user_id, "t": tournament_id},
    )


async def remove_favorite(user_id: UserId, tournament_id: TournamentId) -> None:
    await database.execute(
        "DELETE FROM tournament_favorites WHERE user_id = :u AND tournament_id = :t",
        {"u": user_id, "t": tournament_id},
    )


async def is_favorited(user_id: UserId, tournament_id: TournamentId) -> bool:
    found = await database.fetch_val(
        "SELECT EXISTS(SELECT 1 FROM tournament_favorites WHERE user_id = :u AND tournament_id = :t)",
        {"u": user_id, "t": tournament_id},
    )
    return bool(found)


async def get_followed_tournaments(user_id: UserId) -> list[Tournament]:
    """Tournaments the user follows: ones they explicitly favorited, ones they
    participate in (a team bound to their account), or ones they are a scorer
    for. Independent of club membership."""
    rows = await database.fetch_all(
        """
        SELECT DISTINCT t.*
        FROM tournaments t
        WHERE t.id IN (SELECT tournament_id FROM tournament_favorites WHERE user_id = :u)
           OR t.id IN (SELECT tournament_id FROM teams_x_users WHERE user_id = :u)
           OR t.id IN (SELECT tournament_id FROM tournament_scorers WHERE user_id = :u)
        ORDER BY t.start_time DESC
        """,
        {"u": user_id},
    )
    return [Tournament.model_validate(r) for r in rows]
