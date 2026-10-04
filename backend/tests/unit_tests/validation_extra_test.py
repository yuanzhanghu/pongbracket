"""
Unit tests for bracket/sql/validation.py — specifically the per-tournament
foreign-key check helpers and check_foreign_keys_belong_to_tournament.

We mock the DB-touching helpers (get_team_by_id, get_player_by_id,
get_full_tournament_details, get_all_players_in_tournament,
get_all_courts_in_tournament) so the tests stay in-process and fast.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from bracket.models.db.match import Match, MatchWithDetailsDefinitive
from bracket.models.db.round import Round
from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage import Stage
from bracket.models.db.stage_item import StageItem, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInput,
    StageItemInputEmpty,
)
from bracket.models.db.util import (
    RoundWithMatches,
    StageItemWithRounds,
    StageWithStageItems,
)
from bracket.sql.validation import (
    check_court_belongs_to_tournament,
    check_foreign_keys_belong_to_tournament,
    check_match_belongs_to_tournament,
    check_player_belongs_to_tournament,
    check_players_belong_to_tournament,
    check_round_belongs_to_tournament,
    check_stage_belongs_to_tournament,
    check_stage_item_belongs_to_tournament,
    check_stage_item_input_belongs_to_tournament,
    check_team_belongs_to_tournament,
    raise_exception,
)
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import (
    CourtId,
    MatchId,
    PlayerId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


# ---------------------------------------------------------------------------
# Helpers to build StageWithStageItems trees for the pure-logic checks.
# ---------------------------------------------------------------------------


def _make_input(input_id: StageItemInputId) -> StageItemInput:
    return StageItemInputEmpty(
        id=input_id,
        slot=1,
        tournament_id=TournamentId(-1),
        stage_item_id=None,
    )


def _make_match(match_id: MatchId) -> Match:
    return Match(
        id=match_id,
        created=DUMMY_MOCK_TIME,
        start_time=None,
        duration_minutes=10,
        margin_minutes=5,
        custom_duration_minutes=None,
        custom_margin_minutes=None,
        position_in_schedule=None,
        round_id=RoundId(-1),
        stage_item_input1_id=None,
        stage_item_input2_id=None,
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        court_id=None,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        games=None,
        best_of=3,
    )


def _make_round(round_id: RoundId, match_ids: list[MatchId]) -> RoundWithMatches:
    return RoundWithMatches(
        id=round_id,
        created=DUMMY_MOCK_TIME,
        is_draft=False,
        name="R",
        stage_item_id=StageItemId(-1),
        matches=[_make_match(mid) for mid in match_ids],
    )


def _make_stage_item(
    stage_item_id: StageItemId,
    input_ids: list[StageItemInputId],
    round_ids: list[MatchId] | None = None,
    match_ids: list[MatchId] | None = None,
) -> StageItemWithRounds:
    return StageItemWithRounds(
        id=stage_item_id,
        stage_id=StageId(-1),
        name="SI",
        created=DUMMY_MOCK_TIME,
        type=StageType.ROUND_ROBIN,
        team_count=2,
        ranking_id=None,
        rounds=[_make_round(rid, match_ids or []) for rid in (round_ids or [])],
        inputs=[_make_input(iid) for iid in input_ids],
        type_name="Round robin",
    )


def _make_stage(stage_id: StageId, stage_items: list[StageItemWithRounds]) -> StageWithStageItems:
    return StageWithStageItems(
        id=stage_id,
        tournament_id=TournamentId(-1),
        name="S",
        created=DUMMY_MOCK_TIME,
        is_active=True,
        stage_items=stage_items,
    )


# ---------------------------------------------------------------------------
# check_team_belongs_to_tournament (line 37) — DB call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_team_belongs_to_tournament_true() -> None:
    with patch(
        "bracket.sql.validation.get_team_by_id", AsyncMock(return_value=object())
    ) as mock_get:
        result = await check_team_belongs_to_tournament(TeamId(42), [], TournamentId(1))
    assert result is True
    mock_get.assert_awaited_once_with(TeamId(42), TournamentId(1))


@pytest.mark.asyncio
async def test_check_team_belongs_to_tournament_false() -> None:
    with patch("bracket.sql.validation.get_team_by_id", AsyncMock(return_value=None)):
        result = await check_team_belongs_to_tournament(TeamId(42), [], TournamentId(1))
    assert result is False


# ---------------------------------------------------------------------------
# check_stage_item_input_belongs_to_tournament (line 51) — pure logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_stage_item_input_belongs_true() -> None:
    target = StageItemInputId(7)
    si = _make_stage_item(StageItemId(1), [target])
    stages: list[StageWithStageItems] = [_make_stage(StageId(1), [si])]
    assert (
        await check_stage_item_input_belongs_to_tournament(target, stages, TournamentId(1)) is True
    )


@pytest.mark.asyncio
async def test_check_stage_item_input_belongs_false() -> None:
    si = _make_stage_item(StageItemId(1), [StageItemInputId(7)])
    stages: list[StageWithStageItems] = [_make_stage(StageId(1), [si])]
    assert (
        await check_stage_item_input_belongs_to_tournament(
            StageItemInputId(999), stages, TournamentId(1)
        )
        is False
    )


# ---------------------------------------------------------------------------
# check_match_belongs_to_tournament (line 73) — pure logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_match_belongs_true() -> None:
    target = MatchId(11)
    si = _make_stage_item(StageItemId(1), [], round_ids=[RoundId(1)], match_ids=[target])
    stages: list[StageWithStageItems] = [_make_stage(StageId(1), [si])]
    assert await check_match_belongs_to_tournament(target, stages, TournamentId(1)) is True


@pytest.mark.asyncio
async def test_check_match_belongs_false() -> None:
    si = _make_stage_item(StageItemId(1), [], round_ids=[RoundId(1)], match_ids=[MatchId(11)])
    stages: list[StageWithStageItems] = [_make_stage(StageId(1), [si])]
    assert await check_match_belongs_to_tournament(MatchId(999), stages, TournamentId(1)) is False


# ---------------------------------------------------------------------------
# check_player_belongs_to_tournament (line 85) — DB call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_player_belongs_true() -> None:
    with patch(
        "bracket.sql.validation.get_player_by_id", AsyncMock(return_value=object())
    ) as mock_get:
        result = await check_player_belongs_to_tournament(PlayerId(5), [], TournamentId(1))
    assert result is True
    mock_get.assert_awaited_once_with(PlayerId(5), TournamentId(1))


@pytest.mark.asyncio
async def test_check_player_belongs_false() -> None:
    with patch("bracket.sql.validation.get_player_by_id", AsyncMock(return_value=None)):
        result = await check_player_belongs_to_tournament(PlayerId(5), [], TournamentId(1))
    assert result is False


# ---------------------------------------------------------------------------
# raise_exception — direct unit test
# ---------------------------------------------------------------------------


def test_raise_exception_uses_type_name() -> None:
    with pytest.raises(HTTPException) as exc_info:
        raise_exception(TeamId, TeamId(42))
    assert exc_info.value.status_code == 400
    assert "队伍" in str(exc_info.value.detail)
    assert "42" in str(exc_info.value.detail)


def test_raise_exception_unknown_type() -> None:
    with pytest.raises(HTTPException) as exc_info:
        raise_exception(None, 42)
    assert "Unknown type" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# check_foreign_keys_belong_to_tournament — recursive + error paths
# ---------------------------------------------------------------------------


class _Nested(BaseModel):
    player_id: PlayerId


class _BodyWithNested(BaseModelORM):
    nested: _Nested


class _BodyWithUnknownSet(BaseModelORM):
    items: set[int]


class _BodyWithInvalidPlayer(BaseModelORM):
    player_id: PlayerId


class _BodyWithInvalidMatch(BaseModelORM):
    match_id: MatchId


class _BodyWithInvalidStageItemInput(BaseModelORM):
    stage_item_input_id: StageItemInputId


class _BodyWithInvalidStageItem(BaseModelORM):
    stage_item_id: StageItemId


class _BodyWithInvalidRound(BaseModelORM):
    round_id: RoundId


class _BodyWithInvalidCourt(BaseModelORM):
    court_id: CourtId


class _BodyWithInvalidStage(BaseModelORM):
    stage_id: StageId


class _BodyWithNoneSet(BaseModelORM):
    items: set[PlayerId] | None = None


class _BodyWithNoneField(BaseModelORM):
    player_id: PlayerId | None = None


@pytest.mark.asyncio
async def test_check_foreign_keys_recursive_nested_basemodel() -> None:
    """Line 135: a BaseModel-typed field recurses into check_foreign_keys..."""
    with (
        patch(
            "bracket.sql.validation.get_full_tournament_details",
            AsyncMock(return_value=[]),
        ),
        patch(
            "bracket.sql.validation.get_player_by_id",
            AsyncMock(return_value=object()),
        ),
    ):
        # Should not raise — the nested player's id is "valid" by the mock.
        await check_foreign_keys_belong_to_tournament(
            _BodyWithNested(nested=_Nested(player_id=PlayerId(1))),
            TournamentId(1),
        )


@pytest.mark.asyncio
async def test_check_foreign_keys_unknown_set_type_raises() -> None:
    """Line 141: a set field whose annotation is not set[PlayerId] raises."""
    with patch(
        "bracket.sql.validation.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(Exception, match="Unknown set type"):
            await check_foreign_keys_belong_to_tournament(
                _BodyWithUnknownSet(items={1, 2, 3}), TournamentId(1)
            )


@pytest.mark.asyncio
async def test_check_foreign_keys_player_not_found_raises() -> None:
    """Line 150: invalid PlayerId triggers raise_exception via the lookup."""
    with (
        patch(
            "bracket.sql.validation.get_full_tournament_details",
            AsyncMock(return_value=[]),
        ),
        patch("bracket.sql.validation.get_player_by_id", AsyncMock(return_value=None)),
    ):
        with pytest.raises(HTTPException, match="找不到"):
            await check_foreign_keys_belong_to_tournament(
                _BodyWithInvalidPlayer(player_id=PlayerId(999)),
                TournamentId(1),
            )


@pytest.mark.asyncio
async def test_check_foreign_keys_match_not_found_raises() -> None:
    with patch(
        "bracket.sql.validation.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException, match="找不到"):
            await check_foreign_keys_belong_to_tournament(
                _BodyWithInvalidMatch(match_id=MatchId(999)),
                TournamentId(1),
            )


@pytest.mark.asyncio
async def test_check_foreign_keys_stage_item_input_not_found_raises() -> None:
    with patch(
        "bracket.sql.validation.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException, match="找不到"):
            await check_foreign_keys_belong_to_tournament(
                _BodyWithInvalidStageItemInput(stage_item_input_id=StageItemInputId(999)),
                TournamentId(1),
            )


@pytest.mark.asyncio
async def test_check_foreign_keys_stage_item_not_found_raises() -> None:
    with patch(
        "bracket.sql.validation.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException, match="找不到"):
            await check_foreign_keys_belong_to_tournament(
                _BodyWithInvalidStageItem(stage_item_id=StageItemId(999)),
                TournamentId(1),
            )


@pytest.mark.asyncio
async def test_check_foreign_keys_round_not_found_raises() -> None:
    with patch(
        "bracket.sql.validation.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException, match="找不到"):
            await check_foreign_keys_belong_to_tournament(
                _BodyWithInvalidRound(round_id=RoundId(999)), TournamentId(1)
            )


@pytest.mark.asyncio
async def test_check_foreign_keys_court_not_found_raises() -> None:
    with (
        patch(
            "bracket.sql.validation.get_full_tournament_details",
            AsyncMock(return_value=[]),
        ),
        patch(
            "bracket.sql.validation.get_all_courts_in_tournament",
            AsyncMock(return_value=[]),
        ),
    ):
        with pytest.raises(HTTPException, match="找不到"):
            await check_foreign_keys_belong_to_tournament(
                _BodyWithInvalidCourt(court_id=CourtId(999)), TournamentId(1)
            )


@pytest.mark.asyncio
async def test_check_foreign_keys_stage_not_found_raises() -> None:
    with patch(
        "bracket.sql.validation.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException, match="找不到"):
            await check_foreign_keys_belong_to_tournament(
                _BodyWithInvalidStage(stage_id=StageId(999)), TournamentId(1)
            )


@pytest.mark.asyncio
async def test_check_foreign_keys_none_field_skipped() -> None:
    """Line 131-132: None fields are skipped."""
    with patch(
        "bracket.sql.validation.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        # Should not raise — field is None and gets skipped.
        await check_foreign_keys_belong_to_tournament(_BodyWithNoneField(), TournamentId(1))


@pytest.mark.asyncio
async def test_check_foreign_keys_none_set_skipped() -> None:
    """A None set field is also skipped (None check fires first)."""
    with patch(
        "bracket.sql.validation.get_full_tournament_details",
        AsyncMock(return_value=[]),
    ):
        await check_foreign_keys_belong_to_tournament(_BodyWithNoneSet(), TournamentId(1))


# ---------------------------------------------------------------------------
# check_players_belong_to_tournament — covers the set/PlayerId happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_players_belong_true() -> None:
    with patch(
        "bracket.sql.validation.get_all_players_in_tournament",
        AsyncMock(
            return_value=[
                type(
                    "P",
                    (),
                    {"id": PlayerId(1)},
                )()
            ]
        ),
    ):
        result = await check_players_belong_to_tournament({PlayerId(1)}, TournamentId(1))
    assert result is True


@pytest.mark.asyncio
async def test_check_players_belong_false() -> None:
    with patch(
        "bracket.sql.validation.get_all_players_in_tournament",
        AsyncMock(return_value=[]),
    ):
        result = await check_players_belong_to_tournament({PlayerId(1)}, TournamentId(1))
    assert result is False


# ---------------------------------------------------------------------------
# check_court_belongs_to_tournament
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_court_belongs_true() -> None:
    with patch(
        "bracket.sql.validation.get_all_courts_in_tournament",
        AsyncMock(return_value=[type("C", (), {"id": CourtId(1)})()]),
    ):
        assert await check_court_belongs_to_tournament(CourtId(1), [], TournamentId(1)) is True


@pytest.mark.asyncio
async def test_check_court_belongs_false() -> None:
    with patch(
        "bracket.sql.validation.get_all_courts_in_tournament",
        AsyncMock(return_value=[]),
    ):
        assert await check_court_belongs_to_tournament(CourtId(1), [], TournamentId(1)) is False


# ---------------------------------------------------------------------------
# check_stage_belongs_to_tournament, check_stage_item_belongs_to_tournament,
# check_round_belongs_to_tournament — exercise the any(...) branches.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_stage_belongs_true() -> None:
    stage = _make_stage(StageId(7), [])
    assert await check_stage_belongs_to_tournament(StageId(7), [stage], TournamentId(1)) is True


@pytest.mark.asyncio
async def test_check_stage_belongs_false() -> None:
    stage = _make_stage(StageId(7), [])
    assert await check_stage_belongs_to_tournament(StageId(8), [stage], TournamentId(1)) is False


@pytest.mark.asyncio
async def test_check_stage_item_belongs_true() -> None:
    si = _make_stage_item(StageItemId(7), [])
    stage = _make_stage(StageId(1), [si])
    assert (
        await check_stage_item_belongs_to_tournament(StageItemId(7), [stage], TournamentId(1))
        is True
    )


@pytest.mark.asyncio
async def test_check_stage_item_belongs_false() -> None:
    si = _make_stage_item(StageItemId(7), [])
    stage = _make_stage(StageId(1), [si])
    assert (
        await check_stage_item_belongs_to_tournament(StageItemId(8), [stage], TournamentId(1))
        is False
    )


@pytest.mark.asyncio
async def test_check_round_belongs_true() -> None:
    si = _make_stage_item(StageItemId(1), [], round_ids=[RoundId(7)], match_ids=[])
    stage = _make_stage(StageId(1), [si])
    assert await check_round_belongs_to_tournament(RoundId(7), [stage], TournamentId(1)) is True


@pytest.mark.asyncio
async def test_check_round_belongs_false() -> None:
    si = _make_stage_item(StageItemId(1), [], round_ids=[RoundId(7)], match_ids=[])
    stage = _make_stage(StageId(1), [si])
    assert await check_round_belongs_to_tournament(RoundId(8), [stage], TournamentId(1)) is False
