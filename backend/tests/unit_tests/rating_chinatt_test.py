import pytest

from bracket.logic.rating.chinatt import compute_exchange


@pytest.mark.parametrize(
    "diff, high_gain, low_gain",
    [
        (0, 8, 8),
        (12, 8, 8),
        (13, 7, 10),
        (37, 7, 10),
        (38, 6, 13),
        (62, 6, 13),
        (63, 5, 16),
        (87, 5, 16),
        (88, 4, 20),
        (112, 4, 20),
        (113, 3, 25),
        (137, 3, 25),
        (138, 2, 30),
        (162, 2, 30),
        (163, 2, 35),
        (187, 2, 35),
        (188, 1, 40),
        (212, 1, 40),
        (213, 1, 45),
        (237, 1, 45),
        (238, 0, 50),
        (1000, 0, 50),
    ],
)
def test_exchange_bins(diff: int, high_gain: int, low_gain: int) -> None:
    base = 1500
    # Higher-rated wins.
    assert compute_exchange(base + diff, base) == (high_gain, high_gain)
    # Lower-rated wins (upset).
    assert compute_exchange(base, base + diff) == (low_gain, low_gain)


def test_official_example() -> None:
    # 开球网 official example: A=2000, B=1950 (diff 50, bin 38-62).
    assert compute_exchange(2000, 1950) == (6, 6)  # A wins: A +6, B -6
    assert compute_exchange(1950, 2000) == (13, 13)  # A loses: B +13, A -13


def test_equal_ratings_is_minimum_exchange() -> None:
    assert compute_exchange(1500, 1500) == (8, 8)
