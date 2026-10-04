from collections import defaultdict
from decimal import Decimal

import pytest
from heliclockter import datetime_utc

from bracket.logic.ranking.calculation import (
    determine_team_ranking_for_stage_item,
    set_statistics_for_stage_item_input,
)
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import DUMMY_TEAM1, DUMMY_TEAM2, DUMMY_TEAM3, DUMMY_TEAM4
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


def _make_input(input_id: int, team_id: int, points: Decimal) -> StageItemInputFinal:
    dummy_teams = {1: DUMMY_TEAM1, 2: DUMMY_TEAM2, 3: DUMMY_TEAM3, 4: DUMMY_TEAM4}
    return StageItemInputFinal(
        id=StageItemInputId(input_id),
        team_id=TeamId(team_id),
        slot=team_id,
        tournament_id=TournamentId(-1),
        team=Team(**dummy_teams[team_id].model_dump(), id=TeamId(team_id)),
        points=points,
    )


def _make_ranking(
    *,
    add_score_points: bool = False,
    win_points: Decimal = Decimal("1.0"),
    draw_points: Decimal = Decimal("0.5"),
    loss_points: Decimal = Decimal("0.0"),
) -> Ranking:
    now = datetime_utc.now()
    return Ranking(
        id=RankingId(-1),
        tournament_id=TournamentId(-1),
        created=now,
        win_points=win_points,
        draw_points=draw_points,
        loss_points=loss_points,
        add_score_points=add_score_points,
        position=0,
    )


def _make_stage_item(
    *,
    stage_type: StageType | str = StageType.SINGLE_ELIMINATION,
    rounds: list[RoundWithMatches] | None = None,
    inputs: list[StageItemInputFinal] | None = None,
) -> StageItemWithRounds:
    now = datetime_utc.now()
    return StageItemWithRounds(
        rounds=rounds or [],
        inputs=inputs or [],
        type_name=str(stage_type).lower().capitalize().replace("_", " ")
        if not isinstance(stage_type, StageType)
        else str(stage_type.value).lower().capitalize().replace("_", " "),
        team_count=4,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=stage_type,  # type: ignore[arg-type]
    )


def test_set_statistics_for_stage_item_input_with_add_score_points_team1_wins() -> None:
    """`add_score_points=True` should add the match score to the win/draw/loss points."""
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(-1),
        stage_item_input1_score=11,  # team1 wins
        stage_item_input2_score=7,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    set_statistics_for_stage_item_input(
        team_index=0,
        stats=stats,
        match=match,
        stage_item_input_id=StageItemInputId(-1),
        ranking=_make_ranking(add_score_points=True),
        stage_item=_make_stage_item(stage_type=StageType.SINGLE_ELIMINATION),
    )

    assert stats[StageItemInputId(-1)].wins == 1
    assert stats[StageItemInputId(-1)].points == Decimal("12")  # 1.0 + 11


def test_set_statistics_for_stage_item_input_with_add_score_points_team2_wins() -> None:
    """For team_index=1 (team2), the team's own score is added, not team1's."""
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(-1),
        stage_item_input1_score=7,  # team2 wins
        stage_item_input2_score=11,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    set_statistics_for_stage_item_input(
        team_index=1,
        stats=stats,
        match=match,
        stage_item_input_id=StageItemInputId(-2),
        ranking=_make_ranking(add_score_points=True),
        stage_item=_make_stage_item(stage_type=StageType.SINGLE_ELIMINATION),
    )

    assert stats[StageItemInputId(-2)].wins == 1
    assert stats[StageItemInputId(-2)].points == Decimal("12")  # 1.0 + 11


def test_set_statistics_for_stage_item_input_unsupported_stage_type() -> None:
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(-1),
        stage_item_input1_score=11,
        stage_item_input2_score=7,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    fake_stage_item = StageItemWithRounds.model_construct(
        rounds=[],
        inputs=[input1, input2],
        type_name="Fake Stage",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type="FAKE_STAGE_TYPE",
    )

    with pytest.raises(ValueError, match="Unsupported stage type"):
        set_statistics_for_stage_item_input(
            team_index=0,
            stats=stats,
            match=match,
            stage_item_input_id=StageItemInputId(-1),
            ranking=_make_ranking(),
            stage_item=fake_stage_item,
        )


def test_set_statistics_for_stage_item_input_unsupported_stage_type_forfeit() -> None:
    """The forfeit branch also rejects an unsupported stage type."""
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        forfeit_input=2,  # routes into the forfeit branch
    )
    stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    fake_stage_item = StageItemWithRounds.model_construct(
        rounds=[],
        inputs=[input1, input2],
        type_name="Fake Stage",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type="FAKE_STAGE_TYPE",
    )

    with pytest.raises(ValueError, match="Unsupported stage type"):
        set_statistics_for_stage_item_input(
            team_index=0,
            stats=stats,
            match=match,
            stage_item_input_id=StageItemInputId(-1),
            ranking=_make_ranking(),
            stage_item=fake_stage_item,
        )


def test_determine_team_ranking_sorts_cluster_by_wins() -> None:
    """
    Two inputs with the same points (tie) and different wins -> the one with more wins ranks higher.
    """
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    input3 = _make_input(-3, 3, Decimal("1200"))
    input4 = _make_input(-4, 4, Decimal("1200"))

    matches = [
        # input1 beats input4 (win for input1)
        MatchWithDetailsDefinitive(
            id=MatchId(-1),
            stage_item_input1=input1,
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
        # input2 beats input3 (win for input2)
        MatchWithDetailsDefinitive(
            id=MatchId(-2),
            stage_item_input1=input2,
            stage_item_input2=input3,
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

    # Make input1/input2 share a tie cluster via equal points; input3/input4 also equal.
    stage_item = _make_stage_item(
        stage_type=StageType.SINGLE_ELIMINATION,
        rounds=[round_],
        inputs=[input1, input2, input3, input4],
    )
    ranking = _make_ranking()

    result = determine_team_ranking_for_stage_item(stage_item, ranking)
    ranked_ids = [input_id for input_id, _ in result]

    # input1 has wins=1 in the cluster (input1, input2): ranks above input2.
    # input3 has wins=0 in the cluster (input3, input4): ranks below input4.
    # input2 vs input4 -> equal wins, so tied alphabetically by sort stability.
    assert ranked_ids[0] == StageItemInputId(-1)  # input1
    assert ranked_ids[1] == StageItemInputId(-2)  # input2
    assert StageItemInputId(-3) in ranked_ids[2:]
    assert StageItemInputId(-4) in ranked_ids[2:]


def test_determine_team_ranking_sorts_cluster_by_games_ratio() -> None:
    """
    Two inputs tied on points AND tied on wins -> sort by games won/lost ratio.
    """
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    input3 = _make_input(-3, 3, Decimal("1200"))
    input4 = _make_input(-4, 4, Decimal("1200"))

    matches = [
        # input1 beats input2 with 2-0 (high games ratio)
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
        # input3 beats input4 with 2-1 (lower games ratio)
        MatchWithDetailsDefinitive(
            id=MatchId(-2),
            stage_item_input1=input3,
            stage_item_input2=input4,
            created=now,
            duration_minutes=90,
            margin_minutes=15,
            round_id=RoundId(-1),
            stage_item_input1_score=2,
            stage_item_input2_score=1,
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
        stage_type=StageType.SINGLE_ELIMINATION,
        rounds=[round_],
        inputs=[input1, input2, input3, input4],
    )
    ranking = _make_ranking()

    # Tie cluster: input1/input3 (both 1 win). Sort by games ratio.
    result = determine_team_ranking_for_stage_item(stage_item, ranking)
    ranked_ids = [input_id for input_id, _ in result]

    # input1 ratio = 2/0 = inf; input3 ratio = 2/1 = 2.0. input1 ranks higher.
    assert ranked_ids[0] == StageItemInputId(-1)
    assert ranked_ids[1] == StageItemInputId(-3)


def test_determine_team_ranking_sorts_cluster_by_points_ratio_via_games() -> None:
    """
    Two inputs tied on points, wins, and games ratio -> sort by points ratio (per-game).
    """
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    input3 = _make_input(-3, 3, Decimal("1200"))
    input4 = _make_input(-4, 4, Decimal("1200"))

    # input1 vs input2: 2 wins, 0 losses (games), points ratio via games: 22/10=2.2
    # input3 vs input4: 2 wins, 0 losses (games), points ratio via games: 12/11=~1.09
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
            games=[[11, 5], [11, 5]],
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
            games=[[6, 5], [6, 6]],
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
        stage_type=StageType.SINGLE_ELIMINATION,
        rounds=[round_],
        inputs=[input1, input2, input3, input4],
    )
    ranking = _make_ranking()

    result = determine_team_ranking_for_stage_item(stage_item, ranking)
    ranked_ids = [input_id for input_id, _ in result]

    # input1 has higher points ratio -> ranks above input3.
    assert ranked_ids[0] == StageItemInputId(-1)
    assert ranked_ids[1] == StageItemInputId(-3)


def test_determine_team_ranking_ignores_matches_outside_cluster() -> None:
    """
    A match where neither input belongs to the cluster should be ignored.
    """
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    input3 = _make_input(-3, 3, Decimal("1200"))
    input4 = _make_input(-4, 4, Decimal("1200"))

    # Tie cluster: input1/input2 (both 1 win, both 2-0 in games)
    # input3 vs input4 match must be ignored by submetrics (filter out by id).
    # The cluster test only uses the cluster's ids {input1.id, input2.id}.
    matches = [
        MatchWithDetailsDefinitive(
            id=MatchId(-1),
            stage_item_input1=input1,
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
        MatchWithDetailsDefinitive(
            id=MatchId(-2),
            stage_item_input1=input2,
            stage_item_input2=input3,
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
        stage_type=StageType.SINGLE_ELIMINATION,
        rounds=[round_],
        inputs=[input1, input2, input3, input4],
    )
    ranking = _make_ranking()

    result = determine_team_ranking_for_stage_item(stage_item, ranking)
    ranked_ids = [input_id for input_id, _ in result]

    # input1 and input2 have wins=1 each -> equal; games_won=2, games_lost=0 -> ratio inf -> equal.
    # Falls through to points_ratio via games (none provided, points_won=points_lost=0 -> 0.0).
    # So both are tied at the deepest tie-break -> relative order is whatever sort gives.
    assert StageItemInputId(-1) in ranked_ids[:2]
    assert StageItemInputId(-2) in ranked_ids[:2]


def test_determine_team_ranking_uses_games_points_aggregation() -> None:
    """
    Verify that per-game scores (sum across games) feed into points_won/points_lost.
    Two inputs with same games (won=2, lost=0) but different per-game point totals get
    sorted by points ratio.
    """
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("1200"))
    input2 = _make_input(-2, 2, Decimal("1200"))
    input3 = _make_input(-3, 3, Decimal("1200"))
    input4 = _make_input(-4, 4, Decimal("1200"))

    # input1's per-game total: 11+9 = 20; input2's: 5+7 = 12; ratio = 20/12 = 1.667
    # input3's per-game total: 8+8 = 16; input4's: 9+7 = 16; ratio = 16/16 = 1.0
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
            games=[[11, 5], [9, 7]],
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
            games=[[8, 9], [8, 7]],
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
        stage_type=StageType.SINGLE_ELIMINATION,
        rounds=[round_],
        inputs=[input1, input2, input3, input4],
    )
    ranking = _make_ranking()

    result = determine_team_ranking_for_stage_item(stage_item, ranking)
    ranked_ids = [input_id for input_id, _ in result]

    # input1 ratio=20/12 > input3 ratio=16/16
    assert ranked_ids[0] == StageItemInputId(-1)
    assert ranked_ids[1] == StageItemInputId(-3)


def test_determine_team_ranking_skips_draft_round_matches() -> None:
    """Draft rounds should be filtered out when computing ranks."""
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("0"))
    input2 = _make_input(-2, 2, Decimal("0"))

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
    ]
    round_draft = RoundWithMatches(
        id=RoundId(-2),
        matches=[
            MatchWithDetails(  # not definitive -> ignored
                id=MatchId(-2),
                created=now,
                duration_minutes=90,
                margin_minutes=15,
                round_id=RoundId(-2),
                stage_item_input1_score=0,
                stage_item_input2_score=2,
                stage_item_input1_conflict=False,
                stage_item_input2_conflict=False,
            ),
        ],
        stage_item_id=StageItemId(-1),
        created=now,
        is_draft=True,
        name="draft",
    )
    round_final = RoundWithMatches(
        id=RoundId(-1),
        matches=matches,
        stage_item_id=StageItemId(-1),
        created=now,
        is_draft=False,
        name="R1",
    )
    stage_item = _make_stage_item(
        stage_type=StageType.SINGLE_ELIMINATION,
        rounds=[round_final, round_draft],
        inputs=[input1, input2],
    )
    ranking = _make_ranking()

    result = determine_team_ranking_for_stage_item(stage_item, ranking)
    stats_dict = dict(result)
    # input1 wins 1 match -> wins=1, draws=0, losses=0; input2 wins=0.
    assert stats_dict[StageItemInputId(-1)].wins == 1
    assert stats_dict[StageItemInputId(-2)].wins == 0


def test_determine_team_ranking_submetrics_3way_cluster() -> None:
    """
    3-input round-robin (each input plays the other two once). Each input ends up
    with 1W + 1L -> equal points -> single 3-way cluster. Within the cluster:
      - Match A (input1 vs input2, 2-0): s1 > s2 -> line 134 (wins[id1] += 1)
      - Match C (input1 vs input3, 1-2): s2 > s1 -> line 136 (wins[id2] += 1)
      - All matches have games -> lines 138-143
      - games_lost > 0 for each input -> ratio() returns won/lost (line 148)
    """
    now = datetime_utc.now()
    input1 = _make_input(-1, 1, Decimal("0"))
    input2 = _make_input(-2, 2, Decimal("0"))
    input3 = _make_input(-3, 3, Decimal("0"))

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
            games=[[11, 0], [11, 0]],
        ),
        MatchWithDetailsDefinitive(
            id=MatchId(-2),
            stage_item_input1=input2,
            stage_item_input2=input3,
            created=now,
            duration_minutes=90,
            margin_minutes=15,
            round_id=RoundId(-1),
            stage_item_input1_score=2,
            stage_item_input2_score=0,
            stage_item_input1_conflict=False,
            stage_item_input2_conflict=False,
            games=[[11, 0], [11, 0]],
        ),
        MatchWithDetailsDefinitive(
            id=MatchId(-3),
            stage_item_input1=input1,
            stage_item_input2=input3,
            created=now,
            duration_minutes=90,
            margin_minutes=15,
            round_id=RoundId(-1),
            stage_item_input1_score=1,
            stage_item_input2_score=2,
            stage_item_input1_conflict=False,
            stage_item_input2_conflict=False,
            games=[[8, 11], [9, 11]],
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
        stage_type=StageType.SINGLE_ELIMINATION,
        rounds=[round_],
        inputs=[input1, input2, input3],
    )
    ranking = _make_ranking()

    result = determine_team_ranking_for_stage_item(stage_item, ranking)
    stats = dict(result)
    ranked_ids = [input_id for input_id, _ in result]

    # Each input: 1W 1L -> equal points -> same cluster.
    assert stats[StageItemInputId(-1)].wins == 1
    assert stats[StageItemInputId(-2)].wins == 1
    assert stats[StageItemInputId(-3)].wins == 1
    # Sort by games ratio: input1 (3/2 = 1.5) > input2 (2/2 = 1.0) > input3 (2/3 = 0.667).
    assert ranked_ids == [
        StageItemInputId(-1),
        StageItemInputId(-2),
        StageItemInputId(-3),
    ]
