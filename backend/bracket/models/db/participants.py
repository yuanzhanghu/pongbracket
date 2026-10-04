from __future__ import annotations

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import UserId


class JoinRequestBody(BaseModelORM):
    trust_creator: bool = False


class ParticipantAddBody(BaseModelORM):
    user_id: UserId


class AddableParticipantItem(BaseModelORM):
    user_id: UserId
    name: str


class JoinStatusItem(BaseModelORM):
    is_participant: bool
    # Whether the join / leave affordances should be offered right now. Both are
    # only allowed on an individual tournament before it starts (no match yet) and
    # before it is settled — so a started tournament shows neither 参赛 nor 退出.
    can_join: bool = False
    can_leave: bool = False
    can_manage: bool = False
    can_record: bool = False
    # Whether a schedule exists (play has started); drives the organizer-facing
    # 报名状态 hint on the settings page.
    has_matches: bool = False


class TrustedManagerAddBody(BaseModelORM):
    manager_email: str


class TrustedManagerItem(BaseModelORM):
    manager_id: UserId
    name: str


class ScorerAddBody(BaseModelORM):
    user_email: str


class ScorerItem(BaseModelORM):
    user_id: UserId
    name: str
