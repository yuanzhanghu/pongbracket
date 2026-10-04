from fastapi import HTTPException
from starlette import status

from bracket.models.db.match import Match, MatchCreateBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.sql.matches import sql_create_match
from bracket.sql.rounds import get_rounds_for_stage_item
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.i18n import tr
from bracket.utils.id_types import TournamentId


def determine_matches_first_round(
    round_: RoundWithMatches,
    stage_item: StageItemWithRounds,
    tournament: Tournament,
    best_of: int = 3,
) -> list[MatchCreateBody]:
    suggestions: list[MatchCreateBody] = []

    for i in range(0, len(stage_item.inputs), 2):
        first_input = stage_item.inputs[i + 0]
        second_input = stage_item.inputs[i + 1]
        suggestions.append(
            MatchCreateBody(
                round_id=round_.id,
                court_id=None,
                stage_item_input1_id=first_input.id,
                stage_item_input1_winner_from_match_id=None,
                stage_item_input2_id=second_input.id,
                stage_item_input2_winner_from_match_id=None,
                duration_minutes=tournament.duration_minutes,
                margin_minutes=tournament.margin_minutes,
                custom_duration_minutes=None,
                custom_margin_minutes=None,
                best_of=best_of,
            )
        )

    return suggestions


def determine_matches_subsequent_round(
    prev_matches: list[Match],
    round_: RoundWithMatches,
    tournament: Tournament,
    best_of: int = 3,
) -> list[MatchCreateBody]:
    suggestions: list[MatchCreateBody] = []

    for i in range(0, len(prev_matches), 2):
        first_match = prev_matches[i + 0]
        second_match = prev_matches[i + 1]

        suggestions.append(
            MatchCreateBody(
                round_id=round_.id,
                court_id=None,
                stage_item_input1_id=None,
                stage_item_input2_id=None,
                stage_item_input1_winner_from_match_id=first_match.id,
                stage_item_input2_winner_from_match_id=second_match.id,
                duration_minutes=tournament.duration_minutes,
                margin_minutes=tournament.margin_minutes,
                custom_duration_minutes=None,
                custom_margin_minutes=None,
                best_of=best_of,
            )
        )
    return suggestions


def best_of_for_round(round_index: int, round_count: int) -> int:
    # Final and semi-final (the last two rounds) are best-of-5; earlier rounds best-of-3.
    return 5 if round_index >= round_count - 2 else 3


async def build_single_elimination_stage_item(
    tournament_id: TournamentId, stage_item: StageItemWithRounds
) -> None:
    rounds = await get_rounds_for_stage_item(tournament_id, stage_item.id)
    tournament = await sql_get_tournament(tournament_id)

    assert len(rounds) > 0
    round_count = len(rounds)
    first_round = rounds[0]

    prev_matches = [
        await sql_create_match(match)
        for match in determine_matches_first_round(
            first_round, stage_item, tournament, best_of_for_round(0, round_count)
        )
    ]

    for round_index, round_ in enumerate(rounds[1:], start=1):
        prev_matches = [
            await sql_create_match(match)
            for match in determine_matches_subsequent_round(
                prev_matches, round_, tournament, best_of_for_round(round_index, round_count)
            )
        ]


def get_number_of_rounds_to_create_single_elimination(team_count: int) -> int:
    if team_count < 1:
        return 0

    game_count_lookup = {
        2: 1,
        4: 2,
        8: 3,
        16: 4,
        32: 5,
    }
    if team_count not in game_count_lookup:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("队伍数量无效，应为 {options} 之一").format(
                options=list(game_count_lookup.keys())
            ),
        )

    return game_count_lookup[team_count]
