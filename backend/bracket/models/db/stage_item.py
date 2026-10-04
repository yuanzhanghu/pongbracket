from enum import auto
from typing import Any, Literal

from heliclockter import datetime_utc
from pydantic import Field, model_validator

from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage_item_inputs import StageItemInputCreateBody
from bracket.utils.id_types import RankingId, StageId, StageItemId
from bracket.utils.types import EnumAutoStr


class StageType(EnumAutoStr):
    ROUND_ROBIN = auto()
    SINGLE_ELIMINATION = auto()

    @property
    def supports_dynamic_number_of_rounds(self) -> bool:
        return False

    @property
    def default_name(self) -> str:
        return {
            StageType.ROUND_ROBIN: "循环赛",
            StageType.SINGLE_ELIMINATION: "单淘汰赛",
        }[self]


class StageItemInsertable(BaseModelORM):
    stage_id: StageId
    name: str
    created: datetime_utc
    type: StageType
    team_count: int = Field(ge=2, le=64)
    ranking_id: RankingId | None = None


class StageItem(StageItemInsertable):
    id: StageItemId


class StageItemUpdateBody(BaseModelORM):
    name: str
    ranking_id: RankingId


class StageItemActivateNextBody(BaseModelORM):
    adjust_to_time: datetime_utc | None = None


class RoundRobinGroupsCreateBody(BaseModelORM):
    stage_id: StageId
    group_count: int = Field(ge=1, le=32)
    team_count: int = Field(ge=2, le=64)
    # "snake" spreads consecutive seeds across groups serpentine-style; "block" fills
    # each group with a consecutive segment of seeds. Both seed from the team ordering
    # shown on the teams page (rating for rating tournaments, else creation order).
    method: Literal["snake", "block"] = "snake"


class EliminationSource(BaseModelORM):
    stage_item_id: StageItemId
    positions: int = Field(ge=1, le=64)


class EliminationFromSourcesCreateBody(BaseModelORM):
    stage_id: StageId
    name: str | None = None
    sources: list[EliminationSource]
    # "top" takes the first `positions` finishers of each source (winners bracket),
    # "bottom" the last `positions` (consolation bracket).
    take: Literal["top", "bottom"] = "top"


class StageItemCreateBody(BaseModelORM):
    stage_id: StageId
    name: str | None = None
    type: StageType
    team_count: int = Field(ge=2, le=64)
    ranking_id: RankingId | None = None

    def get_name_or_default_name(self) -> str:
        return self.name if self.name is not None else self.type.default_name


class StageItemWithInputsCreate(StageItemCreateBody):
    inputs: list[StageItemInputCreateBody]

    def get_name_or_default_name(self) -> str:
        return self.name if self.name is not None else self.type.default_name

    @model_validator(mode="before")
    def handle_inputs_length(cls, values: Any) -> Any:
        if ("inputs" in values and "team_count" in values) and (
            len(values["inputs"]) != values["team_count"]
        ):
            raise ValueError("team_count doesn't match length of inputs")
        return values
