"""Additional user-perspective use cases for settings, user profile, and 404.

These tests cover real user flows that the existing suite doesn't exercise:

  - 404 page renders with the expected 404 / not_found / back-home copy.
  - User profile: the language tab is present and has an interactive
    <Select> bound to the current locale.
  - User profile: updating the name in the details tab persists across reload.
  - Tournament settings: the "Archive Tournament" button actually archives
    (status flips OPEN -> ARCHIVED, archive button disappears, unarchive
    appears) without going through the API.
  - Tournament settings: the sharing fieldset shows this tournament's results
    URL and an enabled copy button.

All tests namespace any created data with a unique E2E- prefix and clean
up via the API. Tests that mutate shared resources (user name) capture the
current value and restore it.
"""
from __future__ import annotations

import uuid

import requests
from playwright.sync_api import Page, expect

from ._helpers import (
    BASE_URL,
    _api_headers,
    api_create_tournament,
    api_delete_tournament,
    api_get_tournament,
)


# Chinese locale strings used by these tests. The app is Chinese by
# default; using the literal Chinese strings as selectors is the most
# stable approach because the build does not have data-testid attributes.
_T = {
    "edit_profile_title": "\u7f16\u8f91\u4e2a\u4eba\u8d44\u6599",  # edit profile
    "edit_language_tab": "\u66f4\u6539\u8bed\u8a00",  # change language
    "name_input_label": "\u540d\u79f0",  # name
    "save_button": "\u4fdd\u5b58",  # save
    "back_home_nav": "\u56de\u5230\u4e3b\u9875",  # back to home page
    "not_found_title": "\u4f60\u627e\u5230\u4e86\u4e00\u4e2a\u79d8\u5bc6\u5730\u65b9",  # you have found a secret place
    "archive_tournament": "\u5f52\u6863\u6bd4\u8d5b",  # archive tournament
    "unarchive_tournament": "\u53d6\u6d88\u5f52\u6863\u6bd4\u8d5b",  # unarchive tournament (contains archive_tournament!)
    "copy_url": "\u590d\u5236\u94fe\u63a5",  # copy URL
    "share_settings_group": "\u5206\u4eab\u8bbe\u7f6e",  # sharing settings (fieldset legend)
    "settings_placeholder": "\u6700\u4f73\u6bd4\u8d5b",  # best tournament
}


# ---------------------------------------------------------------------------
# 404 page
# ---------------------------------------------------------------------------


def test_404_page_renders_for_anon(anon_page: Page) -> None:
    """L1: a non-existent route renders the 404 page (anon visitor)."""
    anon_page.goto(
        f"{BASE_URL}/this-route-does-not-exist-{uuid.uuid4().hex[:6]}",
        wait_until="domcontentloaded",
    )
    expect(anon_page.locator("body")).to_contain_text("404", timeout=10_000)
    expect(anon_page.locator("body")).to_contain_text(
        _T["not_found_title"], timeout=10_000
    )
    back_home = anon_page.get_by_role("button", name=_T["back_home_nav"]).first
    expect(back_home).to_be_visible(timeout=5_000)


def test_404_page_renders_for_logged_in(page: Page) -> None:
    """L2: the 404 page renders the same way for a logged-in user."""
    page.goto(
        f"{BASE_URL}/another-missing-route-{uuid.uuid4().hex[:6]}",
        wait_until="domcontentloaded",
    )
    expect(page.locator("body")).to_contain_text("404", timeout=10_000)
    expect(
        page.get_by_role("button", name=_T["back_home_nav"]).first
    ).to_be_visible(timeout=5_000)


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------


def _user_form_visible(page: Page) -> None:
    page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded")
    expect(page.locator("body")).to_contain_text(
        _T["edit_profile_title"], timeout=10_000
    )


def test_user_language_tab_is_interactive(page: Page) -> None:
    """L3: the language tab on /user lists at least 2 locales (Chinese +
    English) in its dropdown.

    B4b drives the full locale-swap flow end-to-end (open language tab,
    pick "English", assert URL + nav swap). To earn a separate spot,
    L3 asserts a complementary structural fact B4b doesn't: opening the
    Mantine Select reveals MULTIPLE language options, and "English" is
    among them. A regression that ships an empty / single-option Select
    would still pass B4b's happy path (it would just hit a stale cached
    \"English\" option) but fails here because we count options.
    """
    _user_form_visible(page)
    lang_tab = page.get_by_role("tab", name=_T["edit_language_tab"]).first
    expect(lang_tab).to_be_visible(timeout=5_000)
    lang_tab.click()
    page.wait_for_timeout(500)
    panel = page.get_by_role("tabpanel").last
    textbox = panel.get_by_role("textbox").first
    expect(textbox).to_be_visible(timeout=5_000)
    current_value = textbox.input_value()
    assert current_value and "Chinese" in current_value, (
        f"expected the Select to show the current Chinese locale, got "
        f"{current_value!r}"
    )
    # Open the dropdown and assert >= 2 options including English.
    textbox.click()
    page.wait_for_timeout(500)
    options = page.get_by_role("option")
    option_count = options.count()
    assert option_count >= 2, (
        f"expected the language Select to list >= 2 locales, got "
        f"{option_count}"
    )
    option_texts = [options.nth(i).inner_text() for i in range(option_count)]
    assert any("English" in t for t in option_texts), (
        f"expected 'English' in the language options, got {option_texts!r}"
    )
    assert any("Chinese" in t for t in option_texts), (
        f"expected 'Chinese' in the language options, got {option_texts!r}"
    )


def test_user_name_update_persists(page: Page) -> None:
    """L4: editing the user's name in the details tab persists across reload.

    J1 only checks the form renders. This test exercises the actual
    name-update path: details tab -> rename -> save -> reload -> assert
    the new name is still there. Restores the original name in `finally`
    so we don't pollute the E2E account for sibling tests.
    """
    _user_form_visible(page)
    name_input = page.get_by_role(
        "textbox", name=_T["name_input_label"], exact=True
    ).first
    expect(name_input).to_be_visible(timeout=5_000)
    original_name = name_input.input_value()
    assert original_name, "expected the name input to be pre-populated"

    new_name = f"E2E-Name-{uuid.uuid4().hex[:6]}"
    try:
        name_input.fill(new_name)
        # The save button is the green \u4fdd\u5b58 inside the details form.
        # The details form is the first <form> on the page; the password
        # form is inside a hidden tabpanel.
        page.locator("form").first.get_by_role(
            "button", name=_T["save_button"]
        ).first.click()
        # Poll the API until the new name is persisted.
        import time
        from ._helpers import _api_headers as _h
        for _ in range(20):
            r = requests.get(f"{BASE_URL}/api/users/me", headers=_h(), timeout=10)
            if r.status_code == 200 and r.json().get("data", {}).get("name") == new_name:
                break
            time.sleep(0.5)
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("body")).to_contain_text(
            _T["edit_profile_title"], timeout=10_000
        )
        name_input2 = page.get_by_role(
            "textbox", name=_T["name_input_label"], exact=True
        ).first
        assert name_input2.input_value() == new_name, (
            f"expected name {new_name!r} after reload, got "
            f"{name_input2.input_value()!r}"
        )
    finally:
        # Always restore the original name.
        page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded")
        expect(page.locator("body")).to_contain_text(
            _T["edit_profile_title"], timeout=10_000
        )
        name_input3 = page.get_by_role(
            "textbox", name=_T["name_input_label"], exact=True
        ).first
        name_input3.fill(original_name)
        page.locator("form").first.get_by_role(
            "button", name=_T["save_button"]
        ).first.click()
        page.wait_for_timeout(1500)


# ---------------------------------------------------------------------------
# Tournament settings
# ---------------------------------------------------------------------------


def _settings_url(tid: int) -> str:
    return f"{BASE_URL}/tournaments/{tid}/settings"


def _wait_settings_loaded(page: Page) -> None:
    """Wait for the tournament settings form (name input with the
    \u6700\u4f73\u6bd4\u8d5b placeholder) to render."""
    page.wait_for_selector(
        f'input[placeholder="{_T["settings_placeholder"]}"]', timeout=15_000
    )


def _share_link_input(page: Page):
    """Return the read-only share-link TextInput.

    The Chinese locale uses the same placeholder for the tournament name as
    elsewhere and the Mantine TextInput's accessible name falls back to it, so
    the field is addressed as the only <input> inside the "\u5206\u4eab\u8bbe\u7f6e"
    (sharing settings) fieldset group.
    """
    group = page.get_by_role("group", name=_T["share_settings_group"]).first
    return group.locator("input").first


def test_tournament_archive_button_archives(page: Page, shared_club_id: int) -> None:
    """L5: the "Archive Tournament" button on settings actually archives.

    We use a dedicated tournament (created in the test) so the test is
    independent of the shared tournament's lifecycle. The button is
    rendered conditionally: when status is OPEN, the archive button is
    shown; after clicking, the status flips to ARCHIVED and the button
    is replaced by the unarchive button. The API confirms the change.

    IMPORTANT: unarchive (\u53d6\u6d88\u5f52\u6863\u6bd4\u8d5b) CONTAINS archive
    (\u5f52\u6863\u6bd4\u8d5b) as a substring, so role-based name matching
    would match both. We use exact=True to disambiguate.
    """
    tname = f"E2E-ArchUI-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        page.goto(_settings_url(tid), wait_until="domcontentloaded")
        _wait_settings_loaded(page)
        archive_btn = page.get_by_role(
            "button", name=_T["archive_tournament"], exact=True
        ).first
        expect(archive_btn).to_be_visible(timeout=10_000)
        archive_btn.click()
        unarchive_btn = page.get_by_role(
            "button", name=_T["unarchive_tournament"], exact=True
        ).first
        expect(unarchive_btn).to_be_visible(timeout=15_000)
        assert (
            page.get_by_role("button", name=_T["archive_tournament"], exact=True).count() == 0
        ), "archive button should disappear after clicking it"
        body = api_get_tournament(tid)
        assert body.get("status") == "ARCHIVED", (
            f"expected status=ARCHIVED after UI click, got {body.get('status')!r}"
        )
    finally:
        # Restore OPEN before deleting.
        try:
            requests.post(
                f"{BASE_URL}/api/tournaments/{tid}/change-status",
                headers=_api_headers(),
                json={"status": "OPEN"},
                timeout=10,
            )
        except Exception:
            pass
        api_delete_tournament(tid)


def test_tournament_share_link_is_the_results_url(page: Page, shared_club_id: int) -> None:
    """L6: the sharing fieldset offers the results URL of this tournament and an
    enabled copy button.

    Sharing used to hang off a custom dashboard slug; the dashboard is gone, so
    the only shared view is /tournaments/<id>/results and the link needs no
    configuration.
    """
    tname = f"E2E-ShareUI-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        page.goto(_settings_url(tid), wait_until="domcontentloaded")
        _wait_settings_loaded(page)
        link_input = _share_link_input(page)
        expect(link_input).to_be_visible(timeout=10_000)
        assert link_input.input_value().endswith(f"/tournaments/{tid}/results"), (
            f"expected the results URL in the share field, got "
            f"{link_input.input_value()!r}"
        )
        copy_btn = page.get_by_role("button", name=_T["copy_url"], exact=True).first
        expect(copy_btn).to_be_visible(timeout=5_000)
        assert not copy_btn.is_disabled(), "the copy-link button should always be enabled"
    finally:
        api_delete_tournament(tid)


def test_tournament_unarchive_button_unarchives(page: Page, shared_club_id: int) -> None:
    """L5b: the "Unarchive Tournament" button on settings actually unarchives.

    Complements L5 (which exercises archive). We seed an ARCHIVED
    tournament via the API, navigate to settings, click the unarchive
    button and assert:
      - the unarchive button is replaced by the archive button (the
        archive/unarchive controls are mutually exclusive);
      - the API confirms the status flipped back to OPEN.

    Uses `exact=True` because \u53d6\u6d88\u5f52\u6863\u6bd4\u8d5b CONTAINS \u5f52\u6863\u6bd4\u8d5b
    as a substring; without exact matching the role-name lookup hits both.
    """
    tname = f"E2E-Unarch-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        # Seed ARCHIVED via the API (tested via L5; here we just need the state).
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/change-status",
            headers=_api_headers(),
            json={"status": "ARCHIVED"},
            timeout=10,
        )
        r.raise_for_status()
        assert api_get_tournament(tid).get("status") == "ARCHIVED"

        page.goto(_settings_url(tid), wait_until="domcontentloaded")
        _wait_settings_loaded(page)
        unarchive_btn = page.get_by_role(
            "button", name=_T["unarchive_tournament"], exact=True
        ).first
        expect(unarchive_btn).to_be_visible(timeout=10_000)
        unarchive_btn.click()
        archive_btn = page.get_by_role(
            "button", name=_T["archive_tournament"], exact=True
        ).first
        expect(archive_btn).to_be_visible(timeout=15_000)
        assert (
            page.get_by_role("button", name=_T["unarchive_tournament"], exact=True).count() == 0
        ), "unarchive button should disappear after clicking it"

        # Poll the API until the status flip is persisted (the click
        # fires an async PUT; SWR mutate updates the UI before the
        # request necessarily lands on the next GET).
        status = None
        for _ in range(20):
            status = api_get_tournament(tid).get("status")
            if status == "OPEN":
                break
            page.wait_for_timeout(250)
        assert status == "OPEN", (
            f"expected status=OPEN after UI unarchive click, got {status!r}"
        )
    finally:
        api_delete_tournament(tid)


def test_user_password_change_persists(page: Page) -> None:
    """L7: changing the password on the /user password tab persists \u2014 a
    fresh login round-trip with the new password succeeds, and the old
    password no longer works.

    The user.tsx form exposes a `password` tab (separate from `details`)
    with a PasswordInput + green \u4fdd\u5b58 button. Submitting calls
    `updatePassword(user.id, password)` which PUTs /users/{id}/password.

    We exercise the real flow:
      1. Open /user, switch to the \u7f16\u8f91\u5bc6\u7801 (edit_password_tab_title) tab.
      2. Fill the password input with a known new password and click \u4fdd\u5b58.
      3. Wait for the success notification (\u5bc6\u7801\u5df2\u66f4\u65b0).
      4. Independently confirm the change took on the server: a POST to
         /api/token with the NEW password returns 200, and a POST with
         the OLD password returns 401.
      5. Restore the original password in `finally` (via the API token
         minted with the new password) so the shared E2E account stays
         usable for sibling tests.

    Restoring through the API (not the UI) is intentional: a UI-only
    restore that fails mid-way would leave the E2E account locked into
    the test password and break every other test in the session that
    relies on the seeded credentials.
    """
    import requests as _requests

    from ._helpers import E2E_EMAIL, E2E_PASSWORD

    new_password = f"E2E-NewPwd-{uuid.uuid4().hex[:8]}!"
    original_password = E2E_PASSWORD

    def _post_token(pwd: str):
        return _requests.post(
            f"{BASE_URL}/api/token",
            data={"grant_type": "password", "username": E2E_EMAIL, "password": pwd},
            timeout=10,
        )

    # Sanity: the original password works before we start.
    assert _post_token(original_password).status_code == 200, (
        "precondition failed: original password should authenticate"
    )

    page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded")
    expect(page.locator("body")).to_contain_text(
        _T["edit_profile_title"], timeout=10_000
    )
    pw_tab = page.get_by_role("tab", name="\u7f16\u8f91\u5bc6\u7801").first
    expect(pw_tab).to_be_visible(timeout=5_000)
    pw_tab.click()
    expect(pw_tab).to_have_attribute("aria-selected", "true", timeout=5_000)

    # The password tab's panel has exactly one PasswordInput (Mantine
    # renders it as input[type=password]) plus the green \u4fdd\u5b58 button.
    panel = page.get_by_role("tabpanel").last
    pw_input = panel.locator('input[type="password"]').first
    expect(pw_input).to_be_visible(timeout=5_000)
    pw_input.fill(new_password)
    save_btn = panel.get_by_role("button", name=_T["save_button"]).first
    expect(save_btn).to_be_visible(timeout=5_000)
    save_btn.click()

    # The form fires a green notification with title "\u5bc6\u7801\u5df2\u66f4\u65b0"
    # (password_saved_title) on success. Wait for it to render \u2014 a
    # save-no-op or a 4xx response would never produce this text.
    expect(page.locator("body")).to_contain_text(
        "\u5bc6\u7801\u5df2\u66f4\u65b0", timeout=10_000
    )

    api_restored = False
    try:
        # Server-side ground truth: the new password authenticates and
        # the old one no longer does. Poll briefly because the PUT and
        # the next /api/token call race against each other.
        new_ok = False
        old_rejected = False
        for _ in range(20):
            r_new = _post_token(new_password)
            r_old = _post_token(original_password)
            new_ok = r_new.status_code == 200
            old_rejected = r_old.status_code == 401
            if new_ok and old_rejected:
                break
            page.wait_for_timeout(250)
        assert new_ok, (
            f"new password did not authenticate after UI save; "
            f"last /api/token status was {r_new.status_code}"
        )
        assert old_rejected, (
            f"old password STILL authenticated after UI save (the change "
            f"didn't take); last /api/token status was {r_old.status_code}"
        )
    finally:
        # Restore the original password via the API using a token minted
        # with the NEW password. This must run even if assertions above
        # failed, otherwise the shared E2E account stays locked into the
        # test password and breaks every sibling test.
        try:
            tr = _post_token(new_password)
            if tr.status_code == 200:
                tok = tr.json()["access_token"]
                me = _requests.get(
                    f"{BASE_URL}/api/users/me",
                    headers={"Authorization": f"bearer {tok}"},
                    timeout=10,
                )
                me.raise_for_status()
                user_id = me.json()["data"]["id"]
                rr = _requests.put(
                    f"{BASE_URL}/api/users/{user_id}/password",
                    headers={"Authorization": f"bearer {tok}"},
                    json={"password": original_password},
                    timeout=10,
                )
                api_restored = rr.status_code == 200
        except Exception:
            pass
        # Final safety: if we somehow could not restore via the new
        # password (e.g. UI change actually failed mid-way), the original
        # password is still good and no restore is needed. Otherwise
        # raise loudly so the test fails on cleanup rather than leaving
        # the account in a broken state.
        if not api_restored:
            still_old_ok = _post_token(original_password).status_code == 200
            assert still_old_ok, (
                "BAD STATE: could not restore E2E account password. "
                "The account is now locked into the test-only new password. "
                "Manual fix required."
            )