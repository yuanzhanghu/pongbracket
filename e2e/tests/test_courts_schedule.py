"""Courts & scheduling tests (G1-G4)."""
from __future__ import annotations

import uuid

from playwright.sync_api import Page, expect

from ._helpers import (
    BASE_URL,
    api_create_court,
    api_create_round_robin,
    api_create_stage,
    api_create_team,
    api_create_tournament,
    api_delete_court,
    api_delete_stage,
    api_delete_tournament,
    api_get_courts,
    api_get_stages,
    api_schedule_matches,
)


def _schedule_url(tid: int) -> str:
    return f"{BASE_URL}/tournaments/{tid}/schedule"


def _scheduled_match_count(tournament_id: int, stage_id: int) -> int:
    """Count matches in the given stage that have a non-null start_time
    (i.e. have actually been scheduled)."""
    count = 0
    for s in api_get_stages(tournament_id):
        if s["id"] != stage_id:
            continue
        for item in s.get("stage_items", []):
            for rd in item.get("rounds", []):
                for m in rd.get("matches", []):
                    if m.get("start_time"):
                        count += 1
    return count


def _wait_schedule_loaded(page: Page) -> None:
    """Wait for the \u6dfb\u52a0\u573a\u5730 button to render \u2014 the schedule page
    always shows it (as a standalone button when no courts exist, or inside
    the per-court column when at least one does). This is a more reliable
    signal than the planning title, which is also rendered as a sub-label
    inside the empty-state NoContent element."""
    page.wait_for_selector(
        'button:has-text("\u6dfb\u52a0\u573a\u5730")', state="visible", timeout=15_000
    )


def _delete_court_by_name(tid: int, name: str) -> None:
    for c in api_get_courts(tid):
        if c["name"] == name:
            api_delete_court(tid, c["id"])


def _court_column_with(page: Page, name: str):
    """Return the court column containing the h4 with `name`.

    The schedule page renders each court as a column whose header has an
    <h4> with the court name and a kebab ActionIcon. The whole column
    lives inside a `Droppable` wrapper from hello-pangea/dnd. We locate
    the column by walking from the h4 up to the nearest ancestor div
    that contains a Mantine ActionIcon button (the kebab). This is
    stable across CSS / theme / wrapper refactors because we anchor on
    the ActionIcon (a semantic class), not an inline style.
    """
    h4 = page.locator("h4", has_text=name).first
    expect(h4).to_be_visible(timeout=10_000)
    col = h4.locator(
        "xpath=ancestor::div[.//button[contains(@class, 'mantine-ActionIcon-root')]][1]"
    ).first
    return col


def test_create_court(page: Page, shared_tournament_id: int) -> None:
    """G1: adding a court via the UI makes it appear on the schedule page."""
    page.goto(_schedule_url(shared_tournament_id), wait_until="domcontentloaded")
    _wait_schedule_loaded(page)
    page.get_by_role("button", name="\u6dfb\u52a0\u573a\u5730").first.click()
    page.wait_for_selector(".mantine-Modal-content", state="visible", timeout=10_000)
    court_name = f"E2E-Court-{uuid.uuid4().hex[:6]}"
    try:
        page.get_by_placeholder("\u6700\u597d\u7684\u573a\u5730").first.fill(court_name)
        page.locator(".mantine-Modal-content").last.get_by_role(
            "button", name="\u4fdd\u5b58"
        ).first.click()
        expect(page.locator(".mantine-Modal-content").last).to_be_hidden(timeout=10_000)
        expect(page.locator("body")).to_contain_text(court_name, timeout=10_000)
        # API confirms the court was actually persisted.
        assert any(
            c["name"] == court_name for c in api_get_courts(shared_tournament_id)
        ), f"expected court {court_name!r} in API list"
    finally:
        # Keep the shared tournament tidy across runs.
        _delete_court_by_name(shared_tournament_id, court_name)


def test_delete_court(page: Page, shared_tournament_id: int) -> None:
    """G2 (delete half): deleting a court via the in-page kebab menu removes it from the schedule."""
    court_name = f"E2E-DelCourt-{uuid.uuid4().hex[:6]}"
    api_create_court(shared_tournament_id, court_name)
    page.goto(_schedule_url(shared_tournament_id), wait_until="domcontentloaded")
    _wait_schedule_loaded(page)
    expect(page.locator("body")).to_contain_text(court_name, timeout=15_000)
    # Use the stable h4-anchored column locator (see _court_column_with).
    col = _court_column_with(page, court_name)
    # The kebab menu trigger is the only Mantine ActionIcon in the column
    # header. ActionIcons in the column body (e.g. add match) are
    # different, but in the current build the header is the only one with
    # the IconDots icon. Click the first one in the column.
    col.locator('button.mantine-ActionIcon-root').first.click()
    page.get_by_role("menuitem", name="\u5220\u9664\u573a\u5730").first.click()
    # The court column disappears (text gone from the page).
    expect(page.locator("body")).not_to_contain_text(court_name, timeout=10_000)
    # API agrees.
    assert not any(
        c["name"] == court_name for c in api_get_courts(shared_tournament_id)
    ), f"court {court_name!r} should be deleted from API"


def test_court_kebab_menu_has_no_edit_option(
    page: Page, shared_tournament_id: int
) -> None:
    """G2 (edit half): the court kebab menu currently exposes no edit affordance.

    The current build (frontend/src/pages/tournaments/[id]/schedule.tsx)
    only renders a single \u5220\u9664\u573a\u5730 menu item in the court column's kebab
    menu \u2014 there is no \u7f16\u8f91\u573a\u5730 / \u91cd\u547d\u540d menu item. This test locks
    in that behaviour so any future regression that adds or removes a
    menu item will surface here. G2 is therefore partially covered:
    delete is end-to-end; edit is asserted to be not present in the UI.
    """
    court_name = f"E2E-EditProbe-{uuid.uuid4().hex[:6]}"
    api_create_court(shared_tournament_id, court_name)
    try:
        page.goto(_schedule_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_schedule_loaded(page)
        expect(page.locator("body")).to_contain_text(court_name, timeout=15_000)
        col = _court_column_with(page, court_name)
        col.locator('button.mantine-ActionIcon-root').first.click()
        # The menu contains at least the delete item.
        expect(
            page.get_by_role("menuitem", name="\u5220\u9664\u573a\u5730").first
        ).to_be_visible(timeout=5_000)
        # The menu does NOT contain an "edit court" item in the current build.
        # Use a regex-ish name match: common Chinese names for "edit court".
        assert (
            page.get_by_role("menuitem", name="\u7f16\u8f91\u573a\u5730").count() == 0
        ), "expected no '\u7f16\u8f91\u573a\u5730' menu item in the court kebab menu"
        assert (
            page.get_by_role("menuitem", name="\u91cd\u547d\u540d\u573a\u5730").count() == 0
        ), "expected no '\u91cd\u547d\u540d\u573a\u5730' menu item in the court kebab menu"
        # Close the menu so the test exits cleanly.
        page.keyboard.press("Escape")
    finally:
        _delete_court_by_name(shared_tournament_id, court_name)


def test_auto_schedule_matches(page: Page, shared_tournament_id: int) -> None:
    """G3: \u5b89\u6392\u6240\u6709\u672a\u5b89\u6392\u7684\u6bd4\u8d5b auto-schedules unscheduled matches."""
    court_names = [
        f"E2E-Ct-{uuid.uuid4().hex[:4]}",
        f"E2E-Ct-{uuid.uuid4().hex[:4]}",
    ]
    for cn in court_names:
        api_create_court(shared_tournament_id, cn)
    stage_id = api_create_stage(shared_tournament_id, f"E2E-Sched-{uuid.uuid4().hex[:6]}")
    try:
        api_create_round_robin(shared_tournament_id, stage_id, team_count=4, group_count=1)
        # Ground truth BEFORE the click: the RR matches exist but are
        # unscheduled (no start_time).
        assert _scheduled_match_count(shared_tournament_id, stage_id) == 0, (
            "expected the new round-robin matches to be unscheduled before the click"
        )
        page.goto(_schedule_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_schedule_loaded(page)
        page.get_by_role("button", name="\u5b89\u6392\u6240\u6709\u672a\u5b89\u6392\u7684\u6bd4\u8d5b").first.click()
        # The team names are visible on the page BEFORE the click too (in the
        # unscheduled list), so a text check alone cannot prove scheduling
        # happened. Assert the GROUND TRUTH: at least one match now has a
        # start_time (poll briefly for the UI action to round-trip).
        scheduled = 0
        for _ in range(20):
            scheduled = _scheduled_match_count(shared_tournament_id, stage_id)
            if scheduled > 0:
                break
            page.wait_for_timeout(500)
        assert scheduled > 0, (
            "expected at least one match to have a start_time after clicking "
            "\u5b89\u6392\u6240\u6709\u672a\u5b89\u6392\u7684\u6bd4\u8d5b"
        )
    finally:
        api_delete_stage(shared_tournament_id, stage_id)
        for cn in court_names:
            _delete_court_by_name(shared_tournament_id, cn)


def test_schedule_view_renders(page: Page, shared_tournament_id: int) -> None:
    """G4: the schedule/planning view renders court columns."""
    court_name = f"E2E-View-{uuid.uuid4().hex[:6]}"
    api_create_court(shared_tournament_id, court_name)
    try:
        page.goto(_schedule_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_schedule_loaded(page)
        # The court appears as an <h4> in its own column.
        expect(page.locator("h4", has_text=court_name)).to_be_visible(timeout=10_000)
    finally:
        _delete_court_by_name(shared_tournament_id, court_name)


def test_schedule_page_does_not_open_score_modal(page: Page, shared_club_id: int) -> None:
    """G5: the 规划 (schedule) page no longer opens the score modal.

    The rebrand REMOVED the match-scoring affordance from the schedule page —
    score entry now lives exclusively on the 填分和结果 (results) page's
    GroupGrid cells. The schedule page's match cards are plain Draggable Cards
    with no onClick handler. Clicking a scheduled match card on /schedule must
    NOT open the 编辑比分 / 填入分数 modal. A regression that re-wired the
    schedule card's onClick to open the score modal would fail here.
    """
    tname = f"E2E-SchedNoModal-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        for i in range(4):
            api_create_team(tid, f"E2E-SNMTeam-{i}-{uuid.uuid4().hex[:4]}")
        stage_id = api_create_stage(tid, f"E2E-SNMSt-{uuid.uuid4().hex[:6]}")
        api_create_round_robin(tid, stage_id, team_count=4, group_count=1)
        api_create_court(tid, f"E2E-SNMCt-{uuid.uuid4().hex[:4]}")
        api_schedule_matches(tid)

        page.goto(_schedule_url(tid), wait_until="domcontentloaded")
        _wait_schedule_loaded(page)
        # Wait for at least one match card to render (scheduled matches appear
        # inside court columns as Draggable Cards).
        cards = page.locator(".mantine-Card-root")
        expect(cards.first).to_be_visible(timeout=15_000)
        assert cards.count() >= 1, "expected at least one scheduled match card"

        # Click the first match card.
        cards.first.click()
        page.wait_for_timeout(1500)
        # The score modal must NOT open.
        expect(page.locator(".mantine-Modal-content")).to_have_count(0, timeout=3_000)
        # The 填入分数 / 编辑比分 modal title must not be in the body.
        assert page.locator("body").inner_text().count("填入分数") == 0, (
            "the schedule page must not open the score modal"
        )
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass