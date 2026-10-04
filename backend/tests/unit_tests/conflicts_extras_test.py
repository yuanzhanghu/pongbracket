from datetime import timedelta

from bracket.logic.planning.conflicts import get_conflicting_matches, matches_overlap
from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.utils.dummy_records import DUMMY_MATCH1, DUMMY_MOCK_TIME, DUMMY_TEAM1, DUMMY_TEAM2
from bracket.utils.id_types import (
    CourtId,
    MatchId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)
from tests.integration_tests.mocks import MOCK_NOW


def _match_with(start_time=None, duration_minutes=0, margin_minutes=0):
    """Build a Match with start_time set; end_time is computed by the property."""
    return DUMMY_MATCH1.model_copy(
        update={
            "start_time": start_time,
            "duration_minutes": duration_minutes,
            "margin_minutes": margin_minutes,
        }
    )


def _input(idx: int, team_id: int) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(idx),
        team_id=TeamId(team_id),
        slot=team_id,
        tournament_id=TournamentId(-1),
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(team_id)),
    )


def test_matches_overlap_returns_false_when_start_time_is_none() -> None:
    """When match1 has no start_time, the function returns False immediately. (line 16)"""
    match1 = _match_with(start_time=None, duration_minutes=10)
    match2 = _match_with(start_time=DUMMY_MOCK_TIME, duration_minutes=10)
    assert matches_overlap(match1, match2) is False


def test_matches_overlap_returns_false_when_match2_start_time_is_none() -> None:
    match1 = _match_with(start_time=DUMMY_MOCK_TIME, duration_minutes=10)
    match2 = _match_with(start_time=None, duration_minutes=10)
    assert matches_overlap(match1, match2) is False


def test_matches_overlap_returns_true_for_identical_intervals() -> None:
    """
    Two matches with the same start_time AND the same end_time return True.
    """
    match1 = _match_with(start_time=DUMMY_MOCK_TIME, duration_minutes=30)
    match2 = _match_with(start_time=DUMMY_MOCK_TIME, duration_minutes=30)
    assert matches_overlap(match1, match2) is True


def test_matches_overlap_returns_false_for_non_overlapping_intervals() -> None:
    """Two matches that don't overlap return False."""
    match1 = _match_with(start_time=DUMMY_MOCK_TIME, duration_minutes=30)
    match2 = _match_with(
        start_time=DUMMY_MOCK_TIME + timedelta(minutes=60),
        duration_minutes=30,
    )
    assert matches_overlap(match1, match2) is False


def test_get_conflicting_matches_skips_same_id_duplicate() -> None:
    """
    When two matches share the same id (line 45 check), the inner loop `continue`s
    so they are NOT compared against each other. This exercises line 46.
    """
    # Build a stage item where two rounds each contain a match with the same id (-1).
    # We need the same match listed twice in `matches`; since `matches` is built by
    # flattening stage_item.rounds.matches, having two rounds each with one match of
    # the same id produces two entries with id == -1.
    tournament_id = TournamentId(-1)
    inp1 = _input(-1, 1)
    inp2 = _input(-2, 2)
    match_a = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=inp1,
        stage_item_input2=inp2,
        stage_item_input1_id=inp1.id,
        stage_item_input2_id=inp2.id,
        created=DUMMY_MOCK_TIME,
        start_time=DUMMY_MOCK_TIME,
        duration_minutes=60,
        margin_minutes=0,
        round_id=RoundId(-3),
        court_id=CourtId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    match_b = MatchWithDetailsDefinitive(
        id=MatchId(-1),  # same id -> hits line 46 (continue)
        stage_item_input1=inp1,
        stage_item_input2=inp2,
        stage_item_input1_id=inp1.id,
        stage_item_input2_id=inp2.id,
        created=DUMMY_MOCK_TIME,
        start_time=DUMMY_MOCK_TIME,
        duration_minutes=60,
        margin_minutes=0,
        round_id=RoundId(-4),
        court_id=CourtId(-2),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    round_a = RoundWithMatches(
        id=RoundId(-3),
        matches=[match_a],
        stage_item_id=StageItemId(-1),
        created=DUMMY_MOCK_TIME,
        is_draft=False,
        name="",
    )
    round_b = RoundWithMatches(
        id=RoundId(-4),
        matches=[match_b],
        stage_item_id=StageItemId(-1),
        created=DUMMY_MOCK_TIME,
        is_draft=False,
        name="",
    )
    stage_item_inner = StageItemWithRounds(
        rounds=[round_a, round_b],
        inputs=[inp1, inp2],
        type_name="Single Elimination",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=MOCK_NOW,
        type=StageType.SINGLE_ELIMINATION,
    )
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[stage_item_inner],
    )

    # Both matches have id -1, so the inner loop hits line 46 (continue) when
    # comparing match_a to match_b -> no conflict recorded.
    conflicts_to_set, conflicts_to_clear = get_conflicting_matches([stage])
    assert conflicts_to_set == {}
    # Both matches land in conflicts_to_clear because they have no recorded conflicts.
    assert conflicts_to_clear == {MatchId(-1)}


def test_get_conflicting_matches_input2_conflict_branch() -> None:
    """
    Two overlapping matches where match2's stage_item_input2 is in match1's input set
    exercises line 53 (conflicting_input_ids.append(match2.stage_item_input2_id)).
    """
    tournament_id = TournamentId(-1)
    # match1: input1=-1, input2=-2
    inp1 = _input(-1, 1)
    inp2 = _input(-2, 2)
    inp3 = _input(-3, 3)
    # match2: input1=-3, input2=-1  (so match2's input2 == match1's input1 -> line 53)
    match1 = MatchWithDetailsDefinitive(
        id=MatchId(-10),
        stage_item_input1=inp1,
        stage_item_input2=inp2,
        stage_item_input1_id=inp1.id,
        stage_item_input2_id=inp2.id,
        created=DUMMY_MOCK_TIME,
        start_time=DUMMY_MOCK_TIME,
        duration_minutes=60,
        margin_minutes=0,
        round_id=RoundId(-3),
        court_id=CourtId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    match2 = MatchWithDetailsDefinitive(
        id=MatchId(-20),
        stage_item_input1=inp3,
        stage_item_input2=inp1,  # shared with match1's input1 -> line 53
        stage_item_input1_id=inp3.id,
        stage_item_input2_id=inp1.id,
        created=DUMMY_MOCK_TIME,
        start_time=DUMMY_MOCK_TIME,  # same start -> overlap
        duration_minutes=60,
        margin_minutes=0,
        round_id=RoundId(-3),
        court_id=CourtId(-2),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    round_ = RoundWithMatches(
        id=RoundId(-3),
        matches=[match1, match2],
        stage_item_id=StageItemId(-1),
        created=DUMMY_MOCK_TIME,
        is_draft=False,
        name="",
    )
    stage_item_inner = StageItemWithRounds(
        rounds=[round_],
        inputs=[inp1, inp2],
        type_name="Single Elimination",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=MOCK_NOW,
        type=StageType.SINGLE_ELIMINATION,
    )
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[stage_item_inner],
    )

    conflicts_to_set, conflicts_to_clear = get_conflicting_matches([stage])
    # The shared input is match2.stage_item_input2 == match1.stage_item_input1 (-1).
    # match1's input1 conflicts (True), match1's input2 does not (False).
    # match2's input1 does not conflict (False), match2's input2 conflicts (True)
    # — this exercises line 53 (`append(match2.stage_item_input2_id)`).
    assert conflicts_to_set == {MatchId(-10): [True, False], MatchId(-20): [False, True]}
    assert conflicts_to_clear == set()


def test_get_conflicting_matches_no_shared_inputs_overlap() -> None:
    """
    Two overlapping matches with NO shared inputs hit line 56 (continue) — they
    overlap but contribute no conflict, so both end up in conflicts_to_clear.
    """
    tournament_id = TournamentId(-1)
    inp1 = _input(-1, 1)
    inp2 = _input(-2, 2)
    inp3 = _input(-3, 3)
    inp4 = _input(-4, 4)
    match1 = MatchWithDetailsDefinitive(
        id=MatchId(-30),
        stage_item_input1=inp1,
        stage_item_input2=inp2,
        stage_item_input1_id=inp1.id,
        stage_item_input2_id=inp2.id,
        created=DUMMY_MOCK_TIME,
        start_time=DUMMY_MOCK_TIME,
        duration_minutes=60,
        margin_minutes=0,
        round_id=RoundId(-3),
        court_id=CourtId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    match2 = MatchWithDetailsDefinitive(
        id=MatchId(-40),
        stage_item_input1=inp3,
        stage_item_input2=inp4,  # no overlap with match1's {-1, -2}
        stage_item_input1_id=inp3.id,
        stage_item_input2_id=inp4.id,
        created=DUMMY_MOCK_TIME,
        start_time=DUMMY_MOCK_TIME,  # same time -> overlap
        duration_minutes=60,
        margin_minutes=0,
        round_id=RoundId(-3),
        court_id=CourtId(-2),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    round_ = RoundWithMatches(
        id=RoundId(-3),
        matches=[match1, match2],
        stage_item_id=StageItemId(-1),
        created=DUMMY_MOCK_TIME,
        is_draft=False,
        name="",
    )
    stage_item_inner = StageItemWithRounds(
        rounds=[round_],
        inputs=[inp1, inp2],
        type_name="Single Elimination",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=MOCK_NOW,
        type=StageType.SINGLE_ELIMINATION,
    )
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[stage_item_inner],
    )

    conflicts_to_set, conflicts_to_clear = get_conflicting_matches([stage])
    # matches overlap but share no inputs -> line 56 (continue) -> nothing set
    assert conflicts_to_set == {}
    # both matches end up in conflicts_to_clear
    assert conflicts_to_clear == {MatchId(-30), MatchId(-40)}
