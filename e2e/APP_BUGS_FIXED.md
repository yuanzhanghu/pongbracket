# App bugs found by the E2E suite and fixed at the source

## BUG-1: unplayed round-robin matches counted as 0-0 draws in the standings

**Found:** 2026-06-27, by adversarial probing of the live standings (not the
existing tests — they only ever checked fully-scored stages).

**Symptom (user-visible):** in a round-robin, scoring a single match left every
*other* match counted as a 0-0 draw. In a 4-team RR (6 matches, each team plays
3), after one 11-0 result the two teams that had not played a single match each
showed **3 draws and 1.5 points** and ranked above zero. The leaderboard was
wrong for the entire tournament until the last match was played.

**Root cause:** `backend/bracket/logic/ranking/calculation.py`. The match list
fed to the ranking computation filtered only on `not round_.is_draft` and
`isinstance(match, MatchWithDetailsDefinitive)` — it did NOT exclude unplayed
matches. An unplayed match has scores 0-0, so in
`set_statistics_for_stage_item_input` `was_draw = (0 == 0)` was `True` and both
sides were awarded a draw + `draw_points`.

**Fix:** added `_match_has_result(match)` (a match counts only if it has a
forfeit or a non-zero score) and applied it to both match-list comprehensions in
`determine_ranking_for_stage_item` and `determine_team_ranking_for_stage_item`.
A genuine drawn match (e.g. a 1-1 games split → scores 1-1) is still counted; a
forfeit (0-0 + `forfeit_input`) is still counted.

**Verification:**
- Live API: after the fix, scoring one 11-0 match in a 4-team RR yields exactly
  one win / one loss; the two non-participating teams show W=D=L=0, pts=0.
- Backend unit tests unaffected (their only 0-0 matches are forfeits or
  non-definitive).
- Regression test added: `e2e/tests/test_progression_results.py::
  test_unplayed_rr_matches_not_counted_as_draws` (I7) — asserts total draws == 0
  and the two non-participating teams have empty records after a single result.

## BUG-2: a FORFEIT match blocks rated settlement ("no recorded result") and is silently dropped from the rating exchange

**Found:** 2026-06-27, by the iteration-2 e2e critic (the existing suite only
ever settled rated tournaments scored with a decisive 2:0; no test attempted to
settle a rated tournament containing a forfeit).

**Symptom (user-visible):** a creator who settles a rated individual tournament
(加华积分) where one or more matches ended in a forfeit (a normal table-tennis
outcome — illness / no-show) gets a confusing "Some matches still have no
recorded result" error and cannot settle at all. Even if that gate were
bypassed, the forfeit-only match would silently contribute nothing to the
rating exchange: the non-forfeiting player gets no +rating and the forfeiting
player gets no −rating.

**Root cause:** the settlement path consulted `score1`/`score2` only and never
`forfeit_input`. A forfeit is persisted as scores 0-0 + `forfeit_input ∈ {1,2}`,
so it was indistinguishable from an unplayed match at both gates:

1. `validate_settlement_ready` (`backend/bracket/logic/rating/settlement.py:108-110`)
   completeness gate checked only `r["score1"] == r["score2"]` and did not
   consult `forfeit_input` — a 0-0 forfeit was treated as "no recorded result".
2. `scored_matches_from_rows` (`backend/bracket/sql/ratings.py:267`) skipped
   any match where `score1 == score2` — a forfeit was silently dropped from
   the rating exchange.
3. The `get_definitive_matches_with_bindings` query did not even SELECT
   `forfeit_input`, so the value was unavailable downstream.
4. `settle_tournament` winner/loser determination (`settlement.py:172-175`)
   used `m.score1 > m.score2` only; a 0-0 forfeit has no decisive score.
5. `ScoredMatch` (`backend/bracket/models/db/rating.py:151`) had no
   `forfeit_input` field.

**Fix (minimal, 5 files):**
- `models/db/rating.py`: added `forfeit_input: int | None = None` to
  `ScoredMatch`.
- `sql/ratings.py`: `get_definitive_matches_with_bindings` now SELECTs
  `m.forfeit_input`; `scored_matches_from_rows` includes a match when
  `forfeit_input is not None` even at a 0-0 tie, and passes `forfeit_input`
  into `ScoredMatch`.
- `logic/rating/settlement.py`: completeness gate now blocks only when
  `score1 == score2 AND forfeit_input is None`; `settle_tournament`
  winner/loser determination consults `forfeit_input` first (`1` ⇒ side2 wins,
  `2` ⇒ side1 wins) before falling back to score comparison.

This mirrors how the (correct, non-rated) ranking path in
`calculation.py:46-53` already treats a forfeit as a win for the
non-forfeiting side. The 弃权 (forfeit) buttons are intentionally kept on the
rated match modal — a forfeit IS a legitimate result and the non-forfeiting
player deserves their ChinaTT gain.

**Verification:**
- New regression test: `e2e/tests/test_rating.py::
  test_forfeit_match_settles_on_rated_tournament` (M26) — forfeits the sole
  match of a 2-player rated RR via the UI 弃权 button, settles, and asserts the
  leaderboard shows the correct +8/−8 ChinaTT exchange (equal 1500 seeds) with
  matches_played==1 each.

## BUG-4: settled SE bracket was silently read-only (no freeze notification) unlike RR

**Found:** 2026-06-30, by the iteration-3 critic (Med). H9/H9b only exercised the
settled-freeze on an RR GroupGrid cell, where `results.tsx`'s `openMatchModal`
fires `showNotification` and returns. The SE bracket takes a different code path:
`results.tsx:175` passes `readOnly={!canRecord || isFrozen}` to
`EliminationBracket`, and `match.tsx:94` rendered a plain `<div>` (no
`UnstyledButton`, no `onClick`) when `readOnly`. So on a SETTLED tournament
with an SE stage, clicking a bracket match **silently did nothing**: no modal
opened (correct) BUT **no error notification rendered** either, unlike the RR
cell. The same settled tournament surfaced two inconsistent UIs depending on
the stage type.

**Root cause:** the `Match` component had no way to signal "frozen" on click when
read-only; the `EliminationBracket` and `results.tsx` did not wire a freeze
callback for the SE path.

**Fix (minimal, 3 files):**
- `frontend/src/components/brackets/match.tsx` — added an optional
  `onClickFrozen?: () => void` prop. When `readOnly` and `onClickFrozen` is
  provided, the card renders an `UnstyledButton` (so it's still clickable) whose
  `onClick` calls the callback; when `onClickFrozen` is undefined it stays a
  plain `<div>` (preserving the prior behavior for the stages bracket page and
  non-recorder viewers).
- `frontend/src/components/brackets/brackets.tsx` — `EliminationBracket` accepts
  and forwards `onClickFrozen` to each `Match`.
- `frontend/src/pages/tournaments/[id]/results.tsx` — passes
  `onClickFrozen={isFrozen ? () => showNotification({...scores_frozen...}) : undefined}`
  to the `EliminationBracket`, so a settled SE bracket shows the same
  `scores_frozen_title`/`scores_frozen_message` notification as the RR cell.

**Verification:**
- New regression test: `e2e/tests/test_match_scoring.py::
  test_settled_tournament_freezes_se_bracket` (H9c) — advances an RR→SE so SE
  inputs resolve, sets `settled_seq=1`, navigates to /results, clicks an SE
  bracket match, and asserts the fill modal does NOT open AND the same
  `.mantine-Notification-root` renders as the RR cell path (H9), plus backend
  PUT /matches returns 400 frozen.