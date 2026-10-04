"""KaiQiu (开球网) ChinaTT rating exchange table.

Pure, table-driven engine: the points exchanged in a match depend only on the
two players' pre-match ratings (an integer difference). The winner's gain always
equals the loser's loss (zero-sum per match). There is no draw branch — table
tennis has no draws, and the settlement layer filters those out before calling
here.

Official source: 开球网《ChinaTT 即中国乒乓球水平积分制度》(http://www.kaiqiu.wang/post/970.html).
Bins are closed intervals on the absolute rating difference, per design §11.
"""

# (inclusive upper bound, gain when higher-rated wins, gain when lower-rated wins).
# The final 238+ bin is handled separately (no upper bound).
_TABLE: list[tuple[int, int, int]] = [
    (12, 8, 8),
    (37, 7, 10),
    (62, 6, 13),
    (87, 5, 16),
    (112, 4, 20),
    (137, 3, 25),
    (162, 2, 30),
    (187, 2, 35),
    (212, 1, 40),
    (237, 1, 45),
]
_TOP_HIGHER_WINS = 0
_TOP_LOWER_WINS = 50


def compute_exchange(winner_rating: int, loser_rating: int) -> tuple[int, int]:
    """Return ``(winner_gain, loser_loss)`` for a decided match.

    Both values are equal non-negative integers: the winner gains exactly what
    the loser loses. Expected results (higher-rated wins) exchange little; upsets
    (lower-rated wins) exchange a lot.
    """
    diff = abs(winner_rating - loser_rating)
    higher_won = winner_rating >= loser_rating

    for upper, high_gain, low_gain in _TABLE:
        if diff <= upper:
            exchange = high_gain if higher_won else low_gain
            return exchange, exchange

    exchange = _TOP_HIGHER_WINS if higher_won else _TOP_LOWER_WINS
    return exchange, exchange
