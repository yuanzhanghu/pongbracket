"""Rating system tests (M1-M11).

Asserts:
  M1: The create-tournament modal exposes 个人赛 + 参与积分 + 积分类别 (default
      加华积分), with 参与积分 gated behind 个人赛; settings are fixed at creation.
  M2: Admin back-office at /admin is reachable for the admin account and
      lists rating categories (加华积分 / CanadaChinaTT present).
  M3: Admin: create a new rating category, see it listed, then delete it.
  M4: Admin: 初始分审核 + 结算队列 section renders (empty state OK).
  M5: Category leaderboard page /rating/1/leaderboard renders a table
      (empty state OK).
  M6: Public individual-tournament dashboard shows a 参赛 (instant-join)
      affordance with a 信任创建者 (permanent) checkbox.
  M8: Pre-seed: on a rated individual tournament's teams page, an
      initial-rating control is present per team.
  M9: 申请积分结算 button is present on a rated individual tournament and
      reports status.
  M10: 我的托管管理员 section on /user: add by email / remove.
  M11: Scorers management (记分员) on the tournament: add by email / remove.

The E2E account is a site admin, so admin flows are reachable. Tests
create and clean up their own dedicated rated tournaments so they do not
mutate the shared fixture.
"""
from __future__ import annotations

import time
import uuid

import requests
from playwright.sync_api import Browser, Page, expect

from ._helpers import (
    BASE_URL,
    _api_headers,
    api_create_court,
    api_delete_tournament,
    api_get_stages,
    api_get_tournament,
    api_schedule_matches,
    forfeit_match,
    set_match_result,
)


# ---- helpers ---------------------------------------------------------------


def _create_rated_individual_tournament(
    shared_club_id: int, dashboard_endpoint: str = ""
) -> int:
    """Create a dedicated, rated, individual tournament. Rating settings
    (is_individual=True, rating_category_id=1) are fixed at creation time and
    are immutable afterwards.

    Returns the new tournament id.
    """
    auth = _api_headers()
    tname = f"E2E-Rated-{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": tname,
            "club_id": shared_club_id,
            "dashboard_public": True,
            "dashboard_endpoint": dashboard_endpoint,
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
    # POST returns success only; resolve the id by name.
    r2 = requests.get(
        f"{BASE_URL}/api/tournaments?filter_=ALL", headers=auth, timeout=15
    )
    r2.raise_for_status()
    tid = next(t["id"] for t in r2.json()["data"] if t["name"] == tname)
    return tid


def _create_team_in_tournament(tournament_id: int, name: str) -> int:
    auth = _api_headers()
    r = requests.post(
        f"{BASE_URL}/api/tournaments/{tournament_id}/teams",
        headers=auth,
        json={"name": name, "active": True, "player_names": []},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def _add_scorer(tournament_id: int, email: str) -> int:
    auth = _api_headers()
    r = requests.post(
        f"{BASE_URL}/api/tournaments/{tournament_id}/scorers",
        headers=auth,
        json={"user_email": email},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]["user_id"]


def _remove_scorer(tournament_id: int, user_id: int) -> None:
    auth = _api_headers()
    requests.delete(
        f"{BASE_URL}/api/tournaments/{tournament_id}/scorers/{user_id}",
        headers=auth,
        timeout=15,
    )


def _add_trusted_manager(email: str) -> int:
    auth = _api_headers()
    r = requests.post(
        f"{BASE_URL}/api/me/trusted-managers",
        headers=auth,
        json={"manager_email": email},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]["manager_id"]


def _remove_trusted_manager(manager_id: int) -> None:
    auth = _api_headers()
    requests.delete(
        f"{BASE_URL}/api/me/trusted-managers/{manager_id}",
        headers=auth,
        timeout=15,
    )


# ---- lifecycle helpers (multi-account end-to-end) -------------------------

_APPLICANT_PW = "e2e-Passw0rd!"


def _psql(sql: str) -> str:
    """Run a SQL statement against the dev DB via the postgres container.

    Used only for test teardown of settled tournaments (which the API
    intentionally refuses to delete) and for ground-truth assertions.
    """
    import subprocess

    out = subprocess.run(
        [
            "docker", "exec", "bracket-dev-postgres-1",
            "psql", "-U", "bracket_dev", "-d", "bracket_dev", "-tAc", sql,
        ],
        capture_output=True, text=True, timeout=15,
    )
    assert out.returncode == 0, f"psql failed: {out.stderr!r} (sql={sql!r})"
    return out.stdout.strip()


def _headers_for(token: str) -> dict:
    return {"Authorization": f"bearer {token}", "Accept": "application/json"}


def _register_account(prefix: str) -> dict:
    """Register a fresh account and return its email/name/token/user id.

    The backend normalizes emails to lowercase (sql/users.py normalize_email),
    so we lowercase here so the value we carry around matches what the DB stores
    and what the UI renders."""
    email = f"e2e-{prefix}-{uuid.uuid4().hex[:8]}@local.test".lower()
    name = f"E2E {prefix} {uuid.uuid4().hex[:4]}"
    requests.post(
        f"{BASE_URL}/api/users/register",
        json={
            "email": email,
            "name": name,
            "password": _APPLICANT_PW,
            "captcha_token": "e2e-dev",
        },
        timeout=15,
    ).raise_for_status()
    tok = requests.post(
        f"{BASE_URL}/api/token",
        data={"grant_type": "password", "username": email, "password": _APPLICANT_PW},
        timeout=15,
    )
    tok.raise_for_status()
    token = tok.json()["access_token"]
    me = requests.get(f"{BASE_URL}/api/users/me", headers=_headers_for(token), timeout=15)
    me.raise_for_status()
    return {"email": email, "name": name, "token": token, "uid": me.json()["data"]["id"]}


def _apply_to_join(tid: int, token: str, trust_creator: bool = False) -> None:
    r = requests.post(
        f"{BASE_URL}/api/tournaments/{tid}/join-requests",
        headers=_headers_for(token),
        json={"trust_creator": trust_creator},
        timeout=15,
    )
    r.raise_for_status()


def _build_stage_with_one_match(tid: int) -> tuple[int, int]:
    """Create a stage + a 2-team round-robin (one match between the two bound
    teams). Returns (match_id, round_id)."""
    auth = _api_headers()
    requests.post(
        f"{BASE_URL}/api/tournaments/{tid}/stages", headers=auth, json={"name": "S1"}, timeout=15
    ).raise_for_status()
    stages = requests.get(
        f"{BASE_URL}/api/tournaments/{tid}/stages", headers=auth, timeout=15
    ).json()["data"]
    stage_id = stages[-1]["id"]
    requests.post(
        f"{BASE_URL}/api/tournaments/{tid}/stage_items/round_robin_groups",
        headers=auth,
        json={"stage_id": stage_id, "group_count": 1, "team_count": 2},
        timeout=15,
    ).raise_for_status()
    stages = requests.get(
        f"{BASE_URL}/api/tournaments/{tid}/stages", headers=auth, timeout=15
    ).json()["data"]
    for s in stages:
        for it in s.get("stage_items", []):
            for rd in it.get("rounds", []):
                for m in rd.get("matches", []):
                    return m["id"], rd["id"]
    raise RuntimeError("no match produced by the round-robin")


def _score_match(tid: int, match_id: int, round_id: int, games: list) -> None:
    s1 = sum(1 for g in games if g[0] > g[1])
    s2 = sum(1 for g in games if g[1] > g[0])
    requests.put(
        f"{BASE_URL}/api/tournaments/{tid}/matches/{match_id}",
        headers=_api_headers(),
        json={
            "id": match_id,
            "round_id": round_id,
            "games": games,
            "best_of": 3,
            "stage_item_input1_score": s1,
            "stage_item_input2_score": s2,
            "court_id": None,
            "custom_duration_minutes": None,
            "custom_margin_minutes": None,
        },
        timeout=15,
    ).raise_for_status()


def _force_cleanup_rated(tid: int, user_ids: list) -> None:
    """Tear down a (possibly settled) rated individual tournament.

    A settled tournament is frozen against the normal API delete path, so we
    first clear the ledger + unfreeze via psql, then cascade-delete the
    stage_items/stages/teams/players/tournament through the API.
    """
    auth = _api_headers()
    try:
        if user_ids:
            ids = ",".join(str(u) for u in user_ids)
            _psql(f"DELETE FROM rating_events WHERE tournament_id = {tid};")
            _psql(f"DELETE FROM player_ratings WHERE user_id IN ({ids});")
        _psql(f"UPDATE tournaments SET settled_seq = NULL, settled_at = NULL WHERE id = {tid};")
    except Exception:
        pass
    try:
        stages = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/stages", headers=auth, timeout=15
        ).json().get("data", [])
        for s in stages:
            for it in s.get("stage_items", []):
                requests.delete(
                    f"{BASE_URL}/api/tournaments/{tid}/stage_items/{it['id']}",
                    headers=auth, timeout=15,
                )
            requests.delete(
                f"{BASE_URL}/api/tournaments/{tid}/stages/{s['id']}", headers=auth, timeout=15
            )
        teams = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/teams", headers=auth, timeout=15
        ).json().get("data", {}).get("teams", [])
        for tm in teams:
            requests.delete(
                f"{BASE_URL}/api/tournaments/{tid}/teams/{tm['id']}", headers=auth, timeout=15
            )
        players = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/players", headers=auth, timeout=15
        ).json().get("data", {}).get("players", [])
        for p in players:
            requests.delete(
                f"{BASE_URL}/api/tournaments/{tid}/players/{p['id']}", headers=auth, timeout=15
            )
        requests.delete(f"{BASE_URL}/api/tournaments/{tid}", headers=auth, timeout=15)
    except Exception:
        pass


# ---- M1: Tournament settings expose rating toggles + select ---------------


def test_create_modal_exposes_rating_options(page: Page, shared_club_id: int) -> None:
    """M1: the create-tournament modal exposes 个人赛 + 参与积分 + 积分类别, with
    参与积分 gated behind 个人赛 (only individual tournaments can be rated). Rating
    settings are fixed at creation; the settings page then shows them read-only.
    """
    # Part 1: the create modal exposes the controls with the correct gating.
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.get_by_role("button", name="创建比赛").first.click()
    modal = page.locator(".mantine-Modal-content").last
    expect(modal).to_be_visible(timeout=10_000)
    # 个人赛 is checked by default, so 参与积分 shows straight away; unchecking 个人赛
    # hides it again (only individual tournaments can be rated). (exact=True so the
    # 个人赛 checkbox's description text — which mentions 参与积分 — is not matched.)
    expect(modal.get_by_text("个人赛", exact=True)).to_be_visible(timeout=5_000)
    expect(modal.get_by_text("参与积分", exact=True)).to_be_visible(timeout=5_000)
    modal.get_by_text("个人赛", exact=True).click()
    expect(modal.get_by_text("参与积分", exact=True)).to_have_count(0, timeout=5_000)
    modal.get_by_text("个人赛", exact=True).click()
    expect(modal.get_by_text("参与积分", exact=True)).to_be_visible(timeout=5_000)
    modal.get_by_text("参与积分", exact=True).click()
    expect(modal.get_by_text("积分类别", exact=True)).to_be_visible(timeout=5_000)
    page.keyboard.press("Escape")

    # Part 2: creation persists the (immutable) rating settings; settings is read-only.
    tid = _create_rated_individual_tournament(shared_club_id)
    try:
        body = api_get_tournament(tid)
        assert body.get("is_individual") is True, (
            f"expected is_individual=True, got {body.get('is_individual')}"
        )
        assert body.get("rating_category_id") == 1, (
            f"expected rating_category_id=1 (加华积分), got {body.get('rating_category_id')}"
        )
        page.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
        expect(page.get_by_text("积分设置", exact=True)).to_be_visible(timeout=15_000)
        expect(page.locator("body")).to_contain_text("创建后不可修改", timeout=5_000)
    finally:
        api_delete_tournament(tid)


# ---- M2: Admin back-office at /admin is reachable ------------------------


def test_admin_page_lists_rating_categories(page: Page) -> None:
    """M2: Admin back-office at /admin is reachable for the admin account
    and lists rating categories (加华积分 / CanadaChinaTT present).
    """
    page.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded")
    # The admin page renders 积分类别 + a table with the seeded category.
    expect(page.get_by_text("积分类别", exact=True)).to_be_visible(timeout=15_000)
    expect(page.locator("body")).to_contain_text("加华积分", timeout=10_000)
    # The seeded category key is CanadaChinaTT.
    expect(page.locator("body")).to_contain_text("CanadaChinaTT", timeout=10_000)


# ---- M3: Admin: create / list / delete a rating category ------------------


def test_admin_create_and_delete_rating_category(page: Page) -> None:
    """M3: Admin: create a new rating category, see it listed, then delete it.

    Drives the admin form end-to-end: type name + key + algorithm, click
    新建类别, assert the new row appears, then click its delete button
    and assert the row disappears.
    """
    cat_name = f"E2E-Cat-{uuid.uuid4().hex[:6]}"
    cat_key = f"e2e_cat_{uuid.uuid4().hex[:8]}"
    page.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded")
    expect(page.get_by_text("积分类别", exact=True)).to_be_visible(timeout=15_000)

    # The form has three TextInputs labeled 名称 / 标识 (key) / 算法 and a
    # 新建类别 submit button.
    page.get_by_label("名称", exact=True).fill(cat_name)
    page.get_by_label("标识 (key)", exact=True).fill(cat_key)
    # The algorithm field defaults to "elo" so we leave it.
    page.get_by_role("button", name="新建类别").click()

    # Poll the API for the new category (SWR mutate is async).
    cat_id = None
    for _ in range(20):
        page.wait_for_timeout(500)
        r = requests.get(
            f"{BASE_URL}/api/rating-categories", headers=_api_headers(), timeout=15
        )
        if r.status_code == 200:
            for c in r.json().get("data", []):
                if c.get("key") == cat_key:
                    cat_id = c["id"]
                    break
        if cat_id is not None:
            break
    assert cat_id is not None, f"new category {cat_key!r} not found via API"

    # The new category should now be rendered in the admin table.
    expect(page.locator("body")).to_contain_text(cat_name, timeout=10_000)

    # Find the row's delete (trash) button and click it.
    row = page.locator("tr", has=page.get_by_text(cat_name, exact=True)).first
    row.locator("button").last.click()
    # Poll until the API confirms deletion.
    for _ in range(20):
        page.wait_for_timeout(500)
        r = requests.get(
            f"{BASE_URL}/api/rating-categories", headers=_api_headers(), timeout=15
        )
        if r.status_code == 200:
            present = any(c.get("id") == cat_id for c in r.json().get("data", []))
            if not present:
                break
    else:
        assert False, f"category {cat_key!r} still present after delete"


# ---- M4: Admin 初始分审核 + 结算队列 section renders -----------------------


def test_admin_review_queue_section_renders(page: Page) -> None:
    """M4: Admin 初始分审核 + 结算队列 section renders (empty state OK).

    The section shows 暂无待审核并结算的赛事。 when nothing is queued.
    """
    page.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded")
    expect(page.get_by_text("初始分审核 + 结算队列", exact=True)).to_be_visible(timeout=15_000)
    # The empty-state message is rendered in the page.
    expect(page.locator("body")).to_contain_text("暂无待审核并结算的赛事", timeout=10_000)


# ---- M5: Category leaderboard renders -------------------------------------


def test_leaderboard_page_renders(page: Page) -> None:
    """M5: Category leaderboard page /rating/1/leaderboard renders a table.

    The seeded category id=1 is CanadaChinaTT / 加华积分. The page renders
    a 积分排行榜 title and a Table with 排名 / 姓名 / 当前积分 / 比赛场次
    column headers. An empty state (no rated users yet) is acceptable.
    """
    page.goto(f"{BASE_URL}/rating/1/leaderboard", wait_until="domcontentloaded")
    expect(page.get_by_text("积分排行榜", exact=True)).to_be_visible(timeout=15_000)
    # The table headers should render even when empty.
    expect(page.locator("body")).to_contain_text("排名", timeout=10_000)
    expect(page.locator("body")).to_contain_text("当前积分", timeout=10_000)
    expect(page.locator("body")).to_contain_text("比赛场次", timeout=10_000)


# ---- M6: Public individual-tournament results page shows 参赛 (auto-join) --


def test_individual_tournament_results_shows_join_section(
    browser: Browser, shared_club_id: int
) -> None:
    """M6: the public results page of an individual tournament shows a 参赛
    (instant-join) affordance with a 信任创建者 (permanent) checkbox.

    The join section is a spectator tool, so it is asserted as an outsider
    account — the owner never sees it. N2/N3 cover clicking through the join;
    this test pins the trust checkbox and its 永久生效 warning.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    outsider = _register_account("m6join")
    ctx = browser.new_context(base_url=BASE_URL)
    ctx.add_init_script(
        'window.localStorage.setItem(\'login\', \'{"access_token":"%s"}\');' % outsider["token"]
    )
    try:
        pg = ctx.new_page()
        pg.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        # JoinSection renders a \u53c2\u8d5b (instant-join) button + the \u201c\u5141\u8bb8\u521b\u5efa\u8005...\u201d
        # trust checkbox + an Alert explaining the permanence of the checkbox.
        expect(pg.get_by_role("button", name="\u53c2\u8d5b", exact=True)).to_be_visible(timeout=15_000)
        expect(pg.locator("body")).to_contain_text("\u5141\u8bb8\u521b\u5efa\u8005", timeout=5_000)
        # The Alert text mentions \u6c38\u4e45\u751f\u6548.
        expect(pg.locator("body")).to_contain_text("\u6c38\u4e45\u751f\u6548", timeout=5_000)
    finally:
        ctx.close()
        _force_cleanup_rated(tid, [outsider["uid"]])


# ---- M8: Pre-seed control on rated individual tournament teams page --------


def test_seed_ratings_section_renders_on_teams_page(
    page: Page, shared_club_id: int
) -> None:
    """M8: On a rated individual tournament's teams page, an initial-rating
    control is present per team.

    Creates a dedicated rated individual tournament, inserts a team directly
    via psql (the API now correctly forbids free-text team creation on
    individual tournaments \u2014 see M12), navigates to /teams, and asserts the
    \u521d\u59cb\u79ef\u5206\u9884\u8bbe Fieldset renders a NumberInput + \u4fdd\u5b58 button per team.
    """
    import subprocess

    tid = _create_rated_individual_tournament(shared_club_id)
    team_name = f"E2E-Seeded-{uuid.uuid4().hex[:6]}"
    sql = (
        "INSERT INTO teams (name, active, created, tournament_id) "
        f"VALUES ('{team_name}', true, NOW(), {tid});"
    )
    out = subprocess.run(
        [
            "docker", "exec", "bracket-dev-postgres-1",
            "psql", "-U", "bracket_dev", "-d", "bracket_dev", "-c", sql,
        ],
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 0, (
        f"psql insert failed: rc={out.returncode}, stderr={out.stderr!r}"
    )
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded"
        )
        expect(page.locator("body")).to_contain_text(team_name, timeout=15_000)
        # The initial-rating control now lives in the team EDIT modal (commit
        # 61fc848 moved it off the teams page into team_update_modal.tsx). Open
        # the row's \u7f16\u8f91 (edit) button and assert the \u521d\u59cb\u79ef\u5206 Fieldset +
        # NumberInput render for this rated individual tournament.
        row = page.locator("tr", has=page.get_by_text(team_name, exact=True)).first
        row.get_by_role("button", name="\u7f16\u8f91", exact=True).first.click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible(timeout=10_000)
        # Fieldset legend \u521d\u59cb\u79ef\u5206 + the NumberInput placeholder \"\u4f8b\u5982 1500\".
        expect(dialog.get_by_text("\u521d\u59cb\u79ef\u5206", exact=True)).to_be_visible(
            timeout=5_000
        )
        dialog.get_by_placeholder("\u4f8b\u5982 1500").first.wait_for(
            state="visible", timeout=5_000
        )
    finally:
        # Clean up the unbound team row we inserted, then delete the tournament.
        try:
            subprocess.run(
                [
                    "docker", "exec", "bracket-dev-postgres-1",
                    "psql", "-U", "bracket_dev", "-d", "bracket_dev",
                    "-c", f"DELETE FROM teams WHERE tournament_id = {tid};",
                ],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            pass
        api_delete_tournament(tid)


# ---- M9: 申请积分结算 button + status ------------------------------------


def test_settlement_button_renders_on_rated_tournament(
    page: Page, shared_club_id: int
) -> None:
    """M9: 申请积分结算 button is present on a rated individual tournament
    and reports status.

    Creates a dedicated rated individual tournament, navigates to
    settings, and asserts the 积分结算 Fieldset + 申请积分结算 button +
    the status message render.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded"
        )
        # The SettlementSection Fieldset with legend 积分结算.
        expect(page.get_by_text("积分结算", exact=True)).to_be_visible(timeout=15_000)
        # The status message (ready / awaiting review / settled).
        expect(page.get_by_role("button", name="申请积分结算")).to_be_visible(
            timeout=10_000
        )
        # The leaderboard link.
        expect(page.locator("body")).to_contain_text("查看积分排行榜", timeout=5_000)
    finally:
        api_delete_tournament(tid)


# ---- M10: 我的托管管理员 section on /user --------------------------------


def test_trusted_managers_add_and_remove(page: Page) -> None:
    """M10: \u6211\u7684\u6258\u7ba1\u7ba1\u7406\u5458 section on /user: add by email AND remove via UI.

    Both halves are exercised through the UI:
      * Add: type the manager's email and click \u6dfb\u52a0; poll the API for
        the new manager id; assert the row renders.
      * Remove: click the row's red trash ActionIcon (the only red
        action button in the row); assert the row disappears from the
        rendered table; the API confirms the manager is gone.
    """
    # Create a second user we can add as a manager (the backend requires
    # the email to match an existing account).
    manager_email = f"e2e-mgr-{uuid.uuid4().hex[:6]}@local.test"
    manager_password = "e2e-Passw0rd!"
    manager_name = f"E2E Manager {uuid.uuid4().hex[:4]}"
    requests.post(
        f"{BASE_URL}/api/users/register",
        json={
            "email": manager_email,
            "name": manager_name,
            "password": manager_password,
            "captcha_token": "e2e-dev",
        },
        timeout=15,
    )

    page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded")
    expect(page.get_by_text("\u5141\u8bb8\u62c9\u6211\u8fdb\u5165\u6bd4\u8d5b\u7684\u4eba\u5458", exact=True)).to_be_visible(timeout=15_000)

    # Add by email via the UI.
    page.get_by_label("\u6309\u90ae\u7bb1\u6216\u540d\u79f0\u6dfb\u52a0\uff08\u5141\u8bb8\u5176\u4eca\u540e\u628a\u6211\u62c9\u8fdb\u6bd4\u8d5b\uff09", exact=True).fill(manager_email)
    page.get_by_role("button", name="\u6dfb\u52a0").click()

    # Poll the API until the new manager appears.
    new_id = None
    for _ in range(20):
        page.wait_for_timeout(500)
        r = requests.get(
            f"{BASE_URL}/api/me/trusted-managers", headers=_api_headers(), timeout=15
        )
        if r.status_code == 200:
            for m in r.json().get("data", []):
                if m.get("name") == manager_name:
                    new_id = m.get("manager_id")
                    break
        if new_id is not None:
            break
    assert new_id is not None, f"manager {manager_email!r} not found via API"

    # The manager row should render in the table (name only; emails are private).
    row = page.locator("tr", has=page.get_by_text(manager_name, exact=True)).first
    expect(row).to_be_visible(timeout=10_000)

    # Remove via the row's UI delete button (the red ActionIcon).
    # ActionIcon renders as a button; the delete one has the red color
    # variant. We pick the only button in the row's last <td>.
    delete_btn = row.locator("button").last
    delete_btn.click()

    # The row must disappear from the rendered table.
    expect(
        page.locator("tr", has=page.get_by_text(manager_name, exact=True))
    ).to_have_count(0, timeout=10_000)

    # And the API confirms removal.
    for _ in range(10):
        page.wait_for_timeout(300)
        r = requests.get(
            f"{BASE_URL}/api/me/trusted-managers", headers=_api_headers(), timeout=15
        )
        present = any(
            m.get("manager_id") == new_id for m in r.json().get("data", [])
        )
        if not present:
            break
    else:
        assert False, f"manager {manager_email!r} still present in API after UI remove"


# ---- M11: Scorers management on the tournament ---------------------------


def test_scorers_management_add_and_remove(page: Page, shared_club_id: int) -> None:
    """M11: Scorers management (\u8bb0\u5206\u5458) on the tournament: add by email AND
    remove via UI.

    Both halves are exercised through the UI: add via the form, remove
    via the row's red trash ActionIcon. The API is polled afterwards
    as ground truth.
    """
    # Seed a second user to be the scorer.
    scorer_email = f"e2e-scorer-{uuid.uuid4().hex[:6]}@local.test"
    scorer_name = f"E2E Scorer {uuid.uuid4().hex[:4]}"
    requests.post(
        f"{BASE_URL}/api/users/register",
        json={
            "email": scorer_email,
            "name": scorer_name,
            "password": "e2e-Passw0rd!",
            "captcha_token": "e2e-dev",
        },
        timeout=15,
    )

    tid = _create_rated_individual_tournament(shared_club_id)
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded"
        )
        # The \u8bb0\u5206\u5458\u7ba1\u7406 Fieldset.
        expect(page.get_by_text("\u8bb0\u5206\u5458\u7ba1\u7406", exact=True)).to_be_visible(timeout=15_000)

        # Add via the UI form.
        page.get_by_label("\u6309\u90ae\u7bb1\u6216\u540d\u79f0\u6dfb\u52a0\u8bb0\u5206\u5458", exact=True).fill(scorer_email)
        page.get_by_role("button", name="\u6dfb\u52a0").click()

        # Poll the API for the new scorer.
        scorer_id = None
        for _ in range(20):
            page.wait_for_timeout(500)
            r = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/scorers",
                headers=_api_headers(),
                timeout=15,
            )
            if r.status_code == 200:
                for s in r.json().get("data", []):
                    if s.get("name") == scorer_name:
                        scorer_id = s.get("user_id")
                        break
            if scorer_id is not None:
                break
        assert scorer_id is not None, f"scorer {scorer_email!r} not found via API"

        # The scorer row should render. Scope to the \u8bb0\u5206\u5458\u7ba1\u7406
        # fieldset so we don't pick up stray rows from elsewhere on
        # the settings page.
        scorers_fs = page.locator(
            "fieldset",
            has=page.get_by_text("\u8bb0\u5206\u5458\u7ba1\u7406", exact=True),
        ).first
        row = scorers_fs.locator(
            "tr", has=page.get_by_text(scorer_name, exact=True)
        ).first
        expect(row).to_be_visible(timeout=10_000)

        # Remove via the row's UI delete button (the red ActionIcon).
        row.locator("button").last.click()

        # The row must disappear from the table.
        expect(
            scorers_fs.locator(
                "tr", has=page.get_by_text(scorer_name, exact=True)
            )
        ).to_have_count(0, timeout=10_000)

        # And the API confirms removal.
        for _ in range(10):
            page.wait_for_timeout(300)
            r = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/scorers",
                headers=_api_headers(),
                timeout=15,
            )
            present = any(
                s.get("user_id") == scorer_id for s in r.json().get("data", [])
            )
            if not present:
                break
        else:
            assert False, (
                f"scorer {scorer_email!r} still present in API after UI remove"
            )
    finally:
        api_delete_tournament(tid)


# ---- M12: Individual tournament has NO free-text team-create modal --------


def test_individual_tournament_has_no_freetext_team_create(
    page: Page, shared_club_id: int
) -> None:
    """M12: After creating an individual rated tournament, the teams page must
    NOT offer a free-text \"add team\" entry (no team_create_modal with a name
    TextInput). Only the \u76f4\u63a5\u6dfb\u52a0\u53c2\u8d5b\u8005 picker (select a hosted account)
    is allowed.

    Also asserts the backend rejects POST /tournaments/{id}/teams with a name on
    an individual tournament (400) and still accepts it on a non-individual one.
    """
    # Part 1: UI \u2014 individual rated tournament has no \u6dfb\u52a0\u961f\u4f0d affordance
    # but does render the \u76f4\u63a5\u6dfb\u52a0\u53c2\u8d5b\u8005 fieldset.
    tid_ind = _create_rated_individual_tournament(shared_club_id)
    # Non-individual control tournament for the UI/API contrast.
    auth = _api_headers()
    ctrl_name = f"E2E-Ctrl-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": ctrl_name,
            "club_id": shared_club_id,
            "dashboard_public": True,
            "dashboard_endpoint": "",
            "players_can_be_in_multiple_teams": False,
            "auto_assign_courts": True,
            "start_time": "2030-01-01T00:00:00Z",
            "duration_minutes": 10,
            "margin_minutes": 5,
        },
        timeout=15,
    ).raise_for_status()
    r = requests.get(
        f"{BASE_URL}/api/tournaments?filter_=ALL", headers=auth, timeout=15
    )
    r.raise_for_status()
    tid_ctrl = next(t["id"] for t in r.json()["data"] if t["name"] == ctrl_name)

    try:
        # Individual tournament teams page: no free-text add-team button.
        page.goto(
            f"{BASE_URL}/tournaments/{tid_ind}/teams", wait_until="domcontentloaded"
        )
        # The \u76f4\u63a5\u6dfb\u52a0\u53c2\u8d5b\u8005 fieldset MUST be present.
        expect(
            page.get_by_text("\u76f4\u63a5\u6dfb\u52a0\u53c2\u8d5b\u8005", exact=True)
        ).to_be_visible(timeout=15_000)
        # The free-text \u6dfb\u52a0\u961f\u4f0d button MUST be absent. We assert count==0
        # (rather than .to_be_hidden()) because the button never renders at
        # all on an individual tournament \u2014 TeamCreateModal is gated out.
        assert (
            page.get_by_role("button", name="\u6dfb\u52a0\u961f\u4f0d", exact=True).count() == 0
        ), "individual tournament must NOT render the \u6dfb\u52a0\u961f\u4f0d button"
        # And the create-team modal title \u521b\u5efa\u961f\u4f0d must not be present.
        assert (
            page.get_by_text("\u521b\u5efa\u961f\u4f0d", exact=True).count() == 0
        ), "individual tournament must NOT render the \u521b\u5efa\u961f\u4f0d modal"

        # Control: non-individual tournament DOES render the add-team button.
        page.goto(
            f"{BASE_URL}/tournaments/{tid_ctrl}/teams",
            wait_until="domcontentloaded",
        )
        expect(
            page.get_by_role("button", name="\u6dfb\u52a0\u961f\u4f0d", exact=True).first
        ).to_be_visible(timeout=15_000)

        # Part 2: API \u2014 backend rejects free-text team creation on the individual
        # tournament with 400, and accepts it on the control.
        team_name = f"E2E-FreeTextTeam-{uuid.uuid4().hex[:6]}"
        r_ind = requests.post(
            f"{BASE_URL}/api/tournaments/{tid_ind}/teams",
            headers=_api_headers(),
            json={"name": team_name, "active": True, "player_names": []},
            timeout=15,
        )
        assert r_ind.status_code == 400, (
            f"expected 400 on individual tournament free-text team create, "
            f"got {r_ind.status_code}: {r_ind.text[:200]}"
        )

        r_ctrl = requests.post(
            f"{BASE_URL}/api/tournaments/{tid_ctrl}/teams",
            headers=_api_headers(),
            json={"name": team_name, "active": True, "player_names": []},
            timeout=15,
        )
        assert r_ctrl.status_code in (200, 201), (
            f"expected 2xx on non-individual free-text team create, "
            f"got {r_ctrl.status_code}: {r_ctrl.text[:200]}"
        )
    finally:
        api_delete_tournament(tid_ind)
        api_delete_tournament(tid_ctrl)


# ---- M13: Settlement is blocked on an empty tournament --------------------


def test_settlement_blocked_on_empty_tournament(
    page: Page, shared_club_id: int
) -> None:
    """M13: \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 must be impossible with nothing to settle.

    Creates a rated individual tournament with ZERO teams and ZERO matches and
    asserts:
      - POST /tournaments/{id}/settlement-request returns 400 with a
        not-ready / no-completed-matches message.
      - The tournament's settled_seq stays null after the rejected request.
      - Driving the UI button surfaces the rejection: settled_seq is still
        null, the \u5df2\u7ed3\u7b97 badge is NOT shown, and the \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 button
        remains visible (the request was not accepted).
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    try:
        # Pre-condition: empty tournament, not yet settled.
        body = api_get_tournament(tid)
        assert body.get("settled_seq") is None
        # API ground truth.
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/settlement-request",
            headers=_api_headers(),
            timeout=15,
        )
        assert r.status_code == 400, (
            f"expected 400 on empty-tournament settlement, got {r.status_code}: {r.text[:200]}"
        )
        msg = (r.json().get("detail") or "").lower()
        assert "没有已完成的对阵" in msg or "结算" in msg, (
            f"expected a not-ready message, got: {msg!r}"
        )
        # settled_seq must stay null.
        body2 = api_get_tournament(tid)
        assert body2.get("settled_seq") is None, (
            f"settled_seq must remain null after rejected settlement, got {body2.get('settled_seq')}"
        )

        # UI: drive the button and confirm the tournament does not become \u5df2\u7ed3\u7b97.
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded"
        )
        button = page.get_by_role("button", name="\u7533\u8bf7\u79ef\u5206\u7ed3\u7b97")
        expect(button).to_be_visible(timeout=15_000)
        button.click()
        # The frontend must surface the backend's 400 to the user via a
        # Mantine error notification (handleRequestError in adapter.tsx renders
        # title="An error occurred" + the detail text). A regression where the
        # frontend silently swallowed the failure would still leave settled_seq
        # null (so the post-reload assertions below would pass) \u2014 we lock the
        # toast in here before reloading so the surface-the-error contract is
        # actually exercised.
        toast_title = page.get_by_text("操作失败", exact=True).first
        expect(toast_title).to_be_visible(timeout=10_000)
        # The toast body should mention the backend's "no completed matches" /
        # "settle" error detail \u2014 not just a generic title.
        notif = page.locator(
            ".mantine-Notification-root, .mantine-Notifications-notification"
        ).filter(has_text="操作失败").first
        expect(notif).to_be_visible(timeout=5_000)
        notif_text = notif.inner_text().lower()
        assert (
            "没有已完成的对阵" in notif_text or "结算" in notif_text
        ), f"settlement error toast should explain the failure, got: {notif_text!r}"
        # The button must still be there and the \u5df2\u7ed3\u7b97 badge absent.
        body3 = api_get_tournament(tid)
        assert body3.get("settled_seq") is None, (
            f"settled_seq must remain null after UI click, got {body3.get('settled_seq')}"
        )
        # Reload settings; \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 button still visible (not replaced
        # by a \u5df2\u7ed3\u7b97 badge).
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded"
        )
        expect(
            page.get_by_role("button", name="\u7533\u8bf7\u79ef\u5206\u7ed3\u7b97")
        ).to_be_visible(timeout=15_000)
        assert (
            page.get_by_text("\u5df2\u7ed3\u7b97", exact=True).count() == 0
        ), "tournament must NOT show \u5df2\u7ed3\u7b97 after a rejected settlement"
    finally:
        api_delete_tournament(tid)


# ---- M13b: Settlement blocked when matches exist but are ALL UNPLAYED --------


def test_settlement_blocked_on_unplayed_matches(shared_club_id: int) -> None:
    """M13b: the distinct "matches all unplayed" cell of the settlement matrix.

    A rated individual tournament with TWO bound applicants (via instant-join)
    and a created round-robin match that has NOT been scored must still reject
    settlement with 400 ("no completed matches"). settled_seq stays null.

    This is different from M13 (zero teams / zero matches) and M14 (unbound
    teams): here teams ARE bound and a match EXISTS, but no scores were entered.
    A settlement validator that counted existing matches as "settleable" before
    checking whether they're completed would silently settle an unplayed
    tournament \u2014 this test catches that code path.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    applicant_a = _register_account("m13bA")
    applicant_b = _register_account("m13bB")
    uids = [applicant_a["uid"], applicant_b["uid"]]
    try:
        # Instant-join both applicants \u2014 creates two bound 1-player teams.
        _apply_to_join(tid, applicant_a["token"])
        _apply_to_join(tid, applicant_b["token"])
        teams = []
        for _ in range(20):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
            if len(teams) >= 2:
                break
            time.sleep(0.5)
        assert len(teams) == 2, f"expected 2 bound teams, got {len(teams)}"
        bound = _psql(f"SELECT count(*) FROM teams_x_users WHERE tournament_id = {tid};")
        assert bound == "2", f"expected 2 account bindings, got {bound!r}"

        # Seed initial ratings for both applicants (a rated tournament requires
        # every player to have an initial/formal rating before matches can be
        # generated \u2014 the backend rejects stage-item creation with "\u6709 N \u540d\u9009\u624b
        # \u5c1a\u672a\u914d\u7f6e\u521d\u59cb/\u6b63\u5f0f\u79ef\u5206" otherwise). We seed via psql (the UI path is
        # exercised by M15/M8); the point of THIS test is the unplayed-matches
        # settlement rejection, not the seed flow.
        for uid in uids:
            _psql(
                "INSERT INTO player_ratings (user_id, category_id, initial_rating, "
                "current_rating, status) VALUES "
                f"({uid}, 1, 1500, 1500, 'ACTIVE');"
            )

        # Create an RR stage item (1 match between the 2 bound teams) but do NOT
        # score it.
        match_id, round_id = _build_stage_with_one_match(tid)
        # Confirm the match exists and is unscored (no games).
        auth = _api_headers()
        stages = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/stages", headers=auth, timeout=15
        ).json()["data"]
        found_unscored = False
        for s in stages:
            for it in s.get("stage_items", []):
                for rd in it.get("rounds", []):
                    for m in rd.get("matches", []):
                        if m["id"] == match_id and not m.get("games"):
                            found_unscored = True
        assert found_unscored, "the RR match must exist and be unscored"

        # Pre-condition: not yet settled.
        assert api_get_tournament(tid).get("settled_seq") is None

        # API: settlement must be rejected with 400 (no completed matches).
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/settlement-request",
            headers=auth,
            timeout=15,
        )
        assert r.status_code == 400, (
            f"expected 400 on unplayed-matches settlement, got {r.status_code}: {r.text[:200]}"
        )
        msg = (r.json().get("detail") or "").lower()
        assert (
            "没有已完成的对阵" in msg or "结算" in msg or "没有录入结果" in msg
        ), f"expected a not-ready message, got: {msg!r}"
        # settled_seq must stay null.
        assert api_get_tournament(tid).get("settled_seq") is None, (
            "settled_seq must remain null after rejected settlement on unplayed matches"
        )
    finally:
        _force_cleanup_rated(tid, uids)


# ---- M14: Settlement is blocked when team(s) are unbound ------------------

# ---- M14: Settlement is blocked when team(s) are unbound ------------------


def test_settlement_blocked_when_team_unbound(shared_club_id: int) -> None:
    """M14: An individual tournament whose team(s) are not bound to an account
    must block settlement.

    Setup: create a rated individual tournament and insert a free-text team via
    psql (bypassing the backend's `disallow_individual_tournament` guard) so the
    team is unbound (no teams_x_users row). The settlement validation then has
    to fall through the unbound-count check.

    Assertion: POST /tournaments/{id}/settlement-request returns 400 with a
    "not yet linked to an account"/blocked message; settled_seq stays null.
    """
    import subprocess

    tid = _create_rated_individual_tournament(shared_club_id)
    try:
        # Insert an unbound team directly via psql.
        team_name = f"E2E-Unbound-{uuid.uuid4().hex[:6]}"
        sql = (
            "INSERT INTO teams (name, active, created, tournament_id) "
            f"VALUES ('{team_name}', true, NOW(), {tid});"
        )
        out = subprocess.run(
            [
                "docker",
                "exec",
                "bracket-dev-postgres-1",
                "psql",
                "-U",
                "bracket_dev",
                "-d",
                "bracket_dev",
                "-c",
                sql,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert out.returncode == 0, (
            f"psql insert failed: rc={out.returncode}, stderr={out.stderr!r}"
        )

        # Settlement must be rejected.
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/settlement-request",
            headers=_api_headers(),
            timeout=15,
        )
        assert r.status_code == 400, (
            f"expected 400 on unbound-team settlement, got {r.status_code}: {r.text[:200]}"
        )
        msg = (r.json().get("detail") or "").lower()
        # The unbound team has zero matches, so the settlement validator may
        # trip EITHER the unbound-team gate ("linked to an account") OR the
        # no-completed-matches gate ("no completed matches" / "not yet" /
        # "settle" / "no recorded result") depending on validation ordering.
        # Both rejections are correct for this setup; the regression we guard
        # against is settlement SUCCEEDING despite an unbound team. Assert a
        # rejection happened (400 above) and settled_seq stays null (below);
        # accept either gate's message so a backend reorder of validation steps
        # does not break this test.
        assert (
            "未绑定账号" in msg or "没有已完成的对阵" in msg or "结算" in msg or "没有录入结果" in msg
        ), f"expected a settlement-rejection message, got: {msg!r}"

        # settled_seq must remain null.
        body = api_get_tournament(tid)
        assert body.get("settled_seq") is None, (
            f"settled_seq must remain null after rejected settlement, got {body.get('settled_seq')}"
        )
    finally:
        # Clean up unbound team rows we inserted (FK cascade via the tournament
        # delete also handles this, but be explicit).
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "bracket-dev-postgres-1",
                    "psql",
                    "-U",
                    "bracket_dev",
                    "-d",
                    "bracket_dev",
                    "-c",
                    f"DELETE FROM teams WHERE tournament_id = {tid};",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass
        api_delete_tournament(tid)


# ---- M15: Full individual-rating happy-path lifecycle ---------------------


def test_individual_rating_full_lifecycle(page: Page, shared_club_id: int) -> None:
    """M15: the entire \u52a0\u534e\u79ef\u5206 individual-rating workflow, end to end.

    apply (API, applicant tokens) -> applying INSTANTLY joins both accounts (no
    creator approval / no PENDING inbox; bound teams auto-created, one per
    applicant) -> owner seeds each newcomer's \u4e34\u65f6\u521d\u59cb\u5206 in the UI (assert
    persisted) -> a real match between the two bound accounts is created and
    scored (via API; UI score entry is covered by H2\u2013H5) -> owner clicks
    \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 (newcomers' ratings PENDING -> \u5f85\u5ba1\u6838) -> admin approves the
    initial ratings in /admin -> owner clicks \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 again -> tournament
    is \u5df2\u7ed3\u7b97 -> the category leaderboard reflects the settled ratings (winner
    up, loser down, per ChinaTT; sum conserved; one match each).
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    applicant_a = _register_account("lcA")
    applicant_b = _register_account("lcB")
    uids = [applicant_a["uid"], applicant_b["uid"]]
    try:
        # 1) Both applicants apply through the API (their own tokens).
        _apply_to_join(tid, applicant_a["token"])
        _apply_to_join(tid, applicant_b["token"])

        # 2) Applying auto-joins both accounts (no approval step). Bound teams are
        #    auto-created (one per applicant, exactly one player each).
        teams = []
        for _ in range(20):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
            if len(teams) >= 2:
                break
            time.sleep(0.5)
        assert len(teams) == 2, f"expected 2 auto-created bound teams, got {len(teams)}"
        for tm in teams:
            assert len(tm.get("players", [])) == 1, (
                f"each individual team must have exactly one player, got {tm}"
            )
        bound = _psql(f"SELECT count(*) FROM teams_x_users WHERE tournament_id = {tid};")
        assert bound == "2", f"expected 2 account bindings, got {bound!r}"

        # 3) Owner seeds each newcomer's initial rating through the UI and we
        #    assert it actually persisted (not just that the control renders).
        #    The seed control now lives in the team EDIT modal (commit 61fc848).
        page.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
        for tm in teams:
            row = page.locator(
                "tr", has=page.get_by_text(tm["name"], exact=True)
            ).first
            expect(row).to_be_visible(timeout=15_000)
            row.get_by_role("button", name="\u7f16\u8f91", exact=True).first.click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible(timeout=10_000)
            dialog.get_by_placeholder("\u4f8b\u5982 1500").first.fill("1500")
            dialog.get_by_role("button", name="\u4fdd\u5b58", exact=True).first.click()
            expect(dialog).not_to_be_visible(timeout=10_000)
            page.wait_for_timeout(500)
        seeded = _psql(
            "SELECT count(*) FROM player_ratings WHERE category_id = 1 "
            f"AND user_id IN ({uids[0]},{uids[1]}) AND initial_rating = 1500;"
        )
        assert seeded == "2", f"expected both seeds persisted at 1500, got {seeded!r}"

        # 4) A real match between the two bound accounts, scored decisively
        #    THROUGH THE UI (the brief mandates user-facing steps be asserted
        #    through the UI, not just the API). Build the stage, add courts +
        #    schedule so the GroupGrid renders on /results, then open the match
        #    modal and click a result button (2:0 — a decisive win for
        #    applicant_a). The new modal saves on a single click (games=null).
        match_id, round_id = _build_stage_with_one_match(tid)
        # Courts + scheduling so the results page renders the GroupGrid.
        api_create_court(tid, f"E2E-LifecycleCt-{uuid.uuid4().hex[:4]}")
        api_create_court(tid, f"E2E-LifecycleCt-{uuid.uuid4().hex[:4]}")
        api_schedule_matches(tid)

        page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        # The two bound teams' names are the applicant display names. The
        # GroupGrid renders a table; click the first '—' cell to open the
        # match modal (there is only one match in this 2-team RR).
        cell = page.locator("button", has_text="—").first
        expect(cell).to_be_visible(timeout=15_000)
        cell.click()
        expect(page.locator(".mantine-Modal-content")).to_be_visible(timeout=10_000)
        expect(page.locator("body")).to_contain_text("录入分数", timeout=5_000)
        modal = page.locator(".mantine-Modal-content").last
        # Click the '2:0' result button — saves immediately and closes.
        set_match_result(modal, 2, 0)
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground-truth: the match we clicked now has a 2:0 score with
        # games=null (no per-game points recorded in the new modal).
        saved_match = None
        for _ in range(20):
            for s in api_get_stages(tid):
                for it in s.get("stage_items", []):
                    for rd in it.get("rounds", []):
                        for m in rd.get("matches", []):
                            if m["id"] == match_id:
                                saved_match = m
            if saved_match and (saved_match.get("stage_item_input1_score") or 0) > 0:
                break
            time.sleep(0.5)
        assert saved_match is not None, "the scored match must persist"
        assert saved_match.get("stage_item_input1_score") == 2, (
            f"UI score entry must persist input1_score=2, got {saved_match.get('stage_item_input1_score')!r}"
        )
        assert saved_match.get("stage_item_input2_score") == 0, (
            f"UI score entry must persist input2_score=0, got {saved_match.get('stage_item_input2_score')!r}"
        )
        assert not saved_match.get("games"), (
            f"games must be null/empty (new modal records no per-game points), "
            f"got {saved_match.get('games')!r}"
        )

        # 5) Settlement request — pressed ONCE. Newcomers are still PENDING, so the
        #    tournament is parked for admin review (no second owner click needed).
        page.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
        btn = page.get_by_role("button", name="申请积分结算")
        expect(btn).to_be_visible(timeout=15_000)
        btn.click()
        # Assert the DURABLE page state (not the transient toast): after reload the
        # section shows "待管理员审核并结算" and the settle button is gone.
        page.reload(wait_until="domcontentloaded")
        expect(page.get_by_text("待管理员审核并结算")).to_be_visible(timeout=15_000)
        assert api_get_tournament(tid).get("settled_seq") is None

        # 6) Admin approves the seeds AND settles in one action ("批准并结算").
        page.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded")
        expect(page.get_by_text("初始分审核 + 结算队列", exact=True)).to_be_visible(timeout=15_000)
        expect(page.get_by_text(applicant_a["name"], exact=True)).to_be_visible(timeout=10_000)
        page.get_by_role("button", name="批准并结算").first.click()
        # Settlement completed in the same action -> settled_seq assigned.
        settled_seq = None
        for _ in range(20):
            settled_seq = api_get_tournament(tid).get("settled_seq")
            if settled_seq is not None:
                break
            time.sleep(0.5)
        assert settled_seq is not None, "tournament must be settled by the admin action"
        active = _psql(
            "SELECT count(*) FROM player_ratings WHERE category_id = 1 "
            f"AND user_id IN ({uids[0]},{uids[1]}) AND status = 'ACTIVE';"
        )
        assert active == "2", f"expected both ratings ACTIVE after approve-and-settle, got {active!r}"

        # 已结算 badge renders for the owner after reload.
        page.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
        expect(page.get_by_text("已结算", exact=True).first).to_be_visible(timeout=15_000)

        # 8) Leaderboard reflects the settled ratings.
        page.goto(f"{BASE_URL}/rating/1/leaderboard", wait_until="domcontentloaded")
        expect(page.locator("body")).to_contain_text(applicant_a["name"], timeout=15_000)
        expect(page.locator("body")).to_contain_text(applicant_b["name"], timeout=10_000)

        lb = requests.get(
            f"{BASE_URL}/api/rating-categories/1/leaderboard", headers=_api_headers(), timeout=15
        ).json()["data"]
        rows = {r["user_id"]: r for r in lb if r.get("user_id") in uids}
        assert set(rows) == set(uids), f"both participants must be on the leaderboard, got {rows}"
        ra = rows[applicant_a["uid"]]["current_rating"]
        rb = rows[applicant_b["uid"]]["current_rating"]
        # ChinaTT: equal seeds (1500), one winner one loser -> +8 / -8, sum conserved.
        assert {ra, rb} == {1508, 1492}, (
            f"expected one rating up and one down by 8 from 1500, got a={ra} b={rb}"
        )
        assert ra + rb == 3000, f"rating exchange must be conserved, got {ra}+{rb}"
        for u in uids:
            assert rows[u]["matches_played"] == 1, (
                f"each participant must have one settled match, got {rows[u]}"
            )

        # UI half: the rendered leaderboard ROW for each participant must show the
        # settled rating value (rounded), not just the name. A regression that
        # rendered names but blank/wrong rating cells would pass the API check
        # above but fail here.
        for u in uids:
            name = applicant_a["name"] if u == applicant_a["uid"] else applicant_b["name"]
            expected_rating = str(int(round(rows[u]["current_rating"])))
            row = page.locator("tr").filter(has_text=name)
            expect(row.first).to_be_visible(timeout=10_000)
            expect(row.first).to_contain_text(expected_rating)
    finally:
        _force_cleanup_rated(tid, uids)


# ---- M16: Trusted-creator direct add + hosted-account picker --------------


def test_trusted_creator_direct_add_picker(page: Page, shared_club_id: int) -> None:
    """M16: the owner's 直接添加参赛者 picker lists ONLY accounts that have
    trusted the owner, and adding one creates a bound team with no join request.

    A free-text team name is never an option on an individual tournament (see
    M12); the only owner-initiated entry is selecting a hosted account. We
    register a truster (adds the owner as a trusted manager) and a control
    account that does NOT trust the owner, then assert the picker contains
    exactly the truster.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    # The owner is the e2e account; resolve its email for the trust call.
    owner_email = requests.get(
        f"{BASE_URL}/api/users/me", headers=_api_headers(), timeout=15
    ).json()["data"]["email"]
    truster = _register_account("trust")
    control = _register_account("ctrl")
    uids = [truster["uid"], control["uid"]]
    try:
        # The truster authorises the owner as a trusted manager (their token).
        requests.post(
            f"{BASE_URL}/api/me/trusted-managers",
            headers=_headers_for(truster["token"]),
            json={"manager_email": owner_email},
            timeout=15,
        ).raise_for_status()

        # Owner opens the teams page: NO free-text create, a 直接添加参赛者 picker.
        page.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
        expect(page.get_by_text("直接添加参赛者", exact=True)).to_be_visible(timeout=15_000)
        # Individual tournaments call a team 参赛人员; neither wording may appear here.
        assert page.get_by_role("button", name="添加参赛人员").count() == 0, (
            "rated individual tournaments must not expose the free-text create entry"
        )
        assert page.get_by_role("button", name="添加队伍").count() == 0, (
            "rated individual tournaments must not expose the free-text 添加队伍 entry"
        )

        # API ground truth for the picker contents: exactly the truster.
        addable = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/addable-participants",
            headers=_api_headers(), timeout=15,
        ).json()["data"]
        addable_uids = {a["user_id"] for a in addable}
        assert truster["uid"] in addable_uids, "the trusting account must be addable"
        assert control["uid"] not in addable_uids, (
            "an account that did NOT trust the owner must not be addable"
        )

        # Drive the picker in the UI and add the truster. The picker is a
        # searchable Mantine Select; across a full session the addable list
        # accumulates many truster accounts, so blindly hunting the option in
        # the (capped/virtualized) dropdown is flaky — it times out when this
        # run's option isn't in the rendered set. TYPE the unique email to
        # filter the dropdown down to the single matching option first.
        picker = page.locator(
            "fieldset", has=page.get_by_text("直接添加参赛者", exact=True)
        ).first
        search = picker.get_by_placeholder("按姓名 / 邮箱搜索")
        search.click()
        search.fill(truster["email"])
        option = page.get_by_role("option", name=truster["email"], exact=False).first
        expect(option).to_be_visible(timeout=10_000)
        option.click()
        picker.get_by_role("button", name="添加", exact=True).click()

        # A bound team for the truster appears (one player, bound to the account).
        bound_uid = None
        for _ in range(20):
            bound_uid = _psql(
                f"SELECT user_id FROM teams_x_users WHERE tournament_id = {tid};"
            )
            if bound_uid:
                break
            time.sleep(0.5)
        assert bound_uid == str(truster["uid"]), (
            f"direct-add must bind the truster's account, got {bound_uid!r}"
        )
        teams = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
        ).json()["data"]["teams"]
        assert len(teams) == 1 and len(teams[0]["players"]) == 1, (
            f"direct-add must create exactly one bound 1-player team, got {teams}"
        )
    finally:
        _force_cleanup_rated(tid, uids)


def test_owner_can_add_self_via_picker(page: Page, shared_club_id: int) -> None:
    """M24: the tournament CREATOR appears in their OWN 直接添加参赛者 picker and can
    add themselves as a participant — a creator may compete in their own
    individual tournament. Free-text team creation is blocked on rated
    individual tournaments (M12), so the hosted-account picker is the only entry
    path; before this it excluded the owner (no self-trust row) AND the
    participants endpoint 403'd self-add (is_trusted_manager(self, self) is
    false), so a creator was locked out of their own event.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    me = requests.get(
        f"{BASE_URL}/api/users/me", headers=_api_headers(), timeout=15
    ).json()["data"]
    owner_uid, owner_email = me["id"], me["email"]
    try:
        # API ground truth: the owner is addable to their own tournament.
        addable = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/addable-participants",
            headers=_api_headers(), timeout=15,
        ).json()["data"]
        assert any(a["user_id"] == owner_uid for a in addable), (
            "the creator must appear in their own addable-participants picker"
        )

        # Drive the picker in the UI: type the owner's email, select, 添加.
        page.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
        picker = page.locator(
            "fieldset", has=page.get_by_text("直接添加参赛者", exact=True)
        ).first
        expect(picker).to_be_visible(timeout=15_000)
        search = picker.get_by_placeholder("按姓名 / 邮箱搜索")
        search.click()
        search.fill(owner_email)
        option = page.get_by_role("option", name=owner_email, exact=False).first
        expect(option).to_be_visible(timeout=10_000)
        option.click()
        picker.get_by_role("button", name="添加", exact=True).click()

        # A bound 1-player team for the owner appears.
        bound_uid = None
        for _ in range(20):
            bound_uid = _psql(
                f"SELECT user_id FROM teams_x_users WHERE tournament_id = {tid};"
            )
            if bound_uid:
                break
            time.sleep(0.5)
        assert bound_uid == str(owner_uid), (
            f"self-add must bind the owner's account, got {bound_uid!r}"
        )
        teams = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
        ).json()["data"]["teams"]
        assert len(teams) == 1 and len(teams[0]["players"]) == 1, (
            f"self-add must create exactly one bound 1-player team, got {teams}"
        )
        # Once bound, the owner drops out of the addable list (already participates).
        addable2 = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/addable-participants",
            headers=_api_headers(), timeout=15,
        ).json()["data"]
        assert not any(a["user_id"] == owner_uid for a in addable2), (
            "a bound owner must no longer be addable"
        )
    finally:
        _force_cleanup_rated(tid, [])


# ---- M18: Non-rated individual tournament allows BOTH entry paths ---------


def _create_nonrated_individual_tournament(shared_club_id: int) -> int:
    """Create an individual tournament that does NOT participate in ratings
    (is_individual=True, rating_category_id=None)."""
    auth = _api_headers()
    tname = f"E2E-IndivNR-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
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
        },
        timeout=15,
    ).raise_for_status()
    r = requests.get(f"{BASE_URL}/api/tournaments?filter_=ALL", headers=auth, timeout=15)
    r.raise_for_status()
    return next(t["id"] for t in r.json()["data"] if t["name"] == tname)


def test_nonrated_individual_allows_freetext_and_picker(
    page: Page, shared_club_id: int
) -> None:
    """M18: A non-rated individual tournament lets the creator add teams BOTH
    ways — type a free-text name (not bound to any account) AND select a hosted
    account — so the free-text 添加参赛人员 entry and the 直接添加参赛者 picker are
    both present, and the backend accepts a free-text POST /teams.

    Contrast with M12 (rated individual), where free-text is blocked.
    """
    tid = _create_nonrated_individual_tournament(shared_club_id)
    try:
        # API: free-text team creation is ALLOWED (unbound team, no account lookup).
        team_name = f"E2E-FreeIndiv-{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/teams",
            headers=_api_headers(),
            json={"name": team_name, "active": True, "player_names": []},
            timeout=15,
        )
        assert r.status_code in (200, 201), (
            f"non-rated individual must accept free-text team create, got "
            f"{r.status_code}: {r.text[:200]}"
        )
        # The created team is unbound (no account binding) — "不查数据库".
        bound = _psql(f"SELECT count(*) FROM teams_x_users WHERE tournament_id = {tid};")
        assert bound == "0", f"free-text team must be unbound, got {bound!r} bindings"

        # UI: BOTH the free-text 添加参赛人员 button AND the 直接添加参赛者 picker
        # render (an individual tournament says 参赛人员 where a team one says 队伍).
        page.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
        expect(
            page.get_by_role("button", name="添加参赛人员", exact=True).first
        ).to_be_visible(timeout=15_000)
        expect(page.get_by_text("直接添加参赛者", exact=True)).to_be_visible(timeout=10_000)
        # The free-text team we created is listed.
        expect(page.locator("body")).to_contain_text(team_name, timeout=10_000)
    finally:
        # No settlement here, so the normal cascade delete suffices.
        _force_cleanup_rated(tid, [])



# ---- M19: A non-member can view a public tournament + apply to join -------


def test_public_dashboard_viewable_by_nonmember_and_join(shared_club_id: int) -> None:
    """M19: a logged-in account that is NOT a member of the tournament's club
    can still read the public tournament (regression: GET /stages used to 403
    public viewers with "Can't view draft rounds when not authorized", which
    broke the public dashboard the 参赛 button lives on) and join.

    Drives the data layer that the dashboard depends on, from a fresh
    non-member account's token.
    """
    tid = _create_nonrated_individual_tournament(shared_club_id)
    outsider = _register_account("outsider")
    try:
        h = _headers_for(outsider["token"])
        # The tournament itself reads (public dashboard).
        r_t = requests.get(f"{BASE_URL}/api/tournaments/{tid}", headers=h, timeout=15)
        assert r_t.status_code == 200, f"public tournament read failed: {r_t.status_code}"
        # Regression: stages must be readable by a non-member (draft rounds are
        # transparently hidden, not a 403).
        r_s = requests.get(f"{BASE_URL}/api/tournaments/{tid}/stages", headers=h, timeout=15)
        assert r_s.status_code == 200, (
            f"non-member must read public stages (no 403), got {r_s.status_code}: "
            f"{r_s.text[:200]}"
        )
        # Courts/teams the dashboard also fetches must not 403 either.
        for ep in ("courts", "teams"):
            rc = requests.get(f"{BASE_URL}/api/tournaments/{tid}/{ep}", headers=h, timeout=15)
            assert rc.status_code == 200, f"non-member /{ep} read failed: {rc.status_code}"
        # The actual join action works for the non-member.
        r_j = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/join-requests",
            headers=h,
            json={"trust_creator": False},
            timeout=15,
        )
        assert r_j.status_code == 200, f"join failed: {r_j.status_code}: {r_j.text[:200]}"
        # Applying auto-joins: the outsider is now a participant (no approval).
        st = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/my-join-status", headers=h, timeout=15
        ).json()["data"]
        assert st["is_participant"] is True, f"outsider should be auto-joined, got {st}"
    finally:
        _force_cleanup_rated(tid, [outsider["uid"]])



# ---- M20: public dashboard resolves by id (no custom endpoint slug) -------


def test_public_dashboard_resolves_by_id_for_anyone(shared_club_id: int) -> None:
    """M20: the public dashboard URL /tournaments/{id}/dashboard resolves the
    tournament via GET /tournaments?endpoint_name={id} for ANY viewer — a
    logged-in non-member AND an anonymous visitor — even when no custom
    dashboard_endpoint slug is set (regression: this used to 401, breaking the
    shareable dashboard link). A non-public tournament must still NOT resolve.
    """
    tid = _create_nonrated_individual_tournament(shared_club_id)  # dashboard_public=True
    outsider = _register_account("byid")
    try:
        # Logged-in non-member resolves it by id.
        r_out = requests.get(
            f"{BASE_URL}/api/tournaments?endpoint_name={tid}",
            headers=_headers_for(outsider["token"]),
            timeout=15,
        )
        assert r_out.status_code == 200, f"non-member resolve failed: {r_out.status_code}"
        assert r_out.json()["data"][0]["id"] == tid

        # Anonymous (no token) resolves it too — public dashboards are anon-readable.
        r_anon = requests.get(
            f"{BASE_URL}/api/tournaments?endpoint_name={tid}", timeout=15
        )
        assert r_anon.status_code == 200, f"anon resolve failed: {r_anon.status_code}"
        assert r_anon.json()["data"][0]["id"] == tid

        # The authenticated listing (no endpoint_name) still requires a token.
        r_list = requests.get(f"{BASE_URL}/api/tournaments?filter_=OPEN", timeout=15)
        assert r_list.status_code == 401, (
            f"the tournament listing must require auth, got {r_list.status_code}"
        )
    finally:
        _force_cleanup_rated(tid, [outsider["uid"]])


def test_nonpublic_tournament_not_resolvable_by_id() -> None:
    """M20b: a tournament with dashboard_public=false must NOT be resolvable by
    id through the public endpoint (no info leak)."""
    import json as _json

    auth = _api_headers()
    # Find or make a non-public tournament: create one then flip it private.
    me_clubs = requests.get(f"{BASE_URL}/api/clubs", headers=auth, timeout=15).json()["data"]
    club_id = me_clubs[0]["id"]
    tname = f"E2E-Private-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": tname, "club_id": club_id, "dashboard_public": False,
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
    try:
        r = requests.get(f"{BASE_URL}/api/tournaments?endpoint_name={tid}", timeout=15)
        assert r.status_code == 401, (
            f"non-public tournament must not resolve publicly, got {r.status_code}: {r.text[:120]}"
        )
    finally:
        requests.delete(f"{BASE_URL}/api/tournaments/{tid}", headers=auth, timeout=15)


# ---- M20c: site admin may READ a private tournament (rating review) --------


def test_admin_can_read_private_tournament() -> None:
    """A site admin may READ any tournament — including a private one they don't
    own — so the initial-rating reviewer can open its results from /admin. A
    non-admin non-member is still blocked (401)."""
    owner = _register_account("privown")
    club_id = requests.get(
        f"{BASE_URL}/api/clubs", headers=_headers_for(owner["token"]), timeout=15
    ).json()["data"][0]["id"]
    tname = f"E2E-AdminRead-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=_headers_for(owner["token"]),
        json={
            "name": tname, "club_id": club_id, "dashboard_public": False,
            "dashboard_endpoint": "", "players_can_be_in_multiple_teams": False,
            "auto_assign_courts": True, "start_time": "2030-01-01T00:00:00Z",
            "duration_minutes": 10, "margin_minutes": 5, "is_individual": True,
            "rating_category_id": 1,
        },
        timeout=15,
    ).raise_for_status()
    tid = next(
        t["id"]
        for t in requests.get(
            f"{BASE_URL}/api/tournaments?filter_=ALL",
            headers=_headers_for(owner["token"]), timeout=15,
        ).json()["data"]
        if t["name"] == tname
    )
    outsider = _register_account("privread")
    try:
        # The shared E2E account is the site admin and is NOT a member here.
        admin_me = requests.get(
            f"{BASE_URL}/api/users/me", headers=_api_headers(), timeout=15
        ).json()["data"]
        assert admin_me.get("is_admin") is True, "E2E account must be a site admin"
        r_admin = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/stages", headers=_api_headers(), timeout=15
        )
        assert r_admin.status_code == 200, (
            f"admin must read a private tournament, got {r_admin.status_code}: {r_admin.text[:150]}"
        )
        # A non-admin non-member is still blocked.
        r_out = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/stages",
            headers=_headers_for(outsider["token"]), timeout=15,
        )
        assert r_out.status_code == 401, (
            f"non-admin non-member must be blocked, got {r_out.status_code}"
        )
    finally:
        requests.delete(
            f"{BASE_URL}/api/tournaments/{tid}", headers=_headers_for(owner["token"]), timeout=15
        )


# ---- M21: follow/favorite tournaments (home "我关注的比赛" tab) ----------


def test_follow_favorite_tournaments(shared_club_id: int) -> None:
    """M21: a user's followed list (GET /me/tournaments) = favorites ∪ joined.

    - favoriting a public tournament adds it to the followed list, and
      unfavoriting removes it;
    - a tournament the user participates in appears automatically (no favorite
      needed);
    - favoriting a tournament the user cannot view (private, not a member /
      participant) is rejected with 403.
    """
    pub_tid = _create_nonrated_individual_tournament(shared_club_id)  # dashboard_public=True
    follower = _register_account("follow")
    h = _headers_for(follower["token"])

    # A private tournament under the owner's club the follower cannot see.
    auth = _api_headers()
    priv_name = f"E2E-Priv-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": priv_name, "club_id": shared_club_id, "dashboard_public": False,
            "dashboard_endpoint": "", "players_can_be_in_multiple_teams": False,
            "auto_assign_courts": True, "start_time": "2030-01-01T00:00:00Z",
            "duration_minutes": 10, "margin_minutes": 5,
        },
        timeout=15,
    ).raise_for_status()
    priv_tid = next(
        t["id"]
        for t in requests.get(
            f"{BASE_URL}/api/tournaments?filter_=ALL", headers=auth, timeout=15
        ).json()["data"]
        if t["name"] == priv_name
    )

    def followed_ids() -> set:
        data = requests.get(f"{BASE_URL}/api/me/tournaments", headers=h, timeout=15).json()["data"]
        return {t["id"] for t in data}

    try:
        # Initially the follower follows nothing.
        assert pub_tid not in followed_ids()

        # Favorite the public tournament -> appears.
        r_add = requests.post(f"{BASE_URL}/api/me/favorites/{pub_tid}", headers=h, timeout=15)
        assert r_add.status_code == 200, f"favorite failed: {r_add.status_code}: {r_add.text[:150]}"
        assert pub_tid in followed_ids(), "favorited tournament must appear in followed list"

        # Unfavorite -> gone.
        requests.delete(f"{BASE_URL}/api/me/favorites/{pub_tid}", headers=h, timeout=15)
        assert pub_tid not in followed_ids(), "unfavorited tournament must leave followed list"

        # Joining surfaces a tournament automatically (apply = instant join).
        _apply_to_join(pub_tid, follower["token"])
        assert pub_tid in followed_ids(), "a joined tournament must appear in the followed list"

        # Cannot favorite a private tournament the follower can't view.
        r_priv = requests.post(f"{BASE_URL}/api/me/favorites/{priv_tid}", headers=h, timeout=15)
        assert r_priv.status_code == 403, (
            f"favoriting an inaccessible private tournament must 403, got {r_priv.status_code}"
        )
    finally:
        requests.delete(f"{BASE_URL}/api/tournaments/{priv_tid}", headers=auth, timeout=15)
        _force_cleanup_rated(pub_tid, [follower["uid"]])


# ---- M22: being added as a scorer auto-follows the tournament -------------


def test_scorer_auto_follows_tournament(shared_club_id: int) -> None:
    """M22: when a user is added as a 记分员 (scorer), the tournament appears in
    their followed list (GET /me/tournaments) automatically — without
    favoriting or joining."""
    tid = _create_nonrated_individual_tournament(shared_club_id)
    scorer = _register_account("scorerfollow")
    h = _headers_for(scorer["token"])

    def followed_ids() -> set:
        return {
            t["id"]
            for t in requests.get(
                f"{BASE_URL}/api/me/tournaments", headers=h, timeout=15
            ).json()["data"]
        }

    try:
        assert tid not in followed_ids(), "not following before being made a scorer"
        # Owner adds the account as a scorer (POST returns SuccessResponse).
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/scorers",
            headers=_api_headers(),
            json={"user_email": scorer["email"]},
            timeout=15,
        ).raise_for_status()
        assert tid in followed_ids(), "a scorer must auto-follow the tournament"
        # Removing the scorer role drops it from the followed list (not favorited).
        _remove_scorer(tid, scorer["uid"])
        assert tid not in followed_ids(), "removing the scorer role unfollows it"
    finally:
        _force_cleanup_rated(tid, [scorer["uid"]])


# ---- M23: a scorer can read (and thus score) a PRIVATE tournament ---------


def test_scorer_can_read_private_tournament(shared_club_id: int) -> None:
    """M23: a scorer assigned to a non-public tournament can read it (by-id +
    stages + courts) so they can open the results page and record scores —
    regression for scorers/participants being 401'd on private tournaments."""
    auth = _api_headers()
    name = f"E2E-PrivScore-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": name, "club_id": shared_club_id, "dashboard_public": False,
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
        if t["name"] == name
    )
    scorer = _register_account("privscorer")
    h = _headers_for(scorer["token"])
    try:
        # Before being a scorer: no read access to the private tournament.
        assert requests.get(
            f"{BASE_URL}/api/tournaments/{tid}", headers=h, timeout=15
        ).status_code == 401, "outsider must not read a private tournament"

        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/scorers",
            headers=auth, json={"user_email": scorer["email"]}, timeout=15,
        ).raise_for_status()

        # After: the scorer can read the tournament + its stages + courts.
        for ep in ("", "/stages", "/courts"):
            code = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}{ep}", headers=h, timeout=15
            ).status_code
            assert code == 200, f"scorer must read /tournaments/{tid}{ep}, got {code}"
    finally:
        requests.delete(f"{BASE_URL}/api/tournaments/{tid}/scorers/{scorer['uid']}", headers=auth, timeout=15)
        requests.delete(f"{BASE_URL}/api/tournaments/{tid}", headers=auth, timeout=15)


def test_rated_tournament_rejects_draw_score(shared_club_id: int) -> None:
    """M25: a rated individual tournament rejects a tied non-zero score (draw)
    with 400 'Table tennis has no draws; enter a decisive score'.

    The one-tap UI buttons can only produce decisive scores (winner in
    {2,3,4}), so the UI can't trigger this guard — but the API guard exists
    as defense-in-depth and is untested. A regression that dropped the guard
    (allowing a 1:1 draw to persist on a rated tournament, corrupting the
    rating settlement) would pass the entire suite.

    This is an API-level negative test: PUT /matches/{id} with
    input1_score=1, input2_score=1 on a rated individual tournament → 400.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    applicant_a = _register_account("drawA")
    applicant_b = _register_account("drawB")
    try:
        _apply_to_join(tid, applicant_a["token"])
        _apply_to_join(tid, applicant_b["token"])

        # Wait for 2 bound teams.
        teams: list = []
        for _ in range(20):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams",
                headers=_api_headers(), timeout=15,
            ).json()["data"]["teams"]
            if len(teams) >= 2:
                break
            time.sleep(0.5)
        assert len(teams) >= 2

        # Seed both as ACTIVE so the RR can be built.
        for app in (applicant_a, applicant_b):
            _psql(
                "INSERT INTO player_ratings (category_id, user_id, initial_rating, "
                "current_rating, matches_played, status) "
                f"VALUES (1, {app['uid']}, 1500, 1500, 0, 'ACTIVE') "
                "ON CONFLICT (category_id, user_id) DO UPDATE "
                "SET initial_rating=1500, current_rating=1500, matches_played=0, status='ACTIVE';"
            )

        match_id, round_id = _build_stage_with_one_match(tid)

        # Attempt a 1:1 draw — must be rejected with 400.
        auth = _api_headers()
        r = requests.put(
            f"{BASE_URL}/api/tournaments/{tid}/matches/{match_id}",
            headers=auth,
            json={
                "id": match_id,
                "round_id": round_id,
                "games": None,
                "best_of": 3,
                "stage_item_input1_score": 1,
                "stage_item_input2_score": 1,
                "forfeit_input": None,
                "court_id": None,
                "custom_duration_minutes": None,
                "custom_margin_minutes": None,
            },
            timeout=15,
        )
        assert r.status_code == 400, (
            f"rated tournament must reject a 1:1 draw with 400, got {r.status_code}: {r.text[:200]}"
        )
        assert "draw" in r.text.lower() or "decisive" in r.text.lower(), (
            f"rejection must mention draws/decisive, got {r.text[:200]}"
        )

        # A 0:0 score (unplayed) is NOT a draw and must NOT be rejected.
        r0 = requests.put(
            f"{BASE_URL}/api/tournaments/{tid}/matches/{match_id}",
            headers=auth,
            json={
                "id": match_id,
                "round_id": round_id,
                "games": None,
                "best_of": 3,
                "stage_item_input1_score": 0,
                "stage_item_input2_score": 0,
                "forfeit_input": None,
                "court_id": None,
                "custom_duration_minutes": None,
                "custom_margin_minutes": None,
            },
            timeout=15,
        )
        assert r0.status_code == 200, (
            f"0:0 (unplayed) must NOT be rejected as a draw, got {r0.status_code}: {r0.text[:200]}"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass


# ---- M26: A FORFEIT match settles correctly on a rated tournament ----------


def test_forfeit_match_settles_on_rated_tournament(
    page: Page, shared_club_id: int
) -> None:
    """M26: a rated individual tournament whose sole match is a FORFEIT settles
    correctly and applies the ChinaTT rating exchange to the non-forfeiting
    winner.

    This closes the gap the critic found: the settlement completeness gate
    (validate_settlement_ready) previously treated a 0-0 forfeit as "no
    recorded result" and blocked settlement, and scored_matches_from_rows
    silently dropped it. After the fix, a forfeit (0-0 + forfeit_input) IS a
    recorded result: settlement succeeds and the non-forfeiting player gains
    ChinaTT points while the forfeiting player loses them.

    Flow: create rated individual tournament -> 2 applicants instant-join ->
    seed both at 1500 -> build 2-team RR (one match) -> courts + schedule so
    /results renders the GroupGrid -> forfeit the match via the UI 弃权 button
    (applicant_b forfeits, so applicant_a wins) -> owner requests settlement ->
    admin approves-and-settles -> assert leaderboard shows +8/-8 (equal seeds)
    and matches_played == 1 each.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    applicant_a = _register_account("ftA")
    applicant_b = _register_account("ftB")
    uids = [applicant_a["uid"], applicant_b["uid"]]
    try:
        # 1) Both applicants instant-join (applying == joining, no approval).
        _apply_to_join(tid, applicant_a["token"])
        _apply_to_join(tid, applicant_b["token"])
        teams = []
        for _ in range(20):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams",
                headers=_api_headers(),
                timeout=15,
            ).json()["data"]["teams"]
            if len(teams) >= 2:
                break
            time.sleep(0.5)
        assert len(teams) == 2, f"expected 2 auto-created bound teams, got {len(teams)}"
        # Determine which team belongs to which applicant (by binding).
        bindings = {}
        for tm in teams:
            row = _psql(
                "SELECT user_id FROM teams_x_users WHERE team_id = "
                f"{tm['id']};"
            )
            bindings[int(row)] = tm
        team_a = bindings[applicant_a["uid"]]
        team_b = bindings[applicant_b["uid"]]

        # 2) Owner seeds both at 1500 through the team-edit modal.
        page.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
        for tm in teams:
            row = page.locator("tr", has=page.get_by_text(tm["name"], exact=True)).first
            expect(row).to_be_visible(timeout=15_000)
            row.get_by_role("button", name="编辑", exact=True).first.click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible(timeout=10_000)
            dialog.get_by_placeholder("例如 1500").first.fill("1500")
            dialog.get_by_role("button", name="保存", exact=True).first.click()
            expect(dialog).not_to_be_visible(timeout=10_000)
            page.wait_for_timeout(500)
        seeded = _psql(
            "SELECT count(*) FROM player_ratings WHERE category_id = 1 "
            f"AND user_id IN ({uids[0]},{uids[1]}) AND initial_rating = 1500;"
        )
        assert seeded == "2", f"expected both seeds persisted at 1500, got {seeded!r}"

        # 3) Build the 2-team RR (one match), add courts + schedule so /results
        #    renders the GroupGrid cross-table.
        match_id, _round_id = _build_stage_with_one_match(tid)
        api_create_court(tid, f"E2E-ForfeitCt-{uuid.uuid4().hex[:4]}")
        api_create_court(tid, f"E2E-ForfeitCt-{uuid.uuid4().hex[:4]}")
        api_schedule_matches(tid)

        # 4) Forfeit the match via the UI: applicant_b (team_b) forfeits, so
        #    applicant_a (team_a) wins the walkover.
        page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        cell = page.locator("button", has_text="—").first
        expect(cell).to_be_visible(timeout=15_000)
        cell.click()
        expect(page.locator(".mantine-Modal-content")).to_be_visible(timeout=10_000)
        modal = page.locator(".mantine-Modal-content").last
        # The forfeit button is labelled '<team_name> 弃权'.
        forfeit_match(modal, team_b["name"])
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)

        # API ground truth: the match is persisted with 0-0 scores + forfeit.
        saved = None
        for _ in range(20):
            for s in api_get_stages(tid):
                for it in s.get("stage_items", []):
                    for rd in it.get("rounds", []):
                        for m in rd.get("matches", []):
                            if m["id"] == match_id:
                                saved = m
            if saved and saved.get("forfeit_input") is not None:
                break
            time.sleep(0.5)
        assert saved is not None, "the forfeited match must persist"
        assert saved.get("stage_item_input1_score") == 0, (
            f"forfeit leaves scores at 0, got {saved!r}"
        )
        assert saved.get("stage_item_input2_score") == 0
        assert saved.get("forfeit_input") in (1, 2), (
            f"forfeit_input must be set, got {saved.get('forfeit_input')!r}"
        )
        assert not saved.get("games"), "forfeit must not record per-game points"

        # 5) Owner requests settlement. Seeds are PENDING -> parked for review.
        page.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
        btn = page.get_by_role("button", name="申请积分结算")
        expect(btn).to_be_visible(timeout=15_000)
        btn.click()
        page.reload(wait_until="domcontentloaded")
        expect(page.get_by_text("待管理员审核并结算")).to_be_visible(timeout=15_000)
        assert api_get_tournament(tid).get("settled_seq") is None

        # 6) Admin approves-and-settles in one action.
        page.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded")
        expect(page.get_by_text("初始分审核 + 结算队列", exact=True)).to_be_visible(timeout=15_000)
        expect(page.get_by_text(applicant_a["name"], exact=True)).to_be_visible(timeout=10_000)
        page.get_by_role("button", name="批准并结算").first.click()
        settled_seq = None
        for _ in range(20):
            settled_seq = api_get_tournament(tid).get("settled_seq")
            if settled_seq is not None:
                break
            time.sleep(0.5)
        assert settled_seq is not None, "tournament must settle despite a forfeit match"
        active = _psql(
            "SELECT count(*) FROM player_ratings WHERE category_id = 1 "
            f"AND user_id IN ({uids[0]},{uids[1]}) AND status = 'ACTIVE';"
        )
        assert active == "2", f"expected both ratings ACTIVE, got {active!r}"

        # 7) Leaderboard: the non-forfeiting winner (applicant_a) is up 8, the
        #    forfeiting loser (applicant_b) is down 8 (equal 1500 seeds, ChinaTT
        #    diff 0 -> 8/8 exchange). This proves the forfeit contributed to the
        #    rating exchange instead of being silently dropped.
        page.goto(f"{BASE_URL}/rating/1/leaderboard", wait_until="domcontentloaded")
        expect(page.locator("body")).to_contain_text(applicant_a["name"], timeout=15_000)
        expect(page.locator("body")).to_contain_text(applicant_b["name"], timeout=10_000)
        lb = requests.get(
            f"{BASE_URL}/api/rating-categories/1/leaderboard",
            headers=_api_headers(),
            timeout=15,
        ).json()["data"]
        rows = {r["user_id"]: r for r in lb if r.get("user_id") in uids}
        assert set(rows) == set(uids), f"both participants must be listed, got {rows}"
        ra = rows[applicant_a["uid"]]["current_rating"]
        rb = rows[applicant_b["uid"]]["current_rating"]
        assert {ra, rb} == {1508, 1492}, (
            f"expected +8/-8 ChinaTT exchange from a forfeit, got a={ra} b={rb}"
        )
        assert ra + rb == 3000, f"rating exchange must be conserved, got {ra}+{rb}"
        for u in uids:
            assert rows[u]["matches_played"] == 1, (
                f"each participant must have 1 settled match, got {rows[u]}"
            )
    finally:
        _force_cleanup_rated(tid, uids)


# ---- M27: ChinaTT upset vs expected exchange curve (different seeds) -------
# The critic found that M15/M26 both seed the two applicants at the SAME rating
# (1500 vs 1500). At diff=0 the ChinaTT table returns (8,8) for BOTH the
# higher_won=True and higher_won=False branches, so a regression that dropped,
# inverted, or always-used-high_gain for the upset path would pass every existing
# test. These two variants seed the applicants at DIFFERENT ratings (1500 vs
# 1400, diff=100 -> bin (112, high_gain=4, low_gain=20)) and assert the divergent
# exchange: an UPSET (lower wins) transfers 20; an expected result (higher wins)
# transfers only 4 — a 5x difference the equal-seed tests cannot detect.


def _seed_active_ratings(uids, seed_a, seed_b):
    """Seed both participants ACTIVE at the given ratings via psql (so the
    round-robin stage can be built on a rated individual tournament, which
    refuses to start while players have no configured rating)."""
    for uid, seed in ((uids[0], seed_a), (uids[1], seed_b)):
        _psql(
            "INSERT INTO player_ratings (category_id, user_id, initial_rating, "
            "current_rating, matches_played, status) "
            f"VALUES (1, {uid}, {seed}, {seed}, 0, 'ACTIVE') "
            "ON CONFLICT (category_id, user_id) DO UPDATE "
            f"SET initial_rating={seed}, current_rating={seed}, matches_played=0, status='ACTIVE';"
        )


def _build_and_score_one_match_for_settlement(tid, team_a, team_b, winner_is_a):
    """Build a 2-team RR (one match), score it via the API so the named winner
    wins, and return (match_id, round_id). Used by the upset/expected tests."""
    match_id, round_id = _build_stage_with_one_match(tid)
    # Determine input order: the first input's team is whichever the API
    # happened to assign to slot 1.
    stages = api_get_stages(tid)
    in1_uid = None
    for s in stages:
        for it in s.get("stage_items", []):
            for rd in it.get("rounds", []):
                for m in rd.get("matches", []):
                    if m["id"] == match_id:
                        in1_uid = (m.get("stage_item_input1") or {}).get("team_id")
    # Score: if the winner is input1, 2:0; if the winner is input2, 0:2.
    if winner_is_a:
        s1, s2 = (2, 0) if in1_uid == team_a["id"] else (0, 2)
    else:
        s1, s2 = (2, 0) if in1_uid == team_b["id"] else (0, 2)
    requests.put(
        f"{BASE_URL}/api/tournaments/{tid}/matches/{match_id}",
        headers=_api_headers(),
        json={
            "id": match_id,
            "round_id": round_id,
            "games": None,
            "best_of": 3,
            "stage_item_input1_score": s1,
            "stage_item_input2_score": s2,
            "forfeit_input": None,
            "court_id": None,
            "custom_duration_minutes": None,
            "custom_margin_minutes": None,
        },
        timeout=15,
    ).raise_for_status()
    return match_id, round_id


def _settle_and_get_leaderboard(tid, uids):
    """Settle via the admin /settle endpoint (seeds already ACTIVE) and return
    the leaderboard rows dict keyed by user_id."""
    auth = _api_headers()
    r = requests.post(f"{BASE_URL}/api/tournaments/{tid}/settle", headers=auth, timeout=15)
    assert r.status_code == 200, (
        f"admin /settle must succeed, got {r.status_code}: {r.text[:200]}"
    )
    settled_seq = None
    for _ in range(20):
        settled_seq = api_get_tournament(tid).get("settled_seq")
        if settled_seq is not None:
            break
        time.sleep(0.5)
    assert settled_seq is not None, "tournament must settle"
    lb = requests.get(
        f"{BASE_URL}/api/rating-categories/1/leaderboard", headers=auth, timeout=15
    ).json()["data"]
    return {r["user_id"]: r for r in lb if r.get("user_id") in uids}


def test_upset_exchange_lower_beats_higher(shared_club_id: int) -> None:
    """M27a: a LOWER-rated player beating a HIGHER-rated player (an UPSET)
    settles with the ChinaTT *upset* exchange (+20 / -20 for diff=100), NOT the
    expected-result exchange (+4 / -4).

    Seeds: applicant_a=1500, applicant_b=1400 (diff=100). applicant_b (lower)
    wins the match. ChinaTT bin (112, high_gain=4, low_gain=20): because the
    lower-rated player won, low_gain=20 applies. A regression that dropped the
    higher_won flip, inverted it, or always used high_gain would exchange only 4
    and pass M15/M26 (equal seeds) — this test catches it.
    """
    HIGH = 1500
    LOW = 1400
    EXPECTED_GAIN = 20  # low_gain for diff=100, bin (112, 4, 20)

    tid = _create_rated_individual_tournament(shared_club_id)
    applicant_a = _register_account("upA")  # higher-rated
    applicant_b = _register_account("upB")  # lower-rated (the upset winner)
    uids = [applicant_a["uid"], applicant_b["uid"]]
    try:
        _apply_to_join(tid, applicant_a["token"])
        _apply_to_join(tid, applicant_b["token"])
        teams = []
        for _ in range(20):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
            if len(teams) >= 2:
                break
            time.sleep(0.5)
        assert len(teams) == 2
        # Map each team to its applicant.
        bindings = {}
        for tm in teams:
            row = _psql(
                "SELECT user_id FROM teams_x_users WHERE team_id = " f"{tm['id']};"
            )
            bindings[int(row)] = tm
        team_a = bindings[applicant_a["uid"]]
        team_b = bindings[applicant_b["uid"]]

        # Seed ratings FIRST (a rated individual tournament refuses to build the
        # round-robin while players have no configured rating).
        _seed_active_ratings(uids, HIGH, LOW)
        _build_and_score_one_match_for_settlement(tid, team_a, team_b, winner_is_a=False)
        rows = _settle_and_get_leaderboard(tid, uids)

        ra = rows[applicant_a["uid"]]["current_rating"]  # higher, lost
        rb = rows[applicant_b["uid"]]["current_rating"]  # lower, won (upset)
        assert ra == HIGH - EXPECTED_GAIN, (
            f"higher-rated loser must drop {EXPECTED_GAIN} (upset exchange), got {ra} (seed {HIGH})"
        )
        assert rb == LOW + EXPECTED_GAIN, (
            f"lower-rated winner must gain {EXPECTED_GAIN} (upset exchange), got {rb} (seed {LOW})"
        )
        assert ra + rb == HIGH + LOW, (
            f"rating exchange must be conserved, got {ra}+{rb} != {HIGH + LOW}"
        )
        # Crucially, the gain must NOT be the expected-result value (4).
        assert rb - LOW != 4, (
            "upset must use low_gain (20), not high_gain (4); the higher_won "
            "branch looks inverted"
        )
        for u in uids:
            assert rows[u]["matches_played"] == 1
    finally:
        _force_cleanup_rated(tid, uids)


def test_expected_exchange_higher_beats_lower(shared_club_id: int) -> None:
    """M27b: a HIGHER-rated player beating a LOWER-rated player (expected
    result) settles with the ChinaTT *expected* exchange (+4 / -4 for diff=100),
    the complementary case to M27a.

    Same seeds (1500 vs 1400) but applicant_a (higher) wins. ChinaTT bin
    (112, high_gain=4): high_gain=4 applies. A regression that always used
    low_gain (20) would pass M27a's "not 4" assertion but fail here.
    """
    HIGH = 1500
    LOW = 1400
    EXPECTED_GAIN = 4  # high_gain for diff=100, bin (112, 4, 20)

    tid = _create_rated_individual_tournament(shared_club_id)
    applicant_a = _register_account("exA")  # higher-rated (the expected winner)
    applicant_b = _register_account("exB")  # lower-rated
    uids = [applicant_a["uid"], applicant_b["uid"]]
    try:
        _apply_to_join(tid, applicant_a["token"])
        _apply_to_join(tid, applicant_b["token"])
        teams = []
        for _ in range(20):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]
            if len(teams) >= 2:
                break
            time.sleep(0.5)
        assert len(teams) == 2
        bindings = {}
        for tm in teams:
            row = _psql(
                "SELECT user_id FROM teams_x_users WHERE team_id = " f"{tm['id']};"
            )
            bindings[int(row)] = tm
        team_a = bindings[applicant_a["uid"]]
        team_b = bindings[applicant_b["uid"]]

        _seed_active_ratings(uids, HIGH, LOW)
        _build_and_score_one_match_for_settlement(tid, team_a, team_b, winner_is_a=True)
        rows = _settle_and_get_leaderboard(tid, uids)

        ra = rows[applicant_a["uid"]]["current_rating"]  # higher, won
        rb = rows[applicant_b["uid"]]["current_rating"]  # lower, lost
        assert ra == HIGH + EXPECTED_GAIN, (
            f"higher-rated winner must gain {EXPECTED_GAIN} (expected exchange), got {ra}"
        )
        assert rb == LOW - EXPECTED_GAIN, (
            f"lower-rated loser must drop {EXPECTED_GAIN} (expected exchange), got {rb}"
        )
        assert ra + rb == HIGH + LOW, (
            f"rating exchange must be conserved, got {ra}+{rb} != {HIGH + LOW}"
        )
        # The gain must NOT be the upset value (20).
        assert ra - HIGH != 20, (
            "expected result must use high_gain (4), not low_gain (20)"
        )
        for u in uids:
            assert rows[u]["matches_played"] == 1
    finally:
        _force_cleanup_rated(tid, uids)


# ---- M28: Multi-match batch accumulation in settlement ---------------------
# Critic issue 1: every existing settlement test uses exactly 2 teams / 1
# match.  A 4-team RR (6 matches, each player plays 3) exercises the batch
# delta_sum loop and matches_played derivation from the rating_events ledger.


def _seed_all_active_same(uids: list, seed: int) -> None:
    """Seed all users ACTIVE at the same rating via psql."""
    for uid in uids:
        _psql(
            "INSERT INTO player_ratings (category_id, user_id, initial_rating, "
            "current_rating, matches_played, status) "
            f"VALUES (1, {uid}, {seed}, {seed}, 0, 'ACTIVE') "
            "ON CONFLICT (category_id, user_id) DO UPDATE "
            f"SET initial_rating={seed}, current_rating={seed}, "
            "matches_played=0, status='ACTIVE';"
        )


def _build_nteam_rr(tid: int, team_count: int) -> list[dict]:
    """Create a stage + N-team round-robin (1 group) and return all matches
    with their input team assignments."""
    auth = _api_headers()
    requests.post(
        f"{BASE_URL}/api/tournaments/{tid}/stages",
        headers=auth, json={"name": "RR1"}, timeout=15,
    ).raise_for_status()
    stages = requests.get(
        f"{BASE_URL}/api/tournaments/{tid}/stages", headers=auth, timeout=15
    ).json()["data"]
    stage_id = stages[-1]["id"]
    requests.post(
        f"{BASE_URL}/api/tournaments/{tid}/stage_items/round_robin_groups",
        headers=auth,
        json={"stage_id": stage_id, "group_count": 1, "team_count": team_count},
        timeout=15,
    ).raise_for_status()
    matches: list[dict] = []
    for s in api_get_stages(tid):
        for it in s.get("stage_items", []):
            for rd in it.get("rounds", []):
                for m in rd.get("matches", []):
                    matches.append({
                        "match_id": m["id"],
                        "round_id": rd["id"],
                        "team1_id": (m.get("stage_item_input1") or {}).get("team_id"),
                        "team2_id": (m.get("stage_item_input2") or {}).get("team_id"),
                    })
    return matches


def _score_match_decisive(tid: int, match_info: dict, winner_team_id: int) -> None:
    """Score a match 2:0 or 0:2 so *winner_team_id* wins.  games=None."""
    if match_info["team1_id"] == winner_team_id:
        s1, s2 = 2, 0
    else:
        s1, s2 = 0, 2
    requests.put(
        f"{BASE_URL}/api/tournaments/{tid}/matches/{match_info['match_id']}",
        headers=_api_headers(),
        json={
            "id": match_info["match_id"],
            "round_id": match_info["round_id"],
            "games": None,
            "best_of": 3,
            "stage_item_input1_score": s1,
            "stage_item_input2_score": s2,
            "forfeit_input": None,
            "court_id": None,
            "custom_duration_minutes": None,
            "custom_margin_minutes": None,
        },
        timeout=15,
    ).raise_for_status()


def test_settlement_multi_match_batch_accumulation(
    page: Page, shared_club_id: int
) -> None:
    """M28: Settlement correctly accumulates rating deltas across multiple
    matches per player in a 4-team rated individual RR.

    Every existing settlement test (M15, M26, M27a, M27b) uses exactly 2 teams
    / 1 match.  This test creates a 4-team RR (6 matches, each player plays 3),
    scores ALL matches decisively, settles, and asserts:
      - matches_played == 3 for every player
      - cumulative rating deltas are correct (A wins 3 -> +24, B wins 2 -> +8,
        C wins 1 -> -8, D wins 0 -> -24; all seeds 1500, diff=0 -> exchange 8)
    A regression in the batch loop (delta_sum not summing across matches,
    matches_played miscounting, or within-tournament order-independence
    breaking) would pass every existing E2E test but fail here.
    """
    SEED = 1500
    EXCHANGE = 8  # diff=0, ChinaTT bin (12, 8, 8)

    tid = _create_rated_individual_tournament(shared_club_id)
    apps = [_register_account(f"mb{i}") for i in range(4)]
    uids = [a["uid"] for a in apps]
    try:
        for a in apps:
            _apply_to_join(tid, a["token"])
        teams = []
        for _ in range(30):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams",
                headers=_api_headers(), timeout=15,
            ).json()["data"]["teams"]
            if len(teams) >= 4:
                break
            time.sleep(0.5)
        assert len(teams) == 4, f"expected 4 bound teams, got {len(teams)}"

        # Map team_id -> user_id.
        team_to_uid: dict[int, int] = {}
        for tm in teams:
            row = _psql(
                f"SELECT user_id FROM teams_x_users WHERE team_id = {tm['id']};"
            )
            team_to_uid[tm["id"]] = int(row)

        _seed_all_active_same(uids, SEED)

        matches = _build_nteam_rr(tid, 4)
        assert len(matches) == 6, f"expected 6 RR matches, got {len(matches)}"

        # Desired outcomes: A beats everyone, B beats C+D, C beats D, D beats
        # nobody.  apps[0]=A … apps[3]=D.
        uid_a, uid_b, uid_c, uid_d = uids
        wins_map = {
            uid_a: {uid_b, uid_c, uid_d},
            uid_b: {uid_c, uid_d},
            uid_c: {uid_d},
            uid_d: set(),
        }
        for m in matches:
            uid1 = team_to_uid[m["team1_id"]]
            uid2 = team_to_uid[m["team2_id"]]
            if uid2 in wins_map.get(uid1, set()):
                winner_team_id = m["team1_id"]
            else:
                winner_team_id = m["team2_id"]
            _score_match_decisive(tid, m, winner_team_id)

        rows = _settle_and_get_leaderboard(tid, uids)

        expected = {
            uid_a: SEED + 3 * EXCHANGE,   # 1524  (wins 3)
            uid_b: SEED + 1 * EXCHANGE,   # 1508  (wins 2, loses 1: +8+8-8)
            uid_c: SEED - 1 * EXCHANGE,   # 1492  (wins 1, loses 2: +8-8-8)
            uid_d: SEED - 3 * EXCHANGE,   # 1476  (loses 3)
        }
        for uid in uids:
            assert rows[uid]["current_rating"] == expected[uid], (
                f"player {uid}: expected rating {expected[uid]}, "
                f"got {rows[uid]['current_rating']}"
            )
            assert rows[uid]["matches_played"] == 3, (
                f"player {uid}: expected matches_played=3, "
                f"got {rows[uid]['matches_played']}"
            )
        total = sum(rows[u]["current_rating"] for u in uids)
        assert total == 4 * SEED, f"rating sum must be conserved, got {total}"

        # UI: the rendered leaderboard shows each participant's settled rating.
        page.goto(
            f"{BASE_URL}/rating/1/leaderboard", wait_until="domcontentloaded"
        )
        for a in apps:
            expect(page.locator("body")).to_contain_text(
                a["name"], timeout=10_000
            )
    finally:
        _force_cleanup_rated(tid, uids)


# ---- M29: Settlement blocked when active stage is not the last -------------
# Critic issue 2.


def test_settlement_blocked_active_stage_not_last(
    page: Page, shared_club_id: int
) -> None:
    """M29: Settlement is blocked when the active stage is not the last stage.

    validate_settlement_ready calls _active_stage_is_last and raises "Advance
    through all stages before settling" when the active stage has a later
    sibling.  No E2E test exercises this guard: every settlement test uses a
    single-stage tournament.  This test creates a 2-stage rated individual
    tournament, activates stage 1, scores a match, and asserts POST
    /settlement-request returns 400 mentioning "advance"/"stages" and
    settled_seq stays null — plus the UI surfaces the error via a notification.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    applicant_a = _register_account("nsA")
    applicant_b = _register_account("nsB")
    uids = [applicant_a["uid"], applicant_b["uid"]]
    try:
        _apply_to_join(tid, applicant_a["token"])
        _apply_to_join(tid, applicant_b["token"])
        teams = []
        for _ in range(20):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams",
                headers=_api_headers(), timeout=15,
            ).json()["data"]["teams"]
            if len(teams) >= 2:
                break
            time.sleep(0.5)
        assert len(teams) == 2

        _seed_active_ratings(uids, 1500, 1500)

        # Stage 1: 2-team RR (1 match) — unscored for now.
        match_id, round_id = _build_stage_with_one_match(tid)

        # Stage 2: empty stage (no stage items needed — _active_stage_is_last
        # only checks the stages table).
        auth = _api_headers()
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/stages",
            headers=auth, json={"name": "S2"}, timeout=15,
        ).raise_for_status()

        # Activate stage 1 (direction="next" from no active -> activates S1).
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/stages/activate",
            headers=auth, json={"direction": "next"}, timeout=15,
        ).raise_for_status()

        # Verify exactly one active stage and >= 2 stages total.
        stages = api_get_stages(tid)
        active = [s for s in stages if s.get("is_active")]
        assert len(active) == 1, (
            f"expected exactly 1 active stage, got {len(active)}"
        )
        assert len(stages) >= 2, (
            f"expected >= 2 stages, got {len(stages)}"
        )

        # NOW score the match (after activation so update_matches_in_activated
        # stage has already run).
        requests.put(
            f"{BASE_URL}/api/tournaments/{tid}/matches/{match_id}",
            headers=auth,
            json={
                "id": match_id, "round_id": round_id, "games": None,
                "best_of": 3,
                "stage_item_input1_score": 2,
                "stage_item_input2_score": 0,
                "forfeit_input": None, "court_id": None,
                "custom_duration_minutes": None,
                "custom_margin_minutes": None,
            }, timeout=15,
        ).raise_for_status()

        # Pre-condition: not yet settled.
        assert api_get_tournament(tid).get("settled_seq") is None

        # API: settlement must be rejected with 400.
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/settlement-request",
            headers=auth, timeout=15,
        )
        assert r.status_code == 400, (
            f"expected 400 on not-last-stage settlement, "
            f"got {r.status_code}: {r.text[:200]}"
        )
        msg = (r.json().get("detail") or "").lower()
        assert "advance" in msg or "stage" in msg, (
            f"expected 'advance'/'stages' message, got: {msg!r}"
        )
        assert api_get_tournament(tid).get("settled_seq") is None, (
            "settled_seq must remain null after rejected settlement"
        )

        # UI: driving the button surfaces the 400 as a Mantine notification.
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/settings",
            wait_until="domcontentloaded",
        )
        button = page.get_by_role("button", name="\u7533\u8bf7\u79ef\u5206\u7ed3\u7b97")
        expect(button).to_be_visible(timeout=15_000)
        button.click()
        toast = page.get_by_text("操作失败", exact=True).first
        expect(toast).to_be_visible(timeout=10_000)
        assert api_get_tournament(tid).get("settled_seq") is None
    finally:
        _force_cleanup_rated(tid, uids)


# ---- M30: Settlement blocked on PARTIAL results ----------------------------
# Critic issue 3.


def test_settlement_blocked_partial_results(
    page: Page, shared_club_id: int
) -> None:
    """M30: Settlement is blocked when SOME (but not all) matches are unplayed.

    The completeness gate (settlement.py L109-116) rejects when ANY definitive
    match is unplayed (score1 == score2 and forfeit_input is None).  M13b tests
    the ALL-unplayed cell; this test covers the SOME-unplayed cell (3 of 6
    matches scored in a 4-team RR).  A regression that only checked "all
    unplayed" vs "any played" rather than checking each match individually
    would pass M13b but allow settling a partially-played tournament,
    corrupting ratings.
    """
    tid = _create_rated_individual_tournament(shared_club_id)
    apps = [_register_account(f"pr{i}") for i in range(4)]
    uids = [a["uid"] for a in apps]
    try:
        for a in apps:
            _apply_to_join(tid, a["token"])
        teams = []
        for _ in range(30):
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams",
                headers=_api_headers(), timeout=15,
            ).json()["data"]["teams"]
            if len(teams) >= 4:
                break
            time.sleep(0.5)
        assert len(teams) == 4

        _seed_all_active_same(uids, 1500)

        matches = _build_nteam_rr(tid, 4)
        assert len(matches) == 6

        # Score only the first 3 matches decisively; leave 3 unplayed.
        for m in matches[:3]:
            _score_match_decisive(tid, m, m["team1_id"])

        assert api_get_tournament(tid).get("settled_seq") is None

        # API: settlement must be rejected with 400.
        auth = _api_headers()
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/settlement-request",
            headers=auth, timeout=15,
        )
        assert r.status_code == 400, (
            f"expected 400 on partial-results settlement, "
            f"got {r.status_code}: {r.text[:200]}"
        )
        msg = (r.json().get("detail") or "").lower()
        assert "no recorded result" in msg or "match" in msg, (
            f"expected 'no recorded result'/'matches' message, got: {msg!r}"
        )
        assert api_get_tournament(tid).get("settled_seq") is None, (
            "settled_seq must remain null after rejected settlement"
        )

        # UI: driving the button surfaces the 400 as a Mantine notification.
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/settings",
            wait_until="domcontentloaded",
        )
        button = page.get_by_role("button", name="\u7533\u8bf7\u79ef\u5206\u7ed3\u7b97")
        expect(button).to_be_visible(timeout=15_000)
        button.click()
        toast = page.get_by_text("操作失败", exact=True).first
        expect(toast).to_be_visible(timeout=10_000)
        assert api_get_tournament(tid).get("settled_seq") is None
    finally:
        _force_cleanup_rated(tid, uids)