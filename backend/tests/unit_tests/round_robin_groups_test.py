from bracket.logic.scheduling.round_robin_groups import (
    distribute_to_groups,
    distribute_to_groups_block,
    seed_ordered_team_ids,
    split_group_sizes,
)
from bracket.models.db.team import FullTeamWithPlayers
from bracket.models.db.tournament import Tournament
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_TOURNAMENT
from bracket.utils.id_types import RatingCategoryId, TeamId, TournamentId


def _tournament(*, is_individual: bool, rating_category_id: RatingCategoryId | None) -> Tournament:
    return Tournament(
        id=TournamentId(1),
        is_individual=is_individual,
        rating_category_id=rating_category_id,
        **DUMMY_TOURNAMENT.model_dump(),
    )


def _team(team_id: int, rating: int | None, sort_order: int = 0) -> FullTeamWithPlayers:
    return FullTeamWithPlayers(
        id=TeamId(team_id),
        created=DUMMY_MOCK_TIME,
        name=f"Team {team_id}",
        tournament_id=TournamentId(1),
        active=True,
        players=[],
        rating=rating,
        sort_order=sort_order,
    )


def test_split_group_sizes_even_and_uneven() -> None:
    assert split_group_sizes(6, 3) == [2, 2, 2]
    assert split_group_sizes(9, 2) == [5, 4]
    assert split_group_sizes(5, 2) == [3, 2]


def test_distribute_to_groups_snake() -> None:
    # Snake seeding of 5 teams over groups of [3, 2] -> [1, 4, 5] and [2, 3].
    assert distribute_to_groups([1, 2, 3, 4, 5], [3, 2]) == [[1, 4, 5], [2, 3]]


def test_distribute_to_groups_block_consecutive_segments() -> None:
    # Block seeding keeps consecutive seeds together: group 1 = top seeds.
    assert distribute_to_groups_block([1, 2, 3, 4, 5], [3, 2]) == [[1, 2, 3], [4, 5]]


def test_distribute_to_groups_block_leaves_empty_slots() -> None:
    # Fewer teams than slots -> trailing slots stay empty (None).
    assert distribute_to_groups_block([1, 2, 3], [3, 3]) == [[1, 2, 3], [None, None, None]]


def test_seed_ordered_team_ids_by_creation_order_for_non_rating() -> None:
    tournament = _tournament(is_individual=False, rating_category_id=None)
    teams = [_team(3, None), _team(1, None), _team(2, None)]
    assert seed_ordered_team_ids(teams, tournament) == [1, 2, 3]


def test_seed_ordered_team_ids_follows_manual_sort_order_for_non_rating() -> None:
    tournament = _tournament(is_individual=False, rating_category_id=None)
    # Manual order (sort_order) wins over id order.
    teams = [
        _team(1, None, sort_order=3),
        _team(2, None, sort_order=1),
        _team(3, None, sort_order=2),
    ]
    assert seed_ordered_team_ids(teams, tournament) == [2, 3, 1]


def test_seed_ordered_team_ids_by_rating_desc_for_rating_tournament() -> None:
    tournament = _tournament(is_individual=True, rating_category_id=RatingCategoryId(1))
    # Highest rating first; unrated teams sort last, ties broken by id.
    teams = [_team(1, 1200), _team(2, 1800), _team(3, None), _team(4, 1500)]
    assert seed_ordered_team_ids(teams, tournament) == [2, 4, 1, 3]
