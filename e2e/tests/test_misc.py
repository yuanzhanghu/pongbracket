"""Miscellaneous tests (J1-J3)."""

from __future__ import annotations

import uuid

from playwright.sync_api import Page, expect

from ._helpers import (
    BASE_URL,
    _api_headers,
    api_archive_tournament,
    api_create_court,
    api_create_round_robin,
    api_create_stage,
    api_create_team,
    api_create_tournament,
    api_delete_tournament,
    api_schedule_matches,
)
import requests

# The organiser-only hint above the score grid on the results page.
HINT_FILL_SCORES = "\u70b9\u51fb\u8868\u683c\u6216\u5bf9\u9635\u56fe\u4e2d\u7684\u4f4d\u7f6e\u5373\u53ef\u586b\u5199\u6bd4\u5206"


def test_user_profile_page_reachable(page: Page) -> None:
    """J1: /user profile page is reachable and renders the edit-details form.

    The user form has three tabs (details / password / language); the
    details tab is the default and exposes the email + name + save + logout
    controls. The password input lives on a separate tab and is intentionally
    not asserted here.
    """
    page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded")
    expect(page.locator("body")).to_contain_text("\u7f16\u8f91\u4e2a\u4eba\u8d44\u6599", timeout=10_000)
    # The default 'details' tab renders the email input.
    expect(page.locator('input[name="email"], input[type="email"]').first).to_be_visible(timeout=10_000)
    # Logout button (i18n = \u767b\u51fa) is a hard, stable signal of the edit-details form.
    expect(page.get_by_role("button", name="\u767b\u51fa")).to_be_visible(timeout=10_000)


def test_public_results_visible_to_anonymous_and_archived(
    page: Page, anon_page: Page, shared_club_id: int
) -> None:
    """J2: the results page is the only shared view, and a public tournament stays
    readable without logging in — including after it is archived.

    Also covers the archived read-only rule: the owner still sees the results, but
    the 点击表格...填写比分 hint is gone, because every write is rejected once the
    tournament is archived.
    """
    name = f"E2E-PubT-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, name)  # dashboard_public=True
    team_names = [f"E2E-PubTeam-{i}-{uuid.uuid4().hex[:4]}" for i in range(4)]
    for tn in team_names:
        api_create_team(tid, tn)
    stage_id = api_create_stage(tid, f"E2E-PubS-{uuid.uuid4().hex[:6]}")
    try:
        api_create_round_robin(tid, stage_id, team_count=4, group_count=1)

        # Logged out: the public results page renders the participants.
        anon_page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        for tn in team_names:
            expect(anon_page.locator("body")).to_contain_text(tn, timeout=20_000)

        # The owner sees the scoring hint while the tournament is open...
        page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        expect(page.locator("body")).to_contain_text(HINT_FILL_SCORES, timeout=20_000)

        api_archive_tournament(tid)

        # ...and loses it once archived, while the results themselves stay.
        page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        expect(page.locator("body")).to_contain_text(team_names[0], timeout=20_000)
        expect(page.locator("body")).not_to_contain_text(HINT_FILL_SCORES, timeout=10_000)

        # Archiving no longer un-publishes the tournament: the shared link still works.
        anon_page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
        for tn in team_names:
            expect(anon_page.locator("body")).to_contain_text(tn, timeout=20_000)
    finally:
        api_archive_tournament(tid, status="OPEN")
        api_delete_tournament(tid)


def test_mobile_viewport_results_page(page: Page, shared_tournament_id: int) -> None:
    """J3: the results page renders at mobile viewport with the responsive
    nav (Burger button) visible and the results tabs rendered."""
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(
        f"{BASE_URL}/tournaments/{shared_tournament_id}/results",
        wait_until="domcontentloaded",
    )
    page.wait_for_selector('[role="tab"]', timeout=15_000)
    assert "/results" in page.url, f"expected /results in URL, got {page.url}"
    # The Burger menu trigger (Mantine's hamburger) is rendered with
    # hiddenFrom="sm" \u2014 i.e. visible at 375px width. Assert it is visible.
    burger = page.locator(".mantine-Burger-root, button.mantine-Burger-burger").first
    expect(burger).to_be_visible(timeout=5_000)
    # The results page must render the tabs (results, rankings, bracket).
    expect(page.get_by_role("tab", name="\u7ed3\u679c").first).to_be_visible(timeout=10_000)
    expect(page.get_by_role("tab", name="\u6392\u540d").first).to_be_visible(timeout=10_000)