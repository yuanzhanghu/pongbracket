"""Shared helpers for the Bracket E2E suite.

NOTE on ports: docker-compose maps host 8401 -> container 8400. The conftest
guard forbids the browser from being pointed at host port 8400 (a separate
instance). API setup helpers MUST go through host port 8401 so they hit the
same database the browser sees.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

import requests
from playwright.sync_api import Page

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8401")
API_URL = os.environ.get("E2E_API_URL", "http://localhost:8401")
E2E_EMAIL = os.environ.get("E2E_EMAIL", "e2e@local.test")
E2E_PASSWORD = os.environ.get("E2E_PASSWORD", "e2e-Passw0rd!")
E2E_NAME = os.environ.get("E2E_NAME", "E2E Runner")


def unique_prefix() -> str:
    return f"E2E-{uuid.uuid4().hex[:8]}"


# ---- API helpers (setup only) ----

def _api_token() -> str:
    r = requests.post(
        f"{API_URL}/api/token",
        data={"grant_type": "password", "username": E2E_EMAIL, "password": E2E_PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _api_headers() -> Dict[str, str]:
    return {"Authorization": f"bearer {_api_token()}", "Accept": "application/json"}


def api_create_club(name: str) -> int:
    r = requests.post(f"{API_URL}/api/clubs", headers=_api_headers(), json={"name": name}, timeout=15)
    r.raise_for_status()
    return r.json()["data"]["id"]


def api_delete_club(club_id: int) -> None:
    requests.delete(f"{API_URL}/api/clubs/{club_id}", headers=_api_headers(), timeout=15)


def api_create_tournament(
    club_id: int,
    name: str,
    dashboard_public: bool = True,
    start_time: Optional[str] = None,
    dashboard_endpoint: str = "",
) -> int:
    body = {
        "name": name,
        "club_id": club_id,
        "dashboard_public": dashboard_public,
        "dashboard_endpoint": dashboard_endpoint,
        "players_can_be_in_multiple_teams": False,
        "auto_assign_courts": True,
        "start_time": start_time or "2030-01-01T00:00:00Z",
        "duration_minutes": 10,
        "margin_minutes": 5,
    }
    r = requests.post(f"{API_URL}/api/tournaments", headers=_api_headers(), json=body, timeout=15)
    r.raise_for_status()
    # The tournaments endpoint returns {"success":true} without the new id.
    r2 = requests.get(f"{API_URL}/api/tournaments?filter_=ALL", headers=_api_headers(), timeout=15)
    r2.raise_for_status()
    for t in r2.json()["data"]:
        if t["name"] == name and t["club_id"] == club_id:
            return t["id"]
    raise RuntimeError(f"could not find newly created tournament {name!r}")


def api_archive_tournament(tournament_id: int, status: str = "ARCHIVED") -> None:
    """Change a tournament's status (ARCHIVED <-> OPEN) via the change-status endpoint."""
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/change-status",
        headers=_api_headers(),
        json={"status": status},
        timeout=15,
    )
    r.raise_for_status()


def api_get_rankings(tournament_id: int) -> List[Dict[str, Any]]:
    r = requests.get(
        f"{API_URL}/api/tournaments/{tournament_id}/rankings",
        headers=_api_headers(),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]


def api_update_ranking(
    tournament_id: int,
    ranking_id: int,
    win_points: float,
    draw_points: float,
    loss_points: float,
    add_score_points: bool = False,
) -> None:
    r = requests.put(
        f"{API_URL}/api/tournaments/{tournament_id}/rankings/{ranking_id}",
        headers=_api_headers(),
        json={
            "win_points": str(win_points),
            "draw_points": str(draw_points),
            "loss_points": str(loss_points),
            "add_score_points": add_score_points,
            "position": 0,
        },
        timeout=15,
    )
    r.raise_for_status()


def _psql_exec(sql: str) -> str:
    """Run a SQL statement against the dev DB via the postgres container.

    Used by cleanup helpers to unset settled_seq (the API refuses to delete
    settled tournaments) and delete players (the API delete-player endpoint
    refuses on archived tournaments, so psql is more reliable for teardown).
    """
    import subprocess

    out = subprocess.run(
        [
            "docker", "exec", "bracket-dev-postgres-1",
            "psql", "-U", "bracket_dev", "-d", "bracket_dev", "-tAc", sql,
        ],
        capture_output=True, text=True, timeout=15,
    )
    return out.stdout.strip()


def api_delete_tournament(tournament_id: int) -> None:
    """Delete a tournament, cascade-deleting its dependents first.

    The backend's DELETE /tournaments/{id} does NOT cascade: it refuses (400)
    while a tournament still has stages / teams / courts / players, and also
    refuses if the tournament is settled (settled_seq is set). A plain DELETE
    therefore SILENTLY leaves the tournament (and all its dependents) behind,
    so per-test ``finally: api_delete_tournament(tid)`` cleanups were no-ops
    for any tournament that created a stage/team/court or was settled. Over
    many runs the shared club fills to the 64-tournament cap and every
    subsequent POST /tournaments 400s, turning the whole session red. We
    bottom-up delete dependents (stage_items -> stages -> teams -> courts ->
    players) and unset settled_seq via psql before removing the tournament so
    the cleanup actually succeeds.
    """
    h = _api_headers()
    base = f"{API_URL}/api/tournaments/{tournament_id}"
    # Unset settled_seq so the API DELETE endpoint's disallow_settled_tournament
    # guard doesn't reject the deletion.
    try:
        _psql_exec(
            f"UPDATE tournaments SET settled_seq = NULL WHERE id = {tournament_id};"
        )
    except Exception:
        pass
    # Un-archive so the API delete-player endpoint (which disallows archived)
    # can proceed if needed.
    try:
        requests.post(
            f"{base}/change-status", headers=h, json={"status": "OPEN"}, timeout=15
        )
    except Exception:
        pass
    try:
        stages = requests.get(f"{base}/stages", headers=h, timeout=15).json().get("data", [])
        for st in stages:
            for si in st.get("stage_items", []):
                requests.delete(f"{base}/stage_items/{si['id']}", headers=h, timeout=15)
            requests.delete(f"{base}/stages/{st['id']}", headers=h, timeout=15)
    except Exception:
        pass
    try:
        teams = requests.get(f"{base}/teams", headers=h, timeout=15).json().get("data", {})
        for tm in teams.get("teams", []):
            requests.delete(f"{base}/teams/{tm['id']}", headers=h, timeout=15)
    except Exception:
        pass
    try:
        courts = requests.get(f"{base}/courts", headers=h, timeout=15).json().get("data", [])
        if isinstance(courts, list):
            for c in courts:
                requests.delete(f"{base}/courts/{c['id']}", headers=h, timeout=15)
    except Exception:
        pass
    # Delete players via API (the endpoint exists at /players/{player_id}).
    try:
        players_resp = requests.get(f"{base}/players", headers=h, timeout=15)
        if players_resp.ok:
            for p in players_resp.json().get("data", {}).get("players", []):
                requests.delete(f"{base}/players/{p['id']}", headers=h, timeout=15)
    except Exception:
        pass
    # If players still exist (e.g. the API delete refused for some reason),
    # force-delete them via psql so the tournament DELETE can proceed.
    try:
        _psql_exec(
            f"DELETE FROM players WHERE tournament_id = {tournament_id};"
        )
    except Exception:
        pass
    requests.delete(base, headers=h, timeout=15)


def api_create_team(tournament_id: int, name: str) -> int:
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/teams",
        headers=_api_headers(),
        json={"name": name, "active": True, "player_names": []},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def api_create_teams(tournament_id: int, names: List[str]) -> List[int]:
    """Create multiple teams, one at a time (most reliable)."""
    return [api_create_team(tournament_id, n) for n in names]


def api_delete_team(tournament_id: int, team_id: int) -> None:
    requests.delete(
        f"{API_URL}/api/tournaments/{tournament_id}/teams/{team_id}",
        headers=_api_headers(),
        timeout=15,
    )


def api_get_teams(tournament_id: int) -> List[Dict[str, Any]]:
    r = requests.get(
        f"{API_URL}/api/tournaments/{tournament_id}/teams",
        headers=_api_headers(),
        timeout=15,
    )
    r.raise_for_status()
    # Response shape: {"data": {"count": N, "teams": [...]}}
    return r.json()["data"]["teams"]


def api_update_team(
    tournament_id: int, team_id: int, name: str, active: bool = True
) -> None:
    requests.put(
        f"{API_URL}/api/tournaments/{tournament_id}/teams/{team_id}",
        headers=_api_headers(),
        json={"name": name, "active": active, "player_names": []},
        timeout=15,
    ).raise_for_status()


def api_create_court(tournament_id: int, name: str) -> int:
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/courts",
        headers=_api_headers(),
        json={"name": name},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def api_delete_court(tournament_id: int, court_id: int) -> None:
    requests.delete(
        f"{API_URL}/api/tournaments/{tournament_id}/courts/{court_id}",
        headers=_api_headers(),
        timeout=15,
    )


def api_create_stage(tournament_id: int, name: str = "Stage") -> int:
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/stages",
        headers=_api_headers(),
        json={"name": name},
        timeout=15,
    )
    r.raise_for_status()
    stages = api_get_stages(tournament_id)
    for s in stages:
        if s["name"] == name:
            return s["id"]
    if stages:
        return stages[-1]["id"]
    raise RuntimeError(f"could not find newly created stage {name!r}")


def api_activate_next_stage(tournament_id: int, direction: str = "next") -> None:
    """Flip the active stage. Activating a stage is what resolves an elimination
    item's tentative inputs (小组1第1名, ...) into the actual qualifying teams."""
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/stages/activate",
        headers=_api_headers(),
        json={"direction": direction},
        timeout=15,
    )
    r.raise_for_status()


def api_create_round_robin(
    tournament_id: int, stage_id: int, team_count: int = 4, group_count: int = 1
) -> int:
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/stage_items/round_robin_groups",
        headers=_api_headers(),
        json={"stage_id": stage_id, "group_count": group_count, "team_count": team_count},
        timeout=15,
    )
    r.raise_for_status()
    stages = api_get_stages(tournament_id)
    for s in stages:
        if s["id"] == stage_id:
            items = s.get("stage_items", [])
            if items:
                return items[-1]["id"]
    raise RuntimeError("could not find newly created round-robin stage item")


def api_create_single_elimination(
    tournament_id: int, stage_id: int, team_count: int = 4
) -> int:
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/stage_items",
        headers=_api_headers(),
        json={"stage_id": stage_id, "type": "SINGLE_ELIMINATION", "team_count": team_count},
        timeout=15,
    )
    r.raise_for_status()
    stages = api_get_stages(tournament_id)
    for s in stages:
        if s["id"] == stage_id:
            items = s.get("stage_items", [])
            if items:
                return items[-1]["id"]
    raise RuntimeError("could not find newly created SE stage item")

def api_create_single_elimination_from_sources(
    tournament_id: int,
    stage_id: int,
    sources: List[Dict[str, int]],
    take: str = "top",
    name: Optional[str] = None,
) -> int:
    """Create an SE stage item seeded from prior stage-item rankings.

    `sources` is a list of {"stage_item_id": ..., "positions": N} dicts.
    Returns the new SE stage item id.
    """
    body: Dict[str, Any] = {"stage_id": stage_id, "sources": sources, "take": take}
    if name is not None:
        body["name"] = name
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/stage_items/elimination_from_sources",
        headers=_api_headers(),
        json=body,
        timeout=15,
    )
    r.raise_for_status()
    stages = api_get_stages(tournament_id)
    for s in stages:
        if s["id"] == stage_id:
            items = s.get("stage_items", [])
            if items:
                return items[-1]["id"]
    raise RuntimeError("could not find newly created SE-from-sources stage item")


def api_rename_stage_item(tournament_id: int, stage_item_id: int, name: str) -> None:
    """Rename a stage item.

    The backend auto-names round-robin groups 小组1, 小组2, ... (and elimination
    items 单淘汰赛) in Chinese whatever the UI language is, because those names
    are stored rows rather than i18n keys. The demo/screenshot generators rename
    them so an English or French capture has no Chinese left in it.
    """
    ranking_id = None
    for stage in api_get_stages(tournament_id):
        for item in stage.get("stage_items", []):
            if item["id"] == stage_item_id:
                ranking_id = item.get("ranking_id")
    r = requests.put(
        f"{API_URL}/api/tournaments/{tournament_id}/stage_items/{stage_item_id}",
        headers=_api_headers(),
        json={"name": name, "ranking_id": ranking_id},
        timeout=15,
    )
    r.raise_for_status()


def api_get_stages(tournament_id: int) -> List[Dict[str, Any]]:
    r = requests.get(
        f"{API_URL}/api/tournaments/{tournament_id}/stages",
        headers=_api_headers(),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]


def api_get_courts(tournament_id: int) -> List[Dict[str, Any]]:
    r = requests.get(
        f"{API_URL}/api/tournaments/{tournament_id}/courts",
        headers=_api_headers(),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["data"]


def api_schedule_matches(tournament_id: int) -> None:
    """Schedule all unscheduled matches. The endpoint returns SuccessResponse."""
    r = requests.post(
        f"{API_URL}/api/tournaments/{tournament_id}/schedule_matches",
        headers=_api_headers(),
        timeout=30,
    )
    r.raise_for_status()

def api_update_match_score(
    tournament_id: int,
    match_id: int,
    round_id: int,
    games: List[List[int]],
    best_of: int = 3,
) -> None:
    r = requests.put(
        f"{API_URL}/api/tournaments/{tournament_id}/matches/{match_id}",
        headers=_api_headers(),
        json={
            "id": match_id,
            "round_id": round_id,
            "games": games,
            "best_of": best_of,
            "stage_item_input1_score": sum(1 for g in games if g[0] > g[1]),
            "stage_item_input2_score": sum(1 for g in games if g[1] > g[0]),
            "court_id": None,
            "custom_duration_minutes": None,
            "custom_margin_minutes": None,
        },
        timeout=15,
    )
    r.raise_for_status()


def api_delete_match(tournament_id: int, match_id: int) -> None:
    requests.delete(
        f"{API_URL}/api/tournaments/{tournament_id}/matches/{match_id}",
        headers=_api_headers(),
        timeout=15,
    )
def api_get_clubs() -> List[Dict[str, Any]]:
    r = requests.get(f"{API_URL}/api/clubs", headers=_api_headers(), timeout=15)
    r.raise_for_status()
    return r.json()["data"]


def api_get_tournaments() -> List[Dict[str, Any]]:
    r = requests.get(
        f"{API_URL}/api/tournaments?filter_=ALL", headers=_api_headers(), timeout=15
    )
    r.raise_for_status()
    return r.json()["data"]


def api_delete_stage(tournament_id: int, stage_id: int) -> None:
    requests.delete(
        f"{API_URL}/api/tournaments/{tournament_id}/stages/{stage_id}",
        headers=_api_headers(),
        timeout=15,
    )


def api_count_matches(tournament_id: int) -> int:
    """Total number of matches across all stages/rounds (handles round-robin etc)."""
    n = 0
    for stage in api_get_stages(tournament_id):
        for item in stage.get("stage_items", []):
            for rd in item.get("rounds", []):
                n += len(rd.get("matches", []))
    return n


def api_update_tournament_name(tournament_id: int, name: str) -> None:
    """Restore a tournament's name without other side effects."""
    # The PUT endpoint expects a complete payload; fetch current first.
    r = requests.get(
        f"{API_URL}/api/tournaments/{tournament_id}", headers=_api_headers(), timeout=15
    )
    r.raise_for_status()
    body = r.json()["data"]
    body["name"] = name
    requests.put(
        f"{API_URL}/api/tournaments/{tournament_id}",
        headers=_api_headers(),
        json=body,
        timeout=15,
    ).raise_for_status()


def api_get_tournament(tournament_id: int) -> Dict[str, Any]:
    r = requests.get(
        f"{API_URL}/api/tournaments/{tournament_id}", headers=_api_headers(), timeout=15
    )
    r.raise_for_status()
    return r.json()["data"]


# ---- UI helpers ----

def logout_via_ui(page: Page) -> None:
    page.evaluate("() => window.localStorage.removeItem('login')")
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")


def goto_clubs_page(page: Page) -> None:
    page.goto(f"{BASE_URL}/clubs", wait_until="domcontentloaded")


def goto_tournaments_home(page: Page) -> None:
    page.goto(BASE_URL, wait_until="domcontentloaded")


def goto_tournament_tab(page: Page, tournament_id: int, tab: str) -> None:
    page.goto(f"{BASE_URL}/tournaments/{tournament_id}/{tab}", wait_until="domcontentloaded")
    page.wait_for_timeout(500)


# --- match-modal result-button score entry -------------------------------
# The match modal no longer chooses a best-of format or records per-game
# points (小分). Score entry is a single tap on a result button labelled
# "<winner_games>:<loser_games>" (e.g. "2:0", "3:1"). Each exact label appears
# once across the two ("team1 wins" / "team2 wins") sections, so an exact
# role+name match is unambiguous. Games stay empty, so 小分 == 0 for everyone.


def set_match_result(modal, s1: int, s2: int) -> None:
    """Set the match score to s1:s2 (games won) by clicking its result button.

    s1 is input1's games, s2 is input2's games; the winning side's count must
    be 2, 3 or 4. The modal saves and closes on click.
    """
    modal.get_by_role("button", name=f"{int(s1)}:{int(s2)}", exact=True).click()


def forfeit_match(modal, team_name: str) -> None:
    """Mark `team_name` as having forfeited (walkover); saves and closes."""
    modal.get_by_role("button", name=f"{team_name} 弃权").click()


def clear_match_score(modal) -> None:
    """Reset the match back to 0:0 with no forfeit; saves and closes."""
    modal.get_by_role("button", name="清除比分").click()
