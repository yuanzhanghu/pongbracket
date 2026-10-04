from __future__ import annotations

import json
from decimal import Decimal
from typing import Annotated, Literal

from heliclockter import datetime_utc
from pydantic import BaseModel, Field, StringConstraints, field_validator

from bracket.logic.ranking.statistics import START_ELO
from bracket.models.db.player import Player
from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import PlayerId, TeamId, TournamentId, UserId


class TeamInsertable(BaseModelORM):
    created: datetime_utc
    name: str
    tournament_id: TournamentId
    active: bool
    elo_score: Decimal = START_ELO
    wins: int = 0
    draws: int = 0
    losses: int = 0
    logo_path: str | None = None
    # Manual display/seed order for non-rated tournaments (reorderable on the teams page).
    sort_order: int = 0


class Team(TeamInsertable):
    id: TeamId


class TeamWithPlayers(BaseModel):
    id: TeamId
    players: list[Player]
    elo_score: Decimal = START_ELO
    wins: int = 0
    draws: int = 0
    losses: int = 0
    name: str
    logo_path: str | None = None
    # Individual rating tournaments only: the bound account and its rating in the
    # tournament's category. rating_status is PENDING (initial/provisional, shown
    # with a *) or ACTIVE (official). All None for team / non-rated tournaments.
    bound_user_id: UserId | None = None
    rating: int | None = None
    rating_status: str | None = None
    # From this tournament's settlement ledger (rating_events): the rating just
    # before the first counted match and just after the last one. None until
    # the tournament is settled.
    settled_pre_rating: int | None = None
    settled_post_rating: int | None = None

    @property
    def player_ids(self) -> list[PlayerId]:
        return [player.id for player in self.players]

    @field_validator("players", mode="before")
    @staticmethod
    def handle_players(values: list[Player]) -> list[Player]:
        if isinstance(values, str):
            values_json = json.loads(values)
            if values_json == [None]:
                return []
            return values_json

        return values


class FullTeamWithPlayers(TeamWithPlayers, Team):
    pass


class TeamBody(BaseModelORM):
    name: Annotated[str, StringConstraints(min_length=1, max_length=30)]
    active: bool
    # Direct-edit member list: the team's members are synced to exactly these
    # names (new names create players, removed ones are cleaned up). None
    # leaves the current members untouched.
    player_names: list[Annotated[str, StringConstraints(min_length=1, max_length=30)]] | None = None


class TeamMultiBody(BaseModelORM):
    names: str = Field(..., min_length=1)
    active: bool


class TeamMoveBody(BaseModelORM):
    direction: Literal["up", "down"]
