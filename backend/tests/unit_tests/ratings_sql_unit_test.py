"""Pure-function unit tests for bracket/sql/ratings.scored_matches_from_rows.

Covers the draw branch (score1 == score2) and the unbound branch (a side with
no bound user), plus a normal scoring row, with no DB needed.
"""

from bracket.sql.ratings import scored_matches_from_rows


def _row(match_id: int, u1: int | None, u2: int | None, s1: int, s2: int) -> dict:
    return {
        "match_id": match_id,
        "user_id1": u1,
        "user_id2": u2,
        "score1": s1,
        "score2": s2,
    }


def test_scored_matches_from_rows_filters_draw_and_unbound() -> None:
    rows = [
        _row(1, 10, 20, 3, 1),  # scores: kept
        _row(2, 10, 20, 2, 2),  # draw: skipped (score1 == score2)
        _row(3, None, 20, 3, 1),  # side 1 unbound: skipped
        _row(4, 10, None, 3, 1),  # side 2 unbound: skipped
    ]

    scored = scored_matches_from_rows(rows)

    assert len(scored) == 1
    only = scored[0]
    assert only.match_id == 1
    assert only.user_id1 == 10
    assert only.user_id2 == 20
    assert only.score1 == 3
    assert only.score2 == 1


def test_scored_matches_from_rows_empty() -> None:
    assert scored_matches_from_rows([]) == []
