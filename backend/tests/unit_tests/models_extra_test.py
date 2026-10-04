"""
Extra tests for bracket/models/db/* to raise coverage on targeted lines.
"""

from decimal import Decimal

import pytest

from bracket.models.db.account import UserAccountType
from bracket.models.db.match import (
    Match,
    MatchBaseInsertable,
    MatchBody,
    MatchCreateBody,
    MatchWithDetailsDefinitive,
    SuggestedMatch,
    get_match_hash,
)
from bracket.models.db.player import Player, PlayerInsertable
from bracket.models.db.stage_item import (
    StageItemWithInputsCreate,
    StageType,
)
from bracket.models.db.stage_item_inputs import (
    StageItemInputEmpty,
    StageItemInputFinal,
    StageItemInputTentative,
    StageItemInputUpdateBodyTentative,
)
from bracket.models.db.user import User, UserBase
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_TEAM1, DUMMY_TEAM2
from bracket.utils.id_types import (
    MatchId,
    PlayerId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
    UserId,
)
from bracket.utils.types import EnumAutoStr


# ------------------------------------------------------------------
# bracket/models/db/player.py — line 26 (Player.__hash__)
# ------------------------------------------------------------------


def test_player_hash_uses_id() -> None:
    """Player.__hash__ returns its id (line 26)."""
    p1 = Player(
        id=PlayerId(1),
        active=True,
        name="P1",
        created=DUMMY_MOCK_TIME,
        tournament_id=TournamentId(-1),
    )
    p2 = Player(
        id=PlayerId(1),
        active=True,
        name="P1",
        created=DUMMY_MOCK_TIME,
        tournament_id=TournamentId(-1),
    )
    p3 = Player(
        id=PlayerId(2),
        active=True,
        name="P3",
        created=DUMMY_MOCK_TIME,
        tournament_id=TournamentId(-1),
    )
    # Equal ids -> equal hashes (and equal hash-based equality).
    assert hash(p1) == hash(p2) == PlayerId(1)
    assert hash(p1) != hash(p3)


# ------------------------------------------------------------------
# bracket/models/db/user.py — lines 24-26 (UserBase.subscription property)
# ------------------------------------------------------------------


def test_userbase_subscription_property_returns_lookup() -> None:
    """UserBase.subscription property returns subscription_lookup[account_type] (lines 24-26)."""
    from bracket.logic.subscriptions import subscription_lookup

    u = UserBase(
        email="x@example.org",
        name="X",
        created=DUMMY_MOCK_TIME,
        account_type=UserAccountType.REGULAR,
    )
    sub = u.subscription
    assert sub is subscription_lookup[UserAccountType.REGULAR]


def test_user_password_hash_optional() -> None:
    """User.password_hash is optional (None when missing)."""
    u = User(
        id=UserId(1),
        email="x@example.org",
        name="X",
        created=DUMMY_MOCK_TIME,
        account_type=UserAccountType.REGULAR,
        password_hash=None,
    )
    assert u.password_hash is None


# ------------------------------------------------------------------
# bracket/models/db/stage_item.py — lines 62, 71
#   (StageItemWithInputsCreate.get_name_or_default_name + model_validator)
# ------------------------------------------------------------------


def test_stage_item_with_inputs_create_get_name_uses_default() -> None:
    """When name is None, the type title is used (line 62)."""
    from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyEmpty

    obj = StageItemWithInputsCreate(
        stage_id=StageId(-1),
        name=None,
        type=StageType.SINGLE_ELIMINATION,
        team_count=4,
        inputs=[
            StageItemInputCreateBodyEmpty(slot=1),
            StageItemInputCreateBodyEmpty(slot=2),
            StageItemInputCreateBodyEmpty(slot=3),
            StageItemInputCreateBodyEmpty(slot=4),
        ],
    )
    assert obj.get_name_or_default_name() == "Single Elimination"


def test_stage_item_with_inputs_create_get_name_uses_provided() -> None:
    """When name is set, the provided name is returned."""
    from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyEmpty

    obj = StageItemWithInputsCreate(
        stage_id=StageId(-1),
        name="My Bracket",
        type=StageType.SINGLE_ELIMINATION,
        team_count=2,
        inputs=[
            StageItemInputCreateBodyEmpty(slot=1),
            StageItemInputCreateBodyEmpty(slot=2),
        ],
    )
    assert obj.get_name_or_default_name() == "My Bracket"


def test_stage_item_with_inputs_create_validator_team_count_mismatch() -> None:
    """Validator raises if inputs length != team_count (line 71)."""
    from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyEmpty

    with pytest.raises(ValueError, match="team_count doesn't match"):
        StageItemWithInputsCreate.model_validate(
            {
                "stage_id": -1,
                "name": "x",
                "type": StageType.SINGLE_ELIMINATION.value,
                "team_count": 4,
                "inputs": [
                    {"slot": 1},
                    {"slot": 2},
                ],
            }
        )


def test_stage_type_supports_dynamic_number_of_rounds() -> None:
    """StageType.supports_dynamic_number_of_rounds is always False."""
    assert StageType.ROUND_ROBIN.supports_dynamic_number_of_rounds is False
    assert StageType.SINGLE_ELIMINATION.supports_dynamic_number_of_rounds is False


# ------------------------------------------------------------------
# bracket/models/db/stage_item_inputs.py — line 36
#   (StageItemInputGeneric.elo property)
# ------------------------------------------------------------------


def test_stage_item_input_empty_elo_returns_points() -> None:
    """StageItemInputGeneric.elo returns self.points (line 36)."""
    sii = StageItemInputEmpty(
        id=StageItemInputId(-1),
        slot=1,
        tournament_id=TournamentId(-1),
        points=Decimal("1234.5"),
    )
    assert sii.elo == Decimal("1234.5")


def test_stage_item_input_final_elo_returns_points() -> None:
    sii = StageItemInputFinal(
        id=StageItemInputId(-1),
        slot=1,
        tournament_id=TournamentId(-1),
        team_id=TeamId(-1),
        team=TeamId_to_team(TeamId(-1)),  # type: ignore[arg-type]
        points=Decimal("1500"),
    )
    assert sii.elo == Decimal("1500")


def TeamId_to_team(team_id: TeamId):  # type: ignore[no-untyped-def]
    from bracket.models.db.team import Team

    return Team(
        id=team_id,
        active=True,
        name=f"Team-{team_id}",
        created=DUMMY_MOCK_TIME,
        tournament_id=TournamentId(-1),
    )


def test_stage_item_input_tentative_lookup_key() -> None:
    sii = StageItemInputTentative(
        id=StageItemInputId(-1),
        slot=1,
        tournament_id=TournamentId(-1),
        winner_from_stage_item_id=StageItemId(-7),
        winner_position=3,
    )
    assert sii.get_lookup_key() == (StageItemId(-7), 3)


def test_stage_item_input_update_body_tentative_validates_winner_position() -> None:
    """StageItemInputUpdateBodyTentative.winner_position must be >= 1."""
    with pytest.raises(Exception):
        StageItemInputUpdateBodyTentative(
            winner_from_stage_item_id=StageItemId(-1),
            winner_position=0,
        )


# ------------------------------------------------------------------
# bracket/models/db/match.py — lines 37, 154
#   (_parse_games validator + SuggestedMatch.stage_item_input_ids)
# ------------------------------------------------------------------


def test_match_parse_games_validator_passes_through_list() -> None:
    """If value is already a list, _parse_games returns it unchanged."""
    mb = MatchBaseInsertable(
        created=DUMMY_MOCK_TIME,
        duration_minutes=10,
        margin_minutes=5,
        round_id=RoundId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        games=[[11, 9], [9, 11]],
    )
    assert mb.games == [[11, 9], [9, 11]]


def test_match_parse_games_validator_decodes_json_string() -> None:
    """String JSON values are parsed into a list. (line 37)"""
    import json

    mb = MatchBaseInsertable.model_validate(
        {
            "created": DUMMY_MOCK_TIME,
            "duration_minutes": 10,
            "margin_minutes": 5,
            "round_id": -1,
            "stage_item_input1_score": 0,
            "stage_item_input2_score": 0,
            "stage_item_input1_conflict": False,
            "stage_item_input2_conflict": False,
            "games": json.dumps([[11, 9], [11, 7]]),
        }
    )
    assert mb.games == [[11, 9], [11, 7]]


def test_match_parse_games_validator_empty_string_becomes_none() -> None:
    """Empty string JSON value -> None (line 37)."""
    mb = MatchBaseInsertable.model_validate(
        {
            "created": DUMMY_MOCK_TIME,
            "duration_minutes": 10,
            "margin_minutes": 5,
            "round_id": -1,
            "stage_item_input1_score": 0,
            "stage_item_input2_score": 0,
            "stage_item_input1_conflict": False,
            "stage_item_input2_conflict": False,
            "games": "   ",
        }
    )
    assert mb.games is None


def test_match_end_time_computed() -> None:
    """end_time = start_time + duration + margin."""
    from heliclockter import timedelta

    mb = MatchBaseInsertable(
        created=DUMMY_MOCK_TIME,
        start_time=DUMMY_MOCK_TIME,
        duration_minutes=30,
        margin_minutes=10,
        round_id=RoundId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    assert mb.end_time == DUMMY_MOCK_TIME + timedelta(minutes=40)


def test_suggested_match_stage_item_input_ids() -> None:
    """SuggestedMatch.stage_item_input_ids returns [input1.id, input2.id] (line 154)."""
    sii1 = StageItemInputFinal(
        id=StageItemInputId(-10),
        slot=1,
        tournament_id=TournamentId(-1),
        team_id=TeamId(-1),
        team=TeamId_to_team(TeamId(-1)),  # type: ignore[arg-type]
    )
    sii2 = StageItemInputFinal(
        id=StageItemInputId(-20),
        slot=2,
        tournament_id=TournamentId(-1),
        team_id=TeamId(-2),
        team=TeamId_to_team(TeamId(-2)),  # type: ignore[arg-type]
    )
    sm = SuggestedMatch(
        stage_item_input1=sii1,
        stage_item_input2=sii2,
        elo_diff=Decimal("10"),
        is_recommended=True,
        times_played_sum=1,
        player_behind_schedule_count=0,
    )
    assert sm.stage_item_input_ids == [StageItemInputId(-10), StageItemInputId(-20)]


def test_match_get_winner() -> None:
    """Match.get_winner returns the higher-scoring input or None for draw."""
    sii1 = StageItemInputFinal(
        id=StageItemInputId(-10),
        slot=1,
        tournament_id=TournamentId(-1),
        team_id=TeamId(-1),
        team=TeamId_to_team(TeamId(-1)),  # type: ignore[arg-type]
    )
    sii2 = StageItemInputFinal(
        id=StageItemInputId(-20),
        slot=2,
        tournament_id=TournamentId(-1),
        team_id=TeamId(-2),
        team=TeamId_to_team(TeamId(-2)),  # type: ignore[arg-type]
    )
    m_winner1 = Match(
        id=MatchId(-1),
        created=DUMMY_MOCK_TIME,
        duration_minutes=10,
        margin_minutes=5,
        round_id=RoundId(-1),
        stage_item_input1_score=11,
        stage_item_input2_score=7,
        stage_item_input1=sii1,
        stage_item_input2=sii2,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    assert m_winner1.get_winner() == sii1

    m_draw = m_winner1.model_copy(
        update={"stage_item_input1_score": 11, "stage_item_input2_score": 11}
    )
    assert m_draw.get_winner() is None

    m_winner2 = m_winner1.model_copy(
        update={"stage_item_input1_score": 7, "stage_item_input2_score": 11}
    )
    assert m_winner2.get_winner() == sii2


def test_get_match_hash() -> None:
    """get_match_hash returns '{id1}-{id2}'."""
    assert get_match_hash(StageItemInputId(1), StageItemInputId(2)) == "1-2"
    assert get_match_hash(None, StageItemInputId(2)) == "None-2"


def test_match_body_and_create_body() -> None:
    """MatchBody and MatchCreateBody construct with default scores."""
    mb = MatchBody(round_id=RoundId(-1))
    assert mb.stage_item_input1_score == 0
    assert mb.stage_item_input2_score == 0

    mcb = MatchCreateBody(round_id=RoundId(-1), duration_minutes=10, margin_minutes=5)
    assert mcb.duration_minutes == 10
    assert mcb.margin_minutes == 5


def test_match_with_details_definitive_helpers() -> None:
    """stage_item_inputs and stage_item_input_ids properties."""
    sii1 = StageItemInputFinal(
        id=StageItemInputId(-10),
        slot=1,
        tournament_id=TournamentId(-1),
        team_id=TeamId(-1),
        team=TeamId_to_team(TeamId(-1)),  # type: ignore[arg-type]
    )
    sii2 = StageItemInputFinal(
        id=StageItemInputId(-20),
        slot=2,
        tournament_id=TournamentId(-1),
        team_id=TeamId(-2),
        team=TeamId_to_team(TeamId(-2)),  # type: ignore[arg-type]
    )
    md = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        created=DUMMY_MOCK_TIME,
        duration_minutes=10,
        margin_minutes=5,
        round_id=RoundId(-1),
        stage_item_input1_id=StageItemInputId(-10),
        stage_item_input2_id=StageItemInputId(-20),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1=sii1,
        stage_item_input2=sii2,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    assert md.stage_item_inputs == [sii1, sii2]
    assert md.stage_item_input_ids == [StageItemInputId(-10), StageItemInputId(-20)]
    hashes = md.get_input_ids_hashes()
    assert hashes == ["-10--20", "-20--10"]
