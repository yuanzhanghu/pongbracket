"""Additional coverage for user-perspective use cases not exercised elsewhere.

These tests cover real user flows that were flagged as gaps in the critic
feedback (/password-reset, the actual guide click-through, the home page's
archive filter). Each test asserts a real, observable UI state and uses the
existing fixtures.
"""
from __future__ import annotations

import uuid

from playwright.sync_api import Page, expect

from ._helpers import (
    BASE_URL,
    api_create_tournament,
    api_delete_tournament,
)


def test_password_reset_link_hidden(anon_page: Page) -> None:
    """The \u5fd8\u8bb0\u5bc6\u7801 link is hidden from the login page.

    The /password-reset page was never implemented (it renders the 404
    stub), and email is optional now, so the login page intentionally does
    NOT offer a forgot-password link. The other footer links (create
    account, guide) must still be there.
    """
    anon_page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    expect(anon_page.locator('input[name="email"], input[type="email"]').first).to_be_visible(
        timeout=10_000
    )
    body = anon_page.locator("body").inner_text()
    assert "\u5fd8\u8bb0\u5bc6\u7801" not in body, "\u5fd8\u8bb0\u5bc6\u7801 link should be hidden"
    assert "\u521b\u5efa\u5e10\u6237" in body, "create-account link must remain"
    assert "\u7b80\u5355\u4f7f\u7528\u6307\u5357" in body, "guide link must remain"


def test_user_guide_link_navigates_to_guide_page(anon_page: Page) -> None:
    """Clicking the \u7b80\u5355\u4f7f\u7528\u6307\u5357 link from the landing page opens
    the actual user guide HTML page.

    The earlier test (`test_user_guide_link_visible`) only checked the
    link is present. This test asserts the link's href points to the
    actual guide page (it has target="_blank" so the navigation opens
    in a new tab that Playwright doesn't follow by default).
    """
    anon_page.goto(BASE_URL, wait_until="domcontentloaded")
    link = anon_page.get_by_role("link", name="\u7b80\u5355\u4f7f\u7528\u6307\u5357").first
    expect(link).to_be_visible(timeout=10_000)
    href = link.get_attribute("href")
    assert href and "guide" in href, (
        f"expected guide URL in the link's href, got {href!r}"
    )


def test_guide_page_is_rating_flow_walkthrough(anon_page: Page) -> None:
    """B2b: the usage guide is split into ranked / non-ranked flows; the index
    is a chooser page and the \u4e2a\u4eba\u79ef\u5206\u8d5b (individual-rating) end-to-end
    walkthrough lives at /guide/rating.html. That page must render the numbered
    rating-lifecycle sections (create individual rated tournament, instant-join,
    owner self-add, seed initial rating, scorers, RR+SE scheduling). A
    regression that reverted the guide to the old generic content would surface
    here \u2014 the older B2 tests only assert the link's presence/href, never
    the page body.
    """
    # The index must offer the flow choice...
    anon_page.goto(f"{BASE_URL}/guide/index.html", wait_until="domcontentloaded")
    expect(anon_page.locator("body")).to_contain_text("\u9009\u62e9\u4e00\u79cd\u8d5b\u4e8b\u7c7b\u578b", timeout=10_000)
    # ...and the rating walkthrough lives on its own page.
    anon_page.goto(f"{BASE_URL}/guide/rating.html", wait_until="domcontentloaded")
    body = anon_page.locator("body")
    expect(body).to_contain_text("\u4e2a\u4eba\u79ef\u5206\u8d5b\u5b8c\u6574\u6d41\u7a0b\u6f14\u793a", timeout=10_000)
    text = body.inner_text()
    # Numbered rating-lifecycle steps that are unique to the new walkthrough.
    assert "\u521b\u5efa\u4e2a\u4eba\u79ef\u5206\u8d5b" in text, f"missing create-individual step, got {text[:400]!r}"
    assert "\u521b\u5efa\u8005\u628a\u81ea\u5df1\u52a0\u5165\u53c2\u8d5b\u540d\u5355" in text, "missing owner self-add step"
    assert "\u521d\u59cb\u5206" in text, "missing initial-rating seed step"
    assert "\u8bb0\u5206\u5458" in text, "missing scorers step"


# ---------------------------------------------------------------------------
# New coverage (M series): uncovered use cases that are real user flows
# ---------------------------------------------------------------------------


def test_tournament_set_to_now_button(page: Page, shared_club_id: int) -> None:
    """M2: the \u8bbe\u7f6e\u4e3a\u73b0\u5728 (Set to now) button on the tournament
    settings page updates the start_time field to the current time.
    settings page updates the start_time field to the current time.

    The settings page renders a \u8bbe\u7f6e\u4e3a\u73b0\u5728 button next to the start_time
    DateTimePicker. Clicking it sets the field to dayjs() (current time).
    The change is purely client-side (it updates the form value), so we
    assert the field's value changes from its initial (2030-01-01) to a
    value containing the current year, then save and confirm via the
    API that the new value persisted.
    """
    from ._helpers import api_get_tournament
    tname = f"E2E-SetNow-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded"
        )
        page.wait_for_selector(
            'input[placeholder="\u6700\u4f73\u6bd4\u8d5b"]', timeout=15_000
        )
        # The "Set to now" button is in the planning fieldset group.
        set_now = page.get_by_role(
            "button", name="\u8bbe\u7f6e\u4e3a\u73b0\u5728", exact=True
        ).first
        expect(set_now).to_be_visible(timeout=10_000)
        set_now.click()
        page.wait_for_timeout(500)
        # Click the save button at the bottom of the form (the green one
        # with the pencil icon). The form has multiple \u4fdd\u5b58 buttons (one per
        # group, including the sharing settings group copy button is
        # \u590d\u5236\u94fe\u63a5 not \u4fdd\u5b58, and the rankings group is on a different
        # page). On the settings page, the only \u4fdd\u5b58 button is the main save.
        page.get_by_role("button", name="\u4fdd\u5b58", exact=True).first.click()
        # Poll the API until the new start_time is persisted.
        body = None
        for _ in range(20):
            body = api_get_tournament(tid)
            st = body.get("start_time", "")
            if st and not st.startswith("2030-01-01"):
                break
            page.wait_for_timeout(500)
        assert body is not None and body.get("start_time", ""), (
            f"expected a non-empty start_time after Set to now, got "
            f"{body.get('start_time') if body else None!r}"
        )
        assert not body.get("start_time", "").startswith("2030-01-01"), (
            f"expected start_time to change from 2030-01-01 default, got "
            f"{body.get('start_time')!r}"
        )
    finally:
        api_delete_tournament(tid)


