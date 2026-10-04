from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import database
from bracket.logic.planning.matches import update_start_times_of_matches
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
)
from bracket.logic.scheduling.builder import (
    build_matches_for_stage_item,
)
from bracket.logic.scheduling.elimination_seeding import create_elimination_from_sources
from bracket.logic.scheduling.round_robin_groups import create_round_robin_groups
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.stage_item import (
    EliminationFromSourcesCreateBody,
    RoundRobinGroupsCreateBody,
    StageItemCreateBody,
    StageItemUpdateBody,
    StageType,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageItemWithRounds
from bracket.routes.auth import (
    user_authenticated_for_tournament,
)
from bracket.routes.models import SuccessResponse
from bracket.routes.util import disallow_archived_tournament, stage_item_dependency
from bracket.sql.ratings import count_unrated_participants
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import (
    sql_create_stage_item_with_empty_inputs,
)
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.errors import (
    ForeignKey,
    check_foreign_key_violation,
)
from bracket.utils.i18n import tr
from bracket.utils.id_types import StageItemId, TournamentId

router = APIRouter(prefix=config.api_prefix)


async def _block_start_until_all_rated(tournament_id: TournamentId) -> None:
    """An individual rating tournament cannot build its schedule (i.e. officially
    start) until every participant has a configured rating — a PENDING initial or
    an ACTIVE official one."""
    tournament = await sql_get_tournament(tournament_id)
    if tournament.is_individual and tournament.rating_category_id is not None:
        unrated = await count_unrated_participants(tournament_id, tournament.rating_category_id)
        if unrated > 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                tr("有 {count} 名选手尚未配置初始/正式积分，无法开始比赛").format(count=unrated),
            )


@router.delete(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}", response_model=SuccessResponse
)
async def delete_stage_item(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: StageItemWithRounds = Depends(stage_item_dependency),
) -> SuccessResponse:
    with check_foreign_key_violation(
        {ForeignKey.matches_stage_item_input1_id_fkey, ForeignKey.matches_stage_item_input2_id_fkey}
    ):
        await sql_delete_stage_item_with_foreign_keys(stage_item_id)
    await update_start_times_of_matches(tournament_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stage_items", response_model=SuccessResponse)
async def create_stage_item(
    tournament_id: TournamentId,
    stage_body: StageItemCreateBody,
    user: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    await check_foreign_keys_belong_to_tournament(stage_body, tournament_id)
    await _block_start_until_all_rated(tournament_id)

    stages = await get_full_tournament_details(tournament_id)
    existing_stage_items = [stage_item for stage in stages for stage_item in stage.stage_items]
    check_requirement(existing_stage_items, user, "max_stage_items")

    stage_item = await sql_create_stage_item_with_empty_inputs(tournament_id, stage_body)
    await build_matches_for_stage_item(stage_item, tournament_id)
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/stage_items/round_robin_groups",
    response_model=SuccessResponse,
)
async def create_round_robin_groups_endpoint(
    tournament_id: TournamentId,
    body: RoundRobinGroupsCreateBody,
    user: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    await _block_start_until_all_rated(tournament_id)
    stages = await get_full_tournament_details(tournament_id)
    existing_stage_items = [stage_item for stage in stages for stage_item in stage.stage_items]
    check_requirement(existing_stage_items, user, "max_stage_items")

    await create_round_robin_groups(
        tournament_id, body.stage_id, body.group_count, body.team_count, body.method
    )
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/stage_items/elimination_from_sources",
    response_model=SuccessResponse,
)
async def create_elimination_from_sources_endpoint(
    tournament_id: TournamentId,
    body: EliminationFromSourcesCreateBody,
    user: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    await _block_start_until_all_rated(tournament_id)
    stages = await get_full_tournament_details(tournament_id)
    existing_stage_items = [stage_item for stage in stages for stage_item in stage.stage_items]
    check_requirement(existing_stage_items, user, "max_stage_items")

    await create_elimination_from_sources(
        tournament_id, body.stage_id, body.name, body.sources, body.take
    )
    return SuccessResponse()


@router.put(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}", response_model=SuccessResponse
)
async def update_stage_item(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_body: StageItemUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    stage_item: StageItemWithRounds = Depends(stage_item_dependency),
) -> SuccessResponse:
    if stage_item is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("找不到对应的阶段"),
        )

    query = """
        UPDATE stage_items
        SET name = :name
        WHERE stage_items.id = :stage_item_id
    """
    await database.execute(
        query=query,
        values={"stage_item_id": stage_item_id, "name": stage_item_body.name},
    )
    await recalculate_ranking_for_stage_item(tournament_id, stage_item)
    if stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_complete_elimination_stage_item(stage_item)
    return SuccessResponse()
