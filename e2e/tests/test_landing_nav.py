"""Landing & navigation tests (B1-B4).

Asserts:
  B1: anon landing shows marketing content + \u767b\u5f55 / \u521b\u5efa\u5e10\u6237.
  B2: the \u7b80\u5355\u4f7f\u7528\u6307\u5357 (user guide) link is visible on the landing page.
  B3: top nav (\u4ff1\u4e50\u90e8 / \u6bd4\u8d5b / \u7528\u6237 / \u66f4\u591a) is reachable when logged in.
  B4a: ?lng=en switches UI strings from Chinese to English (anon, URL-driven).
  B4b: the /user language tab's Mantine Select swaps the logged-in nav
       to English (full UI flow through the profile page).
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from ._helpers import BASE_URL


def test_anon_landing_page(anon_page: Page) -> None:
    """B1: the anonymous landing page renders the marketing + entry points."""
    anon_page.goto(BASE_URL, wait_until="domcontentloaded")
    # i18n loads async; wait for the expected text rather than a fixed sleep.
    expect(anon_page.locator("body")).to_contain_text("\u767b\u5f55", timeout=10_000)
    body = anon_page.locator("body").inner_text()
    assert "\u521b\u5efa\u5e10\u6237" in body, f"expected '\u521b\u5efa\u5e10\u6237' in body, got: {body[:300]}"
    # At least one feature section title is visible
    assert "\u7075\u6d3b\u8d5b\u5236" in body, f"expected '\u7075\u6d3b\u8d5b\u5236' in body, got: {body[:300]}"


def test_user_guide_link_visible(anon_page: Page) -> None:
    """B2: the \u7b80\u5355\u4f7f\u7528\u6307\u5357 entry point is present on the landing page."""
    anon_page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(anon_page.locator("body")).to_contain_text("\u7b80\u5355\u4f7f\u7528\u6307\u5357", timeout=10_000)


def test_top_nav_present_when_logged_in(page: Page) -> None:
    """B3: the primary nav (\u6bd4\u8d5b / \u7528\u6237) is reachable when logged in.
    Clubs are implicit now, so there is no \u4ff1\u4e50\u90e8 nav entry. The rebrand
    (commit e378e48) REMOVED the \u66f4\u591a dropdown (website/github/api-docs),
    so it must NOT render \u2014 assert its absence to lock that regression."""
    expect(page.locator("body")).to_contain_text("\u6bd4\u8d5b", timeout=10_000)
    body = page.locator("body").inner_text()
    assert "\u6bd4\u8d5b" in body
    assert "\u7528\u6237" in body
    assert "\u66f4\u591a" not in body, f"\u66f4\u591a nav dropdown should be gone after rebrand, body={body!r}"


def test_language_switch_to_english(anon_page: Page) -> None:
    """B4a: ?lng=en replaces the Chinese UI strings with the English ones."""
    anon_page.goto(f"{BASE_URL}/?lng=en", wait_until="domcontentloaded")
    # i18n fetches the English locale asynchronously; wait for the swap.
    expect(anon_page.locator("body")).to_contain_text("Sign in", timeout=15_000)
    body = anon_page.locator("body").inner_text()
    assert "Create account" in body or "Create Account" in body, (
        f"expected 'Create account' in body, got: {body[:500]}"
    )


def test_language_tab_swaps_logged_in_nav_to_english(page: Page) -> None:
    """B4b: the /user language tab's Mantine Select swaps the logged-in
    nav to English end-to-end through the UI.

    Earlier coverage of B4 only tested `?lng=en` on the anonymous landing
    page; the logged-in profile-language-tab path was structurally
    checked (textbox current value) but the actual locale-swap was not
    driven. This version exercises the full flow:

      1. Open /user, click the "change language" tab.
      2. Click the Mantine Select, type "English" to filter.
      3. Click the "English" option.
      4. The changeLanguage handler calls i18n.changeLanguage AND
         navigates to /user?lng=en. Assert the URL contains lng=en.
      5. Assert at least one primary nav label re-renders in English
         (e.g. the user-menu \u7528\u6237 swaps to "User", or the
         \u4ff1\u4e50\u90e8 / \u6bd4\u8d5b / \u66f4\u591a nav swaps to
         Clubs / Tournaments / More).

    A regression that breaks the profile-locale update surfaces here.
    """
    page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded")
    # The edit-profile title is the page-level anchor; wait for it to
    # render before clicking the language tab.
    expect(page.locator("body")).to_contain_text(
        "\u7f16\u8f91\u4e2a\u4eba\u8d44\u6599", timeout=10_000
    )
    page.get_by_role("tab", name="\u66f4\u6539\u8bed\u8a00").first.click()
    page.wait_for_timeout(500)
    # The Mantine Select renders as a textbox in the language tabpanel.
    panel = page.get_by_role("tabpanel").last
    lang_select = panel.get_by_role("textbox").first
    expect(lang_select).to_be_visible(timeout=5_000)
    # Open the dropdown by clicking + typing. Mantine Select with
    # default `searchable=false` can be opened by clicking the textbox
    # (it does not search-as-you-type) but the option list still
    # appears as a portal. To be safe, click the textbox, wait for the
    # option list, then click "English".
    lang_select.click()
    page.wait_for_timeout(500)
    # The option list is a Mantine Combobox dropdown; the option text
    # includes the flag emoji + language name. Click by partial match.
    page.get_by_role("option", name="English").first.click()
    # The changeLanguage handler navigates to /user?lng=en. Wait for
    # the URL to reflect the new locale.
    page.wait_for_url("**/user?lng=en", timeout=10_000)
    assert "lng=en" in page.url, f"expected lng=en in URL, got {page.url!r}"
    # Wait for the i18n locale to swap. The primary nav labels are the
    # most stable signal: \u4ff1\u4e50\u90e8 -> Clubs, \u6bd4\u8d5b ->
    # Tournaments, \u66f4\u591a -> More. Assert at least one swaps.
    page.wait_for_timeout(1500)
    body = page.locator("body").inner_text()
    # After the locale swap, at least one of the English nav labels
    # should be present. Accept any of them (the page is the /user
    # profile, so the primary nav is not always visible; the page-level
    # title is "\u7f16\u8f91\u4e2a\u4eba\u8d44\u6599" in Chinese, but
    # after the swap it should be "Edit profile" in English).
    nav_swapped = (
        "Clubs" in body
        or "Tournaments" in body
        or "More" in body
        or "User" in body
        or "Edit profile" in body
    )
    assert nav_swapped, (
        f"expected at least one English nav label after locale swap, "
        f"got body: {body[:500]}"
    )


def test_no_external_brand_links_after_rebrand(page: Page) -> None:
    """B5: the rebrand removed the Website / GitHub / API-docs external links.

    Before the rebrand the app shell (the \\u66f4\\u591a nav dropdown + the
    footer) carried outbound links to the project website, the GitHub repo
    and the API docs. The rebrand (commit e378e48) stripped those: the footer
    is now just the Bracket brand mark and there is no \\u66f4\\u591a dropdown.

    We assert on a real logged-in page (the tournaments home) that:
      - NO anchor points at github.com or an external project website / api
        docs, and
      - the \\u66f4\\u591a dropdown trigger is absent.
    A regression that re-introduced any of those outbound links surfaces here.
    """
    page.goto(f"{BASE_URL}/tournaments", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    # Collect every anchor href on the page.
    hrefs = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    hrefs = [h for h in hrefs if h]
    offending = [
        h
        for h in hrefs
        if "github.com" in h.lower()
        or "/docs" in h.lower()
        or "api-docs" in h.lower()
        or "swagger" in h.lower()
    ]
    assert not offending, (
        f"rebrand removed the GitHub / Website / API-docs links; "
        f"found outbound links that should be gone: {offending!r}"
    )
    # The \\u66f4\\u591a dropdown must not render.
    body = page.locator("body").inner_text()
    assert "\u66f4\u591a" not in body, (
        f"\\u66f4\\u591a nav dropdown should be gone after rebrand, body={body[:300]!r}"
    )