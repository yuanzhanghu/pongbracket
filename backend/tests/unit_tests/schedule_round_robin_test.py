from bracket.logic.scheduling.round_robin import get_round_robin_combinations


def _real_pairs(rounds: list[list[tuple[int, int]]], team_count: int) -> list[frozenset[int]]:
    return [frozenset(p) for round_ in rounds for p in round_ if all(i < team_count for i in p)]


def test_round_robin_combinations_two_teams() -> None:
    """2 teams -> 1 round, 1 match."""
    assert get_round_robin_combinations(2) == [[(0, 1)]]


def test_round_robin_combinations_three_teams() -> None:
    """3 teams (odd) -> 3 rounds (one round per team)."""
    rounds = get_round_robin_combinations(3)
    assert len(rounds) == 3
    real = _real_pairs(rounds, 3)
    # All unique pairs (3 choose 2 = 3) appear exactly once.
    expected = {frozenset({i, j}) for i in range(3) for j in range(i + 1, 3)}
    assert set(real) == expected
    assert len(real) == 3


def test_round_robin_combinations_four_teams() -> None:
    """4 teams -> 3 rounds, 2 matches per round."""
    rounds = get_round_robin_combinations(4)
    assert len(rounds) == 3
    for round_ in rounds:
        assert len(round_) == 2
    real = _real_pairs(rounds, 4)
    expected = {frozenset({i, j}) for i in range(4) for j in range(i + 1, 4)}
    assert set(real) == expected
    assert len(real) == 6


def test_round_robin_combinations_six_teams() -> None:
    """6 teams -> 5 rounds, 3 matches per round, all unique pairs."""
    rounds = get_round_robin_combinations(6)
    assert len(rounds) == 5
    for round_ in rounds:
        assert len(round_) == 3
    real = _real_pairs(rounds, 6)
    expected = {frozenset({i, j}) for i in range(6) for j in range(i + 1, 6)}
    assert set(real) == expected
    assert len(real) == 15


def test_round_robin_combinations_five_teams() -> None:
    """5 teams (odd) -> 5 rounds; pairs include placeholder, real pairs cover all unique."""
    rounds = get_round_robin_combinations(5)
    assert len(rounds) == 5
    real = _real_pairs(rounds, 5)
    expected = {frozenset({i, j}) for i in range(5) for j in range(i + 1, 5)}
    assert set(real) == expected
    assert len(real) == 10
