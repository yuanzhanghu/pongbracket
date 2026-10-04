"""
Unit tests for bracket/sql/matches.py:121-123 (per-game score aggregation in
sql_update_match).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from heliclockter import datetime_utc

from bracket.models.db.match import MatchBody
from bracket.models.db.tournament import Tournament
from bracket.sql.matches import sql_update_match
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import (
    ClubId,
    MatchId,
    RoundId,
    TournamentId,
)


def _make_tournament() -> Tournament:
    return Tournament(
        id=TournamentId(-1),
        club_id=ClubId(-1),
        name="T",
        created=DUMMY_MOCK_TIME,
        start_time=DUMMY_MOCK_TIME,
        dashboard_public=True,
        dashboard_endpoint="x",
        players_can_be_in_multiple_teams=True,
        auto_assign_courts=True,
        duration_minutes=10,
        margin_minutes=5,
    )


@pytest.mark.asyncio
async def test_sql_update_match_aggregates_per_game_scores() -> None:
    """When `games` is provided, score1/score2 are the number of games won by
    each side, and `games` is serialized to JSON. Exercises lines 121-123 of
    bracket/sql/matches.py.
    """
    # Side 1 wins games 0 and 2; side 2 wins game 1.
    games: list[list[int]] = [[11, 9], [8, 11], [11, 7]]
    body = MatchBody(
        round_id=RoundId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        court_id=None,
        custom_duration_minutes=None,
        custom_margin_minutes=None,
        games=games,
        best_of=3,
    )

    with patch("bracket.sql.matches.database") as mock_db:
        mock_db.execute = AsyncMock()
        await sql_update_match(MatchId(-1), body, _make_tournament())

    assert mock_db.execute.await_count == 1
    call_kwargs = mock_db.execute.await_args.kwargs
    values = call_kwargs["values"]
    # score1 = 2, score2 = 1
    assert values["stage_item_input1_score"] == 2
    assert values["stage_item_input2_score"] == 1
    # games serialized as JSON
    assert values["games"] == json.dumps(games)


@pytest.mark.asyncio
async def test_sql_update_match_forfeit_zeroes_scores_and_games() -> None:
    """A forfeit forces the match score to 0-0 and clears per-game scores so the
    winner's games (局分) and points (小分) stay unchanged; only the forfeit marker
    is persisted.
    """
    body = MatchBody(
        round_id=RoundId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        court_id=None,
        custom_duration_minutes=None,
        custom_margin_minutes=None,
        # Even with stray per-game scores, a forfeit wipes them.
        games=[[11, 9], [11, 7]],
        best_of=3,
        forfeit_input=1,
    )

    with patch("bracket.sql.matches.database") as mock_db:
        mock_db.execute = AsyncMock()
        await sql_update_match(MatchId(-1), body, _make_tournament())

    values = mock_db.execute.await_args.kwargs["values"]
    assert values["stage_item_input1_score"] == 0
    assert values["stage_item_input2_score"] == 0
    assert values["games"] is None
    assert values["forfeit_input"] == 1
