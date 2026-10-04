import pytest

from bracket.logic.ranking.statistics import TeamStatistics
from bracket.logic.scheduling.handle_stage_activation import determine_team_id
from bracket.utils.id_types import StageItemId, StageItemInputId


def test_determine_team_id_returns_correct_id() -> None:
    """Winner at the given position maps to the corresponding stage_item_input id."""
    rank = [
        (StageItemInputId(-1), TeamStatistics(wins=3)),
        (StageItemInputId(-2), TeamStatistics(wins=2)),
        (StageItemInputId(-3), TeamStatistics(wins=1)),
    ]
    stage_item_x_team_rankings = {StageItemId(-99): rank}

    assert determine_team_id(
        winner_from_stage_item_id=StageItemId(-99),
        winner_position=1,
        stage_item_x_team_rankings=stage_item_x_team_rankings,
    ) == StageItemInputId(-1)
    assert determine_team_id(
        winner_from_stage_item_id=StageItemId(-99),
        winner_position=3,
        stage_item_x_team_rankings=stage_item_x_team_rankings,
    ) == StageItemInputId(-3)


def test_determine_team_id_out_of_range_raises_assertion() -> None:
    """Asking for a position larger than the ranking size triggers the assertion. (lines 52-58)"""
    rank = [
        (StageItemInputId(-1), TeamStatistics(wins=3)),
        (StageItemInputId(-2), TeamStatistics(wins=2)),
    ]
    stage_item_x_team_rankings = {StageItemId(-99): rank}
    with pytest.raises(AssertionError, match="out of range"):
        determine_team_id(
            winner_from_stage_item_id=StageItemId(-99),
            winner_position=3,
            stage_item_x_team_rankings=stage_item_x_team_rankings,
        )
