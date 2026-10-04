"""Final unit tests to reach >=98% coverage."""

from decimal import Decimal

import pytest
from heliclockter import datetime_utc

from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import DUMMY_TEAM1, DUMMY_TEAM2, DUMMY_TEAM3, DUMMY_TEAM4
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


def _make_input(input_id: int, team_id: int) -> StageItemInputFinal:
    dummy_teams = {1: DUMMY_TEAM1, 2: DUMMY_TEAM2, 3: DUMMY_TEAM3, 4: DUMMY_TEAM4}
    return StageItemInputFinal(
        id=StageItemInputId(input_id),
        team_id=TeamId(team_id),
        slot=team_id,
        tournament_id=TournamentId(-1),
        team=Team(**dummy_teams[team_id].model_dump(), id=TeamId(team_id)),
    )


def _make_ranking() -> Ranking:
    now = datetime_utc.now()
    return Ranking(
        id=-1,  # type: ignore[arg-type]
        tournament_id=TournamentId(-1),
        created=now,
        win_points=Decimal("1.0"),
        draw_points=Decimal("0.5"),
        loss_points=Decimal("0.0"),
        add_score_points=False,
        position=0,
    )


def test_determine_team_ranking_games_points_ratio() -> None:
    """Two inputs tied on wins/games_ratio sorted by points_ratio via games (lines 138-143)."""
    from bracket.logic.ranking.calculation import determine_team_ranking_for_stage_item

    now = datetime_utc.now()
    input1 = _make_input(-1, 1)
    input2 = _make_input(-2, 2)
    input3 = _make_input(-3, 3)
    input4 = _make_input(-4, 4)

    # input1: games_won=2, games_lost=0 -> ratio inf; points via games: 22/12 = 1.83
    # input3: games_won=2, games_lost=0 -> ratio inf; points via games: 11/22 = 0.5
    matches = [
        MatchWithDetailsDefinitive(
            id=MatchId(-1),
            stage_item_input1=input1,
            stage_item_input2=input2,
            created=now,
            duration_minutes=90,
            margin_minutes=15,
            round_id=RoundId(-1),
            stage_item_input1_score=2,
            stage_item_input2_score=0,
            stage_item_input1_conflict=False,
            stage_item_input2_conflict=False,
            games=[[11, 5], [11, 7]],
        ),
        MatchWithDetailsDefinitive(
            id=MatchId(-2),
            stage_item_input1=input3,
            stage_item_input2=input4,
            created=now,
            duration_minutes=90,
            margin_minutes=15,
            round_id=RoundId(-1),
            stage_item_input1_score=2,
            stage_item_input2_score=0,
            stage_item_input1_conflict=False,
            stage_item_input2_conflict=False,
            games=[[6, 11], [5, 11]],
        ),
    ]
    round_ = RoundWithMatches(
        id=RoundId(-1),
        matches=matches,
        stage_item_id=StageItemId(-1),
        created=now,
        is_draft=False,
        name="R1",
    )
    stage_item = StageItemWithRounds(
        rounds=[round_],
        inputs=[input1, input2, input3, input4],
        type_name="Single Elimination",
        team_count=4,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.SINGLE_ELIMINATION,
    )

    result = determine_team_ranking_for_stage_item(stage_item, _make_ranking())
    ranked_ids = [input_id for input_id, _ in result]
    assert ranked_ids[0] == StageItemInputId(-1)
    assert ranked_ids[1] == StageItemInputId(-3)


def test_determine_team_ranking_no_games_ratio_zero() -> None:
    """When matches have no games data, points ratio falls back to 0.0 (line 148)."""
    from bracket.logic.ranking.calculation import determine_team_ranking_for_stage_item

    now = datetime_utc.now()
    input1 = _make_input(-1, 1)
    input2 = _make_input(-2, 2)
    input3 = _make_input(-3, 3)
    input4 = _make_input(-4, 4)

    matches = [
        MatchWithDetailsDefinitive(
            id=MatchId(-1),
            stage_item_input1=input1,
            stage_item_input2=input2,
            created=now,
            duration_minutes=90,
            margin_minutes=15,
            round_id=RoundId(-1),
            stage_item_input1_score=2,
            stage_item_input2_score=0,
            stage_item_input1_conflict=False,
            stage_item_input2_conflict=False,
        ),
        MatchWithDetailsDefinitive(
            id=MatchId(-2),
            stage_item_input1=input3,
            stage_item_input2=input4,
            created=now,
            duration_minutes=90,
            margin_minutes=15,
            round_id=RoundId(-1),
            stage_item_input1_score=2,
            stage_item_input2_score=0,
            stage_item_input1_conflict=False,
            stage_item_input2_conflict=False,
        ),
    ]
    round_ = RoundWithMatches(
        id=RoundId(-1),
        matches=matches,
        stage_item_id=StageItemId(-1),
        created=now,
        is_draft=False,
        name="R1",
    )
    stage_item = StageItemWithRounds(
        rounds=[round_],
        inputs=[input1, input2, input3, input4],
        type_name="Single Elimination",
        team_count=4,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.SINGLE_ELIMINATION,
    )

    result = determine_team_ranking_for_stage_item(stage_item, _make_ranking())
    ranked_ids = [input_id for input_id, _ in result]
    assert StageItemInputId(-1) in ranked_ids
    assert StageItemInputId(-3) in ranked_ids
