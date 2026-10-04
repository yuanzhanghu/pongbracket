from collections.abc import Iterator
from contextlib import contextmanager
from enum import auto

import asyncpg  # type: ignore[import-untyped]
from fastapi import HTTPException
from starlette import status

from bracket.utils.i18n import tr
from bracket.utils.types import EnumAutoStr


class UniqueIndex(EnumAutoStr):
    ix_tournaments_dashboard_endpoint = auto()
    ix_users_email = auto()
    stage_item_inputs_stage_item_id_team_id_key = auto()
    stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key = auto()
    rating_categories_key_key = auto()
    player_ratings_category_id_user_id_key = auto()
    teams_x_users_team_id_key = auto()
    teams_x_users_tournament_id_user_id_key = auto()
    tournament_scorers_tournament_id_user_id_key = auto()
    user_trusted_managers_user_id_manager_id_key = auto()
    tournament_favorites_user_id_tournament_id_key = auto()


class ForeignKey(EnumAutoStr):
    courts_tournament_id_fkey = auto()
    matches_stage_item_input1_id_fkey = auto()
    matches_stage_item_input2_id_fkey = auto()
    players_tournament_id_fkey = auto()
    stage_item_inputs_team_id_fkey = auto()
    stages_tournament_id_fkey = auto()
    teams_tournament_id_fkey = auto()
    tournaments_club_id_fkey = auto()
    rankings_tournament_id_fkey = auto()
    stage_items_ranking_id_fkey = auto()


# The Chinese strings below are message ids: they are looked up at raise time (not at
# import time) so the message follows the language of the request that hit the violation.
unique_index_violation_error_lookup = {
    UniqueIndex.ix_tournaments_dashboard_endpoint: "该仪表板链接已被占用",
    UniqueIndex.ix_users_email: "该邮箱已被使用",
    UniqueIndex.stage_item_inputs_stage_item_id_team_id_key: ("该队伍已被分配到其他阶段项目"),
    UniqueIndex.stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key: (
        "该晋级位已被分配到其他阶段项目"
    ),
    UniqueIndex.rating_categories_key_key: "已存在相同标识的积分类别",
    UniqueIndex.player_ratings_category_id_user_id_key: ("该账号在此积分类别中已有积分"),
    UniqueIndex.teams_x_users_team_id_key: "该队伍已绑定其他账号",
    UniqueIndex.teams_x_users_tournament_id_user_id_key: ("该账号在本比赛中已有队伍"),
    UniqueIndex.tournament_scorers_tournament_id_user_id_key: ("该账号已是本比赛的记分员"),
    UniqueIndex.user_trusted_managers_user_id_manager_id_key: ("该成员已在你的信任列表中"),
    UniqueIndex.tournament_favorites_user_id_tournament_id_key: ("你已关注该比赛"),
}


foreign_key_violation_error_lookup = {
    ForeignKey.courts_tournament_id_fkey: "该比赛还有场地，请先删除场地",
    ForeignKey.matches_stage_item_input1_id_fkey: "该队伍仍关联着比赛对阵",
    ForeignKey.matches_stage_item_input2_id_fkey: "该队伍仍关联着比赛对阵",
    ForeignKey.stage_item_inputs_team_id_fkey: "该队伍不能作为此阶段项目的输入",
    ForeignKey.stages_tournament_id_fkey: "该比赛还有阶段，请先删除阶段",
    ForeignKey.teams_tournament_id_fkey: "该比赛还有队伍，请先删除队伍",
    ForeignKey.tournaments_club_id_fkey: "该俱乐部下还有比赛，请先删除比赛",
    ForeignKey.rankings_tournament_id_fkey: ("该比赛还有排名设置，请先删除排名"),
    ForeignKey.stage_items_ranking_id_fkey: ("该比赛还有阶段，请先删除阶段"),
}


@contextmanager
def check_unique_constraint_violation(expected_violations: set[UniqueIndex]) -> Iterator[None]:
    try:
        yield
    except asyncpg.exceptions.UniqueViolationError as exc:
        constraint_name = exc.as_dict()["constraint_name"]
        assert constraint_name, "UniqueViolationError occurred but no constraint_name defined"
        assert constraint_name in UniqueIndex.values(), "Unknown UniqueViolationError occurred"
        constraint = UniqueIndex(constraint_name)

        if (
            constraint not in unique_index_violation_error_lookup
            or constraint not in expected_violations
        ):
            raise exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr(unique_index_violation_error_lookup[constraint]),
        ) from exc


@contextmanager
def check_foreign_key_violation(expected_violations: set[ForeignKey]) -> Iterator[None]:
    try:
        yield
    except asyncpg.exceptions.ForeignKeyViolationError as exc:
        constraint_name = exc.as_dict()["constraint_name"]
        assert constraint_name, "ForeignKeyViolationError occurred but no constraint_name defined"
        assert constraint_name in ForeignKey.values(), (
            f"Unknown ForeignKeyViolationError occurred: {constraint_name}"
        )
        constraint = ForeignKey(constraint_name)

        if (
            constraint not in foreign_key_violation_error_lookup
            or constraint not in expected_violations
        ):
            raise exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr(foreign_key_violation_error_lookup[constraint]),
        ) from exc
