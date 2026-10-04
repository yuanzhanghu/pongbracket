"""Extra unit tests round 2 to raise backend coverage."""

import asyncio
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

import pytest
from heliclockter import datetime_utc

from bracket.cronjobs.scheduling import (
    CRONJOBS,
    run_cronjob,
    start_cronjobs,
)
from bracket.logic.ranking.calculation import determine_team_ranking_for_stage_item
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.asyncio import AsyncioTasksManager
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


def _make_stage_item(stage_type: StageType, rounds: list, inputs: list) -> StageItemWithRounds:
    return StageItemWithRounds(
        rounds=rounds,
        inputs=inputs,
        type_name=str(stage_type),
        team_count=max(len(inputs), 2),
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=datetime_utc.now(),
        type=stage_type,
    )


# ------------------------------------------------------------------
# bracket/cronjobs/scheduling.py: 29-35, 42-43
# ------------------------------------------------------------------


def test_start_cronjobs_creates_tasks() -> None:

    async def runner() -> int:
        AsyncioTasksManager._tasks.clear()
        start_cronjobs()
        n = len(AsyncioTasksManager._tasks)
        for task in list(AsyncioTasksManager._tasks):
            task.cancel()
        AsyncioTasksManager._tasks.clear()
        return n

    assert asyncio.run(runner()) == len(CRONJOBS)


# ------------------------------------------------------------------
# bracket/logic/ranking/calculation.py: 134, 136, 138-143, 148
# ------------------------------------------------------------------


def test_determine_team_ranking_points_ratio_via_games() -> None:
    """Sort by points ratio via games when tied on wins/games ratio. (lines 138-143)"""
    now = datetime_utc.now()
    input1 = _make_input(-1, 1)
    input2 = _make_input(-2, 2)
    input3 = _make_input(-3, 3)
    input4 = _make_input(-4, 4)

    # input1 per-game totals: (11+11) = 22 / (5+7) = 12, ratio 22/12 ≈ 1.83
    # input3 per-game totals: (6+5) = 11 / (11+11) = 22, ratio 11/22 ≈ 0.5
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
    stage_item = _make_stage_item(
        StageType.SINGLE_ELIMINATION, [round_], [input1, input2, input3, input4]
    )

    result = determine_team_ranking_for_stage_item(stage_item, _make_ranking())
    ranked_ids = [input_id for input_id, _ in result]
    # input1 has higher points ratio -> ranks above input3
    assert ranked_ids[0] == StageItemInputId(-1)
    assert ranked_ids[1] == StageItemInputId(-3)


def test_determine_team_ranking_no_games_points_ratio_zero() -> None:
    """When matches have no games data, points ratio falls back to 0.0. (line 148)"""
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
    stage_item = _make_stage_item(
        StageType.SINGLE_ELIMINATION, [round_], [input1, input2, input3, input4]
    )

    result = determine_team_ranking_for_stage_item(stage_item, _make_ranking())
    ranked_ids = [input_id for input_id, _ in result]
    assert StageItemInputId(-1) in ranked_ids
    assert StageItemInputId(-2) in ranked_ids
    assert StageItemInputId(-3) in ranked_ids
    assert StageItemInputId(-4) in ranked_ids
