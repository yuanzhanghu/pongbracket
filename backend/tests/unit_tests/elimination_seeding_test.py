from bracket.logic.scheduling.elimination_seeding import (
    build_qualifier_tiers,
    next_power_of_two,
    seed_bracket,
    standard_seed_order,
)
from bracket.utils.id_types import StageItemId

A = StageItemId(1)
B = StageItemId(2)
C = StageItemId(3)
D = StageItemId(4)

# The draw is random, so every property is checked across many independent draws.
_DRAWS = 60


def _first_round_pairs(slots):
    return [(slots[i], slots[i + 1]) for i in range(0, len(slots), 2)]


def _regions(slots, size):
    return [slots[s : s + size] for s in range(0, len(slots), size)]


def _half_of(slots, qualifier):
    index = slots.index(qualifier)
    return index // (len(slots) // 2)


def test_next_power_of_two() -> None:
    assert [next_power_of_two(v) for v in (1, 2, 3, 5, 8, 9)] == [2, 2, 4, 8, 8, 16]


def test_standard_seed_order() -> None:
    assert standard_seed_order(2) == [0, 1]
    assert standard_seed_order(4) == [0, 3, 1, 2]
    assert standard_seed_order(8) == [0, 7, 3, 4, 1, 6, 2, 5]


def test_two_groups_of_four_first_round_cross_group() -> None:
    tiers = build_qualifier_tiers([(A, [1, 2, 3, 4]), (B, [1, 2, 3, 4])])
    for _ in range(_DRAWS):
        slots = seed_bracket(tiers)
        assert len(slots) == 8
        assert all(q is not None for q in slots)  # no byes
        for x, y in _first_round_pairs(slots):
            assert x[0] != y[0]


def test_two_groups_of_four_spreads_top_two_into_different_halves() -> None:
    # (乙) The two strongest of each group are split across halves, so they can only meet
    # in the final. (For 2 groups of 4 each half still holds 2 teams per group, so the
    # remaining same-group pair meets in the semi-final at the earliest.)
    tiers = build_qualifier_tiers([(A, [1, 2, 3, 4]), (B, [1, 2, 3, 4])])
    for _ in range(_DRAWS):
        slots = seed_bracket(tiers)
        a1, a2 = (A, 1), (A, 2)
        b1, b2 = (B, 1), (B, 2)
        assert _half_of(slots, a1) != _half_of(slots, a2)
        assert _half_of(slots, b1) != _half_of(slots, b2)


def test_byes_go_to_top_seeds() -> None:
    # 2 groups of 3 -> 6 qualifiers, 8-slot bracket: the two strongest seeds (the group
    # winners) receive the byes, and the remaining real matches stay cross-group.
    tiers = build_qualifier_tiers([(A, [1, 2, 3]), (B, [1, 2, 3])])
    for _ in range(_DRAWS):
        slots = seed_bracket(tiers)
        assert len(slots) == 8
        assert sum(1 for q in slots if q is None) == 2
        for x, y in _first_round_pairs(slots):
            if x is None:
                assert y is not None and y[1] == 1  # bye partnered with a group winner
            elif y is None:
                assert x[1] == 1
            else:
                assert x[0] != y[0]


def test_four_groups_of_two_separate_into_quarters() -> None:
    # 8 teams from 4 groups: every region down to the quarter can stay same-group-free.
    tiers = build_qualifier_tiers([(A, [1, 2]), (B, [1, 2]), (C, [1, 2]), (D, [1, 2])])
    for _ in range(_DRAWS):
        slots = seed_bracket(tiers)
        for region_size in (2, 4):
            for region in _regions(slots, region_size):
                sources = [q[0] for q in region if q is not None]
                assert len(sources) == len(set(sources))


def test_draw_is_randomized_with_enough_groups() -> None:
    # With more groups the spread constraints leave real room for the draw to vary.
    tiers = build_qualifier_tiers([(A, [1, 2]), (B, [1, 2]), (C, [1, 2]), (D, [1, 2])])
    seen = {tuple(seed_bracket(tiers)) for _ in range(_DRAWS)}
    assert len(seen) > 1
