"""
Smart seeding of qualifiers into a single-elimination bracket.

A qualifier is a (source_stage_item_id, position) pair, e.g. "1st of A组". Qualifiers are
grouped into strength tiers (all the group winners, then all the runners-up, ...). Stronger
tiers take the better seeds, so the leftover top slots become byes for the strongest seeds;
within a tier the draw is random. The draw is constrained to keep two qualifiers from the
same source apart as a best effort: it spreads them across the bracket so they meet as late
as possible, weighting an earlier meeting and a meeting between higher seeds more heavily
(so e.g. a group's top two are split before its bottom two).
"""

import random
from typing import Literal

from fastapi import HTTPException
from starlette import status

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import (
    EliminationSource,
    StageItemWithInputsCreate,
    StageType,
)
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyEmpty,
    StageItemInputCreateBodyTentative,
)
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.i18n import tr
from bracket.utils.id_types import StageId, StageItemId, TournamentId

Qualifier = tuple[StageItemId, int]


def next_power_of_two(value: int) -> int:
    n = 1
    while n < value:
        n *= 2
    return max(n, 2)


def standard_seed_order(n: int) -> list[int]:
    """
    Standard single-elimination seeding: returns a list where entry `slot` holds the
    0-indexed seed rank placed in that bracket slot. E.g. n=4 -> [0, 3, 1, 2] (seed 1 vs
    seed 4, seed 2 vs seed 3).
    """
    seeds = [0]
    while len(seeds) < n:
        size = len(seeds) * 2
        seeds = [s for seed in seeds for s in (seed, size - 1 - seed)]
    return seeds


def build_qualifier_tiers(
    sources: list[tuple[StageItemId, list[int]]],
) -> list[list[Qualifier]]:
    """
    Group qualifiers into strength tiers, strongest tier first: tier `t` holds every
    source's (t+1)-th strongest finisher (each source's positions are ordered strongest
    first). Qualifiers within a tier are of equal seeding strength, and the draw places
    them at random.
    """
    max_count = max((len(positions) for _, positions in sources), default=0)
    return [
        [
            (stage_item_id, positions[index])
            for stage_item_id, positions in sources
            if index < len(positions)
        ]
        for index in range(max_count)
    ]


# Random restarts for the constrained draw; the search space is tiny (bracket <= 64), so a
# handful of restarts reliably reaches the best feasible spread.
_DRAW_RESTARTS = 24


def seed_bracket(tiers: list[list[Qualifier]]) -> list[Qualifier | None]:
    """
    Draw the qualifiers into bracket slots. Returns a list of length
    next_power_of_two(total qualifiers); each entry is a qualifier or None (a bye).

    Stronger tiers take the low (best) seed ranks, so the missing top ranks become byes
    whose round-one partners are the best seeds. Within a tier the draw is random. As a
    best effort the draw spreads two qualifiers from the same source so they meet as late
    as possible, prioritising (a) an earlier meeting round and, within a round, (b) a
    meeting between higher seeds.
    """
    qualifiers = [qualifier for tier in tiers for qualifier in tier]
    count = len(qualifiers)
    n = next_power_of_two(count)
    num_tiers = len(tiers)

    # Rank space: each tier owns a contiguous block of low (best) ranks, strongest tier
    # first; ranks count..n-1 are byes. The draw only permutes qualifiers within their own
    # tier's ranks, so seeding strength and the byes stay fixed however the draw lands.
    tier_ranks: list[list[int]] = []
    rank_strength = [0] * n
    rank = 0
    for tier_index, tier in enumerate(tiers):
        ranks = list(range(rank, rank + len(tier)))
        tier_ranks.append(ranks)
        for r in ranks:
            rank_strength[r] = num_tiers - tier_index  # tier 0 (winners) is strongest
        rank += len(tier)
    base: list[Qualifier | None] = list(qualifiers) + [None] * (n - count)

    order = standard_seed_order(n)
    slot_strength = [rank_strength[order[slot]] for slot in range(n)]

    # Two slots meet in the round given by the smallest power-of-two block holding both:
    # block 2 is the first round, ..., block n is the final. Record each slot pair's round
    # as an index into `levels` (finest first), or None when they meet only in the final
    # (block n) -- which is free.
    levels: list[int] = []
    block = 2
    while block <= n // 2:
        levels.append(block)
        block *= 2
    level_of_block = {size: index for index, size in enumerate(levels)}
    pair_level: dict[tuple[int, int], int | None] = {}
    for i in range(n):
        for j in range(i + 1, n):
            block = 2
            while i // block != j // block:
                block *= 2
            pair_level[(i, j)] = level_of_block.get(block)

    def cost(assignment: list[Qualifier | None]) -> tuple[int, ...]:
        slot_source: list[StageItemId | None] = []
        for slot in range(n):
            qualifier = assignment[order[slot]]
            slot_source.append(qualifier[0] if qualifier is not None else None)

        # Sum the seed-strength product of every same-source pair, bucketed by meeting
        # round (finest first). Comparing cost tuples then minimises earlier-round
        # collisions first, and breaks ties towards splitting the stronger seeds.
        per_round = [0] * len(levels)
        for i in range(n):
            source = slot_source[i]
            if source is None:
                continue
            for j in range(i + 1, n):
                if slot_source[j] != source:
                    continue
                level = pair_level[(i, j)]
                if level is not None:
                    per_round[level] += slot_strength[i] * slot_strength[j]
        return tuple(per_round)

    def draw() -> tuple[list[Qualifier | None], tuple[int, ...]]:
        assignment = list(base)
        for ranks in tier_ranks:
            shuffled = [assignment[r] for r in ranks]
            random.shuffle(shuffled)
            for r, qualifier in zip(ranks, shuffled):
                assignment[r] = qualifier

        # Hill-climb: swap two equal-strength qualifiers (same tier) whenever it lowers the
        # cost. Same-tier swaps preserve seeding strength and the byes.
        current = cost(assignment)
        improved = True
        while improved and any(current):
            improved = False
            for ranks in tier_ranks:
                for i in range(len(ranks)):
                    for j in range(i + 1, len(ranks)):
                        ri, rj = ranks[i], ranks[j]
                        assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
                        candidate = cost(assignment)
                        if candidate < current:
                            current = candidate
                            improved = True
                        else:
                            assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
        return assignment, current

    best, best_cost = draw()
    for _ in range(_DRAW_RESTARTS - 1):
        if not any(best_cost):
            break
        assignment, current = draw()
        if current < best_cost:
            best, best_cost = assignment, current

    return [best[seed_rank] for seed_rank in order]


async def create_elimination_from_sources(
    tournament_id: TournamentId,
    stage_id: StageId,
    name: str | None,
    sources: list[EliminationSource],
    take: Literal["top", "bottom"] = "top",
) -> None:
    """
    Create a single-elimination stage item seeded from the given sources. With take="top"
    each source contributes its first `positions` finishers (winners bracket); with
    take="bottom" its last `positions` finishers (consolation bracket). Qualifiers are
    smart-seeded into a bracket of the next power-of-two size, with byes for the top seeds.
    """
    expanded_sources = []
    for source in sources:
        if take == "top":
            positions = list(range(1, source.positions + 1))
        else:
            stage_item = await get_stage_item(tournament_id, source.stage_item_id)
            first = max(1, stage_item.team_count - source.positions + 1)
            positions = list(range(first, stage_item.team_count + 1))
        expanded_sources.append((source.stage_item_id, positions))

    tiers = build_qualifier_tiers(expanded_sources)
    if sum(len(tier) for tier in tiers) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("淘汰赛至少需要选择 2 个晋级名额"),
        )

    slots = seed_bracket(tiers)
    if len(slots) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=tr("单个对阵表的晋级人数过多（最多 64 人）"),
        )

    inputs: list[StageItemInputCreateBodyTentative | StageItemInputCreateBodyEmpty] = []
    for slot, qualifier in enumerate(slots):
        if qualifier is None:
            inputs.append(StageItemInputCreateBodyEmpty(slot=slot + 1))
        else:
            inputs.append(
                StageItemInputCreateBodyTentative(
                    slot=slot + 1,
                    winner_from_stage_item_id=qualifier[0],
                    winner_position=qualifier[1],
                )
            )

    stage_item = await sql_create_stage_item_with_inputs(
        tournament_id,
        StageItemWithInputsCreate(
            stage_id=stage_id,
            name=name,
            type=StageType.SINGLE_ELIMINATION,
            team_count=len(slots),
            inputs=inputs,
        ),
    )
    await build_matches_for_stage_item(stage_item, tournament_id)
