"""Permission- & state-dependent GUI rendering (Section N).

The v3.1.6 "follow + spectator-scoped view" feature makes the SAME results page
render differently per role/state. These tests drive the page THROUGH the UI
with DISTINCT accounts (owner = the shared E2E admin via the `page` fixture;
anonymous via `anon_page`; fresh applicant/scorer accounts logged into their own
browser context via a localStorage token injection) and assert what each one
SEES, not just an API status code.

  N1 anonymous guest: public results render read-only; clicking a match does NOT
     open the editable score modal; management routes bounce to /login.
  N2 logged-in NON-participant: 申请参赛 join section + ⭐关注 toggle shown;
     matches read-only (no editable modal).
  N3 申请参赛 auto-hides after applying (pending badge replaces the form).
  N4 ⭐ follow toggle flips state AND the tournament appears under the home
     我关注的比赛 tab (and NOT under 我创建的比赛); un-following removes it.
  N5 a non-member hitting a management route (/settings) is REDIRECTED to
     /results; the owner stays on /settings and sees the management form.
  N6 a 记分员 scorer on a PRIVATE tournament can open the editable score modal
     (can_record) but is still bounced off /settings (not can_manage).
  N7 a followed card on the home 我关注 tab links to the READ-ONLY results page.
  N8 an APPROVED participant/member sees read-only results with NEITHER the 申请参赛
     join affordance NOR the 参赛申请已提交 pending badge (results-matrix state (d)).
"""
from __future__ import annotations

import uuid

import requests
from playwright.sync_api import Browser, Page, expect

from ._helpers import (
    BASE_URL,
    _api_headers,
    api_create_court,
    api_create_round_robin,
    api_create_stage,
    api_create_team,
    api_schedule_matches,
    set_match_result,
)
from .test_rating import (
    _apply_to_join,
    _create_nonrated_individual_tournament,
    _force_cleanup_rated,
    _headers_for,
    _register_account,
    _remove_scorer,
)

EDIT_MODAL_TITLE = "\u5f55\u5165\u6bd4\u5206"  # edit_match_modal_title (was "\u7f16\u8f91\u6bd4\u8d5b")
# The Mantine v8 Modal renders the title in a <h2 class="mantine-Modal-title">
# element. get_by_text with exact=True can fail to match heading-role elements
# in some Playwright versions, so use a CSS selector for reliability.
EDIT_MODAL_SELECTOR = ".mantine-Modal-title"
# The join flow is now INSTANT (commit d9d473c): the affordance is a \u53c2\u8d5b button
# (no creator approval), and after joining the user immediately becomes a
# participant shown the \u60a8\u5df2\u53c2\u8d5b badge \u2014 there is no longer a pending state.
JOIN_BUTTON = "\u53c2\u8d5b"
PARTICIPANT_BADGE = "\u60a8\u5df2\u53c2\u8d5b"
FOLLOW_BUTTON = "\u5173\u6ce8"
FOLLOWED_LABEL = "\u5df2\u5173\u6ce8"
TAB_FOLLOWED = "\u6211\u5173\u6ce8\u7684\u6bd4\u8d5b"
TAB_CREATED = "\u6211\u521b\u5efa\u7684\u6bd4\u8d5b"
# Unique to the settings management form (the "set start time to now" button);
# absent on the read-only results page that non-managers are bounced to.
SETTINGS_MARKER = "\u8bbe\u7f6e\u4e3a\u73b0\u5728"  # set_to_new_button


def _logged_in_context(browser: Browser, token: str):
    """A fresh browser context authenticated as an arbitrary account, by
    injecting the login token into localStorage before any app JS runs (mirrors
    conftest.make_logged_in_context, replicated here to avoid an import-path
    dependency on the top-level conftest module)."""
    ctx = browser.new_context(base_url=BASE_URL)
    payload = '{"access_token":"%s"}' % token
    ctx.add_init_script(f"window.localStorage.setItem('login', '{payload}');")
    return ctx


def _build_scheduled_rr(tid: int) -> str:
    """Create 4 teams + an RR stage + 2 courts + scheduled matches so the
    results 结果 tab renders match cards. Returns the unique team-name prefix
    so callers can scope assertions to this tournament's cards."""
    prefix = f"E2E-PermTeam-{uuid.uuid4().hex[:4]}"
    for i in range(4):
        api_create_team(tid, f"{prefix}-{i}")
    stage_id = api_create_stage(tid, f"E2E-PermStage-{uuid.uuid4().hex[:6]}")
    api_create_round_robin(tid, stage_id, team_count=4, group_count=1)
    api_create_court(tid, f"E2E-PermCt-{uuid.uuid4().hex[:4]}")
    api_create_court(tid, f"E2E-PermCt-{uuid.uuid4().hex[:4]}")
    api_schedule_matches(tid)
    return prefix


def _create_private_tournament(club_id: int) -> int:
    auth = _api_headers()
    name = f"E2E-PermPriv-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": name, "club_id": club_id, "dashboard_public": False,
            "dashboard_endpoint": "", "players_can_be_in_multiple_teams": False,
            "auto_assign_courts": True, "start_time": "2030-01-01T00:00:00Z",
            "duration_minutes": 10, "margin_minutes": 5,
        },
        timeout=15,
    ).raise_for_status()
    return next(
        t["id"]
        for t in requests.get(
            f"{BASE_URL}/api/tournaments?filter_=ALL", headers=auth, timeout=15
        ).json()["data"]
        if t["name"] == name
    )


# ---- N1: anonymous guest ---------------------------------------------------


def test_anon_results_read_only(anon_page: Page, shared_club_id: int) -> None:
    """N1: an anonymous guest sees public results read-only; the GroupGrid
    renders team names as plain text (no clickable cell buttons), and management
    routes redirect to /login (no management chrome)."""
    tid = _create_nonrated_individual_tournament(shared_club_id)
    try:
        prefix = _build_scheduled_rr(tid)

        anon_page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        anon_page.wait_for_selector('[role="tab"]', timeout=15_000)
        # The GroupGrid renders a table with the team names; an anonymous
        # viewer gets a read-only table (no clickable cell buttons).
        expect(anon_page.locator("table").first).to_be_visible(timeout=15_000)
        expect(anon_page.locator("body")).to_contain_text(prefix, timeout=15_000)

        # Anonymous viewers get NO follow / join affordances (they must log in).
        expect(anon_page.get_by_role("button", name=JOIN_BUTTON)).to_have_count(0)
        expect(anon_page.get_by_role("button", name=FOLLOW_BUTTON, exact=True)).to_have_count(0)

        # Read-only: no clickable cell buttons exist (GroupGrid renders plain
        # Text, not UnstyledButton, when openMatchModal is null).
        assert anon_page.locator("button", has_text="—").count() == 0, (
            "anon viewer should see read-only GroupGrid (no clickable cell buttons)"
        )

        # A management route bounces an anonymous visitor to /login.
        anon_page.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
        anon_page.wait_for_url("**/login**", timeout=15_000)
        assert "/login" in anon_page.url
    finally:
        _force_cleanup_rated(tid, [])

# ---- N2 + N3: logged-in non-participant, then after joining ----------------


def test_nonparticipant_sees_join_and_follow_then_pending(
    browser: Browser, shared_club_id: int
) -> None:
    """N2: a logged-in non-participant on a not-yet-started individual
    tournament sees the \u53c2\u8d5b (instant-join) button + \u2b50\u5173\u6ce8 toggle.
    N3: after joining, the \u53c2\u8d5b form auto-hides and is replaced by the
    \u60a8\u5df2\u53c2\u8d5b participant badge.

    NOTE: joining is only open BEFORE play starts (no match generated) \u2014 see
    my_join_status / request_to_join (commit d9d473c). So this test must NOT
    pre-generate matches; read-only match rendering for a non-recorder is
    covered by N1 (anon) and N8 (approved participant)."""
    tid = _create_nonrated_individual_tournament(shared_club_id)
    outsider = _register_account("permn2")
    ctx = _logged_in_context(browser, outsider["token"])
    try:
        pg = ctx.new_page()
        pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        pg.wait_for_load_state("networkidle")

        # N2: instant-join + follow affordances are shown to a logged-in
        # non-member while joining is still open (no matches yet).
        expect(pg.get_by_role("button", name=JOIN_BUTTON, exact=True)).to_be_visible(
            timeout=15_000
        )
        expect(pg.get_by_role("button", name=FOLLOW_BUTTON, exact=True)).to_be_visible(
            timeout=15_000
        )

        # N3: the same account CLICKS the \u53c2\u8d5b button in the browser (exercising
        # the JoinSection onClick -> requestToJoin handler end-to-end, NOT the API
        # helper). The button must then be replaced IN PLACE by the \u60a8\u5df2\u53c2\u8d5b
        # participant badge (SWR mutate, no reload needed), and a real
        # teams_x_users binding must exist for this account.
        h = _headers_for(outsider["token"])
        before = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
        }
        pg.get_by_role("button", name=JOIN_BUTTON, exact=True).click()
        # The badge appears via SWR revalidation after the POST succeeds (no reload).
        expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_be_visible(timeout=15_000)
        expect(pg.get_by_role("button", name=JOIN_BUTTON, exact=True)).to_have_count(0)

        # Ground truth: the click actually joined \u2014 my-join-status now reports the
        # account as a participant, and a NEW bound team was auto-created. A broken
        # onClick (wrong endpoint / silent no-op) would leave both unchanged.
        status = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/my-join-status", headers=h, timeout=15
        ).json()["data"]
        assert status["is_participant"] is True, (
            f"clicking \u53c2\u8d5b must make the account a participant, got {status}"
        )
        after = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
        }
        assert len(after - before) == 1, (
            f"clicking \u53c2\u8d5b must auto-create exactly one bound team, before={before} after={after}"
        )

        # Persisting across a hard reload proves it was a real server-side join.
        pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        pg.wait_for_load_state("networkidle")
        expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_be_visible(timeout=15_000)
        expect(pg.get_by_role("button", name=JOIN_BUTTON, exact=True)).to_have_count(0)
    finally:
        ctx.close()
        _force_cleanup_rated(tid, [outsider["uid"]])


# ---- N4: follow toggle flips state + home 我关注 tab ----------------------


def test_follow_toggle_and_home_followed_tab(
    browser: Browser, shared_club_id: int
) -> None:
    """N4: the ⭐ follow toggle on the results page flips state, the tournament
    then appears under the home 我关注的比赛 tab (and NOT under 我创建的比赛,
    since this account didn't create it), and un-following removes it."""
    auth = _api_headers()
    tname = f"E2E-PermFollow-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": tname, "club_id": shared_club_id, "dashboard_public": True,
            "dashboard_endpoint": "", "players_can_be_in_multiple_teams": False,
            "auto_assign_courts": True, "start_time": "2030-01-01T00:00:00Z",
            "duration_minutes": 10, "margin_minutes": 5,
        },
        timeout=15,
    ).raise_for_status()
    tid = next(
        t["id"]
        for t in requests.get(
            f"{BASE_URL}/api/tournaments?filter_=ALL", headers=auth, timeout=15
        ).json()["data"]
        if t["name"] == tname
    )
    follower = _register_account("permn4")
    ctx = _logged_in_context(browser, follower["token"])
    h = _headers_for(follower["token"])
    try:
        pg = ctx.new_page()
        pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        follow_btn = pg.get_by_role("button", name=FOLLOW_BUTTON, exact=True)
        expect(follow_btn).to_be_visible(timeout=15_000)

        # Click follow -> button flips to 已关注 and the API records the favorite.
        follow_btn.click()
        expect(pg.get_by_role("button", name=FOLLOWED_LABEL, exact=True)).to_be_visible(
            timeout=15_000
        )
        followed = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/me/tournaments", headers=h, timeout=15
            ).json()["data"]
        }
        assert tid in followed, "the followed list must include the toggled tournament"

        # Home: the tournament appears under 我关注的比赛, NOT under 我创建的比赛.
        pg.goto(BASE_URL, wait_until="domcontentloaded")
        pg.get_by_role("tab", name=TAB_FOLLOWED).click()
        # The followed card links to the read-only results page.
        expect(
            pg.locator(f'a[href*="/tournaments/{tid}/results"]').first
        ).to_be_visible(timeout=15_000)
        # The two tabs are distinct: the 我创建的比赛 tab's cards link to /stages
        # (the organiser entry point). This account created nothing, so no
        # /stages link for this tournament exists in either tab panel.
        assert pg.locator(f'a[href*="/tournaments/{tid}/stages"]').count() == 0, (
            "a tournament this account did not create must not show under 我创建的比赛"
        )

        # Un-follow from the results page -> drops out of the followed list.
        pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        pg.get_by_role("button", name=FOLLOWED_LABEL, exact=True).click()
        expect(pg.get_by_role("button", name=FOLLOW_BUTTON, exact=True)).to_be_visible(
            timeout=15_000
        )
        followed_after = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/me/tournaments", headers=h, timeout=15
            ).json()["data"]
        }
        assert tid not in followed_after, "un-following must remove it from the list"
    finally:
        ctx.close()
        requests.delete(f"{BASE_URL}/api/tournaments/{tid}", headers=auth, timeout=15)


# ---- N5: management route gating (non-member redirected, owner not) --------


def test_management_route_redirects_nonmember(
    page: Page, browser: Browser, shared_club_id: int
) -> None:
    """N5: a logged-in non-member hitting ANY management route (/settings,
    /teams, /stages, /courts) is redirected to /results and sees no management
    form; the owner (club member) stays on /settings and sees the management
    form.

    The redirect logic is likely shared, but a regression that accidentally
    gated only /settings (leaving /teams, /stages, or /courts accessible to a
    non-member) would pass a /settings-only check.
    """
    tid = _create_nonrated_individual_tournament(shared_club_id)
    outsider = _register_account("permn5")
    ctx = _logged_in_context(browser, outsider["token"])
    try:
        # Non-member: every management route bounces to /results and shows no
        # management form (the settings-only "\u8bbe\u7f6e\u4e3a\u73b0\u5728" button is absent).
        # The management routes (from navbar _main_links) are /settings, /teams,
        # /stages, /schedule (NOT /courts — courts live under /schedule).
        pg = ctx.new_page()
        for route in ("settings", "teams", "stages", "schedule"):
            pg.goto(
                f"{BASE_URL}/tournaments/{tid}/{route}", wait_until="domcontentloaded"
            )
            pg.wait_for_url(f"**/tournaments/{tid}/results", timeout=15_000)
            assert pg.url.rstrip("/").endswith(f"/tournaments/{tid}/results"), (
                f"non-member hitting /{route} must redirect to /results, got {pg.url}"
            )
            expect(pg.get_by_role("button", name=SETTINGS_MARKER)).to_have_count(0)

        # Owner (the E2E admin via the `page` fixture, a member of the shared club)
        # stays on /settings and sees the management form.
        page.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
        expect(page).to_have_url(f"{BASE_URL}/tournaments/{tid}/settings", timeout=15_000)
        expect(
            page.get_by_role("button", name=SETTINGS_MARKER)
        ).to_be_visible(timeout=15_000)
    finally:
        ctx.close()
        _force_cleanup_rated(tid, [outsider["uid"]])


# ---- N6: scorer on a PRIVATE tournament can score but not manage ----------


def test_scorer_can_score_private_but_not_manage(
    browser: Browser, shared_club_id: int
) -> None:
    """N6: a 记分员 scorer on a PRIVATE tournament can open the editable score
    modal (can_record) in the browser AND actually SAVE a result that
    persists server-side under the scorer's token, but is still redirected off
    /settings (can_record without can_manage).

    The save half is non-trivial: a regression that wired the scorer's token
    correctly to GET stages but DROPPED the PUT /matches (or 403'd it because
    the score-save route stopped being gated on can_record) would still let the
    modal open but silently discard the save. So after the modal opens we click
    the one-tap 2:0 result button (set_match_result), and assert the API —
    fetched via the scorer's own token, not the owner's — carries a 2:0 result
    with games=null for that match. A frozen / dropped save fails here.
    """
    tid = _create_private_tournament(shared_club_id)
    scorer = _register_account("permn6")
    auth = _api_headers()
    try:
        prefix = _build_scheduled_rr(tid)
        # Owner authorises the scorer.
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/scorers",
            headers=auth,
            json={"user_email": scorer["email"]},
            timeout=15,
        ).raise_for_status()
        ctx = _logged_in_context(browser, scorer["token"])
        try:
            pg = ctx.new_page()
            pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
            pg.wait_for_selector('[role="tab"]', timeout=15_000)
            # The scorer (can_record) sees clickable GroupGrid cells (buttons).
            expect(pg.locator("table").first).to_be_visible(timeout=15_000)
            expect(pg.locator("body")).to_contain_text(prefix, timeout=15_000)

            # Capture the table text so we can correlate with the API match.
            table_text = pg.locator("table").first.inner_text()

            # can_record: clicking a GroupGrid cell opens the EDITABLE score modal.
            cell = pg.locator("button", has_text="—").first
            expect(cell).to_be_visible(timeout=15_000)
            cell.click()
            expect(pg.locator(EDIT_MODAL_SELECTOR)).to_be_visible(timeout=15_000)

            # Click a result button (2:0) — saves immediately and closes the modal.
            modal = pg.locator(".mantine-Modal-content").last
            set_match_result(modal, 2, 0)
            expect(pg.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

            # API ground truth UNDER THE SCORER'S TOKEN: GET the stages payload
            # with the scorer's bearer; assert one match in this tournament now
            # carries the saved 2:0 result (games=null, no per-game points).
            import time
            saved = None
            scorer_headers = _headers_for(scorer["token"])
            for _ in range(20):
                stages = requests.get(
                    f"{BASE_URL}/api/tournaments/{tid}/stages",
                    headers=scorer_headers, timeout=15,
                ).json()["data"]
                for s in stages:
                    for it in s.get("stage_items", []):
                        for rd in it.get("rounds", []):
                            for m in rd.get("matches", []):
                                if (
                                    m.get("stage_item_input1_score") == 2
                                    and m.get("stage_item_input2_score") == 0
                                ):
                                    saved = m
                                    break
                if saved is not None:
                    break
                time.sleep(0.5)
            assert saved is not None, (
                "scorer's UI save must persist the 2:0 result on a private "
                f"tournament — stages: {stages!r}"
            )
            assert saved.get("stage_item_input1_score") == 2, (
                f"winner side must score 2, got {saved!r}"
            )
            assert saved.get("stage_item_input2_score") == 0, (
                f"loser side must score 0, got {saved!r}"
            )
            assert not saved.get("games"), (
                f"games must be null/empty (no per-game points), got {saved.get('games')!r}"
            )
            # Sanity: the saved match really involves one of the teams we saw.
            t1 = saved.get("stage_item_input1", {}).get("team", {}).get("name", "")
            t2 = saved.get("stage_item_input2", {}).get("team", {}).get("name", "")
            assert (t1 and t1 in table_text) or (t2 and t2 in table_text), (
                f"saved match teams {t1!r}/{t2!r} must overlap the table "
                f"text {table_text!r}"
            )

            # NOT can_manage: /settings redirects the scorer to /results.
            pg.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
            pg.wait_for_url(f"**/tournaments/{tid}/results", timeout=15_000)
            assert pg.url.rstrip("/").endswith(f"/tournaments/{tid}/results")
            expect(pg.get_by_role("button", name=SETTINGS_MARKER)).to_have_count(0)
        finally:
            ctx.close()
    finally:
        requests.delete(
            f"{BASE_URL}/api/tournaments/{tid}/scorers/{scorer['uid']}", headers=auth, timeout=15
        )
        _force_cleanup_rated(tid, [])


# ---- N7: followed card on home opens the read-only results page -----------


def test_followed_card_links_to_results(
    browser: Browser, shared_club_id: int
) -> None:
    """N7: a followed tournament's card on the home 我关注的比赛 tab links to the
    READ-ONLY /results page (not the organiser dashboard/stages page)."""
    tid = _create_nonrated_individual_tournament(shared_club_id)
    follower = _register_account("permn7")
    ctx = _logged_in_context(browser, follower["token"])
    h = _headers_for(follower["token"])
    try:
        # Favorite via API (the toggle itself is covered by N4).
        r = requests.post(f"{BASE_URL}/api/me/favorites/{tid}", headers=h, timeout=15)
        assert r.status_code == 200, f"favorite failed: {r.status_code}: {r.text[:150]}"

        pg = ctx.new_page()
        pg.goto(BASE_URL, wait_until="domcontentloaded")
        pg.get_by_role("tab", name=TAB_FOLLOWED).click()
        link = pg.locator(f'a[href*="/tournaments/{tid}/results"]').first
        expect(link).to_be_visible(timeout=15_000)
        # The card must NOT instead point at the organiser stages/dashboard route.
        assert pg.locator(f'a[href*="/tournaments/{tid}/stages"]').count() == 0
    finally:
        ctx.close()
        _force_cleanup_rated(tid, [follower["uid"]])


# ---- N8: approved participant/member sees read-only results, no join/pending --


def test_approved_participant_results_read_only(
    browser: Browser, shared_club_id: int
) -> None:
    """N8 (results-page role matrix state (d)): a user who has JOINED an
    individual tournament opens /results and sees the 您已参赛 participant badge
    but NEITHER the 参赛 join button (they're already in), and the page is still
    read-only for them — the GroupGrid has no clickable cell buttons, so no
    录入分数 modal can open (a plain participant is not a recorder).

    The participant must join BEFORE matches are generated (instant-join is only
    open before play starts), then we build the scheduled RR so the GroupGrid
    renders read-only."""
    tid = _create_nonrated_individual_tournament(shared_club_id)
    applicant = _register_account("permn8")
    ctx = _logged_in_context(browser, applicant["token"])
    try:
        # Join while the window is open (no matches yet); instant-join binds.
        _apply_to_join(tid, applicant["token"])
        # Now generate the scheduled bracket so the GroupGrid renders.
        prefix = _build_scheduled_rr(tid)

        pg = ctx.new_page()
        pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        pg.wait_for_selector('[role="tab"]', timeout=15_000)

        # The GroupGrid table renders with team names (read-only for a participant).
        expect(pg.locator("table").first).to_be_visible(timeout=15_000)
        expect(pg.locator("body")).to_contain_text(prefix, timeout=15_000)

        # Joined participant: the 您已参赛 badge shows, the 参赛 join button is gone.
        expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_be_visible(timeout=15_000)
        expect(pg.get_by_role("button", name=JOIN_BUTTON, exact=True)).to_have_count(0)

        # Still read-only: no clickable cell buttons exist (openMatchModal is
        # null for non-recorders), so the edit modal cannot open.
        assert pg.locator("button", has_text="—").count() == 0, (
            "a joined participant is not a recorder — GroupGrid must be read-only"
        )
        expect(pg.locator(EDIT_MODAL_SELECTOR)).to_have_count(0)
    finally:
        ctx.close()
        _force_cleanup_rated(tid, [applicant["uid"]])


# ---- N9: non-member is DENIED a PRIVATE tournament's results (negative) ----


def test_nonmember_cannot_view_private_results(
    browser: Browser, shared_club_id: int
) -> None:
    """N9 (negative security): a logged-in account that is NOT a club member,
    scorer, or bound participant must NOT be able to read a PRIVATE
    tournament's results. N6 only proves an AUTHORISED scorer CAN view a
    private tournament; without this, a regression that leaked private stages
    to any logged-in user would pass the whole suite.

    Proven two ways: (a) the protected stages API returns 401 for the
    outsider, and (b) the outsider's browser at /results renders NO match
    cards (the page cannot populate without the stages payload)."""
    tid = _create_private_tournament(shared_club_id)
    outsider = _register_account("permn9")
    try:
        prefix = _build_scheduled_rr(tid)

        # (a) API ground truth: the outsider is denied the stages payload.
        r = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/stages",
            headers=_headers_for(outsider["token"]),
            timeout=15,
        )
        assert r.status_code == 401, (
            f"a non-member must be denied a private tournament's stages, "
            f"got {r.status_code}: {r.text[:150]}"
        )
        # The owner (member) is allowed — proves the 401 is about authorisation,
        # not a broken endpoint.
        owner_r = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/stages", headers=_api_headers(), timeout=15
        )
        assert owner_r.status_code == 200, (
            f"owner must still read the private stages, got {owner_r.status_code}"
        )

        # (b) UI: the outsider's browser shows NO GroupGrid table (the page
        # cannot populate without the stages payload).
        ctx = _logged_in_context(browser, outsider["token"])
        try:
            pg = ctx.new_page()
            pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            expect(pg.locator("table")).to_have_count(0)
            expect(pg.locator("body")).not_to_contain_text(prefix)
        finally:
            ctx.close()
    finally:
        _force_cleanup_rated(tid, [outsider["uid"]])


# ---- N10: the OWNER sees NO spectator affordances on their own results -----


def test_owner_sees_no_spectator_affordances_on_own_results(
    page: Page, shared_club_id: int
) -> None:
    """N10: the OWNER/manager viewing their OWN individual tournament's results
    page must NOT see the spectator affordances — 关注 (follow), 申请参赛 (join),
    or 信任创建者 (trust creator). An owner already has the tournament under the
    home 我创建的比赛 tab and cannot meaningfully apply to / follow a tournament
    they run. (Control: N2 proves a non-participant DOES see join + follow on
    the same page, so these are gated on can_manage, not globally removed.)"""
    tid = _create_nonrated_individual_tournament(shared_club_id)
    try:
        prefix = _build_scheduled_rr(tid)
        page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        page.wait_for_selector('[role="tab"]', timeout=15_000)

        expect(page.locator("table").first).to_be_visible(timeout=15_000)
        # The owner CAN record: clicking a GroupGrid cell opens the editable
        # modal. This also proves my-join-status (hence can_manage) has loaded,
        # so the affordance-absence checks below run in the settled state, not
        # during the brief pre-SWR render where can_manage is still unknown.
        cell = page.locator("button", has_text="—").first
        expect(cell).to_be_visible(timeout=15_000)
        cell.click()
        expect(page.locator(EDIT_MODAL_SELECTOR)).to_be_visible(timeout=15_000)
        page.keyboard.press("Escape")
        expect(page.locator(EDIT_MODAL_SELECTOR)).to_have_count(0, timeout=10_000)

        # None of the spectator affordances render for the owner/manager.
        expect(page.get_by_role("button", name=FOLLOW_BUTTON, exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name=FOLLOWED_LABEL, exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name=JOIN_BUTTON, exact=True)).to_have_count(0)
        expect(page.get_by_text("信任创建者", exact=False)).to_have_count(0)
    finally:
        _force_cleanup_rated(tid, [])


# ---- N10 / M24: self-withdraw (\u9000\u51fa\u8d5b\u4e8b) through the UI ---------------------

WITHDRAW_BUTTON = "\u9000\u51fa\u8d5b\u4e8b"


def test_participant_can_withdraw_via_ui(browser: Browser, shared_club_id: int) -> None:
    """M24: a joined participant who has not yet started play sees the \u9000\u51fa\u8d5b\u4e8b
    (self-withdraw) button next to the \u60a8\u5df2\u53c2\u8d5b badge, and CLICKING it removes
    their bound team and reverts them to a non-participant who is shown the
    \u53c2\u8d5b join button again.

    This exercises the JoinSection leave handler (leaveTournament -> POST
    /leave) end-to-end through the browser, complementing N3 (which exercises
    the join handler). A regression in the leave button's onClick (wrong
    endpoint, silent no-op, swallowed error) would leave the badge + the bound
    team in place and fail here."""
    tid = _create_nonrated_individual_tournament(shared_club_id)
    member = _register_account("permn10")
    ctx = _logged_in_context(browser, member["token"])
    h = _headers_for(member["token"])
    try:
        # The account joins (instant), so the results page now shows the badge.
        _apply_to_join(tid, member["token"])
        # Ground truth: a bound team exists for this account before withdrawal.
        bound_before = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
        }
        assert len(bound_before) == 1, f"join must auto-create one team, got {bound_before}"

        pg = ctx.new_page()
        pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        pg.wait_for_load_state("networkidle")
        # Joined state: badge + the \u9000\u51fa\u8d5b\u4e8b button are both shown (leave window
        # is open because no matches have been generated).
        expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_be_visible(timeout=15_000)
        withdraw = pg.get_by_role("button", name=WITHDRAW_BUTTON, exact=True)
        expect(withdraw).to_be_visible(timeout=15_000)

        # Click withdraw -> badge disappears and the \u53c2\u8d5b join button returns
        # (SWR mutate, in place).
        withdraw.click()
        expect(pg.get_by_role("button", name=JOIN_BUTTON, exact=True)).to_be_visible(
            timeout=15_000
        )
        expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_have_count(0)

        # Ground truth: my-join-status reverts to non-participant and the bound
        # team is gone.
        status = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/my-join-status", headers=h, timeout=15
        ).json()["data"]
        assert status["is_participant"] is False, (
            f"clicking \u9000\u51fa\u8d5b\u4e8b must revert participant status, got {status}"
        )
        bound_after = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
        }
        assert bound_before.isdisjoint(bound_after), (
            f"withdrawing must delete the bound team, still present: {bound_after & bound_before}"
        )
    finally:
        ctx.close()
        _force_cleanup_rated(tid, [member["uid"]])


# ---- N11: join affordance hidden + blocked once play has started -----------


def test_join_button_hidden_and_blocked_once_started(
    browser: Browser, shared_club_id: int
) -> None:
    """N11 (negative guard for commit 8834b4d): once an individual tournament
    has STARTED (a match has been generated), the 参赛 instant-join affordance
    must be HIDDEN on the results page for a logged-in non-participant, AND the
    backend must REJECT a join attempt. This is the complement of N2/N3 (which
    prove the button SHOWS and works *before* start): nothing else in the suite
    locks in that joining a started tournament is impossible. A regression that
    kept rendering 参赛 (or re-opened the join window server-side) would let a
    user "join" mid-event, dropping an unseeded extra team into a running
    bracket.

    Asserts (a) UI — a fresh non-member on /results of a started tournament sees
    the 关注 follow toggle but NO 参赛 button and no 您已参赛 badge;
    (b) my-join-status reports can_join == False; (c) backend — POST
    /join-requests returns 400 "比赛已开始，无法加入" and creates no
    team/binding for the outsider."""
    tid = _create_nonrated_individual_tournament(shared_club_id)
    outsider = _register_account("permn11")
    ctx = _logged_in_context(browser, outsider["token"])
    h = _headers_for(outsider["token"])
    try:
        # Start play: generate scheduled matches (4 seed teams + RR + courts).
        _build_scheduled_rr(tid)

        pg = ctx.new_page()
        pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        pg.wait_for_load_state("networkidle")

        # (a) UI: the follow toggle still renders, but the 参赛 join button is
        # GONE now that play has started (JoinSection sees can_join == False and
        # renders nothing); the outsider also has no participant badge.
        expect(pg.get_by_role("button", name=FOLLOW_BUTTON, exact=True)).to_be_visible(
            timeout=15_000
        )
        expect(pg.get_by_role("button", name=JOIN_BUTTON, exact=True)).to_have_count(0)
        expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_have_count(0)

        # (b) my-join-status: the server says joining is closed for a started run.
        status = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/my-join-status", headers=h, timeout=15
        ).json()["data"]
        assert status["can_join"] is False, (
            f"can_join must be False on a started tournament, got {status}"
        )
        assert status["is_participant"] is False, (
            f"the outsider never joined, got {status}"
        )

        # (c) backend: a direct join attempt is rejected with the started-message,
        # and no team/binding is created for the outsider.
        teams_before = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
        }
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/join-requests",
            headers=h,
            json={"trust_creator": False},
            timeout=15,
        )
        assert r.status_code == 400, (
            f"joining a started tournament must 400, got {r.status_code}: {r.text}"
        )
        assert "比赛已开始" in r.text, (
            f"expected the started-join rejection message, got {r.text}"
        )
        status_after = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/my-join-status", headers=h, timeout=15
        ).json()["data"]
        assert status_after["is_participant"] is False, (
            f"a rejected join must not bind the outsider, got {status_after}"
        )
        teams_after = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
        }
        assert teams_before == teams_after, (
            f"a rejected join must create no team, added: {teams_after - teams_before}"
        )
    finally:
        ctx.close()
        _force_cleanup_rated(tid, [outsider["uid"]])


# ---- M22 UI: scorer auto-follow surfaces on the home 我关注的比赛 tab --------


def test_scorer_auto_follow_home_tab_ui(
    browser: Browser, shared_club_id: int
) -> None:
    """M22 UI complement: after a user is added as a 记分员 (scorer), the
    tournament must appear under the home 我关注的比赛 tab for THAT scorer (not
    just in the API followed-list). N4 covers the manual-favorite path; this
    covers the scorer-specific auto-follow path through the browser so a
    regression that broke the home tab for that path (but not manual favoriting)
    surfaces.

    Asserts: the scorer's home page, after the role is added, shows a card
    linking to /tournaments/{id}/results under the 我关注的比赛 tab (and NOT a
    /stages organiser link, since the scorer did not create it). Removing the
    scorer role unfollows and the card leaves the tab.
    """
    tid = _create_nonrated_individual_tournament(shared_club_id)
    scorer = _register_account("permn22")
    h = _headers_for(scorer["token"])
    try:
        # Before being a scorer: the home 我关注的比赛 tab does NOT list it.
        ctx0 = _logged_in_context(browser, scorer["token"])
        pg0 = ctx0.new_page()
        pg0.goto(BASE_URL, wait_until="domcontentloaded")
        pg0.get_by_role("tab", name=TAB_FOLLOWED).click()
        # Scope to the visible (followed) panel: the hidden 可以参赛的比赛 panel
        # may legitimately list this joinable tournament.
        expect(
            pg0.locator(f'div[role="tabpanel"]:visible a[href*="/tournaments/{tid}/results"]')
        ).to_have_count(0)
        ctx0.close()

        # Owner adds the account as a scorer -> auto-follows.
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/scorers",
            headers=_api_headers(),
            json={"user_email": scorer["email"]},
            timeout=15,
        ).raise_for_status()
        followed = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/me/tournaments", headers=h, timeout=15
            ).json()["data"]
        }
        assert tid in followed, "scorer must auto-follow the tournament"

        # UI: the home 我关注的比赛 tab now shows a card linking to /results.
        ctx = _logged_in_context(browser, scorer["token"])
        pg = ctx.new_page()
        pg.goto(BASE_URL, wait_until="domcontentloaded")
        pg.get_by_role("tab", name=TAB_FOLLOWED).click()
        expect(
            pg.locator(f'a[href*="/tournaments/{tid}/results"]').first
        ).to_be_visible(timeout=15_000)
        # The scorer did not create it, so no /stages organiser link exists.
        assert pg.locator(f'a[href*="/tournaments/{tid}/stages"]').count() == 0, (
            "a tournament the scorer did not create must not show under 我创建的比赛"
        )
        ctx.close()

        # Removing the scorer role unfollows -> the card leaves the tab.
        _remove_scorer(tid, scorer["uid"])
        followed_after = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/me/tournaments", headers=h, timeout=15
            ).json()["data"]
        }
        assert tid not in followed_after, "removing scorer role must unfollow"
    finally:
        _force_cleanup_rated(tid, [scorer["uid"]])


# ---- M6b: \u4fe1\u4efb\u521b\u5efa\u8005 checkbox actually adds the owner as a trusted manager ----

TRUST_CHECKBOX_PARTIAL = "\u5141\u8bb8\u521b\u5efa\u8005\u4ee5\u540e\u62c9\u6211\u8fdb\u5165\u6bd4\u8d5b"


def _owner_user_id() -> int:
    """Return the user id of the E2E owner (the shared admin account)."""
    auth = _api_headers()
    me = requests.get(f"{BASE_URL}/api/users/me", headers=auth, timeout=15).json()["data"]
    return me["id"]


def test_trust_creator_checkbox_marks_owner_as_trusted_manager(
    browser: Browser, shared_club_id: int
) -> None:
    """M6b: clicking the \u4fe1\u4efb\u521b\u5efa\u8005 (\u5141\u8bb8\u521b\u5efa\u8005\u4ee5\u540e\u62c9\u6211\u8fdb\u5165\u6bd4\u8d5b)
    checkbox in JoinSection while joining must mark the tournament's club owner
    as a trusted manager of the joining account.

    Two halves are proven through the browser:
      (positive) a fresh account ticks the checkbox + clicks \u53c2\u8d5b -> the joiner's
      GET /me/trusted-managers contains the owner;
      (negative) a second fresh account joins WITHOUT ticking the checkbox ->
      the same call does NOT contain the owner.

    Without this assertion, a regression that dropped the Checkbox's onChange or
    stopped forwarding trust_creator server-side would still pass the suite.
    """
    owner_uid = _owner_user_id()
    tid_positive = _create_nonrated_individual_tournament(shared_club_id)
    tid_negative = _create_nonrated_individual_tournament(shared_club_id)
    pos = _register_account("trustY")
    neg = _register_account("trustN")
    try:
        # ---- positive: ticked checkbox -> owner becomes a trusted manager ----
        ctx_pos = _logged_in_context(browser, pos["token"])
        try:
            pg = ctx_pos.new_page()
            pg.goto(
                f"{BASE_URL}/tournaments/{tid_positive}/results",
                wait_until="domcontentloaded",
            )
            pg.wait_for_load_state("networkidle")
            join_btn = pg.get_by_role("button", name=JOIN_BUTTON, exact=True)
            expect(join_btn).to_be_visible(timeout=15_000)
            # The Mantine Checkbox renders an <input role="checkbox"> whose
            # accessible name is the full label text. get_by_role finds it
            # robustly regardless of label/input nesting. The label is a long
            # Chinese string with parentheses; use a regex on the partial.
            import re
            checkbox = pg.get_by_role(
                "checkbox",
                name=re.compile(re.escape(TRUST_CHECKBOX_PARTIAL)),
            )
            expect(checkbox).to_be_visible(timeout=10_000)
            checkbox.check()
            expect(checkbox).to_be_checked(timeout=5_000)
            join_btn.click()
            expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_be_visible(
                timeout=15_000
            )
            # Ground truth: the joiner's trusted-managers list now contains the owner.
            h_pos = _headers_for(pos["token"])
            tm = requests.get(
                f"{BASE_URL}/api/me/trusted-managers", headers=h_pos, timeout=15
            ).json()["data"]
            tm_ids = {row.get("manager_id") for row in tm}
            assert owner_uid in tm_ids, (
                f"ticking \u4fe1\u4efb\u521b\u5efa\u8005 must add the owner (uid={owner_uid}) to the "
                f"joiner's trusted-managers; got {tm_ids!r}"
            )
        finally:
            ctx_pos.close()

        # ---- negative: unchecked checkbox -> owner is NOT added --------------
        ctx_neg = _logged_in_context(browser, neg["token"])
        try:
            pg = ctx_neg.new_page()
            pg.goto(
                f"{BASE_URL}/tournaments/{tid_negative}/results",
                wait_until="domcontentloaded",
            )
            pg.wait_for_load_state("networkidle")
            join_btn = pg.get_by_role("button", name=JOIN_BUTTON, exact=True)
            expect(join_btn).to_be_visible(timeout=15_000)
            # Leave the checkbox unchecked; click \u53c2\u8d5b directly.
            join_btn.click()
            expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_be_visible(
                timeout=15_000
            )

            h_neg = _headers_for(neg["token"])
            tm = requests.get(
                f"{BASE_URL}/api/me/trusted-managers", headers=h_neg, timeout=15
            ).json()["data"]
            tm_ids = {row.get("manager_id") for row in tm}
            assert owner_uid not in tm_ids, (
                f"joining WITHOUT ticking \u4fe1\u4efb\u521b\u5efa\u8005 must NOT add the owner "
                f"(uid={owner_uid}) to the joiner's trusted-managers; got {tm_ids!r}"
            )
        finally:
            ctx_neg.close()
    finally:
        # Best-effort: clear the trust row that the positive half created so
        # the owner's direct-add picker stays clean for sibling tests.
        try:
            requests.delete(
                f"{BASE_URL}/api/me/trusted-managers/{owner_uid}",
                headers=_headers_for(pos["token"]),
                timeout=15,
            )
        except Exception:
            pass
        _force_cleanup_rated(tid_positive, [pos["uid"]])
        _force_cleanup_rated(tid_negative, [neg["uid"]])


# ---- M15b: settled tournament is READ-ONLY (scores frozen, no re-settle) ---


def test_settled_tournament_is_read_only(page: Page, shared_club_id: int) -> None:
    """M15 follow-up: once a rated individual tournament has been SETTLED
    (settled_seq is set), it must be read-only:
      (a) PUT /matches/{id} is rejected with 400 "settled; scores are frozen";
      (b) per-match games stay frozen (saved games unchanged after the rejected
          edit);
      (c) the \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 button is GONE on the settings page (no double
          settle).

    A regression that lets a post-settlement score edit silently mutate a
    player's settled rating would not be caught by M15. This test pinpoints it.
    """
    import time
    from .test_rating import (
        _create_rated_individual_tournament,
        _build_stage_with_one_match,
        _score_match,
        _psql,
    )

    tid = _create_rated_individual_tournament(shared_club_id)
    a = _register_account("settledA")
    b = _register_account("settledB")
    uids = [a["uid"], b["uid"]]
    auth = _api_headers()
    try:
        # 1) Both apply (instant-join); two bound teams auto-create.
        _apply_to_join(tid, a["token"])
        _apply_to_join(tid, b["token"])
        teams = []
        for _ in range(20):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=auth, timeout=15
            ).json()["data"]["teams"]
            if len(teams) >= 2:
                break
            time.sleep(0.5)
        assert len(teams) == 2

        # 2) Seed both newcomers as ACTIVE directly via psql so /settle can
        # succeed in one shot (M15 already proves the seed-approval UI; this
        # test is about the post-settlement read-only contract, not the
        # approval flow).
        for u in uids:
            _psql(
                "INSERT INTO player_ratings (category_id, user_id, initial_rating, "
                "current_rating, matches_played, status) "
                f"VALUES (1, {u}, 1500, 1500, 0, 'ACTIVE') "
                "ON CONFLICT (category_id, user_id) DO UPDATE "
                "SET initial_rating=1500, current_rating=1500, matches_played=0, status='ACTIVE';"
            )

        # 3) Build one match and score it 2:0 so settlement is "ready".
        match_id, round_id = _build_stage_with_one_match(tid)
        _score_match(tid, match_id, round_id, [[11, 7], [11, 5]])

        # 4) Settle through the admin /settle endpoint (no PENDING seeds left).
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/settle", headers=auth, timeout=15
        )
        assert r.status_code == 200, (
            f"admin /settle must succeed after seeds ACTIVE + match scored, "
            f"got {r.status_code}: {r.text[:200]}"
        )
        t = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}", headers=auth, timeout=15
        ).json()["data"]
        assert t.get("settled_seq") is not None, (
            f"settling must assign settled_seq, got {t!r}"
        )

        # (a) The backend rejects a post-settlement score edit.
        body = {
            "id": match_id,
            "round_id": round_id,
            "games": [[1, 11], [1, 11]],
            "best_of": 3,
            "stage_item_input1_score": 0,
            "stage_item_input2_score": 2,
            "court_id": None,
            "custom_duration_minutes": None,
            "custom_margin_minutes": None,
        }
        r = requests.put(
            f"{BASE_URL}/api/tournaments/{tid}/matches/{match_id}",
            headers=auth, json=body, timeout=15,
        )
        assert r.status_code == 400, (
            f"post-settlement PUT /matches must 400, got {r.status_code}: {r.text[:200]}"
        )
        assert "settled" in r.text.lower() or "frozen" in r.text.lower(), (
            f"post-settlement rejection must mention settled/frozen, got {r.text}"
        )

        # (b) Ground truth: the saved games and per-side scores are unchanged.
        stages = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/stages", headers=auth, timeout=15
        ).json()["data"]
        unchanged = None
        for s in stages:
            for it in s.get("stage_items", []):
                for rd in it.get("rounds", []):
                    for m in rd.get("matches", []):
                        if m["id"] == match_id:
                            unchanged = m
        assert unchanged is not None
        assert unchanged.get("games") == [[11, 7], [11, 5]], (
            f"settled scores must NOT change, got {unchanged!r}"
        )
        assert unchanged.get("stage_item_input1_score") == 2
        assert unchanged.get("stage_item_input2_score") == 0

        # (c) The \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 button must be GONE on the settings page.
        page.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_role("button", name="\u7533\u8bf7\u79ef\u5206\u7ed3\u7b97")).to_have_count(0)
        # The \u5df2\u7ed3\u7b97 indicator renders somewhere on the page.
        expect(page.locator("body")).to_contain_text("\u5df2\u7ed3\u7b97", timeout=10_000)
    finally:
        _force_cleanup_rated(tid, uids)


# ---- M24b: withdraw button HIDDEN and POST /leave BLOCKED after start ------

WITHDRAW_BUTTON_AFTER_START = "\u9000\u51fa\u8d5b\u4e8b"


def test_withdraw_button_hidden_and_blocked_once_started(
    browser: Browser, shared_club_id: int
) -> None:
    """M24b (negative inverse of M24): once an individual tournament has STARTED
    (a match has been generated), the \u9000\u51fa\u8d5b\u4e8b self-withdraw affordance must
    auto-hide on the results page for an already-joined participant, AND the
    backend must REJECT a withdraw attempt with 400 "\u6bd4\u8d5b\u5df2\u5f00\u59cb".

    Mirrors N11 (which proves the JOIN handler is locked after start) for the
    LEAVE handler. Without this, a regression that left the button rendering or
    re-opened the leave window server-side would let a joined participant
    delete their bound team mid-event.
    """
    tid = _create_nonrated_individual_tournament(shared_club_id)
    member = _register_account("permm24b")
    h = _headers_for(member["token"])
    try:
        # Join BEFORE play starts; instant-join creates the bound team.
        _apply_to_join(tid, member["token"])
        bound_before = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
        }
        assert len(bound_before) == 1, (
            f"join must auto-create exactly one bound team, got {bound_before}"
        )

        # Start play: 4 seeded teams + RR stage + courts + schedule. This is
        # what closes the leave window server-side (tournament_has_matches).
        _build_scheduled_rr(tid)

        # (a) UI: the joined participant still sees the badge, but the
        # \u9000\u51fa\u8d5b\u4e8b button is gone (JoinSection sees can_leave == False).
        ctx = _logged_in_context(browser, member["token"])
        try:
            pg = ctx.new_page()
            pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
            pg.wait_for_load_state("networkidle")
            expect(pg.get_by_text(PARTICIPANT_BADGE, exact=True)).to_be_visible(timeout=15_000)
            expect(
                pg.get_by_role("button", name=WITHDRAW_BUTTON_AFTER_START, exact=True)
            ).to_have_count(0)
        finally:
            ctx.close()

        # (b) my-join-status: can_leave is False once play has started.
        status = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/my-join-status", headers=h, timeout=15
        ).json()["data"]
        assert status["is_participant"] is True, (
            f"the account is still a participant, got {status}"
        )
        assert status.get("can_leave") is False, (
            f"can_leave must be False once play has started, got {status}"
        )

        # (c) Backend: a direct POST /leave is rejected, and the bound team
        # is still present.
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/leave", headers=h, timeout=15
        )
        assert r.status_code == 400, (
            f"leaving a started tournament must 400, got {r.status_code}: {r.text}"
        )
        assert "\u6bd4\u8d5b\u5df2\u5f00\u59cb" in r.text, (
            f"expected the started-leave rejection message, got {r.text}"
        )
        teams_after = {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
        }
        assert bound_before.issubset(teams_after), (
            f"the joined account's bound team must still be present after a "
            f"rejected leave; before={bound_before} after={teams_after}"
        )
    finally:
        _force_cleanup_rated(tid, [member["uid"]])


# ---- N12: non-admin /admin gating renders the 404 stub (no admin form) ------


def test_admin_page_hidden_for_non_admin(browser: Browser) -> None:
    """N12: A logged-in NON-admin visiting /admin must see the 404 stub
    (NotFoundTitle) and NOT the rating-categories / review-queue admin form.

    The page (`frontend/src/pages/admin.tsx`) gates its CategoriesSection +
    ReviewQueueSection behind `user.is_admin`; non-admins get
    `<NotFoundTitle />`. All other tests in the suite log in as the E2E
    account, which IS admin (so it sees the admin form) \u2014 a regression that
    accidentally rendered the admin form to ANY logged-in user (e.g. the
    `!user.is_admin` check inverted or dropped) would be invisible without
    this case.

    Drives a FRESH registered account (created with the default
    `is_admin=False` per `backend/bracket/models/db/user.py`) at /admin and
    asserts: (a) the body shows the 404 marker AND the translated
    not-found title, (b) the admin-only section headings \u79ef\u5206\u7c7b\u522b and
    \u521d\u59cb\u5206\u5ba1\u6838\u961f\u5217 are ABSENT, (c) the \u65b0\u5efa\u7c7b\u522b submit button (the create-form
    affordance) is ABSENT.
    """
    user = _register_account("nonadmin")
    ctx = _logged_in_context(browser, user["token"])
    try:
        # Pre-condition: the account is genuinely non-admin per the API.
        me = requests.get(
            f"{BASE_URL}/api/users/me",
            headers=_headers_for(user["token"]),
            timeout=15,
        )
        me.raise_for_status()
        assert me.json()["data"].get("is_admin") is False, (
            "test prerequisite: fresh accounts must default to is_admin=False"
        )

        pg = ctx.new_page()
        pg.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded")
        # Let the page settle so the SWR /users/me call resolves and the
        # gate flips from the loading skeleton to the 404 branch.
        pg.wait_for_load_state("networkidle", timeout=10_000)

        # (a) 404 stub rendered.
        expect(pg.get_by_text("404", exact=True)).to_be_visible(timeout=15_000)
        # Zh locale's not_found_title from frontend/dist/locales/zh/common.json.
        expect(pg.locator("body")).to_contain_text(
            "\u4f60\u627e\u5230\u4e86\u4e00\u4e2a\u79d8\u5bc6\u5730\u65b9", timeout=5_000
        )

        # (b) The admin section headings must NOT render.
        assert (
            pg.get_by_text("\u79ef\u5206\u7c7b\u522b", exact=True).count() == 0
        ), "non-admin must NOT see the \u79ef\u5206\u7c7b\u522b section heading on /admin"
        assert (
            pg.get_by_text(
                "\u521d\u59cb\u5206\u5ba1\u6838\u961f\u5217", exact=True
            ).count() == 0
        ), "non-admin must NOT see the \u521d\u59cb\u5206\u5ba1\u6838\u961f\u5217 review queue on /admin"

        # (c) The create-category submit button must NOT render.
        assert (
            pg.get_by_role("button", name="\u65b0\u5efa\u7c7b\u522b").count() == 0
        ), "non-admin must NOT see the \u65b0\u5efa\u7c7b\u522b create-category button on /admin"

        pg.close()
    finally:
        ctx.close()