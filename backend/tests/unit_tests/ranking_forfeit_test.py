from decimal import Decimal

from heliclockter import datetime_utc

from bracket.logic.ranking.calculation import determine_ranking_for_stage_item
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import DUMMY_TEAM1, DUMMY_TEAM2
from bracket.utils.id_types import (
    MatchId,
    RankingId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)

NOW = datetime_utc.now()
TOURNAMENT_ID = TournamentId(-1)

INPUT1 = StageItemInputFinal(
    id=StageItemInputId(-1),
    team_id=TeamId(-1),
    slot=1,
    tournament_id=TOURNAMENT_ID,
    team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
)
INPUT2 = StageItemInputFinal(
    id=StageItemInputId(-2),
    team_id=TeamId(-2),
    slot=1,
    tournament_id=TOURNAMENT_ID,
    team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
)

RANKING = Ranking(
    id=RankingId(-1),
    tournament_id=TOURNAMENT_ID,
    created=NOW,
    win_points=Decimal("2.0"),
    draw_points=Decimal("0.5"),
    loss_points=Decimal("1.0"),
    add_score_points=False,
    position=0,
)


def _forfeit_match(forfeit_input: int) -> MatchWithDetailsDefinitive:
    return MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=INPUT1,
        stage_item_input2=INPUT2,
        created=NOW,
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        forfeit_input=forfeit_input,
    )


def _stage_item(match: MatchWithDetailsDefinitive) -> StageItemWithRounds:
    return StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=[match],
                stage_item_id=StageItemId(-1),
                created=NOW,
                is_draft=False,
                name="",
            )
        ],
        inputs=[INPUT1, INPUT2],
        type_name="Round Robin",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=NOW,
        type=StageType.ROUND_ROBIN,
    )


def test_forfeit_awards_win_points_to_other_side() -> None:
    # input1 forfeits: input2 wins (2 pts), input1 gets 0 pts (not loss_points of 1).
    ranking = determine_ranking_for_stage_item(_stage_item(_forfeit_match(1)), RANKING)
    assert ranking == {
        -1: TeamStatistics(wins=0, draws=0, losses=1, points=Decimal("0")),
        -2: TeamStatistics(wins=1, draws=0, losses=0, points=Decimal("2.0")),
    }


def test_forfeit_other_direction() -> None:
    ranking = determine_ranking_for_stage_item(_stage_item(_forfeit_match(2)), RANKING)
    assert ranking == {
        -1: TeamStatistics(wins=1, draws=0, losses=0, points=Decimal("2.0")),
        -2: TeamStatistics(wins=0, draws=0, losses=1, points=Decimal("0")),
    }


def test_get_winner_is_forfeit_aware() -> None:
    assert _forfeit_match(1).get_winner() == INPUT2
    assert _forfeit_match(2).get_winner() == INPUT1
