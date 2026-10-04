from bracket.logic.scheduling.builder import determine_available_inputs
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputFinal,
    StageItemInputTentative,
)
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.models.db.util import StageItemWithRounds, StageWithStageItems
from bracket.utils.dummy_records import (
    DUMMY_MOCK_TIME,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
    DUMMY_TEAM4,
)
from bracket.utils.id_types import (
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


def _make_full_team(team_id: int) -> FullTeamWithPlayers:
    dummy_teams = {1: DUMMY_TEAM1, 2: DUMMY_TEAM2, 3: DUMMY_TEAM3, 4: DUMMY_TEAM4}
    return FullTeamWithPlayers(
        **dummy_teams[team_id].model_dump(),
        id=TeamId(team_id),
        players=[],
    )


def _make_stage_item(
    *,
    stage_item_id: int,
    type_: StageType,
    team_count: int,
    inputs: list[StageItemInputFinal | StageItemInputTentative] | None = None,
) -> StageItemWithRounds:
    return StageItemWithRounds(
        rounds=[],
        inputs=inputs or [],
        type_name=str(type_.value).lower().capitalize().replace("_", " "),
        team_count=team_count,
        ranking_id=None,
        id=StageItemId(stage_item_id),
        stage_id=StageId(-1),
        name="",
        created=DUMMY_MOCK_TIME,
        type=type_,
    )


def test_determine_available_inputs_teams_only_no_inputs_used() -> None:
    """With no stages, every team is available and marked as not taken."""
    teams = [_make_full_team(1), _make_full_team(2), _make_full_team(3)]
    result = determine_available_inputs(teams, [])
    # No stages -> empty dict.
    assert result == {}


def test_determine_available_inputs_teams_only_with_inputs_used() -> None:
    """Teams that have been used as inputs in any stage are marked as taken."""
    tournament_id = TournamentId(-1)
    teams = [_make_full_team(1), _make_full_team(2), _make_full_team(3)]
    used_input = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(1),
        slot=1,
        tournament_id=tournament_id,
        team=_make_full_team(1),
    )
    stage_item = _make_stage_item(
        stage_item_id=-1, type_=StageType.ROUND_ROBIN, team_count=2, inputs=[used_input]
    )
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=DUMMY_MOCK_TIME,
        is_active=True,
        stage_items=[stage_item],
    )

    result = determine_available_inputs(teams, [stage])
    available = result[StageId(-1)]
    # team 1 is taken, teams 2 and 3 are not.
    team_options = [opt for opt in available if hasattr(opt, "team_id")]
    taken = [opt for opt in team_options if opt.already_taken]
    not_taken = [opt for opt in team_options if not opt.already_taken]
    assert len(taken) == 1
    assert taken[0].team_id == TeamId(1)
    assert len(not_taken) == 2
    assert {opt.team_id for opt in not_taken} == {TeamId(2), TeamId(3)}


def test_determine_available_inputs_tentative_only_appear_after_source_stage() -> None:
    """
    Tentative inputs from a stage item only become available AFTER the stage that contains them.
    """
    tournament_id = TournamentId(-1)
    teams = [_make_full_team(1), _make_full_team(2)]
    tentative_input = StageItemInputTentative(
        id=StageItemInputId(-10),
        slot=1,
        tournament_id=tournament_id,
        winner_from_stage_item_id=StageItemId(-1),
        winner_position=1,
    )
    rr_stage_item = _make_stage_item(
        stage_item_id=-1,
        type_=StageType.ROUND_ROBIN,
        team_count=2,
        inputs=[tentative_input],
    )
    rr_stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=DUMMY_MOCK_TIME,
        is_active=True,
        stage_items=[rr_stage_item],
    )
    # Subsequent stage where tentative inputs should appear.
    next_stage = StageWithStageItems(
        id=StageId(-2),
        tournament_id=tournament_id,
        name="",
        created=DUMMY_MOCK_TIME,
        is_active=False,
        stage_items=[],
    )

    result = determine_available_inputs(teams, [rr_stage, next_stage])

    # In the rr_stage itself, tentative inputs are not yet available (only team options).
    rr_options = result[StageId(-1)]
    rr_tentatives = [opt for opt in rr_options if not hasattr(opt, "team_id")]
    assert rr_tentatives == []

    # In the next stage, the tentative options (one per winner_position up to team_count)
    # are now available.
    next_options = result[StageId(-2)]
    next_tentatives = [opt for opt in next_options if not hasattr(opt, "team_id")]
    # team_count=2 generates 2 tentative options.
    assert len(next_tentatives) == 2


def test_determine_available_inputs_tentative_already_taken_marked() -> None:
    """
    A tentative input that exists in any stage's stage_items marks the matching
    tentative option as already_taken.
    """
    tournament_id = TournamentId(-1)
    teams = [_make_full_team(1), _make_full_team(2)]
    tentative_input = StageItemInputTentative(
        id=StageItemInputId(-10),
        slot=1,
        tournament_id=tournament_id,
        winner_from_stage_item_id=StageItemId(-1),
        winner_position=1,  # match winner_position=1
    )
    rr_stage_item = _make_stage_item(
        stage_item_id=-1,
        type_=StageType.ROUND_ROBIN,
        team_count=2,
        inputs=[tentative_input],
    )
    rr_stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=DUMMY_MOCK_TIME,
        is_active=True,
        stage_items=[rr_stage_item],
    )
    next_stage = StageWithStageItems(
        id=StageId(-2),
        tournament_id=tournament_id,
        name="",
        created=DUMMY_MOCK_TIME,
        is_active=False,
        stage_items=[],
    )

    result = determine_available_inputs(teams, [rr_stage, next_stage])
    next_options = result[StageId(-2)]
    next_tentatives = [opt for opt in next_options if not hasattr(opt, "team_id")]

    taken = [opt for opt in next_tentatives if opt.already_taken]
    not_taken = [opt for opt in next_tentatives if not opt.already_taken]
    assert len(taken) == 1
    assert taken[0].winner_position == 1
    assert len(not_taken) == 1
    assert not_taken[0].winner_position == 2


def test_determine_available_inputs_elimination_stage_items_ignored() -> None:
    """SINGLE_ELIMINATION stage items do not produce tentative inputs."""
    tournament_id = TournamentId(-1)
    teams = [_make_full_team(1), _make_full_team(2)]
    used_input = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(1),
        slot=1,
        tournament_id=tournament_id,
        team=_make_full_team(1),
    )
    elim_stage_item = _make_stage_item(
        stage_item_id=-1,
        type_=StageType.SINGLE_ELIMINATION,
        team_count=2,
        inputs=[used_input],
    )
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=DUMMY_MOCK_TIME,
        is_active=True,
        stage_items=[elim_stage_item],
    )

    result = determine_available_inputs(teams, [stage])
    options = result[StageId(-1)]
    # Two team options: team 1 marked taken, team 2 not taken.
    team_options = [opt for opt in options if hasattr(opt, "team_id")]
    assert len(team_options) == 2
    taken = next(opt for opt in team_options if opt.already_taken)
    not_taken = next(opt for opt in team_options if not opt.already_taken)
    assert taken.team_id == TeamId(1)
    assert not_taken.team_id == TeamId(2)
    # No tentative options produced (SINGLE_ELIMINATION stage items have no outputs).
    tentative_options = [opt for opt in options if not hasattr(opt, "team_id")]
    assert tentative_options == []
