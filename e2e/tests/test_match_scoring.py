"""Match play & scoring tests (H1-H11).

The match-scoring modal was rewritten: it no longer has a best-of selector or
per-game +/- steppers. Score entry is a SINGLE TAP on a result button labelled
'<winner_games>:<loser_games>' (winner games in {2,3,4}, both orientations).
A single click SAVES immediately (games=null, so 小分 is 0 for everyone) and
CLOSES the modal. Per-side '<队名> 弃权' (forfeit) buttons and a '清除比分'
(clear) button are also present.

The results page (now titled '录入分数和结果') has TWO tabs:
  - '录入分数和结果': RR renders a GroupGrid cross-table whose cells open the fill
    modal; SE renders a clickable EliminationBracket.
  - '排名': standings.
There are no more match cards; the GroupGrid cells are the click targets.
"""
from __future__ import annotations

import uuid

from playwright.sync_api import Page, expect

from ._helpers import (
    BASE_URL,
    _api_headers,
    api_create_court,
    api_create_round_robin,
    api_create_single_elimination_from_sources,
    api_create_stage,
    api_create_team,
    api_create_tournament,
    api_delete_tournament,
    api_get_stages,
    api_get_teams,
    api_schedule_matches,
    set_match_result,
    forfeit_match,
    clear_match_score,
)


def _setup_fresh_rr(shared_club_id: int, prefix: str):
    """Create a fresh tournament with a scheduled RR so the results page
    renders a GroupGrid with clickable cells. Returns (tid, team_prefix, stage_id).
    Caller is responsible for api_delete_tournament."""
    tname = f"E2E-{prefix}-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    team_prefix = f"E2E-{prefix}Team-"
    for i in range(4):
        api_create_team(tid, f"{team_prefix}{i}-{uuid.uuid4().hex[:4]}")
    stage_id = api_create_stage(tid, f"E2E-{prefix}St-{uuid.uuid4().hex[:6]}")
    api_create_round_robin(tid, stage_id, team_count=4, group_count=1)
    api_create_court(tid, f"E2E-{prefix}Ct-{uuid.uuid4().hex[:4]}")
    api_create_court(tid, f"E2E-{prefix}Ct-{uuid.uuid4().hex[:4]}")
    api_schedule_matches(tid)
    return tid, team_prefix, stage_id


def _goto_results(page: Page, tid: int) -> None:
    page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
    page.wait_for_selector('[role="tab"]', timeout=15_000)


def _open_first_cell_modal(page: Page, team_prefix: str):
    """On the results page, click the first unscored GroupGrid cell and wait
    for the 录入分数 modal. Returns the modal locator."""
    # The GroupGrid renders a <table> with <button> cells. An unscored cell
    # shows '—' (em dash). Click the first such button.
    cell = page.locator("button", has_text="—").first
    expect(cell).to_be_visible(timeout=15_000)
    cell.click()
    modal = page.locator(".mantine-Modal-content").last
    expect(modal).to_be_visible(timeout=10_000)
    expect(page.locator("body")).to_contain_text("录入分数", timeout=5_000)
    return modal


def _open_cell_modal_for_teams(page: Page, team_name: str):
    """Open the modal by clicking the GroupGrid cell on the row whose row-label
    contains `team_name`. This scopes the click to a specific pairing's cell
    so the API ground-truth can be unambiguously correlated."""
    # The GroupGrid row label starts with "N. <team_name>". Find the row, then
    # click the first '—' button inside it.
    row = page.locator("tr", has_text=team_name).first
    expect(row).to_be_visible(timeout=15_000)
    cell = row.locator("button", has_text="—").first
    expect(cell).to_be_visible(timeout=10_000)
    cell.click()
    modal = page.locator(".mantine-Modal-content").last
    expect(modal).to_be_visible(timeout=10_000)
    expect(page.locator("body")).to_contain_text("录入分数", timeout=5_000)
    return modal


# ---- H1: open the match edit modal -----------------------------------------


def test_open_match_modal(page: Page, shared_club_id: int) -> None:
    """H1: clicking a GroupGrid cell on the results page opens the 填入分数 modal.

    Beyond opening the modal, this also asserts the modal is not an empty
    shell: at least one result button (e.g. '2:0') is visible, AND the
    '清除比分' button is ABSENT on a fresh (unscored) match — it should only
    appear when the match has a recorded result.
    """
    tid, team_prefix, _ = _setup_fresh_rr(shared_club_id, "MatchH1")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)
        # The modal is not an empty shell — at least one result button is
        # visible.
        expect(modal.get_by_role("button", name="2:0", exact=True)).to_be_visible(timeout=5_000)
        # The '清除比分' button must NOT render on an unscored match.
        assert modal.get_by_role("button", name="清除比分", exact=True).count() == 0, (
            "清除比分 button should be absent on a fresh (unscored) match"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H2: enter a result and save --------------------------------------------


def test_enter_scores_and_save(page: Page, shared_club_id: int) -> None:
    """H2: clicking a result button (e.g. '2:0') saves immediately, closes the
    modal, and persists stage_item_input1_score=2 / input2_score=0 with
    games=null (no per-game points recorded).
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH2")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)
        # Click the '2:0' result button — saves and closes immediately.
        set_match_result(modal, 2, 0)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground-truth: exactly one match in this stage has
        # input1_score=2, input2_score=0, and games is null/empty.
        scored = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") == 2
                            and m.get("stage_item_input2_score") == 0
                        ):
                            scored.append(m)
        assert len(scored) == 1, (
            f"expected exactly one match with 2:0 after save, got {len(scored)}"
        )
        assert not scored[0].get("games"), (
            f"games must be null/empty (no per-game points), got {scored[0].get('games')!r}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H2b: a 3-game result button (3:2) saves and persists --------------------


def test_three_game_result_button_saves(page: Page, shared_club_id: int) -> None:
    """H2b: clicking a best-of-5 result button (e.g. '3:2') saves immediately,
    closes the modal, and persists input1_score=3 / input2_score=2 with
    games=null.

    H2/H11 only exercise the 2:0 / 0:2 (2-game) save path. A regression where
    the 3-game or 4-game buttons rendered but the save handler or backend
    rejected/miscalculated them would pass every existing test.
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH2b")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)
        set_match_result(modal, 3, 2)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        scored = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") == 3
                            and m.get("stage_item_input2_score") == 2
                        ):
                            scored.append(m)
        assert len(scored) == 1, (
            f"expected exactly one match with 3:2 after save, got {len(scored)}"
        )
        assert not scored[0].get("games"), (
            f"games must be null/empty (no per-game points), got {scored[0].get('games')!r}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass

# ---- H3: edit an existing score ---------------------------------------------


def test_edit_existing_score(page: Page, shared_club_id: int) -> None:
    """H3: re-opening a scored match's cell shows the previously saved result
    button highlighted, and the user can change the result."""
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH3")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)
        set_match_result(modal, 2, 0)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # Re-open: the cell now shows '2:0' text. Click it to re-open the modal.
        cell = page.locator("button", has_text="2:0").first
        expect(cell).to_be_visible(timeout=10_000)
        cell.click()
        modal = page.locator(".mantine-Modal-content").last
        expect(modal).to_be_visible(timeout=10_000)
        # The '2:0' result button should now be selected (green/filled variant).
        # We assert the button text is present in the modal.
        expect(modal.get_by_role("button", name="2:0", exact=True)).to_be_visible(
            timeout=5_000
        )

        # Change the result to '0:2' (the other side wins).
        set_match_result(modal, 0, 2)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground-truth: exactly one match now has 0:2 (input1=0, input2=2).
        scored = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") == 0
                            and m.get("stage_item_input2_score") == 2
                        ):
                            scored.append(m)
        assert len(scored) == 1, (
            f"expected exactly one match with 0:2 after edit, got {len(scored)}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H4: result reflected in the GroupGrid cell -----------------------------


def test_match_result_reflected(page: Page, shared_club_id: int) -> None:
    """H4: after saving, the GroupGrid cell text updates to show the result
    (e.g. '2:0') instead of the '—' placeholder."""
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH4")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)
        set_match_result(modal, 2, 0)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # The GroupGrid cell now renders '2:0' (green text for the winner).
        cell = page.locator("button", has_text="2:0").first
        expect(cell).to_be_visible(timeout=10_000)

        # API confirms the 2:0 result.
        scored = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") == 2
                            and m.get("stage_item_input2_score") == 0
                        ):
                            scored.append(m)
        assert len(scored) == 1, (
            f"expected exactly one match with 2:0, got {len(scored)}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H5: all result button labels render ------------------------------------


def test_all_result_buttons_render(page: Page, shared_club_id: int) -> None:
    """H5: the modal renders ALL expected result-button labels in both
    orientations (team1 wins / team2 wins).

    WINNER_GAMES = [2, 3, 4]. For winner_games=w, loser_games ranges 0..w-1.
    Both orientations appear: '<w>:<l>' (team1 wins) and '<l>:<w>' (team2 wins).
    So the full set of labels is:
      2:0, 2:1, 0:2, 1:2,
      3:0, 3:1, 3:2, 0:3, 1:3, 2:3,
      4:0, 4:1, 4:2, 0:4, 1:4, 2:4
    Each label appears exactly once. A regression that dropped a button or
    mislabeled one surfaces here.
    """
    tid, team_prefix, _ = _setup_fresh_rr(shared_club_id, "MatchH5")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)

        expected_labels = set()
        for w in (2, 3, 4):
            for l in range(w):
                expected_labels.add(f"{w}:{l}")
                expected_labels.add(f"{l}:{w}")

        for label in sorted(expected_labels):
            btn = modal.get_by_role("button", name=label, exact=True)
            assert btn.count() == 1, (
                f"expected exactly one button labelled {label!r}, got {btn.count()}"
            )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H6: forfeit a match via the UI -----------------------------------------


def test_forfeit_match_via_ui(page: Page, shared_club_id: int) -> None:
    """H6: clicking a per-side '<队名> 弃权' button marks that side as
    forfeiting; the modal saves and closes, and the API persists
    forfeit_input, zeroes both scores, and games is null/empty.
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "ForfH6")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)

        # The modal shows two forfeit buttons: '<team1Name> 弃权' and
        # '<team2Name> 弃权'. Click the first one we find.
        forfeit_btns = modal.get_by_role("button", name="弃权")
        assert forfeit_btns.count() == 2, (
            f"expected exactly 2 forfeit buttons, got {forfeit_btns.count()}"
        )
        forfeit_btns.first.click()
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground-truth: exactly one match has forfeit_input set.
        forfeited = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if m.get("forfeit_input") is not None:
                            forfeited.append(m)
        assert len(forfeited) == 1, (
            f"expected exactly one forfeited match, got {len(forfeited)}"
        )
        fm = forfeited[0]
        assert fm["forfeit_input"] in (1, 2), (
            f"forfeit_input must be 1 or 2, got {fm['forfeit_input']!r}"
        )
        assert fm.get("stage_item_input1_score") == 0
        assert fm.get("stage_item_input2_score") == 0
        assert not fm.get("games"), (
            f"forfeit must drop per-game scores, got {fm.get('games')!r}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H7: 清除比分 (clear score) button resets to 0:0 ------------------------


def test_clear_score_button(page: Page, shared_club_id: int) -> None:
    """H7: after a match has been scored, the modal shows a '清除比分' button;
    clicking it resets the match to 0:0 with no forfeit and closes the modal.
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH7")
    try:
        _goto_results(page, tid)
        # First score the match 2:0.
        modal = _open_first_cell_modal(page, team_prefix)
        set_match_result(modal, 2, 0)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # Re-open the same cell (now shows '2:0') and clear.
        cell = page.locator("button", has_text="2:0").first
        expect(cell).to_be_visible(timeout=10_000)
        cell.click()
        modal = page.locator(".mantine-Modal-content").last
        expect(modal).to_be_visible(timeout=10_000)

        # The '清除比分' button should be present (only shows when hasScore).
        clear_btn = modal.get_by_role("button", name="清除比分", exact=True)
        expect(clear_btn).to_be_visible(timeout=5_000)
        clear_match_score(modal)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API: the match should now have 0:0 scores and no games.
        cleared = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") in (0, None)
                            and m.get("stage_item_input2_score") in (0, None)
                            and not m.get("games")
                            and m.get("forfeit_input") is None
                        ):
                            cleared.append(m)
        # There should be at least one 0:0 match (the one we cleared plus any
        # unscored ones); we just need to confirm the clear worked, i.e. the
        # 2:0 result is GONE.
        scored_2_0 = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if m.get("stage_item_input1_score") == 2:
                            scored_2_0.append(m)
        assert len(scored_2_0) == 0, (
            f"the 2:0 result must be cleared, but found {len(scored_2_0)} matches "
            f"with input1_score=2"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H8: 录入分数和结果 page title + two-tab structure --------------------------


def test_results_page_title_and_tabs(page: Page, shared_club_id: int) -> None:
    """H8: the results page has exactly THREE tabs: '录入分数和结果' (results),
    '排名' (standings) and '参赛人员' (participants). There is no big page
    title any more (the tournament name lives in the header breadcrumb), and
    the old '对阵图' tab and the match-card-based 'matches' tab are gone."""
    tid, team_prefix, _ = _setup_fresh_rr(shared_club_id, "MatchH8")
    try:
        _goto_results(page, tid)
        # No standalone page heading — the tabs render directly.
        expect(page.get_by_role("heading", name="录入分数和结果")).to_have_count(0)
        # Three tabs render.
        tabs = page.get_by_role("tab")
        expect(tabs).to_have_count(3, timeout=10_000)
        tab_labels = [tabs.nth(i).inner_text().strip() for i in range(3)]
        assert "录入分数和结果" in tab_labels, (
            f"expected '录入分数和结果' tab, got {tab_labels}"
        )
        assert "排名" in tab_labels, (
            f"expected '排名' tab, got {tab_labels}"
        )
        assert "参赛人员" in tab_labels, (
            f"expected '参赛人员' tab, got {tab_labels}"
        )
        # The old '对阵图' tab must NOT exist.
        assert "对阵图" not in tab_labels, (
            f"the '对阵图' tab was removed; got {tab_labels}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H9: settled tournament freezes scores (error notification) --------------


def test_settled_tournament_freezes_scores(page: Page, shared_club_id: int) -> None:
    """H9: on a SETTLED tournament (settled_seq is set), clicking a GroupGrid
    cell does NOT open the fill modal; instead an error notification renders
    (scores are frozen). The backend returns 400 on any match update once
    settled_seq is set.
    """
    from ._helpers import _api_headers
    import requests

    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH9")
    try:
        # Score one match via the API so the stage has at least one result.
        match_id = round_id = None
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        match_id = m["id"]
                        round_id = rd["id"]
                        break
        assert match_id is not None
        # Settle: set settled_seq directly via psql (this is a non-rated
        # tournament so the /settle endpoint isn't available; the freeze
        # check is on settled_seq regardless of rating).
        from ._helpers import BASE_URL as _BU
        # Use the API to set the score first (so we have a "real" match).
        body = {
            "id": match_id,
            "round_id": round_id,
            "games": None,
            "best_of": 3,
            "stage_item_input1_score": 2,
            "stage_item_input2_score": 0,
            "forfeit_input": None,
            "court_id": None,
            "custom_duration_minutes": None,
            "custom_margin_minutes": None,
        }
        requests.put(
            f"{_BU}/api/tournaments/{tid}/matches/{match_id}",
            headers=_api_headers(), json=body, timeout=15,
        ).raise_for_status()

        # Set settled_seq directly via psql.
        from .test_rating import _psql
        _psql(f"UPDATE tournaments SET settled_seq = 1 WHERE id = {tid};")

        _goto_results(page, tid)
        # The page should not show the "tap cell to score" hint (canRecord may
        # still be true for the owner, but isFrozen prevents the modal).
        # Click the first '—' cell.
        cell = page.locator("button", has_text="—").first
        expect(cell).to_be_visible(timeout=15_000)
        cell.click()
        # The modal must NOT open; instead an error notification renders.
        page.wait_for_timeout(1500)
        expect(page.locator(".mantine-Modal-content")).to_have_count(0, timeout=5_000)
        # A Mantine notification should appear (error color).
        expect(page.locator(".mantine-Notification-root")).to_be_visible(timeout=10_000)

        # Backend ground-truth: PUT /matches now returns 400 frozen.
        r = requests.put(
            f"{_BU}/api/tournaments/{tid}/matches/{match_id}",
            headers=_api_headers(), json=body, timeout=15,
        )
        assert r.status_code == 400, (
            f"post-settlement PUT /matches must 400, got {r.status_code}: {r.text[:200]}"
        )
        assert "frozen" in r.text.lower() or "settled" in r.text.lower(), (
            f"rejection must mention settled/frozen, got {r.text}"
        )
    finally:
        # Unset settled_seq so the tournament can be deleted.
        try:
            from .test_rating import _psql
            _psql(f"UPDATE tournaments SET settled_seq = NULL WHERE id = {tid};")
        except Exception:
            pass
        try:
            api_delete_tournament(tid)
        except Exception:
            pass

# ---- H9b: SETTLED *rated* tournament freezes scores on /results UI ---------
# Complements M15b (the API-side freeze contract on a rated tournament, in
# test_permissions.py) with the UI-side surfacing: on a SETTLED rated
# tournament, clicking an unscored GroupGrid cell on /results must NOT open
# the fill modal; instead an error notification renders. A regression that
# only gated the non-rated path (H9) would pass H9 but surface here.


def test_settled_rated_tournament_results_shows_error_notification(
    page: Page, shared_club_id: int
) -> None:
    """H9b: on a SETTLED *rated* tournament, clicking a GroupGrid cell on
    /results does NOT open the fill modal; instead an error notification
    renders. Backend ground-truth: PUT /matches returns 400 mentioning
    'settled'/'frozen' on the same tournament.

    M15b covers the API rejection + /settings button removal for the rated
    path; this test covers the UI surfacing of that same 400 on /results.
    H9 covers the same UI surfacing for a *non-rated* settled tournament.
    The two together lock the freeze UI for both tournament kinds.
    """
    import time

    import requests

    from ._helpers import BASE_URL as _BU
    from ._helpers import _api_headers as _ah
    from .test_rating import _apply_to_join, _psql, _register_account

    # Create a dedicated rated individual tournament.
    tname = f"E2E-MatchH9b-{uuid.uuid4().hex[:6]}"
    auth = _ah()
    r = requests.post(
        f"{_BU}/api/tournaments",
        headers=auth,
        json={
            "name": tname,
            "club_id": shared_club_id,
            "dashboard_public": True,
            "dashboard_endpoint": "",
            "players_can_be_in_multiple_teams": False,
            "auto_assign_courts": True,
            "start_time": "2030-01-01T00:00:00Z",
            "duration_minutes": 10,
            "margin_minutes": 5,
            "is_individual": True,
            "rating_category_id": 1,
        },
        timeout=15,
    )
    r.raise_for_status()
    r2 = requests.get(
        f"{_BU}/api/tournaments?filter_=ALL", headers=auth, timeout=15
    )
    r2.raise_for_status()
    tid = next(t["id"] for t in r2.json()["data"] if t["name"] == tname)

    try:
        # Individual RATED tournaments reject free-text team creation
        # (see M12). Have 4 fresh applicants instant-join; each gets a
        # bound team auto-created.
        applicants = [_register_account(f"h9b{i}") for i in range(4)]
        for app in applicants:
            _apply_to_join(tid, app["token"])

        # Wait for the 4 bound teams to materialise.
        teams: list = []
        for _ in range(20):
            teams = requests.get(
                f"{_BU}/api/tournaments/{tid}/teams",
                headers=auth, timeout=15,
            ).json()["data"]["teams"]
            if len(teams) >= 4:
                break
            time.sleep(0.5)
        assert len(teams) >= 4, (
            f"expected 4 bound teams after 4 instant-joins, got {len(teams)}"
        )

        # A rated individual tournament refuses to build a stage item until
        # every player has an initial/formal rating configured. Seed all 4
        # as ACTIVE via psql so the round_robin_groups endpoint accepts the
        # request. (The seed-approval UI is exercised by M15; this test is
        # about the post-settlement UI surfacing, not the seed flow.)
        for app in applicants:
            _psql(
                "INSERT INTO player_ratings (category_id, user_id, initial_rating, "
                "current_rating, matches_played, status) "
                f"VALUES (1, {app['uid']}, 1500, 1500, 0, 'ACTIVE') "
                "ON CONFLICT (category_id, user_id) DO UPDATE "
                "SET initial_rating=1500, current_rating=1500, matches_played=0, status='ACTIVE';"
            )

        stage_id = api_create_stage(
            tid, f"E2E-MatchH9bSt-{uuid.uuid4().hex[:6]}"
        )
        api_create_round_robin(tid, stage_id, team_count=4, group_count=1)
        api_schedule_matches(tid)

        # Score ONE match so we have a real `stage_item_input1_score`/`...2`
        # record. We then set settled_seq directly via psql — the H9 path —
        # because the full /settle pre-conditions (4 ACTIVE seeds + every
        # match scored) are out of scope for this UI-surface test. The freeze
        # check is on `settled_seq` regardless of how it got set.
        match_id = round_id = None
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        match_id = m["id"]
                        round_id = rd["id"]
                        break
        assert match_id is not None
        body = {
            "id": match_id,
            "round_id": round_id,
            "games": None,
            "best_of": 3,
            "stage_item_input1_score": 2,
            "stage_item_input2_score": 0,
            "forfeit_input": None,
            "court_id": None,
            "custom_duration_minutes": None,
            "custom_margin_minutes": None,
        }
        requests.put(
            f"{_BU}/api/tournaments/{tid}/matches/{match_id}",
            headers=auth, json=body, timeout=15,
        ).raise_for_status()

        # Set settled_seq directly via psql to simulate the settled state.
        _psql(f"UPDATE tournaments SET settled_seq = 1 WHERE id = {tid};")

        _goto_results(page, tid)
        # Click the first unscored ('—') cell.
        cell = page.locator("button", has_text="—").first
        expect(cell).to_be_visible(timeout=15_000)
        cell.click()
        # Modal must NOT open.
        page.wait_for_timeout(1500)
        expect(page.locator(".mantine-Modal-content")).to_have_count(
            0, timeout=5_000
        )
        # A Mantine error notification must render.
        expect(page.locator(".mantine-Notification-root")).to_be_visible(
            timeout=10_000
        )

        # Backend ground-truth: PUT /matches is still 400 frozen on the
        # RATED path (re-proves M15b's contract via this UI flow).
        r = requests.put(
            f"{_BU}/api/tournaments/{tid}/matches/{match_id}",
            headers=auth, json=body, timeout=15,
        )
        assert r.status_code == 400, (
            f"post-settlement PUT /matches must 400, got {r.status_code}: "
            f"{r.text[:200]}"
        )
        assert "frozen" in r.text.lower() or "settled" in r.text.lower(), (
            f"rejection must mention settled/frozen, got {r.text}"
        )
    finally:
        # Unset settled_seq so the tournament can be deleted (DELETE
        # /tournaments/{id} refuses a settled row).
        try:
            _psql(f"UPDATE tournaments SET settled_seq = NULL WHERE id = {tid};")
        except Exception:
            pass
        try:
            api_delete_tournament(tid)
        except Exception:
            pass
# ---- H10: GroupGrid read-only for non-recorders -----------------------------


def test_groupgrid_read_only_for_non_recorder(
    anon_page: Page, shared_club_id: int
) -> None:
    """H10: an anonymous viewer sees the GroupGrid as read-only text — cells
    are NOT clickable buttons. Clicking a cell does not open the edit modal.
    """
    tid, team_prefix, _ = _setup_fresh_rr(shared_club_id, "MatchH10")
    try:
        # An anonymous viewer sees the results page read-only: GroupGrid cells
        # are plain text, not buttons.
        anon_page.goto(
            f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded"
        )
        anon_page.wait_for_selector('[role="tab"]', timeout=15_000)
        # Wait for the GroupGrid table to render.
        expect(anon_page.locator("table").first).to_be_visible(timeout=15_000)
        # No cell buttons exist (read-only mode renders plain Text, not
        # UnstyledButton).
        assert anon_page.locator("button", has_text="—").count() == 0, (
            "anon viewer should see read-only GroupGrid (no clickable cell buttons)"
        )
        # The '—' text IS present (as plain text, not in a button).
        expect(anon_page.locator("body")).to_contain_text("—", timeout=10_000)
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H11: both result-button orientations produce correct scores -------------


def test_result_button_orientations(page: Page, shared_club_id: int) -> None:
    """H11: the two sections ('<team1> 获胜' and '<team1> 负') produce opposite
    score orientations. Clicking '3:1' in the 'wins' section gives input1=3,
    input2=1; clicking '1:3' in the 'loses' section gives input1=1, input2=3.

    We test the 'loses' orientation (input1 < input2) here since H2 already
    covers the 'wins' orientation (2:0). A regression that mixed up the two
    sections would pass H2 but fail here.
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH11")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)
        # Click '0:2' — team2 sweeps. This is in the 'loses' section.
        set_match_result(modal, 0, 2)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API: input1=0, input2=2 (team2 wins 2:0).
        scored = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") == 0
                            and m.get("stage_item_input2_score") == 2
                        ):
                            scored.append(m)
        assert len(scored) == 1, (
            f"expected exactly one match with 0:2 (team2 wins), got {len(scored)}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H12: standings after a one-tap UI result-button score -------------------
# The actual production scoring path (one-tap result button) writes games=null,
# so 局分=2:0 and 小分=0:0. The existing standings tests (I4/I4b/I7) all score
# via the API helper with games=[[11,7]] → 局分=1:0, 小分=11:7. A regression that
# broke standings computation specifically for games=null matches would pass
# those but fail here.


def test_standings_after_one_tap_ui_score(page: Page, shared_club_id: int) -> None:
    """H12: scoring via the one-tap UI result button produces standings where
    the winner's 局分 (games won) cell shows '2:0' (NOT '1:0') and 小分 (points
    sum) shows '0:0' (NOT '11:7'). This locks the standings contract for the
    real production scoring model (games=null), which no existing standings
    test exercises.
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH12")
    try:
        _goto_results(page, tid)
        # Score the first match via the one-tap UI button (2:0 → games=null).
        modal = _open_first_cell_modal(page, team_prefix)
        set_match_result(modal, 2, 0)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # Ground-truth: the match has games=null and 2:0 scores.
        scored = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") == 2
                            and m.get("stage_item_input2_score") == 0
                        ):
                            scored.append(m)
        assert len(scored) == 1
        assert not scored[0].get("games"), (
            f"one-tap score must have games=null, got {scored[0].get('games')!r}"
        )

        # Reload and open the 排名 (standings) tab.
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        page.get_by_role("tab", name="排名").first.click()
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_contain_text(team_prefix, timeout=15_000)

        standings_text = panel.inner_text()
        # The winner's 局分 (games-score) cell must show '2:0', NOT '1:0'.
        # '2:0' is the one-tap UI model (winner_games=2). '1:0' would be the
        # API-helper model (games=[[11,7]] → 1 game won). A regression that
        # computed 局分 from games.length instead of stage_item_input*_score
        # would show '1:0'.
        assert "2:0" in standings_text, (
            f"standings must show '2:0' (games won) for the one-tap UI score; "
            f"got: {standings_text[:400]}"
        )
        assert "1:0" not in standings_text, (
            f"standings must NOT show '1:0' (that's the games=[[11,7]] model, "
            f"not the one-tap games=null model); got: {standings_text[:400]}"
        )
        # The 小分 (points sum) must show '0:0', NOT '11:7'. When games=null,
        # computeScoreTotals iterates an empty array → pw=0, pl=0. A regression
        # that computed 小分 from stage_item_input*_score instead of games
        # would show '2:0' as 小分 too — but '11:7' (the API-helper model) must
        # never appear.
        assert "11:7" not in standings_text, (
            f"standings must NOT show '11:7' (points sum) for the one-tap UI "
            f"score (games=null → 小分=0:0); got: {standings_text[:400]}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H13: SE bracket click → modal → save on /results -----------------------
# The 录入分数和结果 page renders SE stage items as a clickable EliminationBracket
# cells; no test clicks an SE bracket match. This test advances an RR→SE so the
# SE inputs resolve to concrete teams, clicks a bracket match, saves, and asserts
# the score persists.


def test_se_bracket_click_opens_modal_and_saves(page: Page, shared_club_id: int) -> None:
    """H13: clicking an SE bracket match element on /results opens the fill
    modal, and a result-button click saves the score. The click target is the
    UnstyledButton inside the bracket match card — structurally distinct from
    the RR GroupGrid '—' cell button. A regression where the SE bracket's
    onClick stopped opening the modal, or the save silently failed for SE
    matches, would pass I2/I5 (which only assert the bracket renders) but
    fail here.
    """
    import requests

    tname = f"E2E-SEClick-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        # 4 teams + stage 1 (RR) + stage 2 (SE from RR source).
        team_ids: list[int] = []
        team_names: list[str] = []
        for i in range(4):
            nm = f"E2E-SEClickT-{i}-{uuid.uuid4().hex[:4]}"
            team_ids.append(api_create_team(tid, nm))
            team_names.append(nm)
        s1 = api_create_stage(tid, f"E2E-SEClickS1-{uuid.uuid4().hex[:6]}")
        rr_item_id = api_create_round_robin(tid, s1, team_count=4, group_count=1)
        s2 = api_create_stage(tid, f"E2E-SEClickS2-{uuid.uuid4().hex[:6]}")
        se_item_id = api_create_single_elimination_from_sources(
            tid, s2, sources=[{"stage_item_id": rr_item_id, "positions": 4}], take="top"
        )

        # Score ALL 6 RR matches so the ranking is complete (the advance
        # endpoint refuses incomplete rankings). Make team[0] win all 3.
        from ._helpers import api_update_match_score
        champion = team_ids[0]
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
        assert len(rr_matches) == 6
        for mid, rid, in1, in2 in rr_matches:
            if in1 == champion:
                games = [[11, 7]]
            elif in2 == champion:
                games = [[7, 11]]
            else:
                games = [[11, 7]]
            api_update_match_score(tid, mid, rid, games, best_of=1)

        # Pre-activate stage 1, then advance to stage 2 (resolves SE inputs).
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
            headers=_api_headers(), json={"direction": "next"}, timeout=15,
        ).raise_for_status()
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
            headers=_api_headers(), json={"direction": "next"}, timeout=15,
        ).raise_for_status()

        # Verify SE inputs resolved to concrete teams (not Tentative).
        se_item = None
        for s in api_get_stages(tid):
            if s["id"] == s2:
                for it in s.get("stage_items", []):
                    if it["id"] == se_item_id:
                        se_item = it
        assert se_item is not None
        se_inputs = [i for i in se_item.get("inputs", []) if i.get("team_id") is not None]
        assert len(se_inputs) >= 2, (
            f"expected SE inputs to resolve to teams after advance, "
            f"got {len(se_inputs)} resolved"
        )

        # Navigate to /results. The SE bracket renders UnstyledButtons.
        _goto_results(page, tid)
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_be_visible(timeout=10_000)
        # The SE bracket must render (not the RR GroupGrid table).
        # An SE stage item with resolved inputs renders team names in the
        # bracket match cards. Click the first bracket match button.
        # The UnstyledButton wraps the match card; it's a <button> element
        # containing team names (or 空槽位 placeholders if unresolved).
        # We click the first one that contains a resolved team name.
        clicked_team = None
        for nm in team_names:
            btn = panel.locator("button", has_text=nm).first
            if btn.count() > 0 and btn.is_visible():
                clicked_team = nm
                btn.click()
                break
        assert clicked_team is not None, (
            "expected to find a clickable SE bracket match with a resolved team name"
        )

        # The modal must open.
        modal = page.locator(".mantine-Modal-content").last
        expect(modal).to_be_visible(timeout=10_000)
        expect(page.locator("body")).to_contain_text("录入分数", timeout=5_000)

        # Click a result button (2:0) — saves and closes.
        set_match_result(modal, 2, 0)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground-truth: exactly one SE match now has a 2:0 score.
        scored = []
        for s in api_get_stages(tid):
            if s["id"] != s2:
                continue
            for item in s.get("stage_items", []):
                if item["id"] != se_item_id:
                    continue
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") == 2
                            and m.get("stage_item_input2_score") == 0
                        ):
                            scored.append(m)
        assert len(scored) == 1, (
            f"expected exactly one SE match with 2:0 after bracket save, "
            f"got {len(scored)}"
        )
        assert not scored[0].get("games"), (
            f"one-tap save must have games=null, got {scored[0].get('games')!r}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H9c: SETTLED tournament freezes scores on an SE bracket ---------------

# ---- H9c: SETTLED tournament freezes scores on an SE bracket ---------------
# The critic found that H9/H9b only exercise the freeze on an RR GroupGrid cell,
# where openMatchModal fires showNotification. The SE bracket takes a different
# path: results.tsx passes readOnly={!canRecord || isFrozen} to EliminationBracket,
# and Match renders a plain <div> (no onClick) when readOnly. So on a SETTLED
# tournament with an SE stage, clicking a bracket match silently did nothing —
# no modal (correct) BUT no error notification either, unlike the RR cell.
# After the fix (match.tsx + brackets.tsx forward onClickFrozen, results.tsx
# wires it when isFrozen), the SE path now shows the same frozen notification as
# RR, making the two consistent. This test pins that consistency.


def test_settled_tournament_freezes_se_bracket(
    page: Page, shared_club_id: int
) -> None:
    """H9c: on a SETTLED tournament whose active stage is a single-elimination
    bracket, clicking an SE bracket match on /results does NOT open the fill
    modal AND renders the same 'scores frozen' error notification as the RR
    GroupGrid cell path (H9).

    A regression that re-enabled the UnstyledButton onClick (and thus opened a
    fill modal whose save would 400) on a settled SE bracket surfaces here, as
    does a regression that dropped the onClickFrozen wiring (silent read-only
    div, no notification — the RR-vs-SE inconsistency the critic found).
    """
    import requests

    from ._helpers import api_update_match_score

    tname = f"E2E-SEFreeze-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        # 4 teams + stage 1 (RR) + stage 2 (SE from RR source).
        team_names: list[str] = []
        for i in range(4):
            nm = f"E2E-SEFreezeT-{i}-{uuid.uuid4().hex[:4]}"
            api_create_team(tid, nm)
            team_names.append(nm)
        s1 = api_create_stage(tid, f"E2E-SEFreezeS1-{uuid.uuid4().hex[:6]}")
        rr_item_id = api_create_round_robin(tid, s1, team_count=4, group_count=1)
        s2 = api_create_stage(tid, f"E2E-SEFreezeS2-{uuid.uuid4().hex[:6]}")
        se_item_id = api_create_single_elimination_from_sources(
            tid, s2, sources=[{"stage_item_id": rr_item_id, "positions": 4}], take="top"
        )

        # Score ALL 6 RR matches so the ranking is complete (advance refuses
        # incomplete rankings). Make team[0] win all 3 of its matches.
        champion_idx = 0
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
        assert len(rr_matches) == 6
        # Resolve champion team id from the API teams list (names are unique).
        teams = api_get_teams(tid)
        champion_tid = None
        for tm in teams:
            if tm["name"] == team_names[champion_idx]:
                champion_tid = tm["id"]
                break
        assert champion_tid is not None
        for mid, rid, in1, in2 in rr_matches:
            if in1 == champion_tid:
                games = [[11, 7]]
            elif in2 == champion_tid:
                games = [[7, 11]]
            else:
                games = [[11, 7]]
            api_update_match_score(tid, mid, rid, games, best_of=1)

        # Pre-activate stage 1, then advance to stage 2 (resolves SE inputs).
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
            headers=_api_headers(), json={"direction": "next"}, timeout=15,
        ).raise_for_status()
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
            headers=_api_headers(), json={"direction": "next"}, timeout=15,
        ).raise_for_status()

        # Verify SE inputs resolved to concrete teams.
        se_item = None
        for s in api_get_stages(tid):
            if s["id"] == s2:
                for it in s.get("stage_items", []):
                    if it["id"] == se_item_id:
                        se_item = it
        assert se_item is not None
        se_inputs = [i for i in se_item.get("inputs", []) if i.get("team_id") is not None]
        assert len(se_inputs) >= 2, (
            f"expected SE inputs to resolve to teams after advance, got {len(se_inputs)}"
        )

        # Set settled_seq directly via psql to simulate the settled state.
        from .test_rating import _psql
        _psql(f"UPDATE tournaments SET settled_seq = 1 WHERE id = {tid};")

        _goto_results(page, tid)
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_be_visible(timeout=10_000)

        # Click the first SE bracket match that contains a resolved team name.
        # On a settled tournament, readOnly is true and onClickFrozen is wired, so
        # the card is still an UnstyledButton — but its onClick shows the frozen
        # notification, NOT the fill modal.
        clicked_team = None
        for nm in team_names:
            btn = panel.locator("button", has_text=nm).first
            if btn.count() > 0 and btn.is_visible():
                clicked_team = nm
                btn.click()
                break
        assert clicked_team is not None, (
            "expected to find a clickable SE bracket match with a resolved team name"
        )

        # The fill modal must NOT open.
        page.wait_for_timeout(1500)
        expect(page.locator(".mantine-Modal-content")).to_have_count(0, timeout=5_000)
        # The same 'scores frozen' error notification that the RR cell path
        # shows (H9) must render for the SE bracket path too — this is the
        # consistency the critic flagged as missing.
        expect(page.locator(".mantine-Notification-root")).to_be_visible(timeout=10_000)

        # Backend ground-truth: PUT /matches now returns 400 frozen.
        se_match_id = se_item["rounds"][0]["matches"][0]["id"]
        se_round_id = se_item["rounds"][0]["id"]
        body = {
            "id": se_match_id,
            "round_id": se_round_id,
            "games": None,
            "best_of": 3,
            "stage_item_input1_score": 2,
            "stage_item_input2_score": 0,
            "forfeit_input": None,
            "court_id": None,
            "custom_duration_minutes": None,
            "custom_margin_minutes": None,
        }
        r = requests.put(
            f"{BASE_URL}/api/tournaments/{tid}/matches/{se_match_id}",
            headers=_api_headers(), json=body, timeout=15,
        )
        assert r.status_code == 400, (
            f"post-settlement PUT /matches must 400, got {r.status_code}: {r.text[:200]}"
        )
        assert "frozen" in r.text.lower() or "settled" in r.text.lower(), (
            f"rejection must mention settled/frozen, got {r.text}"
        )
    finally:
        try:
            from .test_rating import _psql
            _psql(f"UPDATE tournaments SET settled_seq = NULL WHERE id = {tid};")
        except Exception:
            pass
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H6b: forfeit effect on standings (W/D/L) --------------------------------
# H6 asserts the forfeit persists but never checks the standings. The backend
# treats a forfeit as a WIN for the non-forfeiting side and a LOSS for the
# forfeiting side. This test opens the 排名 tab after a forfeit and asserts the
# W/L columns reflect that.


def test_forfeit_standings_wins_losses(page: Page, shared_club_id: int) -> None:
    """H6b: after forfeiting a match via the UI, the 排名 (standings) tab shows
    the non-forfeiting side with 胜利(wins)=1 / 失败(losses)=0 and the forfeiting
    side with 胜利=0 / 失败=1. A regression that misclassified a forfeit as a
    draw (or awarded 0 points to both sides) would pass H6 but produce wrong
    standings here.
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "ForfH6b")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)

        # We need to know WHICH team forfeited to assert standings. The modal
        # shows two forfeit buttons: '<team1Name> 弃权' and '<team2Name> 弃权'.
        # Click the first forfeit button and capture its label.
        forfeit_btns = modal.get_by_role("button", name="弃权")
        assert forfeit_btns.count() == 2
        first_label = forfeit_btns.nth(0).inner_text().strip()
        # Extract the team name from '<teamName> 弃权'.
        forfeiting_team = first_label.replace("弃权", "").strip()
        forfeit_btns.first.click()
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground-truth: one match is forfeited.
        forfeited = None
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if m.get("forfeit_input") is not None:
                            forfeited = m
        assert forfeited is not None
        assert forfeited["forfeit_input"] in (1, 2)

        # Determine the non-forfeiting team name. The stage_item_input
        # has a team_id; look up the name via the teams API.
        from ._helpers import api_get_teams
        teams_list = api_get_teams(tid)
        team_name_by_id = {t["id"]: t["name"] for t in teams_list}
        in1_team_id = (forfeited.get("stage_item_input1") or {}).get("team_id")
        in2_team_id = (forfeited.get("stage_item_input2") or {}).get("team_id")
        if forfeited["forfeit_input"] == 1:
            non_forfeiting_team = team_name_by_id.get(in2_team_id, "")
        else:
            non_forfeiting_team = team_name_by_id.get(in1_team_id, "")
        assert non_forfeiting_team, (
            f"could not resolve non-forfeiting team name; "
            f"in1_team_id={in1_team_id}, in2_team_id={in2_team_id}"
        )
        # Open the 排名 standings tab.
        page.get_by_role("tab", name="排名").first.click()
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_contain_text(team_prefix, timeout=15_000)

        # Parse the standings rows. Each <tr> has cells:
        # [#, name, 积分, 局分, 小分, 胜利, 失败]
        rows = panel.locator("tbody tr").all_inner_texts()
        assert rows, "expected standings rows after forfeit"

        forfeiting_row = None
        non_forfeiting_row = None
        for row_text in rows:
            cells = row_text.strip().split("\t")
            if len(cells) < 7:
                cells = row_text.strip().split()
            # Find the row containing the team name.
            row_str = row_text
            if forfeiting_team and forfeiting_team in row_str:
                forfeiting_row = cells
            if non_forfeiting_team and non_forfeiting_team in row_str:
                non_forfeiting_row = cells

        assert forfeiting_row is not None, (
            f"could not find forfeiting team '{forfeiting_team}' in standings rows: {rows}"
        )
        assert non_forfeiting_row is not None, (
            f"could not find non-forfeiting team '{non_forfeiting_team}' in standings: {rows}"
        )

        # The 胜利 (wins) column is index 5 (0-based) and 失败 (losses) is 6.
        # But cell splitting can be unreliable; use the row text directly.
        # Wins and losses are small integers near the end of the row.
        # Assert the forfeiting row contains '1' in the losses position and
        # '0' in the wins position; the non-forfeiting row the inverse.
        forfeiting_losses = forfeiting_row[-1].strip()
        forfeiting_wins = forfeiting_row[-2].strip()
        non_forfeiting_losses = non_forfeiting_row[-1].strip()
        non_forfeiting_wins = non_forfeiting_row[-2].strip()

        assert forfeiting_wins == "0", (
            f"forfeiting team must have wins=0, got {forfeiting_wins!r}; row={forfeiting_row}"
        )
        assert forfeiting_losses == "1", (
            f"forfeiting team must have losses=1, got {forfeiting_losses!r}; row={forfeiting_row}"
        )
        assert non_forfeiting_wins == "1", (
            f"non-forfeiting team must have wins=1, got {non_forfeiting_wins!r}; row={non_forfeiting_row}"
        )
        assert non_forfeiting_losses == "0", (
            f"non-forfeiting team must have losses=0, got {non_forfeiting_losses!r}; row={non_forfeiting_row}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H14: no active-stage restriction — any non-settled stage is editable -----


def test_inactive_stage_matches_still_editable(page: Page, shared_club_id: int) -> None:
    """H14: there is NO active-stage restriction on score entry.

    The rebrand removed any gating on `is_active` — any NON-settled stage's
    matches stay editable on the results page, regardless of whether that
    stage is the currently-active one. The results page renders ALL stage
    items (from all stages) as GroupGrids, and the fill modal opens for any
    unscored cell on any non-settled stage.

    This test creates a tournament with two RR stages, activates stage 1
    (so stage 2 is NOT active), navigates to /results, and asserts that a
    GroupGrid cell from BOTH stages opens the fill modal — proving there is
    no `is_active` gate on score entry.
    """
    import requests as _requests

    tname = f"E2E-InactiveSt-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        team_prefix = f"E2E-ISTeam-"
        for i in range(4):
            api_create_team(tid, f"{team_prefix}{i}-{uuid.uuid4().hex[:4]}")
        s1 = api_create_stage(tid, f"E2E-IS-S1-{uuid.uuid4().hex[:6]}")
        api_create_round_robin(tid, s1, team_count=4, group_count=1)
        s2 = api_create_stage(tid, f"E2E-IS-S2-{uuid.uuid4().hex[:6]}")
        api_create_round_robin(tid, s2, team_count=4, group_count=1)
        api_create_court(tid, f"E2E-ISCt-{uuid.uuid4().hex[:4]}")
        api_create_court(tid, f"E2E-ISCt-{uuid.uuid4().hex[:4]}")
        api_schedule_matches(tid)

        # Activate stage 1 so stage 2 is inactive.
        r = _requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
            headers=_api_headers(),
            json={"direction": "next"},
            timeout=15,
        )
        r.raise_for_status()

        # Verify stage 1 is active, stage 2 is not.
        stages = api_get_stages(tid)
        stage_map = {s["id"]: s for s in stages}
        assert stage_map[s1].get("is_active") is True
        assert stage_map[s2].get("is_active") is False

        _goto_results(page, tid)

        # The page renders GroupGrids for ALL stage items — both stages.
        # There should be at least two '—' cells (one per stage's GroupGrid).
        cells = page.locator("button", has_text="\u2014")
        expect(cells.first).to_be_visible(timeout=15_000)
        assert cells.count() >= 2, (
            f"expected cells from both stages' GroupGrids, got {cells.count()}"
        )

        # Click the first cell (from whichever stage renders first) — the
        # modal must open, proving there is no is_active gate.
        cells.first.click()
        modal = page.locator(".mantine-Modal-content").last
        expect(modal).to_be_visible(timeout=10_000)
        expect(page.locator("body")).to_contain_text(
            "\u5f55\u5165\u5206\u6570", timeout=5_000
        )

        # Ground-truth: the backend accepts the score update (no 400 about
        # active stage). Score via the UI one-tap button.
        set_match_result(modal, 2, 0)
        expect(modal).to_be_hidden(timeout=10_000)

        # Verify via the API that a match now has input1_score=2.
        found_scored = False
        for s in api_get_stages(tid):
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if m.get("stage_item_input1_score") == 2:
                            found_scored = True
                            break
        assert found_scored, "expected a match with input1_score=2 after UI save"
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H15: a 4-game result button (4:2) saves and persists --------------------
# Critic issue #1: H2 saves 2:0, H11 saves 0:2, H2b saves 3:2 — but no test ever
# clicks a 4-game button to save and asserts persistence. H5 only asserts all 16
# labels RENDER; it never clicks one. A regression where the 4-game buttons
# render but the save handler rejects or miscalculates them would pass every
# existing test.


def test_four_game_result_button_saves(page: Page, shared_club_id: int) -> None:
    """H15: clicking a best-of-7 result button (e.g. '4:2') saves immediately,
    closes the modal, and persists input1_score=4 / input2_score=2 with
    games=null.

    H2/H11 only exercise 2-game saves; H2b exercises a 3-game save. A
    regression where the 4-game buttons rendered but the save handler or
    backend rejected/miscalculated them (e.g. a validation gate capping
    winner at 3, or a label-parsing bug on double-digit scores) would pass
    every existing test.
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH15")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)
        set_match_result(modal, 4, 2)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        scored = []
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if (
                            m.get("stage_item_input1_score") == 4
                            and m.get("stage_item_input2_score") == 2
                        ):
                            scored.append(m)
        assert len(scored) == 1, (
            f"expected exactly one match with 4:2 after save, got {len(scored)}"
        )
        assert not scored[0].get("games"), (
            f"games must be null/empty (no per-game points), got {scored[0].get('games')!r}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- H16: 清除比分 (clear) on a FORFEITED match resets forfeit_input ----------
# Critic issue #2: H7 scores 2:0 then clears — but forfeit_input was never set,
# so the clear handler's handling of forfeit_input is untested. A regression
# where the clear button zeroes the scores but forgets to include
# forfeit_input=None in the PUT payload (leaving the match still forfeited
# despite showing 0:0) would pass H7. This test exercises the intersection.


def test_clear_score_on_forfeited_match(page: Page, shared_club_id: int) -> None:
    """H16: forfeit a match via the UI, re-open the cell, click 清除比分, and
    assert via the API that forfeit_input is now None (not just that scores
    are 0:0).

    H6 tests the forfeit path in isolation; H7 tests the clear path in
    isolation. Their intersection — clearing a forfeited match — is not
    covered. A regression where the clear button zeroed the scores but
    forgot to include forfeit_input=None in the PUT payload would leave the
    match still forfeited despite showing 0:0, and would pass H7 but fail
    here.
    """
    tid, team_prefix, stage_id = _setup_fresh_rr(shared_club_id, "MatchH16")
    try:
        _goto_results(page, tid)
        modal = _open_first_cell_modal(page, team_prefix)

        # Forfeit via the UI one-tap button.
        forfeit_btns = modal.get_by_role("button", name="弃权")
        assert forfeit_btns.count() == 2, (
            f"expected exactly 2 forfeit buttons, got {forfeit_btns.count()}"
        )
        forfeit_btns.first.click()
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground-truth: exactly one match has forfeit_input set.
        forfeited = None
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if m.get("forfeit_input") is not None:
                            forfeited = m
        assert forfeited is not None, "expected one forfeited match before clear"
        assert forfeited["forfeit_input"] in (1, 2)

        # Re-open the same cell. After a forfeit, the GroupGrid cell shows
        # '弃' (forfeit_loss_short) for the forfeiting side and '胜'
        # (forfeit_win_short) for the non-forfeiting side — NOT '0:0'. The
        # cell is still a clickable button because the match has a recorded
        # result (hasScore=true). We click the button containing '弃' (the
        # forfeiting side's cell).
        cell = page.locator("button", has_text="弃").first
        expect(cell).to_be_visible(timeout=10_000)
        cell.click()
        modal = page.locator(".mantine-Modal-content").last
        expect(modal).to_be_visible(timeout=10_000)

        # The 清除比分 button should be present (only shows when hasScore).
        clear_btn = modal.get_by_role("button", name="清除比分", exact=True)
        expect(clear_btn).to_be_visible(timeout=5_000)
        clear_match_score(modal)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground-truth: the match that was forfeited must now have
        # forfeit_input=None (not just 0:0 scores). We identify it by
        # match id since the clear may have reset scores to 0:0 which
        # is the same as unscored.
        match_id = forfeited["id"]
        cleared_match = None
        for s in api_get_stages(tid):
            if s["id"] != stage_id:
                continue
            for item in s.get("stage_items", []):
                for rd in item.get("rounds", []):
                    for m in rd.get("matches", []):
                        if m["id"] == match_id:
                            cleared_match = m
        assert cleared_match is not None, "could not find the cleared match in API"
        assert cleared_match.get("forfeit_input") is None, (
            f"forfeit_input must be None after clear, got {cleared_match.get('forfeit_input')!r}"
        )
        assert cleared_match.get("stage_item_input1_score") in (0, None), (
            f"input1_score must be 0/None after clear, got {cleared_match.get('stage_item_input1_score')!r}"
        )
        assert cleared_match.get("stage_item_input2_score") in (0, None), (
            f"input2_score must be 0/None after clear, got {cleared_match.get('stage_item_input2_score')!r}"
        )
        assert not cleared_match.get("games"), (
            f"games must be null/empty after clear, got {cleared_match.get('games')!r}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass