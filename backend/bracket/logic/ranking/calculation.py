from collections import defaultdict
from decimal import Decimal
from typing import Any

from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item import StageType
from bracket.models.db.util import StageItemWithRounds
from bracket.sql.rankings import get_ranking_for_stage_item
from bracket.sql.teams import update_team_stats
from bracket.utils.id_types import StageItemInputId, TournamentId


def _match_has_result(match: MatchWithDetailsDefinitive) -> bool:
    """Whether a match has actually been played / decided, so it should count
    toward the standings.

    An unplayed match has no forfeit and a 0-0 score (no games scored yet). It
    must NOT contribute to the ranking — otherwise every not-yet-played match is
    miscounted as a 0-0 draw, handing draw_points to BOTH sides, so teams that
    have not competed (or not played a single match) appear on the leaderboard
    with points. A genuine drawn match (e.g. a 1-1 games split) has a non-zero
    score and is correctly included.
    """
    return (
        match.forfeit_input is not None
        or match.stage_item_input1_score != 0
        or match.stage_item_input2_score != 0
    )


def set_statistics_for_stage_item_input(
    team_index: int,
    stats: defaultdict[StageItemInputId, TeamStatistics],
    match: MatchWithDetailsDefinitive,
    stage_item_input_id: StageItemInputId,
    ranking: Ranking,
    stage_item: StageItemWithRounds,
) -> None:
    is_team1 = team_index == 0

    # Forfeit: the non-forfeiting side wins (win_points), the forfeiting side gets 0.
    # The match score stays 0-0, so games (局分) / points (小分) are unaffected and
    # add_score_points contributes nothing.
    if match.forfeit_input is not None:
        this_side = 1 if is_team1 else 2
        if match.forfeit_input == this_side:
            stats[stage_item_input_id].losses += 1
            score_diff = Decimal("0")
        else:
            stats[stage_item_input_id].wins += 1
            score_diff = ranking.win_points

        match stage_item.type:
            case StageType.ROUND_ROBIN | StageType.SINGLE_ELIMINATION:
                stats[stage_item_input_id].points += score_diff
            case _:
                raise ValueError(f"Unsupported stage type: {stage_item.type}")
        return

    team_score = match.stage_item_input1_score if is_team1 else match.stage_item_input2_score
    was_draw = match.stage_item_input1_score == match.stage_item_input2_score
    has_won = not was_draw and team_score == max(
        match.stage_item_input1_score, match.stage_item_input2_score
    )

    if has_won:
        stats[stage_item_input_id].wins += 1
        score_diff = ranking.win_points
    elif was_draw:
        stats[stage_item_input_id].draws += 1
        score_diff = ranking.draw_points
    else:
        stats[stage_item_input_id].losses += 1
        score_diff = ranking.loss_points

    if ranking.add_score_points:
        score_diff += match.stage_item_input1_score if is_team1 else match.stage_item_input2_score

    match stage_item.type:
        case StageType.ROUND_ROBIN | StageType.SINGLE_ELIMINATION:
            stats[stage_item_input_id].points += score_diff

        case _:
            raise ValueError(f"Unsupported stage type: {stage_item.type}")


def determine_ranking_for_stage_item(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> defaultdict[StageItemInputId, TeamStatistics]:
    input_x_stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    # Seed every input with zero stats so participants that have not played a match yet
    # still appear in the ranking (with 0 points, not phantom draws). Without this, a team
    # whose matches are all unplayed vanishes from the ranking entirely, which also breaks
    # resolving the tentative inputs of a following stage to a team in seed order.
    for stage_item_input in stage_item.inputs:
        _ = input_x_stats[stage_item_input.id]

    matches = [
        match
        for round_ in stage_item.rounds
        if not round_.is_draft
        for match in round_.matches
        if isinstance(match, MatchWithDetailsDefinitive) and _match_has_result(match)
    ]
    for match in matches:
        for team_index, stage_item_input in enumerate(match.stage_item_inputs):
            set_statistics_for_stage_item_input(
                team_index,
                input_x_stats,
                match,
                stage_item_input.id,
                ranking,
                stage_item,
            )

    return input_x_stats


def determine_team_ranking_for_stage_item(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> list[tuple[StageItemInputId, TeamStatistics]]:
    """
    Rank the inputs of a stage item.

    Primary key is the accumulated points (one point per win by default). Inputs that are
    tied on points are re-ranked with the table-tennis group rules, applied among the tied
    players only: head-to-head wins -> games (局分) ratio -> points (小分) ratio.
    """
    team_ranking = determine_ranking_for_stage_item(stage_item, ranking)

    matches = [
        match
        for round_ in stage_item.rounds
        if not round_.is_draft
        for match in round_.matches
        if isinstance(match, MatchWithDetailsDefinitive) and _match_has_result(match)
    ]

    def submetrics(ids: set[StageItemInputId]) -> Any:
        wins = {i: 0 for i in ids}
        games_won = {i: 0 for i in ids}
        games_lost = {i: 0 for i in ids}
        points_won = {i: 0 for i in ids}
        points_lost = {i: 0 for i in ids}
        for match in matches:
            id1 = match.stage_item_inputs[0].id
            id2 = match.stage_item_inputs[1].id
            if id1 not in ids or id2 not in ids:
                continue
            s1 = match.stage_item_input1_score
            s2 = match.stage_item_input2_score
            games_won[id1] += s1
            games_lost[id1] += s2
            games_won[id2] += s2
            games_lost[id2] += s1
            if s1 > s2:
                wins[id1] += 1
            elif s2 > s1:
                wins[id2] += 1
            if match.games:
                p1 = sum(g[0] for g in match.games if len(g) == 2)
                p2 = sum(g[1] for g in match.games if len(g) == 2)
                points_won[id1] += p1
                points_lost[id1] += p2
                points_won[id2] += p2
                points_lost[id2] += p1
        return wins, games_won, games_lost, points_won, points_lost

    def ratio(won: int, lost: int) -> float:
        if lost > 0:
            return won / lost
        return float("inf") if won > 0 else 0.0

    items = sorted(team_ranking.items(), key=lambda x: x[1].points, reverse=True)

    result: list[tuple[StageItemInputId, TeamStatistics]] = []
    idx = 0
    while idx < len(items):
        end = idx
        while end < len(items) and items[end][1].points == items[idx][1].points:
            end += 1
        cluster = items[idx:end]
        if len(cluster) > 1:
            ids = {input_id for input_id, _ in cluster}
            wins, games_won, games_lost, points_won, points_lost = submetrics(ids)
            cluster.sort(
                key=lambda c: (
                    wins[c[0]],
                    ratio(games_won[c[0]], games_lost[c[0]]),
                    ratio(points_won[c[0]], points_lost[c[0]]),
                ),
                reverse=True,
            )
        result.extend(cluster)
        idx = end

    return result


async def recalculate_ranking_for_stage_item(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    ranking = await get_ranking_for_stage_item(tournament_id, stage_item.id)
    assert stage_item, "Stage item not found"
    assert ranking, "Ranking not found"

    team_x_stage_item_input_lookup = {
        stage_item_input.team_id: stage_item_input.id
        for stage_item_input in stage_item.inputs
        if stage_item_input.team_id is not None
    }

    elo_per_input = determine_ranking_for_stage_item(stage_item, ranking)

    for stage_item_input_id in team_x_stage_item_input_lookup.values():
        await update_team_stats(
            tournament_id, stage_item_input_id, elo_per_input[stage_item_input_id]
        )
