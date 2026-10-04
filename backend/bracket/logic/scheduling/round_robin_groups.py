from typing import Literal

from fastapi import HTTPException
from starlette import status

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyEmpty,
    StageItemInputCreateBodyFinal,
)
from bracket.models.db.team import FullTeamWithPlayers
from bracket.models.db.tournament import Tournament
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.teams import get_teams_with_members
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.i18n import tr
from bracket.utils.id_types import StageId, TeamId, TournamentId


def group_name(index: int) -> str:
    """小组1, 小组2, ..."""
    return f"小组{index + 1}"


def split_group_sizes(total_team_count: int, group_count: int) -> list[int]:
    """
    Split `total_team_count` teams across `group_count` groups as evenly as possible.
    E.g. 9 over 2 -> [5, 4]; 6 over 3 -> [2, 2, 2].
    """
    base, remainder = divmod(total_team_count, group_count)
    return [base + (1 if i < remainder else 0) for i in range(group_count)]


def distribute_to_groups(
    team_ids: list[TeamId], group_sizes: list[int]
) -> list[list[TeamId | None]]:
    """
    Snake-distribute (蛇型分组) seeded teams across groups of the given sizes, so the
    strongest teams are spread evenly. Slots that run out of teams stay empty (None).
    """
    groups: list[list[TeamId | None]] = [[None] * size for size in group_sizes]
    idx = 0
    for row in range(max(group_sizes, default=0)):
        order = range(len(group_sizes)) if row % 2 == 0 else range(len(group_sizes) - 1, -1, -1)
        for group_index in order:
            if row < group_sizes[group_index] and idx < len(team_ids):
                groups[group_index][row] = team_ids[idx]
                idx += 1
    return groups


def distribute_to_groups_block(
    team_ids: list[TeamId], group_sizes: list[int]
) -> list[list[TeamId | None]]:
    """
    Block-distribute (分段循环) seeded teams: each group gets a consecutive segment of
    the seeding, so group 1 holds the top seeds, group 2 the next, and so on. Slots that
    run out of teams stay empty (None).
    """
    groups: list[list[TeamId | None]] = []
    idx = 0
    for size in group_sizes:
        segment = team_ids[idx : idx + size]
        idx += len(segment)
        groups.append([*segment, *([None] * (size - len(segment)))])
    return groups


def seed_ordered_team_ids(teams: list[FullTeamWithPlayers], tournament: Tournament) -> list[TeamId]:
    """
    Order teams for group seeding to match the teams page: rating tournaments seed by
    rating (highest first, unrated last), everything else by the manual team order
    (sort_order, i.e. creation order as adjusted with the up/down arrows).
    """
    if tournament.is_individual and tournament.rating_category_id is not None:
        ordered = sorted(
            teams,
            key=lambda team: (team.rating is None, -(team.rating or 0), team.id),
        )
    else:
        ordered = sorted(teams, key=lambda team: (team.sort_order, team.id))
    return [team.id for team in ordered]


async def create_round_robin_groups(
    tournament_id: TournamentId,
    stage_id: StageId,
    group_count: int,
    total_team_count: int,
    method: Literal["snake", "block"] = "snake",
) -> None:
    """
    Create `group_count` round-robin stage items (小组1, 小组2, ...) in the stage by splitting
    `total_team_count` teams across them, then distribute all active teams across their
    slots by seeding using `method` (snake or block). If there are fewer active teams than
    slots, the remaining slots are left empty.
    """
    if group_count < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("小组数量至少为 1"),
        )

    group_sizes = split_group_sizes(total_team_count, group_count)
    if any(size < 2 for size in group_sizes):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("{team_count} 支队伍无法分成 {group_count} 个每组至少 2 队的小组").format(
                team_count=total_team_count, group_count=group_count
            ),
        )

    tournament = await sql_get_tournament(tournament_id)
    teams = await get_teams_with_members(tournament_id, only_active_teams=True)
    team_ids = seed_ordered_team_ids(teams, tournament)

    distribute = distribute_to_groups_block if method == "block" else distribute_to_groups
    for index, slot_assignments in enumerate(distribute(team_ids, group_sizes)):
        inputs: list[StageItemInputCreateBodyFinal | StageItemInputCreateBodyEmpty] = []
        for slot, team_id in enumerate(slot_assignments):
            if team_id is not None:
                inputs.append(StageItemInputCreateBodyFinal(slot=slot + 1, team_id=team_id))
            else:
                inputs.append(StageItemInputCreateBodyEmpty(slot=slot + 1))

        stage_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_id,
                name=group_name(index),
                type=StageType.ROUND_ROBIN,
                team_count=group_sizes[index],
                inputs=inputs,
            ),
        )
        await build_matches_for_stage_item(stage_item, tournament_id)
