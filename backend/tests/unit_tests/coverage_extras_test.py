"""Extra unit tests to raise backend coverage on specific targeted lines."""

from collections import defaultdict
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from heliclockter import datetime_utc

from bracket.config import config, init_sentry
from bracket.cronjobs.scheduling import delete_demo_accounts
from bracket.logic.ranking.calculation import set_statistics_for_stage_item_input
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.logic.scheduling.builder import (
    build_matches_for_stage_item,
    create_rounds_for_new_stage_item,
)
from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item import StageItem, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputEmpty,
    StageItemInputFinal,
)
from bracket.models.db.team import Team
from bracket.models.db.util import StageItemWithRounds
from bracket.sql.teams import get_teams_by_id
from bracket.sql.validation import raise_exception
from bracket.utils.alembic import alembic_run_migrations, get_alembic_config
from bracket.utils.dummy_records import (
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
    DUMMY_TEAM4,
)
from bracket.utils.id_types import (
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


def _make_stage_item(stage_type: StageType, inputs: list) -> StageItemWithRounds:
    return StageItemWithRounds(
        rounds=[],
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
# bracket/config.py
# ------------------------------------------------------------------


def test_is_cors_enabled_with_star_returns_false() -> None:
    with patch.object(config, "cors_origins", "*"):
        assert config.is_cors_enabled() is False


def test_is_cors_enabled_with_specific_origin_returns_true() -> None:
    with patch.object(config, "cors_origins", "https://example.org"):
        assert config.is_cors_enabled() is True


def test_init_sentry_no_dsn() -> None:
    with patch.object(config, "sentry_dsn", None):
        with patch("bracket.config.sentry_sdk.init") as mock_init:
            init_sentry()
            mock_init.assert_not_called()


def test_init_sentry_with_dsn() -> None:
    with patch.object(config, "sentry_dsn", "https://fake@sentry.io/123"):
        with patch("bracket.config.sentry_sdk.init") as mock_init:
            init_sentry()
            mock_init.assert_called_once()


# ------------------------------------------------------------------
# bracket/app.py — exception handlers
# ------------------------------------------------------------------


def test_validation_exception_handler() -> None:
    import asyncio
    import json

    from starlette.exceptions import HTTPException

    from bracket.app import validation_exception_handler

    response = asyncio.run(
        validation_exception_handler(
            request=None,  # type: ignore[arg-type]
            exc=HTTPException(status_code=422, detail="bad input"),
        )
    )
    assert response.status_code == 422
    assert json.loads(response.body) == {"detail": "bad input"}


def test_generic_exception_handler() -> None:
    import asyncio
    import json

    from bracket.app import generic_exception_handler

    response = asyncio.run(
        generic_exception_handler(
            request=None,  # type: ignore[arg-type]
            exc=RuntimeError("boom"),
        )
    )
    assert response.status_code == 500
    assert json.loads(response.body) == {"detail": "Internal server error"}


# ------------------------------------------------------------------
# bracket/utils/alembic.py
# ------------------------------------------------------------------


def test_get_alembic_config_returns_config() -> None:
    cfg = get_alembic_config()
    assert cfg is not None


def test_alembic_run_migrations_calls_upgrade() -> None:
    with patch("bracket.utils.alembic.command.upgrade") as mock_upgrade:
        alembic_run_migrations()
        mock_upgrade.assert_called_once()
        args, _ = mock_upgrade.call_args
        assert args[1] == "head"


# ------------------------------------------------------------------
# bracket/cronjobs/scheduling.py
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_demo_accounts_no_users() -> None:
    with patch("bracket.cronjobs.scheduling.get_expired_demo_users", return_value=[]):
        assert await delete_demo_accounts() is None


# ------------------------------------------------------------------
# bracket/logic/scheduling/builder.py
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rounds_for_new_stage_item_unsupported_type() -> None:
    fake_stage_item = StageItem.model_construct(  # type: ignore[call-arg]
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=datetime_utc.now(),
        type="FAKE_STAGE_TYPE",
        team_count=4,
        ranking_id=None,
    )

    with pytest.raises(NotImplementedError, match="FAKE_STAGE_TYPE"):
        await create_rounds_for_new_stage_item(TournamentId(-1), fake_stage_item)


@pytest.mark.asyncio
async def test_build_matches_for_stage_item_unsupported_type() -> None:
    from fastapi import HTTPException

    fake_stage_item = StageItem.model_construct(  # type: ignore[call-arg]
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=datetime_utc.now(),
        type="FAKE_STAGE_TYPE",
        team_count=4,
        ranking_id=None,
    )

    with (
        patch(
            "bracket.logic.scheduling.builder.create_rounds_for_new_stage_item",
            new=AsyncMock(),
        ),
        patch(
            "bracket.logic.scheduling.builder.get_stage_item",
            new=AsyncMock(return_value=fake_stage_item),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await build_matches_for_stage_item(fake_stage_item, TournamentId(-1))
    assert exc_info.value.status_code == 400


# ------------------------------------------------------------------
# bracket/logic/ranking/calculation.py
# ------------------------------------------------------------------


def test_set_statistics_for_stage_item_input_draw() -> None:
    now = datetime_utc.now()
    input1 = _make_input(-1, 1)
    input2 = _make_input(-2, 2)
    match = MatchWithDetailsDefinitive(
        id=-1,  # type: ignore[arg-type]
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(-1),
        stage_item_input1_score=10,
        stage_item_input2_score=10,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    set_statistics_for_stage_item_input(
        team_index=0,
        stats=stats,
        match=match,
        stage_item_input_id=StageItemInputId(-1),
        ranking=_make_ranking(),
        stage_item=_make_stage_item(StageType.SINGLE_ELIMINATION, [input1, input2]),
    )

    assert stats[StageItemInputId(-1)].draws == 1
    assert stats[StageItemInputId(-1)].wins == 0
    assert stats[StageItemInputId(-1)].losses == 0


def test_set_statistics_for_stage_item_input_loss_team1() -> None:
    now = datetime_utc.now()
    input1 = _make_input(-1, 1)
    input2 = _make_input(-2, 2)
    match = MatchWithDetailsDefinitive(
        id=-1,  # type: ignore[arg-type]
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(-1),
        stage_item_input1_score=5,
        stage_item_input2_score=10,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    set_statistics_for_stage_item_input(
        team_index=0,
        stats=stats,
        match=match,
        stage_item_input_id=StageItemInputId(-1),
        ranking=_make_ranking(),
        stage_item=_make_stage_item(StageType.SINGLE_ELIMINATION, [input1, input2]),
    )

    assert stats[StageItemInputId(-1)].losses == 1
    assert stats[StageItemInputId(-1)].wins == 0


def test_set_statistics_for_stage_item_input_loss_team2() -> None:
    now = datetime_utc.now()
    input1 = _make_input(-1, 1)
    input2 = _make_input(-2, 2)
    match = MatchWithDetailsDefinitive(
        id=-1,  # type: ignore[arg-type]
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(-1),
        stage_item_input1_score=10,
        stage_item_input2_score=5,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    set_statistics_for_stage_item_input(
        team_index=1,
        stats=stats,
        match=match,
        stage_item_input_id=StageItemInputId(-2),
        ranking=_make_ranking(),
        stage_item=_make_stage_item(StageType.SINGLE_ELIMINATION, [input1, input2]),
    )

    assert stats[StageItemInputId(-2)].losses == 1
    assert stats[StageItemInputId(-2)].wins == 0


# ------------------------------------------------------------------
# bracket/models/db/stage_item_inputs.py
# ------------------------------------------------------------------


def test_hash_stage_item_input_final() -> None:
    now = datetime_utc.now()
    team = Team(**DUMMY_TEAM1.model_dump(), id=TeamId(1))
    input_a = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(1),
        slot=1,
        tournament_id=TournamentId(-1),
        winner_from_stage_item_id=None,
        winner_position=None,
        team=team,
        created=now,
    )
    input_b = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(1),
        slot=1,
        tournament_id=TournamentId(-1),
        winner_from_stage_item_id=None,
        winner_position=None,
        team=team,
        created=now,
    )
    assert hash(input_a) == hash(input_b)


def test_hash_stage_item_input_empty() -> None:
    now = datetime_utc.now()
    empty = StageItemInputEmpty(
        id=StageItemInputId(-1),
        slot=1,
        tournament_id=TournamentId(-1),
        created=now,
    )
    assert isinstance(hash(empty), int)


# ------------------------------------------------------------------
# bracket/sql/teams.py
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_teams_by_id_empty_set() -> None:
    result = await get_teams_by_id(set(), TournamentId(-1))
    assert result == []


# ------------------------------------------------------------------
# bracket/sql/validation.py
# ------------------------------------------------------------------


def test_raise_exception() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        raise_exception(TeamId, TeamId(42))
    assert exc_info.value.status_code == 400
    assert "队伍" in exc_info.value.detail
    assert "42" in exc_info.value.detail


def test_raise_exception_none_type() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        raise_exception(None, 42)
    assert "Unknown type" in exc_info.value.detail
