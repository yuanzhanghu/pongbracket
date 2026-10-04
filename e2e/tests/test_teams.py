"""Team tests (E1-E5).

Asserts:
  E1: add a single team.
  E3: teams list shows added teams.
  E4: edit a team (rename).
  E5: delete a team.
"""
from __future__ import annotations

import uuid

from playwright.sync_api import Page, expect

from ._helpers import (
    BASE_URL,
    api_get_teams,
    api_update_team,
)


def test_add_single_team(page: Page, shared_tournament_id: int) -> None:
    """E1 + E3: adding a single team makes it appear in the teams list."""
    team_name = f"E2E-Team-{uuid.uuid4().hex[:6]}"
    page.goto(
        f"{BASE_URL}/tournaments/{shared_tournament_id}/teams", wait_until="domcontentloaded"
    )
    add_btn = page.get_by_role("button", name="\u6dfb\u52a0\u961f\u4f0d").first
    expect(add_btn).to_be_visible(timeout=15_000)
    add_btn.click()
    page.wait_for_selector(".mantine-Modal-content", state="visible", timeout=10_000)
    page.get_by_placeholder("\u6700\u4f73\u961f\u4f0d").first.fill(team_name)
    page.locator(".mantine-Modal-content").last.get_by_role(
        "button", name="\u4fdd\u5b58"
    ).first.click()
    expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)
    expect(page.locator("body")).to_contain_text(team_name, timeout=10_000)


def test_edit_team(page: Page, shared_tournament_id: int) -> None:
    """E4: renaming a team via the 编辑 modal updates the table.

    This mutates the SHARED team E2E-Shared-Team-0, so the original name is
    restored in a `finally` via the API (not the UI) — a UI-only restore
    that fails mid-way would leave the shared team renamed and break every
    other test that relies on the seeded E2E-Shared-Team-N names.
    """
    # Use one of the pre-populated shared teams.
    original = "E2E-Shared-Team-0"
    new_name = f"E2E-Renamed-{uuid.uuid4().hex[:6]}"
    # Resolve the team id up front so the restore is reliable.
    team_id = next(
        (t["id"] for t in api_get_teams(shared_tournament_id) if t["name"] == original),
        None,
    )
    assert team_id is not None, f"shared team {original!r} not found"
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{shared_tournament_id}/teams",
            wait_until="domcontentloaded",
        )
        expect(page.locator("body")).to_contain_text(original, timeout=15_000)
        row = page.locator("tr", has=page.get_by_text(original, exact=True)).first
        row.get_by_role("button", name="编辑", exact=True).first.click()
        page.wait_for_selector(".mantine-Modal-content", state="visible", timeout=10_000)
        page.get_by_placeholder("最佳队伍").first.fill(new_name)
        page.locator(".mantine-Modal-content").last.get_by_role(
            "button", name="保存"
        ).first.click()
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)
        expect(page.locator("body")).to_contain_text(new_name, timeout=10_000)
    finally:
        # Always restore the shared team's original name via the API.
        api_update_team(shared_tournament_id, team_id, original)


def test_delete_team(page: Page, shared_tournament_id: int) -> None:
    """E5: deleting a team via the trash button removes it from the list AND
    the API confirms the row left the server (mirrors C4's API ground-truth).

    Without the API check, an SWR optimistic-update or cache-hide where the
    server DELETE silently fails would still leave the UI text gone (the
    team is removed from the SWR cache locally) and the test would pass."""
    from ._helpers import _api_headers
    import requests
    # Create a temporary team via API
    team_name = f"E2E-DelTeam-{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/api/tournaments/{shared_tournament_id}/teams",
        headers=_api_headers(),
        json={"name": team_name, "active": True, "player_names": []},
        timeout=10,
    )
    r.raise_for_status()
    team_id = r.json()["data"]["id"]

    page.goto(
        f"{BASE_URL}/tournaments/{shared_tournament_id}/teams", wait_until="domcontentloaded"
    )
    expect(page.locator("body")).to_contain_text(team_name, timeout=15_000)
    row = page.locator("tr", has=page.get_by_text(team_name, exact=True)).first
    row.get_by_role("button", name="\u5220\u9664", exact=True).first.click()
    expect(page.locator("body")).not_to_contain_text(team_name, timeout=10_000)
    # API ground truth: the row really left the server (catches an SWR
    # optimistic-hide where the server DELETE silently failed).
    teams = api_get_teams(shared_tournament_id)
    assert not any(t["id"] == team_id for t in teams), (
        f"team id={team_id} still present in API after UI delete: "
        f"{[t for t in teams if t['id'] == team_id]!r}"
    )