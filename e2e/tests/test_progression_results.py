"""Progression & results tests (I1-I6)."""
from __future__ import annotations

import uuid

import requests
from playwright.sync_api import Page, expect

from ._helpers import (
    BASE_URL,
    _api_headers,
    api_create_court,
    api_create_round_robin,
    api_create_single_elimination,
    api_create_single_elimination_from_sources,
    api_create_stage,
    api_create_team,
    api_create_tournament,
    api_delete_stage,
    api_delete_tournament,
    api_get_rankings,
    api_get_stages,
    api_schedule_matches,
    api_update_match_score,
    api_update_ranking,
)


def _setup_rr(shared_tournament_id: int) -> int:
    stage_id = api_create_stage(
        shared_tournament_id, f"E2E-RRProg-{uuid.uuid4().hex[:6]}"
    )
    api_create_round_robin(shared_tournament_id, stage_id, team_count=4, group_count=1)
    return stage_id


def _setup_rr_scheduled(shared_tournament_id: int) -> int:
    """Setup an RR stage and ensure the matches have start_time (the results
    tab Schedule component filters matches with start_time != null)."""
    stage_id = _setup_rr(shared_tournament_id)
    # Courts are required before schedule_matches will fill start_time.
    api_create_court(shared_tournament_id, f"E2E-CtSched-{uuid.uuid4().hex[:4]}")
    api_create_court(shared_tournament_id, f"E2E-CtSched-{uuid.uuid4().hex[:4]}")
    api_schedule_matches(shared_tournament_id)
    return stage_id


def _setup_se(shared_tournament_id: int) -> int:
    stage_id = api_create_stage(
        shared_tournament_id, f"E2E-SEProg-{uuid.uuid4().hex[:6]}"
    )
    api_create_single_elimination(shared_tournament_id, stage_id, team_count=4)
    return stage_id


def test_advance_to_next_stage_modal(page: Page, shared_club_id: int) -> None:
    """I1: clicking \u4e0b\u4e00\u9636\u6bb5 opens the confirmation modal, and
    clicking the submit button activates the next stage.

    Earlier iterations of this test only opened the modal and asserted
    it mentions "\u9636\u6bb5" \u2014 a real assertion of the dialog opening,
    but a no-op for the actual advancement behaviour. This version does
    the full end-to-end:

      1. Create a fresh tournament with 4 teams (we control the exact
         stage ordering on a dedicated tournament because the shared
         tournament accumulates stages across runs).
      2. Create stage 1 (RR with 1 stage item) and stage 2 (SE with 1
         stage item). The next-stage route requires the next stage to
         already exist; it only flips `is_active` between stages.
      3. Pre-activate stage 1 via the API so the next "next" call
         advances to stage 2 (the SQL's get_next_stage_in_tournament
         returns the first inactive stage when no stage is currently
         active \u2014 so we seed the active state to make the UI click
         deterministic).
      4. Visit /stages, click \u4e0b\u4e00\u9636\u6bb5, assert the modal opens.
      5. Click the submit button (\u5f00\u59cb\u4e0b\u4e00\u9636\u6bb5 / plan_next_stage_button).
         Use exact=True because this label contains "\u4e0b\u4e00\u9636\u6bb5" as a
         substring.
      6. Assert the modal closes.
      7. Verify via the API: stage 2 is_active=True, stage 1 is_active=False.
    """
    tname = f"E2E-NextStage-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    for i in range(4):
        api_create_team(tid, f"E2E-NSTeam-{i}-{uuid.uuid4().hex[:4]}")
    s1 = api_create_stage(tid, f"E2E-NS-S1-{uuid.uuid4().hex[:6]}")
    api_create_round_robin(tid, s1, team_count=4, group_count=1)
    s2 = api_create_stage(tid, f"E2E-NS-S2-{uuid.uuid4().hex[:6]}")
    api_create_single_elimination(tid, s2, team_count=4)
    # Pre-activate stage 1 so the next "next" call advances to stage 2.
    # The activate endpoint is the only way to flip is_active.
    r0 = requests.post(
        f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
        headers=_api_headers(),
        json={"direction": "next"},
        timeout=15,
    )
    r0.raise_for_status()
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/stages",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector(
            'button:has-text("\u4e0b\u4e00\u9636\u6bb5")', state="visible", timeout=15_000
        )
        page.get_by_role("button", name="\u4e0b\u4e00\u9636\u6bb5").first.click()
        expect(page.locator(".mantine-Modal-content")).to_be_visible(timeout=10_000)
        # The confirmation dialog mentions starting the next stage.
        modal_text = page.locator(".mantine-Modal-content").last.inner_text()
        assert "\u9636\u6bb5" in modal_text, (
            f"expected next-stage modal to mention '\u9636\u6bb5', got: {modal_text[:300]}"
        )
        # Click the submit button. The plan_next_stage_button label
        # "\u5f00\u59cb\u4e0b\u4e00\u9636\u6bb5" CONTAINS "\u4e0b\u4e00\u9636\u6bb5" as a
        # substring, so use exact=True to disambiguate.
        plan_btn = page.get_by_role(
            "button", name="\u5f00\u59cb\u4e0b\u4e00\u9636\u6bb5", exact=True
        ).first
        expect(plan_btn).to_be_visible(timeout=5_000)
        plan_btn.click()
        # The modal should close after submit.
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=15_000)
        # Verify via API: stage 2 is now is_active=True, stage 1 is_active=False.
        stages = api_get_stages(tid)
        stage_map = {s["id"]: s for s in stages}
        assert stage_map[s2].get("is_active") is True, (
            f"expected stage 2 is_active=True after advance, got "
            f"{stage_map[s2].get('is_active')!r}"
        )
        assert stage_map[s1].get("is_active") is False, (
            f"expected stage 1 is_active=False after advance, got "
            f"{stage_map[s1].get('is_active')!r}"
        )
    finally:
        # Best-effort cleanup: delete stages, then the tournament.
        try:
            api_delete_stage(tid, s2)
        except Exception:
            pass
        try:
            api_delete_stage(tid, s1)
        except Exception:
            pass
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


def test_activate_previous_stage_button(page: Page, shared_club_id: int) -> None:
    """I1c: clicking 上一阶段 opens the confirmation modal, and clicking the
    submit button (返回到上一阶段 / plan_previous_stage_button) activates the
    previous stage.

    This is the inverse of test_advance_to_next_stage_modal. We create two
    stages, activate stage 1 then advance to stage 2 (so stage 2 is active),
    then use the 上一阶段 button in the UI to go back to stage 1.
    """
    tname = f"E2E-PrevStage-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    for i in range(4):
        api_create_team(tid, f"E2E-PSTeam-{i}-{uuid.uuid4().hex[:4]}")
    s1 = api_create_stage(tid, f"E2E-PS-S1-{uuid.uuid4().hex[:6]}")
    api_create_round_robin(tid, s1, team_count=4, group_count=1)
    s2 = api_create_stage(tid, f"E2E-PS-S2-{uuid.uuid4().hex[:6]}")
    api_create_single_elimination(tid, s2, team_count=4)
    # Activate stage 1, then advance to stage 2 — both via API so the active
    # stage is s2 before we exercise the UI's "previous" button.
    for direction in ("next", "next"):
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
            headers=_api_headers(),
            json={"direction": direction},
            timeout=15,
        )
        if r.status_code == 400:
            break  # no more stages in that direction — fine
        r.raise_for_status()
    # Confirm the active stage is s2 before the UI action.
    pre = {s["id"]: s for s in api_get_stages(tid)}
    assert pre[s2].get("is_active") is True, "stage 2 should be active before going back"
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/stages",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector(
            'button:has-text("上一阶段")', state="visible", timeout=15_000
        )
        page.get_by_role("button", name="上一阶段").first.click()
        expect(page.locator(".mantine-Modal-content")).to_be_visible(timeout=10_000)
        modal_text = page.locator(".mantine-Modal-content").last.inner_text()
        assert "阶段" in modal_text, (
            f"expected previous-stage modal to mention '阶段', got: {modal_text[:300]}"
        )
        # Click the submit button (返回到上一阶段, exact to disambiguate from 上一阶段).
        plan_btn = page.get_by_role(
            "button", name="返回到上一阶段", exact=True
        ).first
        expect(plan_btn).to_be_visible(timeout=5_000)
        plan_btn.click()
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=15_000)
        # Verify via API: stage 1 is now is_active=True, stage 2 is_active=False.
        stages = api_get_stages(tid)
        stage_map = {s["id"]: s for s in stages}
        assert stage_map[s1].get("is_active") is True, (
            f"expected stage 1 is_active=True after going back, got "
            f"{stage_map[s1].get('is_active')!r}"
        )
        assert stage_map[s2].get("is_active") is False, (
            f"expected stage 2 is_active=False after going back, got "
            f"{stage_map[s2].get('is_active')!r}"
        )
    finally:
        try:
            api_delete_stage(tid, s2)
        except Exception:
            pass
        try:
            api_delete_stage(tid, s1)
        except Exception:
            pass
        try:
            api_delete_tournament(tid)
        except Exception:
            pass

def test_advance_to_next_stage_seeds_se_from_rr(
    page: Page, shared_club_id: int
) -> None:
    """I1b: advancing from a finished RR stage to an SE stage seeded from
    that RR populates the SE inputs with concrete team ids.

    The user-visible payoff of \"advance to next stage\" is that the next
    stage's bracket is no longer placeholders \u2014 the SE inputs resolve to
    actual team ids drawn from the RR's final ranking. This test exercises
    that propagation end-to-end:

      1. Create a fresh tournament with 4 teams.
      2. Stage 1: RR with 4 teams in 1 group. C(4,2) = 6 matches.
      3. Stage 2: SE seeded from stage 1's RR via the
         /stage_items/elimination_from_sources endpoint with positions=4
         (every RR finisher seeds an SE slot). The 4 SE inputs are
         created as Tentative (winner_from_stage_item_id=<RR>,
         winner_position=N) with team_id=None.
      4. Score every RR match via the API so the RR has a complete final
         ranking (otherwise advance returns 400 from
         get_team_update_for_input).
      5. Pre-activate stage 1 so the next \"next\" call advances to stage 2.
      6. UI: visit /stages, click \u4e0b\u4e00\u9636\u6bb5, click \u5f00\u59cb\u4e0b\u4e00\u9636\u6bb5, assert the
         modal closes.
      7. API ground truth: every input on the SE stage item that referenced
         a winner_from_stage_item_id now has a concrete team_id, and those
         team_ids are exactly the 4 teams we created (the SE inputs were
         populated from the RR ranking, not left as placeholders).

    A regression in update_matches_in_activated_stage,
    get_updates_to_inputs_in_activated_stage, or sql_set_team_id_for_stage_item_input
    leaves the SE inputs with team_id=None and surfaces here. I1
    asserts only the is_active flip; this test asserts the team-id
    propagation, the user-visible payoff.
    """
    tname = f"E2E-NextSeed-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    team_ids: list[int] = []
    for i in range(4):
        team_ids.append(
            api_create_team(tid, f"E2E-NSSeedTeam-{i}-{uuid.uuid4().hex[:4]}")
        )
    s1 = api_create_stage(tid, f"E2E-NSSeed-S1-{uuid.uuid4().hex[:6]}")
    rr_item_id = api_create_round_robin(tid, s1, team_count=4, group_count=1)
    s2 = api_create_stage(tid, f"E2E-NSSeed-S2-{uuid.uuid4().hex[:6]}")
    se_item_id = api_create_single_elimination_from_sources(
        tid,
        s2,
        sources=[{"stage_item_id": rr_item_id, "positions": 4}],
        take="top",
    )
    # Score every RR match so the ranking is complete.
    # (match_id, round_id, input1_team_id, input2_team_id)
    rr_matches: list[tuple[int, int, int | None, int | None]] = []
    for s in api_get_stages(tid):
        if s["id"] != s1:
            continue
        for item in s.get("stage_items", []):
            if item["id"] != rr_item_id:
                continue
            for rd in item.get("rounds", []):
                for m in rd.get("matches", []):
                    in1 = (m.get("stage_item_input1") or {}).get("team_id")
                    in2 = (m.get("stage_item_input2") or {}).get("team_id")
                    rr_matches.append((m["id"], rd["id"], in1, in2))
    assert len(rr_matches) == 6, (
        f"expected 6 RR matches (C(4,2)) before scoring, got {len(rr_matches)}"
    )
    # Make team_ids[0] win ALL 3 of its matches so it is the UNAMBIGUOUS
    # rank-1 finisher (no other team can reach 3 wins). This lets us assert
    # not just that the SE inputs resolve to the right SET of teams, but that
    # SEED ORDER is correct: winner_position==1 must map to the dominant team.
    # A regression that shuffles/reverses the seeding (e.g. last place seeded
    # into slot 1) produces the same set but fails the position-1 check below.
    champion = team_ids[0]
    for mid, rid, in1, in2 in rr_matches:
        if in1 == champion:
            games = [[11, 7]]  # input1 (champion) wins
        elif in2 == champion:
            games = [[7, 11]]  # input2 (champion) wins
        else:
            games = [[11, 7]]  # match not involving the champion; arbitrary
        api_update_match_score(tid, mid, rid, games, best_of=1)

    # Pre-activate stage 1 so the next "next" call advances to stage 2.
    r0 = requests.post(
        f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
        headers=_api_headers(),
        json={"direction": "next"},
        timeout=15,
    )
    r0.raise_for_status()

    # Sanity: BEFORE advance, the SE inputs reference the RR but have no
    # team_id yet (Tentative). This is the pre-condition that the advance
    # flow is supposed to resolve.
    pre_stages = {s["id"]: s for s in api_get_stages(tid)}
    pre_se_item = next(
        (i for i in pre_stages[s2]["stage_items"] if i["id"] == se_item_id),
        None,
    )
    assert pre_se_item is not None
    pre_inputs_referencing_rr = [
        i for i in pre_se_item.get("inputs", [])
        if i.get("winner_from_stage_item_id") == rr_item_id
    ]
    assert len(pre_inputs_referencing_rr) == 4, (
        f"expected 4 SE inputs referencing the RR before advance, got "
        f"{len(pre_inputs_referencing_rr)}"
    )
    # Tentative inputs have team_id=None pre-advance.
    assert all(i.get("team_id") is None for i in pre_inputs_referencing_rr), (
        f"expected all SE Tentative inputs to have team_id=None pre-advance, "
        f"got {[(i.get('winner_position'), i.get('team_id')) for i in pre_inputs_referencing_rr]}"
    )

    try:
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/stages",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector(
            'button:has-text("\u4e0b\u4e00\u9636\u6bb5")', state="visible", timeout=15_000
        )
        page.get_by_role("button", name="\u4e0b\u4e00\u9636\u6bb5").first.click()
        expect(page.locator(".mantine-Modal-content")).to_be_visible(timeout=10_000)
        plan_btn = page.get_by_role(
            "button", name="\u5f00\u59cb\u4e0b\u4e00\u9636\u6bb5", exact=True
        ).first
        expect(plan_btn).to_be_visible(timeout=5_000)
        plan_btn.click()
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=15_000)

        # Ground-truth: stage 2 is_active=True AND the SE inputs that
        # referenced the RR now resolve to concrete team ids drawn from
        # the 4 teams we created.
        post_stages = {s["id"]: s for s in api_get_stages(tid)}
        assert post_stages[s2].get("is_active") is True, (
            f"expected stage 2 is_active=True after advance, got "
            f"{post_stages[s2].get('is_active')!r}"
        )
        post_se_item = next(
            (i for i in post_stages[s2]["stage_items"] if i["id"] == se_item_id),
            None,
        )
        assert post_se_item is not None
        post_inputs = [
            i for i in post_se_item.get("inputs", [])
            if i.get("winner_from_stage_item_id") == rr_item_id
        ]
        assert len(post_inputs) == 4, (
            f"expected 4 SE inputs referencing the RR after advance, got "
            f"{len(post_inputs)}"
        )
        resolved_team_ids = [i.get("team_id") for i in post_inputs]
        assert all(tid_ is not None for tid_ in resolved_team_ids), (
            f"expected every SE input to resolve to a team_id after advance, "
            f"got {resolved_team_ids!r} (placeholders remain \u2014 the seed "
            f"propagation regressed)"
        )
        assert set(resolved_team_ids) == set(team_ids), (
            f"expected SE inputs to resolve to exactly the 4 RR team ids "
            f"{set(team_ids)!r}, got {set(resolved_team_ids)!r}"
        )
        # Seed ORDER: the rank-1 finisher (champion, who won all 3 matches)
        # must be seeded into winner_position==1. Set-equality above cannot
        # catch a seeding shuffle; this does.
        pos1 = next(
            (i for i in post_inputs if i.get("winner_position") == 1), None
        )
        assert pos1 is not None, (
            f"expected an SE input with winner_position==1, got "
            f"{[i.get('winner_position') for i in post_inputs]!r}"
        )
        assert pos1.get("team_id") == champion, (
            f"expected the rank-1 RR finisher (team {champion}) seeded into SE "
            f"slot 1, got team {pos1.get('team_id')!r}"
        )
    finally:
        try:
            api_delete_stage(tid, s2)
        except Exception:
            pass
        try:
            api_delete_stage(tid, s1)
        except Exception:
            pass
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


def test_elimination_bracket_renders(page: Page, shared_tournament_id: int) -> None:
    """I2: a single-elimination stage produces a bracket that renders inline on
    the '录入分数和结果' results tab with real, bracket-specific content.

    The old '对阵图' tab was removed; SE stage items now render an
    EliminationBracket inline in the default '录入分数和结果' tab. This version
    asserts bracket-specific structure:

      * the results panel contains at least one <h3> (the stage-item heading
        rendered by <Title order={3}>), AND
      * the panel text mentions a bracket-specific label ("Single
        Elimination" / "Round 01" / "Round 02").

    Note: the seeded team names are NOT visible because the SE stage item is
    created with team_count=4 but inputs aren't auto-assigned — the bracket
    renders "空槽位" (empty slot) placeholders.
    """
    stage_id = _setup_se(shared_tournament_id)
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{shared_tournament_id}/results",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        # The default '录入分数和结果' tab is active; the SE bracket renders inline.
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_be_visible(timeout=10_000)
        # Real bracket-specific signal: at least one <h3> (the stage-item
        # heading rendered by <Title order={3}>) in the panel.
        h3_count = panel.locator("h3").count()
        assert h3_count >= 1, (
            f"expected at least one stage-item header (h3) in results panel, "
            f"got {h3_count}; panel text: {panel.inner_text()[:200]}"
        )
        # And the panel text should mention a bracket-specific label.
        panel_text = panel.inner_text()
        assert (
            "Single Elimination" in panel_text
            or "Round 01" in panel_text
            or "Round 02" in panel_text
        ), (
            f"expected bracket-specific labels in panel, got: {panel_text[:200]}"
        )
    finally:
        api_delete_stage(shared_tournament_id, stage_id)

def test_results_tab_shows_matches(page: Page, shared_club_id: int) -> None:
    """I3: the '录入分数和结果' tab renders a GroupGrid cross-table with the
    just-created stage's team names.

    The old match-card-based 'matches' tab is gone; RR stage items now render
    a GroupGrid <table> inline. This version uses a DEDICATED fresh tournament
    with a unique team-name prefix so the assertions are scoped to this stage:

      1. Create a fresh tournament + 4 teams + an RR stage + 2 courts +
         schedule_matches.
      2. The GroupGrid renders a <table> whose body contains all 4 team names.
      3. Assert the table renders AND all 4 team names appear.
    """
    from ._helpers import api_create_court, api_create_team, api_create_tournament, api_delete_tournament

    tname = f"E2E-Results-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        team_prefix = f"E2E-ResTeam-{uuid.uuid4().hex[:4]}"
        for i in range(4):
            api_create_team(tid, f"{team_prefix}-{i}")
        stage_id = api_create_stage(tid, f"E2E-ResStage-{uuid.uuid4().hex[:6]}")
        api_create_round_robin(tid, stage_id, team_count=4, group_count=1)
        api_create_court(tid, f"E2E-ResCt-{uuid.uuid4().hex[:4]}")
        api_create_court(tid, f"E2E-ResCt-{uuid.uuid4().hex[:4]}")
        api_schedule_matches(tid)

        page.goto(
            f"{BASE_URL}/tournaments/{tid}/results",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        # Default tab is '录入分数和结果'. Wait for the GroupGrid table to render.
        expect(page.locator("table").first).to_be_visible(timeout=15_000)
        # All 4 team names appear in the GroupGrid.
        for i in range(4):
            expect(page.locator("body")).to_contain_text(f"{team_prefix}-{i}", timeout=10_000)
        # The GroupGrid has clickable cells (the owner can_record): unscored
        # cells show '—' as buttons.
        assert page.locator("button", has_text="—").count() >= 1, (
            "expected at least one clickable unscored cell in the GroupGrid"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass



def test_rankings_tab_renders(page: Page, shared_club_id: int) -> None:
    """I4: the \u6392\u540d (standings) tab shows standings AND updates after scores.

    Uses a DEDICATED fresh tournament so the standings panel reflects
    only this stage's matches \u2014 the shared tournament accumulates
    scored matches across runs, so a "no 1:0 visible before scoring"
    assertion would be unreliable there.

    Drives the full standings-recomputation path:

      1. Create a fresh tournament + 4 teams + an RR stage.
      2. Open the \u6392\u540d tab BEFORE any match is scored. The \u5c0f\u5206
         (points) column shows "0:0" for every row, and no row shows
         a "1:0" or "0:1" games-score (\u5c40\u5206) cell yet.
      3. Score the first match via the API (games=[[11,7]] -> 1:0).
      4. Reload, re-open the \u6392\u540d tab, and assert the standings table
         now shows BOTH a "1:0" games cell (winner) AND an "11:7"
         points cell (the per-points sum that only appears after a
         scored game). A regression in the standings-recomputation
         path surfaces here.
    """
    from ._helpers import api_update_match_score

    tname = f"E2E-Rankings-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        for i in range(4):
            api_create_team(tid, f"E2E-RkTeam-{i}-{uuid.uuid4().hex[:4]}")
        stage_id = api_create_stage(tid, f"E2E-RkRR-{uuid.uuid4().hex[:6]}")
        api_create_round_robin(tid, stage_id, team_count=4, group_count=1)

        page.goto(
            f"{BASE_URL}/tournaments/{tid}/results",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        page.get_by_role("tab", name="\u6392\u540d").first.click()
        panel = page.get_by_role("tabpanel").first
        # Pre-score: team rows render; the points column shows "0:0";
        # the games-score column shows "0:0"; no "1:0"/"0:1"/"11:7"
        # cells exist yet.
        expect(panel).to_contain_text("E2E-RkTeam-", timeout=15_000)
        pre_text = panel.inner_text()
        assert "0:0" in pre_text, (
            f"expected pre-score standings to show '0:0', got: {pre_text[:300]}"
        )
        assert "1:0" not in pre_text and "0:1" not in pre_text, (
            f"unexpected scored cells before scoring any match: "
            f"{pre_text[:300]}"
        )
        assert "11:7" not in pre_text, (
            f"unexpected '11:7' (points sum) cell before scoring: "
            f"{pre_text[:300]}"
        )

        # Score the first match: find round_id + match_id.
        round_id = None
        match_id = None
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    matches = rd.get("matches", [])
                    if matches:
                        round_id = rd["id"]
                        match_id = matches[0]["id"]
                        break
                if round_id is not None:
                    break
        assert round_id is not None and match_id is not None
        api_update_match_score(tid, match_id, round_id, [[11, 7]], best_of=1)

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        page.get_by_role("tab", name="\u6392\u540d").first.click()
        panel = page.get_by_role("tabpanel").first
        # Post-score: the winner's row shows "1:0" (games) and "11:7"
        # (points sum) \u2014 both are recomputed on the client from the
        # match's input scores + games array.
        expect(panel).to_contain_text("1:0", timeout=15_000)
        expect(panel).to_contain_text("11:7", timeout=10_000)
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass



def test_rankings_head_to_head_tiebreak(page: Page, shared_club_id: int) -> None:
    """I4b: when two teams tie on points (= wins), the \u6392\u540d standings break the
    tie by HEAD-TO-HEAD result, NOT by overall point differential.

    Builds a 4-team round robin (A, B, C, D) with a deterministic outcome:

      A beats B (11:9), A beats C (11:9), D beats A (11:9)   -> A: 2 wins
      B beats C (11:1), B beats D (11:1), A beats B          -> B: 2 wins
      C beats D (11:1), C loses to A & B                     -> C: 1 win
      D beats A (11:9), D loses to B & C                     -> D: 1 win

    A and B both finish on 2 wins (equal points). B wins ITS matches by
    blow-outs (11:1) so B's OVERALL points ratio is far higher than A's \u2014 a
    naive tiebreak that sorted the whole table by points-differential would put
    B above A. But A beat B head-to-head, so the correct table-tennis tiebreak
    (head-to-head wins first) ranks A ABOVE B. Likewise C beat D head-to-head,
    so C ranks above D. Expected display order: A, B, C, D.

    This exercises `rankInputsWithTiebreak` in standings.tsx (the documented
    coverage gap) end-to-end through the rendered \u6392\u540d tab.
    """
    tname = f"E2E-H2H-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        sfx = uuid.uuid4().hex[:4]
        names = {
            "A": f"E2E-H2HA-{sfx}",
            "B": f"E2E-H2HB-{sfx}",
            "C": f"E2E-H2HC-{sfx}",
            "D": f"E2E-H2HD-{sfx}",
        }
        ids = {k: api_create_team(tid, v) for k, v in names.items()}
        id_to_key = {v: k for k, v in ids.items()}

        stage_id = api_create_stage(tid, f"E2E-H2HS-{sfx}")
        api_create_round_robin(tid, stage_id, team_count=4, group_count=1)

        # (winner_key, loser_key) pairs for every RR match.
        beats = {
            ("A", "B"), ("A", "C"), ("D", "A"),
            ("B", "C"), ("B", "D"), ("C", "D"),
        }

        # Collect the 6 RR matches with their two input team ids.
        rr_matches: list[tuple[int, int, int | None, int | None]] = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        in1 = (m.get("stage_item_input1") or {}).get("team_id")
                        in2 = (m.get("stage_item_input2") or {}).get("team_id")
                        rr_matches.append((m["id"], rd["id"], in1, in2))
        assert len(rr_matches) == 6, (
            f"expected 6 RR matches (C(4,2)), got {len(rr_matches)}"
        )

        for mid, rid, in1, in2 in rr_matches:
            k1, k2 = id_to_key[in1], id_to_key[in2]
            if (k1, k2) in beats:
                winner_key, in1_wins = k1, True
            else:
                assert (k2, k1) in beats, f"no outcome for pair {k1}-{k2}"
                winner_key, in1_wins = k2, False
            # B's wins are blow-outs (11:1); everyone else's are 11:9.
            margin = [11, 1] if winner_key == "B" else [11, 9]
            games = [margin] if in1_wins else [[margin[1], margin[0]]]
            api_update_match_score(tid, mid, rid, games, best_of=1)

        # Open the \u6392\u540d standings tab and read the rendered row order.
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded"
        )
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        page.get_by_role("tab", name="\u6392\u540d").first.click()
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_contain_text(names["A"], timeout=15_000)

        row_texts = panel.locator("tbody tr").all_inner_texts()
        assert row_texts, "expected at least one rendered standings row"

        # Map each team to its first row index in the rendered table.
        positions: dict[str, int] = {}
        for idx, txt in enumerate(row_texts):
            for key, nm in names.items():
                if nm in txt and key not in positions:
                    positions[key] = idx
        assert set(positions) == {"A", "B", "C", "D"}, (
            f"all 4 teams must render in the standings, got {positions} "
            f"from rows {row_texts}"
        )

        # Head-to-head decides BOTH tied clusters: A above B, C above D.
        assert positions["A"] < positions["B"], (
            f"A beat B head-to-head and ties on points, so A must rank above B; "
            f"positions={positions}"
        )
        assert positions["C"] < positions["D"], (
            f"C beat D head-to-head and ties on points, so C must rank above D; "
            f"positions={positions}"
        )
        # The full expected order is A, B, C, D (the two 2-win teams above the
        # two 1-win teams, each cluster ordered by head-to-head).
        assert positions["A"] < positions["B"] < positions["C"] < positions["D"], (
            f"expected display order A,B,C,D; got positions={positions}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


def test_bracket_tab_renders(page: Page, shared_tournament_id: int) -> None:
    """I5: the EliminationBracket renders inline on the '录入分数和结果' results tab
    as a multi-column bracket.

    The old '对阵图' tab was removed; SE stage items now render an
    EliminationBracket inline in the default '录入分数和结果' tab. I2 already
    asserts the stage-item heading (h3). This test exercises a DIFFERENT bracket
    affordance: the EliminationBracket's multi-column round layout.

    For a 4-team SE bracket the backend creates multiple rounds:
      - Semifinal (1/2决赛, 2 matches) and
      - Final (决赛, 1 match).
    Both round names follow eliminationRoundName: the single-match round is
    决赛 (final_round_name), N-match rounds are 1/N决赛 (fraction_round_name).

    Asserting that BOTH round names appear in the panel is genuinely different
    from I2's h3 stage-item title assertion: a regression that drops the round
    columns from the EliminationBracket while keeping the stage-item title
    would fail I5 but pass I2.
    """
    stage_id = _setup_se(shared_tournament_id)
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{shared_tournament_id}/results",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        # The default '录入分数和结果' tab is active; the SE bracket renders inline.
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_be_visible(timeout=10_000)
        # The stage-item title is an h3 ("Single Elimination").
        h3_count = panel.locator("h3").count()
        assert h3_count >= 1, (
            f"expected at least 1 h3 (stage-item title) in bracket panel, "
            f"got {h3_count}; panel text: {panel.inner_text()[:300]}"
        )
        # The round names follow eliminationRoundName: 决赛 (final) and
        # 1/N决赛 (fraction). For a 4-team bracket both must appear.
        panel_text = panel.inner_text()
        assert "决赛" in panel_text, (
            f"expected '决赛' (final round name) in bracket panel text, "
            f"got: {panel_text[:300]}"
        )
        assert "1/2决赛" in panel_text or "1/4决赛" in panel_text, (
            f"expected fraction round name ('1/2决赛' or '1/4决赛') in "
            f"bracket panel text, got: {panel_text[:300]}"
        )
    finally:
        api_delete_stage(shared_tournament_id, stage_id)


def test_rankings_config_form(page: Page, shared_tournament_id: int) -> None:
    """I6: /rankings shows the scoring-rules config form AND the form persists edits.

    The earlier iteration of this test only asserted the page rendered. The
    real test of the rankings scoring-rules config is end-to-end:

      1. Navigate to /rankings (the Accordion + NumberInput form).
      2. The default ranking 0 ("\u9ed8\u8ba4\u6392\u540d") is open by default.
      3. Change the \u83b7\u80dc\u79ef\u5206 (win_points) NumberInput value.
      4. Click \u4fdd\u5b58 \u6392\u540d 1 (the per-ranking save button).
      5. Reload the page and assert the new value is still in the input.
      6. Also assert the API returns the new value (ground truth).
      7. Restore the original value so the shared tournament stays clean.
    """
    # Read the current default ranking's win_points so we can restore it.
    initial_rankings = api_get_rankings(shared_tournament_id)
    assert initial_rankings, "expected the shared tournament to have at least one ranking"
    default_ranking = next(
        (r for r in initial_rankings if r["position"] == 0),
        initial_rankings[0],
    )
    original_win_points = default_ranking["win_points"]
    new_win_points = "7" if original_win_points != "7" else "3"

    page.goto(
        f"{BASE_URL}/tournaments/{shared_tournament_id}/rankings",
        wait_until="domcontentloaded",
    )
    # \u6dfb\u52a0\u6392\u540d is the "add ranking" button at the bottom of the page.
    page.wait_for_selector(
        'button:has-text("\u6dfb\u52a0\u6392\u540d")', state="visible", timeout=15_000
    )
    expect(page.locator("body")).to_contain_text("\u6392\u540d", timeout=10_000)
    expect(page.locator("body")).to_contain_text("\u6dfb\u52a0\u6392\u540d", timeout=10_000)

    # Wait for the SWR rankings data to load: the \u6dfb\u52a0\u6392\u540d button renders
    # independently of the data fetch, so we must wait for the per-ranking
    # Accordion form to appear. The \u83b7\u80dc\u79ef\u5206 (win_points) NumberInput is
    # rendered inside the open Accordion panel only after the data loads.
    # Wait for the input directly \u2014 it's the most specific element that
    # proves both the form and the data have rendered.
    win_input = page.locator('input[type="text"]').first
    expect(win_input).to_be_visible(timeout=20_000)
    first_form = win_input.locator('xpath=ancestor::form[1]')
    expect(first_form).to_be_visible(timeout=5_000)
    win_input.fill(new_win_points)
    # \u4fdd\u5b58 \u6392\u540d 1 is the per-ranking save button inside the open panel.
    first_form.get_by_role(
        "button", name=f"\u4fdd\u5b58 \u6392\u540d {default_ranking['position'] + 1}"
    ).first.click()
    # Wait for the save to round-trip: reload, then assert the value is still
    # in the input.
    page.wait_for_timeout(1500)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(
        'button:has-text("\u6dfb\u52a0\u6392\u540d")', state="visible", timeout=15_000
    )
    # Same SWR-data race as the initial load: wait for the input directly.
    reloaded_win = page.locator('input[type="text"]').first
    expect(reloaded_win).to_be_visible(timeout=20_000)
    # Mantine NumberInput normalises integer input to a float string
    # (e.g. "7" becomes "7.0"). Accept either form so the test is
    # resilient to that.
    actual = reloaded_win.input_value()
    assert actual in (new_win_points, f"{new_win_points}.0"), (
        f"expected win_points input to be {new_win_points!r} (or {new_win_points}.0), got {actual!r}"
    )
    after_rankings = api_get_rankings(shared_tournament_id)
    after_default = next(
        (r for r in after_rankings if r["position"] == default_ranking["position"]),
        None,
    )
    assert after_default is not None, "default ranking disappeared from API"
    # Mantine NumberInput normalises integer values to floats in the API too,
    # so compare numerically to avoid a brittle "7" vs "7.0" string mismatch.
    assert float(after_default["win_points"]) == float(new_win_points), (
        f"API win_points: expected {new_win_points!r}, got {after_default['win_points']!r}"
    )
    # Restore the original value so the shared fixture stays clean.
    api_update_ranking(
        shared_tournament_id,
        default_ranking["id"],
        win_points=float(original_win_points),
        draw_points=float(default_ranking["draw_points"]),
        loss_points=float(default_ranking["loss_points"]),
add_score_points=bool(default_ranking.get("add_score_points", False)),
    )


def test_unplayed_rr_matches_not_counted_as_draws(shared_club_id: int) -> None:
    """I7: standings must NOT count UNPLAYED round-robin matches as 0-0 draws.

    Regression for a real backend bug (logic/ranking/calculation.py): an
    unplayed match (no forfeit, 0-0, no games) was still fed into the ranking
    computation, where `was_draw = (0 == 0) = True` awarded draw_points to BOTH
    sides. In a 4-team RR (6 matches, each team plays 3), scoring a SINGLE match
    left the two non-participating teams each showing 3 phantom draws and
    points — i.e. teams that had played nothing ranked above zero, and the whole
    leaderboard was wrong until every match was played.

    With the fix, after scoring exactly ONE match 11-0:
      - exactly one win and one loss exist across the whole stage,
      - ZERO draws (no match was an actual draw), and
      - the two teams that did not play have a fully empty W/D/L record.

    The pre-existing I4 standings test only checks the games/points CELLS of
    scored rows, so it never exercised the unplayed-match state and could not
    catch this.
    """
    from ._helpers import (
        api_create_team,
        api_create_tournament,
        api_delete_tournament,
    )

    tid = api_create_tournament(shared_club_id, f"E2E-Unplayed-{uuid.uuid4().hex[:6]}")
    try:
        for i in range(4):
            api_create_team(tid, f"E2E-UnpTeam-{i}-{uuid.uuid4().hex[:4]}")
        stage_id = api_create_stage(tid, f"E2E-UnpRR-{uuid.uuid4().hex[:6]}")
        api_create_round_robin(tid, stage_id, team_count=4, group_count=1)

        def stage_item() -> dict:
            for s in api_get_stages(tid):
                if s["id"] == stage_id:
                    return s["stage_items"][0]
            raise AssertionError("stage item not found")

        si = stage_item()
        matches = [(m["id"], rd["id"]) for rd in si["rounds"] for m in rd["matches"]]
        assert len(matches) == 6, f"4-team RR should have 6 matches, got {len(matches)}"

        # Score exactly ONE match 11-0; the other 5 stay unplayed.
        mid, rid = matches[0]
        api_update_match_score(tid, mid, rid, [[11, 0]], best_of=1)

        inputs = stage_item()["inputs"]
        wld = [
            (inp.get("wins") or 0, inp.get("draws") or 0, inp.get("losses") or 0)
            for inp in inputs
        ]
        total_w = sum(w for w, _, _ in wld)
        total_d = sum(d for _, d, _ in wld)
        total_l = sum(loss for _, _, loss in wld)

        assert total_d == 0, (
            f"unplayed matches must NOT count as draws; got per-input draws "
            f"{[d for _, d, _ in wld]} (total {total_d})"
        )
        assert total_w == 1 and total_l == 1, (
            f"expected exactly one win and one loss after a single 11-0 result, "
            f"got wins={total_w}, losses={total_l}; per-input W/D/L={wld}"
        )
        empty = [t for t in wld if t == (0, 0, 0)]
        assert len(empty) == 2, (
            f"the two non-participating teams must each have W=D=L=0, got {wld}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


def test_se_winner_advancement_propagates_to_final(
    page: Page, shared_club_id: int
) -> None:
    """I8: scoring an SE semifinal propagates the winner to the final match.

    Creates a 4-team SE (not from sources), assigns concrete teams to the 4
    input slots, scores BOTH semifinal matches via the API, then asserts the
    final match's two stage_item_inputs now reference the two semifinal
    winners' team_ids (not None). This is THE core single-elimination behavior;
    a regression where scoring a match failed to propagate the winner to the
    next round (e.g. ``update_inputs_in_subsequent_elimination_rounds`` stopped
    updating downstream inputs) would pass every existing test.
    """
    tname = f"E2E-SEAdv-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        # Create 4 teams.
        team_names = [f"E2E-SEAdvT-{i}-{uuid.uuid4().hex[:4]}" for i in range(4)]
        team_ids: list[int] = []
        for nm in team_names:
            team_ids.append(api_create_team(tid, nm))

        # Create a stage + SE stage item (team_count=4, creates empty inputs).
        stage_id = api_create_stage(tid, f"E2E-SEAdvS-{uuid.uuid4().hex[:6]}")
        se_item_id = api_create_single_elimination(tid, stage_id, team_count=4)

        # Assign teams to the 4 SE input slots via PUT /inputs/{id}.
        stages = api_get_stages(tid)
        se_item = None
        for s in stages:
            if s["id"] == stage_id:
                for it in s.get("stage_items", []):
                    if it["id"] == se_item_id:
                        se_item = it
        assert se_item is not None, "SE stage item not found"
        se_inputs = se_item.get("inputs", [])
        assert len(se_inputs) == 4, (
            f"expected 4 SE inputs, got {len(se_inputs)}"
        )
        # Sort by slot to get deterministic assignment.
        se_inputs.sort(key=lambda x: x.get("slot", 0))
        for inp, tid_val in zip(se_inputs, team_ids):
            r = requests.put(
                f"{BASE_URL}/api/tournaments/{tid}/stage_items/{se_item_id}/inputs/{inp['id']}",
                headers=_api_headers(),
                json={"team_id": tid_val},
                timeout=15,
            )
            r.raise_for_status()

        # Reload SE item to get match structure with assigned teams.
        stages = api_get_stages(tid)
        se_item = None
        for s in stages:
            if s["id"] == stage_id:
                for it in s.get("stage_items", []):
                    if it["id"] == se_item_id:
                        se_item = it
        assert se_item is not None
        rounds = se_item.get("rounds", [])
        assert len(rounds) == 2, (
            f"4-team SE should have 2 rounds (semis + final), got {len(rounds)}"
        )
        # Sort rounds by id to ensure correct ordering (semis before final).
        rounds.sort(key=lambda r: r["id"])
        # Round 1 = semifinals (2 matches), Round 2 = final (1 match).
        semi_round = rounds[0]
        final_round = rounds[1]
        assert len(semi_round["matches"]) == 2, (
            f"expected 2 semifinal matches, got {len(semi_round['matches'])}"
        )
        assert len(final_round["matches"]) == 1, (
            f"expected 1 final match, got {len(final_round['matches'])}"
        )

        # Build a lookup from stage_item_input_id to team_id.
        input_to_team = {}
        for inp in se_item.get("inputs", []):
            input_to_team[inp["id"]] = inp.get("team_id")

        # Score both semifinals. We score each semi so that input1 wins
        # (2:0). Then the final should contain the two input1 winners.
        semi1 = semi_round["matches"][0]
        semi2 = semi_round["matches"][1]
        api_update_match_score(tid, semi1["id"], semi1["round_id"], [[11, 7], [11, 5]], best_of=3)
        api_update_match_score(tid, semi2["id"], semi2["round_id"], [[11, 7], [11, 5]], best_of=3)

        # Reload and assert: the final match's two inputs now reference
        # the two semifinal winners' team_ids (not None).
        stages = api_get_stages(tid)
        se_item = None
        for s in stages:
            if s["id"] == stage_id:
                for it in s.get("stage_items", []):
                    if it["id"] == se_item_id:
                        se_item = it
        assert se_item is not None
        reloaded_rounds = sorted(se_item["rounds"], key=lambda r: r["id"])
        assert len(reloaded_rounds) == 2
        # The final is the round with 1 match (the last round by id).
        final_round = reloaded_rounds[-1]
        assert len(final_round["matches"]) == 1
        final_match = final_round["matches"][0]
        fin_in1 = (final_match.get("stage_item_input1") or {}).get("team_id")
        fin_in2 = (final_match.get("stage_item_input2") or {}).get("team_id")

        # semi1 input1 won, semi2 input1 won.
        semi1_winner = input_to_team.get(semi1.get("stage_item_input1_id"))
        semi2_winner = input_to_team.get(semi2.get("stage_item_input1_id"))
        expected_winners = {semi1_winner, semi2_winner}
        actual_final_teams = {fin_in1, fin_in2}
        assert actual_final_teams == expected_winners, (
            f"final match inputs should be the two semifinal winners "
            f"({expected_winners}), got {actual_final_teams}; "
            f"fin_in1={fin_in1}, fin_in2={fin_in2}"
        )
        assert fin_in1 is not None, "final input1 team_id must not be None after semis scored"
        assert fin_in2 is not None, "final input2 team_id must not be None after semis scored"
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass