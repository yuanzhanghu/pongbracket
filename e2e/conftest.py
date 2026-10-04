"""Shared Playwright fixtures for the Bracket E2E suite.

Runs against the LOCAL DEV instance only (http://localhost:8401, project
bracket-dev). Never point this at production.

No pytest-playwright dependency: browser/context/page fixtures are built
directly on playwright.sync_api so the suite runs with plain
`python3 -m pytest`.

To stay under the 32-club subscription cap, the suite uses a SINGLE shared
club + tournament created once per session. Old E2E-prefixed clubs and
tournaments are pruned at session start to free up the caps.
"""
from __future__ import annotations

import os
import pathlib
import uuid
from typing import Dict, Optional

import pytest
import requests
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8401")
E2E_EMAIL = os.environ.get("E2E_EMAIL", "e2e@local.test")
E2E_PASSWORD = os.environ.get("E2E_PASSWORD", "e2e-Passw0rd!")
E2E_NAME = os.environ.get("E2E_NAME", "E2E Runner")
HEADLESS = os.environ.get("E2E_HEADLESS", "1") != "0"

_HERE = pathlib.Path(__file__).parent
_STATE = _HERE / ".auth" / "state.json"


def _safety_check() -> None:
    if "bracket.ai1to1.com" in BASE_URL or "8400" in BASE_URL:
        raise RuntimeError(
            f"E2E refuses to run against production-like target {BASE_URL!r}. "
            "Use the local dev instance (http://localhost:8401)."
        )


def _login(page: Page) -> bool:
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    email = page.locator('input[type="email"], input[name*="mail" i]').first
    pw = page.locator('input[type="password"]').first
    if not (email.count() and pw.count()):
        return False
    email.fill(E2E_EMAIL)
    pw.fill(E2E_PASSWORD)
    submit = page.locator(
        'button[type="submit"], button:has-text("\u767b\u5f55"), button:has-text("Login")'
    ).first
    submit.click() if submit.count() else pw.press("Enter")
    page.wait_for_timeout(2000)
    return page.url.rstrip("/") == BASE_URL.rstrip("/")


def _register(page: Page) -> bool:
    page.goto(f"{BASE_URL}/create-account", wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    email = page.locator('input[type="email"], input[name*="mail" i]').first
    name = page.locator('input[placeholder*="\u540d" i], input[name*="name" i]').first
    pw = page.locator('input[type="password"]').first
    if not (email.count() and pw.count()):
        return False
    email.fill(E2E_EMAIL)
    if name.count():
        name.fill(E2E_NAME)
    pw.fill(E2E_PASSWORD)
    submit = page.locator(
        'button[type="submit"], button:has-text("\u521b\u5efa"), button:has-text("\u6ce8\u518c"), '
        'button:has-text("Create")'
    ).first
    submit.click() if submit.count() else pw.press("Enter")
    page.wait_for_timeout(2500)
    return page.url.rstrip("/") == BASE_URL.rstrip("/")


def _api_register() -> None:
    """Register the E2E account via the API. In DEVELOPMENT the captcha secret
    is unset so any captcha_token passes. Safe to call when the account may
    already exist (the caller only invokes this after a 401)."""
    try:
        requests.post(
            f"{BASE_URL}/api/users/register",
            json={
                "email": E2E_EMAIL,
                "name": E2E_NAME,
                "password": E2E_PASSWORD,
                "captcha_token": "e2e-dev",
            },
            timeout=10,
        )
    except Exception:
        pass


def _api_token() -> str:
    def _post():
        return requests.post(
            f"{BASE_URL}/api/token",
            data={"grant_type": "password", "username": E2E_EMAIL, "password": E2E_PASSWORD},
            timeout=10,
        )

    r = _post()
    if r.status_code == 401:
        # Account not registered yet (e.g. a fresh dev DB) — self-register and retry.
        _api_register()
        r = _post()
    r.raise_for_status()
    return r.json()["access_token"]


def _api_headers() -> Dict[str, str]:
    return {"Authorization": f"bearer {_api_token()}", "Accept": "application/json"}


def _prune_old_e2e_clubs(keep_recent: int = 0) -> int:
    """Delete old E2E-prefixed clubs to stay under the 32-club cap."""
    try:
        r = requests.get(
            f"{BASE_URL}/api/clubs", headers=_api_headers(), timeout=10
        )
        r.raise_for_status()
    except Exception:
        return 0
    clubs = [
        c for c in r.json().get("data", [])
        if c.get("name", "").startswith("E2E-")
    ]
    clubs.sort(key=lambda c: c.get("created", ""), reverse=True)
    deleted = 0
    auth = _api_headers()
    for c in clubs[keep_recent:]:
        try:
            requests.delete(
                f"{BASE_URL}/api/clubs/{c['id']}", headers=auth, timeout=10
            )
            deleted += 1
        except Exception:
            pass
    return deleted


def _find_existing_shared_club() -> Optional[int]:
    """Return the id of an existing E2E-Shared-Club-* that has room for a
    new tournament, else None.

    The REGULAR subscription caps a club at 64 tournaments. The conftest
    used to return the first E2E-Shared-Club in the list, which (after
    many test runs) could be at the 64-tournament cap, causing the
    session fixture's POST to /api/tournaments to 400. We now prefer a
    shared club with < 64 tournaments; if none exists we return None so
    the caller can try to create a fresh one.
    """
    try:
        r = requests.get(
            f"{BASE_URL}/api/clubs", headers=_api_headers(), timeout=10
        )
        r.raise_for_status()
    except Exception:
        return None
    try:
        t = requests.get(
            f"{BASE_URL}/api/tournaments?filter_=ALL",
            headers=_api_headers(),
            timeout=10,
        )
        t.raise_for_status()
    except Exception:
        t_json: Dict[str, list] = {"data": []}
    else:
        t_json = t.json()
    counts: Dict[int, int] = {}
    for tn in t_json.get("data", []):
        cid = tn.get("club_id")
        if cid is not None:
            counts[cid] = counts.get(cid, 0) + 1
    for c in r.json().get("data", []):
        if c.get("name", "").startswith("E2E-Shared-Club-"):
            if counts.get(c["id"], 0) < 64:
                return c["id"]
    return None

def _create_shared_club() -> int:
    """Create one shared club for the whole session (or reuse existing)."""
    existing = _find_existing_shared_club()
    if existing is not None:
        return existing
    auth = _api_headers()
    r = requests.post(
        f"{BASE_URL}/api/clubs",
        headers=auth,
        json={"name": f"E2E-Shared-Club-{uuid.uuid4().hex[:6]}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def _prune_old_tournaments_in_club(club_id: int, keep_id: Optional[int] = None) -> int:
    """Delete old E2E-* tournaments in the given club.

    Historically this only deleted ``E2E-Shared-T-*`` tournaments, but the
    suite creates many other dedicated-tournament prefixes (``E2E-FreshT-``,
    ``E2E-DashT-``, ``E2E-NextStage-``, ``E2E-Rated-``, ``E2E-Rankings-``,
    ``E2E-MatchH4-``, ``E2E-Open-``, ``E2E-Arch-``, ``E2E-Del-``, ``E2E-T-``,
    ...) that, on test failure, would never be cleaned up and accumulated
    until the per-club cap (64 for the REGULAR subscription) was hit. Once
    full, the session fixture's POST to /api/tournaments would 400 and
    every test in the session that depends on the shared tournament fails.

    We now prune *any* ``E2E-*`` tournament in the club, optionally keeping
    the just-created one (``keep_id``).
    """
    try:
        r = requests.get(
            f"{BASE_URL}/api/tournaments?filter_=ALL",
            headers=_api_headers(),
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        return 0
    auth = _api_headers()
    deleted = 0
    for t in r.json().get("data", []):
        if t.get("club_id") != club_id:
            continue
        if keep_id is not None and t.get("id") == keep_id:
            continue
        if t.get("name", "").startswith("E2E-"):
            try:
                requests.delete(
                    f"{BASE_URL}/api/tournaments/{t['id']}",
                    headers=auth,
                    timeout=10,
                )
                deleted += 1
            except Exception:
                pass
    return deleted


def _psql_exec(sql: str) -> None:
    """Run a SQL statement against the dev DB via the postgres container."""
    import subprocess

    try:
        subprocess.run(
            [
                "docker", "exec", "bracket-dev-postgres-1",
                "psql", "-U", "bracket_dev", "-d", "bracket_dev", "-tAc", sql,
            ],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        pass


def _force_delete_tournament(tid: int, auth: Dict[str, str]) -> bool:
    """Best-effort cascade-delete of a tournament: stage_items -> stages ->
    teams -> courts -> players -> tournament. Returns True if the tournament
    was successfully deleted.

    The DELETE /api/tournaments/{id} endpoint refuses if the tournament
    still has stages/teams/players/etc, and also refuses if the tournament
    is settled (settled_seq is set). Without cascading these dependents
    AND unsetting settled_seq, crashed test runs that left half-built or
    settled tournaments would never be cleaned up and accumulate until
    each shared club hits the 64 per-club cap.
    """
    try:
        # Unset settled_seq so the DELETE endpoint's disallow_settled guard
        # doesn't reject the deletion.
        _psql_exec(f"UPDATE tournaments SET settled_seq = NULL WHERE id = {tid};")
        # Un-archive so API delete-player (which disallows archived) can proceed.
        requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/change-status",
            headers=auth, json={"status": "OPEN"}, timeout=10,
        )
        sg = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/stages", headers=auth, timeout=10
        )
        if sg.ok:
            for s in sg.json().get("data", []):
                for it in s.get("stage_items", []):
                    requests.delete(
                        f"{BASE_URL}/api/tournaments/{tid}/stage_items/{it['id']}",
                        headers=auth,
                        timeout=10,
                    )
                requests.delete(
                    f"{BASE_URL}/api/tournaments/{tid}/stages/{s['id']}",
                    headers=auth,
                    timeout=10,
                )
        tg = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/teams", headers=auth, timeout=10
        )
        if tg.ok:
            for tm in tg.json().get("data", {}).get("teams", []):
                requests.delete(
                    f"{BASE_URL}/api/tournaments/{tid}/teams/{tm['id']}",
                    headers=auth,
                    timeout=10,
                )
        cg = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/courts", headers=auth, timeout=10
        )
        if cg.ok:
            for ct in cg.json().get("data", []):
                requests.delete(
                    f"{BASE_URL}/api/tournaments/{tid}/courts/{ct['id']}",
                    headers=auth,
                    timeout=10,
                )
        # Delete players via API.
        pg = requests.get(
            f"{BASE_URL}/api/tournaments/{tid}/players", headers=auth, timeout=10
        )
        if pg.ok:
            for p in pg.json().get("data", {}).get("players", []):
                requests.delete(
                    f"{BASE_URL}/api/tournaments/{tid}/players/{p['id']}",
                    headers=auth,
                    timeout=10,
                )
        # Force-delete any remaining players via psql (API may refuse on
        # archived or settled tournaments).
        _psql_exec(f"DELETE FROM players WHERE tournament_id = {tid};")
        r = requests.delete(
            f"{BASE_URL}/api/tournaments/{tid}", headers=auth, timeout=10
        )
        return r.ok
    except Exception:
        return False


def _prune_all_e2e_tournaments(keep_ids: Optional[set] = None) -> int:
    """Delete every E2E-* tournament across all clubs except those in keep_ids.

    Called once at session start to clear out leftover tournaments from
    crashed test runs that filled every shared club to the 64-cap.
    Cascade-deletes stages / teams / courts so the DELETE /tournaments
    endpoint accepts (it refuses on dependents).

    NOTE: this is aggressive (deletes ALL E2E-* tournaments, any age) so it
    reliably clears the per-club cap left by crashed/killed runs. It is
    therefore only safe under SINGLE-SESSION execution — two overlapping
    pytest sessions on the same dev DB will delete each other's live shared
    tournament. The loop's author/critic must run pytest one invocation at a
    time (see loop_create_playwright_e2e.sh task prompts).
    """
    keep = keep_ids or set()
    try:
        r = requests.get(
            f"{BASE_URL}/api/tournaments?filter_=ALL",
            headers=_api_headers(),
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        return 0
    auth = _api_headers()
    deleted = 0
    for t in r.json().get("data", []):
        if t.get("id") in keep:
            continue
        if t.get("name", "").startswith("E2E-"):
            if _force_delete_tournament(t["id"], auth):
                deleted += 1
    return deleted



def _create_shared_tournament(club_id: int) -> int:
    """Create a fresh shared tournament for the session."""
    _prune_old_tournaments_in_club(club_id)
    name = f"E2E-Shared-T-{uuid.uuid4().hex[:6]}"
    auth = _api_headers()
    r = requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": name,
            "club_id": club_id,
            "dashboard_public": True,
            "dashboard_endpoint": "",
            "players_can_be_in_multiple_teams": False,
            "auto_assign_courts": True,
            "start_time": "2030-01-01T00:00:00Z",
            "duration_minutes": 10,
            "margin_minutes": 5,
        },
        timeout=10,
    )
    r.raise_for_status()
    r2 = requests.get(
        f"{BASE_URL}/api/tournaments?filter_=ALL", headers=auth, timeout=10
    )
    r2.raise_for_status()
    for t in r2.json()["data"]:
        if t["name"] == name and t["club_id"] == club_id:
            return t["id"]
    raise RuntimeError("could not find shared tournament")


def _create_team(tournament_id: int, name: str) -> int:
    auth = _api_headers()
    r = requests.post(
        f"{BASE_URL}/api/tournaments/{tournament_id}/teams",
        headers=auth,
        json={"name": name, "active": True, "player_names": []},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


@pytest.fixture(scope="session", autouse=True)
def _shared_resources():
    """Create one shared club + tournament for the whole session.

    Before creating, aggressively prune all leftover E2E-* tournaments so the
    REGULAR per-club 64-tournament cap doesn't block the new shared tournament
    POST. Without this, an accumulated cap from prior crashed runs causes
    every test in the session to fail.
    """
    _safety_check()
    _prune_all_e2e_tournaments()
    _prune_old_e2e_clubs()
    _prune_old_e2e_clubs()
    club_id = _create_shared_club()
    tournament_id = _create_shared_tournament(club_id)
    for i in range(8):
        _create_team(tournament_id, f"E2E-Shared-Team-{i}")
    yield {"club_id": club_id, "tournament_id": tournament_id}
    try:
        auth = _api_headers()
        requests.delete(
            f"{BASE_URL}/api/tournaments/{tournament_id}", headers=auth, timeout=10
        )
        requests.delete(
            f"{BASE_URL}/api/clubs/{club_id}", headers=auth, timeout=10
        )
    except Exception:
        pass


@pytest.fixture()
def shared_tournament_id(_shared_resources) -> int:
    return _shared_resources["tournament_id"]


@pytest.fixture()
def shared_club_id(_shared_resources) -> int:
    return _shared_resources["club_id"]


@pytest.fixture(scope="session")
def _playwright():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(_playwright) -> Browser:
    b = _playwright.chromium.launch(headless=HEADLESS)
    yield b
    b.close()


@pytest.fixture(scope="session")
def auth_state(browser: Browser) -> str:
    ctx = browser.new_context(base_url=BASE_URL)
    page = ctx.new_page()
    if not _login(page):
        _register(page) or _login(page)
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    ctx.storage_state(path=str(_STATE))
    ctx.close()
    return str(_STATE)


@pytest.fixture()
def context(browser: Browser, auth_state: str) -> BrowserContext:
    ctx = browser.new_context(base_url=BASE_URL, storage_state=auth_state)
    yield ctx
    ctx.close()


@pytest.fixture()
def page(context: BrowserContext) -> Page:
    """A fresh, already-logged-in page for each test."""
    pg = context.new_page()
    pg.goto(BASE_URL, wait_until="domcontentloaded")
    yield pg
    pg.close()


@pytest.fixture()
def anon_page(browser: Browser) -> Page:
    """A logged-out page for auth/landing-page tests."""
    ctx = browser.new_context(base_url=BASE_URL)
    pg = ctx.new_page()
    yield pg
    ctx.close()


def make_logged_in_context(browser: Browser, access_token: str) -> BrowserContext:
    """Return a fresh BrowserContext logged in as an ARBITRARY account, given
    only its API access token. The frontend's source of truth is
    localStorage['login'] = JSON.stringify({access_token, ...}) and the axios
    adapter reads `.access_token` off it (see frontend/src/services/
    local_storage.tsx + adapter.tsx), so injecting that one key via an init
    script (runs before any app JS on every page in the context) is a complete,
    durable login — no UI form, no flaky waits.

    Use this to drive the SAME page as different roles (owner vs applicant vs
    scorer vs outsider) and assert the permission-dependent affordances each one
    sees. Caller owns the context and must close it.

        ctx = make_logged_in_context(browser, applicant["token"])
        pg = ctx.new_page(); pg.goto(f"/tournaments/{tid}/results"); ...
        ctx.close()
    """
    ctx = browser.new_context(base_url=BASE_URL)
    payload = '{"access_token":"%s"}' % access_token
    ctx.add_init_script(f"window.localStorage.setItem('login', '{payload}');")
    return ctx