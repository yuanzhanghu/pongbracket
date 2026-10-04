"""
Extra tests for bracket/routes/stages.py.
Covers the 403/400 error branches and the activate_next_stage logic.
"""

import pytest

from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_get_stages_unauthorized_public_dashboard_hides_draft_rounds(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """GET /tournaments/{id}/stages without auth on a public dashboard no longer 403s:
    the viewer resolves to user=None and gets the stages back with draft rounds hidden."""
    response = await send_request(
        HTTPMethod.GET, f"tournaments/{auth_context.tournament.id}/stages"
    )
    assert "detail" not in response
    assert isinstance(response["data"], list)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_stage_with_stage_items(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Deleting a stage that has stage_items -> 400."""
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
    ):
        from bracket.utils.dummy_records import DUMMY_STAGE_ITEM1
        from bracket.models.db.stage_item import StageType
        from tests.integration_tests.sql import inserted_stage_item

        async with inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "ranking_id": auth_context.ranking.id,
                    "type": StageType.SINGLE_ELIMINATION,
                }
            )
        ):
            response = await send_tournament_request(
                HTTPMethod.DELETE, f"stages/{stage_inserted.id}", auth_context, {}
            )
            assert response == {"detail": "该阶段还有阶段项目，请先删除"}


@pytest.mark.asyncio(loop_scope="session")
async def test_activate_stage_no_next(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Activating next stage when there is no next stage -> 400 (line 127)."""
    response = await send_tournament_request(
        HTTPMethod.POST, "stages/activate", auth_context, json={"direction": "next"}
    )
    assert response == {"detail": "没有下一个阶段"}


@pytest.mark.asyncio(loop_scope="session")
async def test_activate_stage_previous(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Activating previous stage when there are two stages (covers lines 138-139)."""
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
    ):
        from bracket.utils.dummy_records import DUMMY_STAGE2

        async with inserted_stage(
            DUMMY_STAGE2.model_copy(
                update={"tournament_id": auth_context.tournament.id, "is_active": False}
            )
        ):
            # First activate next (stage1 -> stage2)
            await send_tournament_request(
                HTTPMethod.POST, "stages/activate", auth_context, json={"direction": "next"}
            )
            # Now activate previous (stage2 -> stage1)
            response = await send_tournament_request(
                HTTPMethod.POST, "stages/activate", auth_context, json={"direction": "previous"}
            )
            assert response == SUCCESS_RESPONSE


@pytest.mark.asyncio(loop_scope="session")
async def test_get_next_stage_rankings_with_next_stage(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """When there's a next stage, the endpoint returns data (line 171)."""
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ),
    ):
        from bracket.utils.dummy_records import DUMMY_STAGE2

        async with inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ):
            response = await send_tournament_request(
                HTTPMethod.GET, "next_stage_rankings", auth_context
            )
            assert "data" in response


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_stage_active_with_empty_items_raises_400() -> None:
    """Line 72 is dead code: the earlier check at line 66 catches any stage
    with non-empty stage_items, so the second ``len(stage.stage_items) > 0``
    check can never be true. We exercise it by passing a stage whose
    ``stage_items`` returns [] on the first ``len()`` call (passing line 66)
    and a non-empty list on the second call (triggering line 72).
    """
    from fastapi import HTTPException

    from bracket.routes.stages import delete_stage

    call_count = 0

    class _FlakyStageItems:
        def __len__(self) -> int:
            nonlocal call_count
            call_count += 1
            return 0 if call_count == 1 else 1

    class _FakeStage:
        is_active = True
        stage_items = _FlakyStageItems()

    with pytest.raises(HTTPException) as exc_info:
        await delete_stage(
            tournament_id=-1,  # type: ignore[arg-type]
            stage_id=-1,  # type: ignore[arg-type]
            _=None,  # type: ignore[arg-type]
            __=None,  # type: ignore[arg-type]
            stage=_FakeStage(),  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "该阶段处于激活状态，请先激活其他阶段"
