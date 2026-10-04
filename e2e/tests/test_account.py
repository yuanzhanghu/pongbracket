"""Account & session tests (A1-A6).

Asserts:
  A1: /create-account form renders with the right fields.
  A2: log in with valid credentials lands on the authenticated dashboard.
  A3: bad password shows a notification and keeps the user on /login.
  A4: an authenticated session persists across navigation/reload.
  A5: clearing the session returns to the logged-out landing page.
  A6: hitting a protected route while logged out redirects to /login.
"""
from __future__ import annotations

import subprocess
import uuid

import requests
from playwright.sync_api import Page, expect

from ._helpers import (
    API_URL,
    BASE_URL,
    E2E_EMAIL,
    E2E_PASSWORD,
    logout_via_ui,
)


def _delete_user_by_email(email: str) -> None:
    """Best-effort cleanup of a UI-created E2E user.

    There is no admin DELETE-user API in this build, so we delete directly
    from postgres via `docker exec`. The container name is `bracket-dev-postgres-1`
    (set by docker-compose project name `bracket-dev`). Failures are
    ignored: the cleanup is best-effort and the e2e user prefix is unique
    per test invocation, so a leftover record is harmless.
    """
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
                f"DELETE FROM users WHERE email = '{email}';",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        pass


def test_create_account_form_renders(anon_page: Page) -> None:
    """A1a: /create-account exposes the form to anonymous users (smoke).

    Note: this deployment may show a "registration disabled" alert on top of
    the form, but the email + password inputs are still rendered. This test
    is a SMOKE check that the form chrome renders; the substantive A1 test
    that the form actually creates a user lives in
    `test_create_account_via_ui_creates_user`.
    """
    anon_page.goto(f"{BASE_URL}/create-account", wait_until="domcontentloaded")
    anon_page.wait_for_timeout(1000)
    expect(anon_page.locator('input[name="email"], input[type="email"]').first).to_be_visible(timeout=10_000)
    expect(anon_page.locator('input[type="password"]').first).to_be_visible(timeout=10_000)
    # The page title or the form must contain "\u5e10\u6237" somewhere.
    body = anon_page.locator("body").inner_text()
    assert "\u5e10\u6237" in body, f"expected '\u5e10\u6237' in body, got: {body[:500]}"


def test_create_account_via_ui_creates_user(anon_page: Page) -> None:
    """A1: filling the create-account form creates a real, usable account.

    Earlier iterations of A1 only asserted the form fields render, which would
    not catch a regression in the form's onSubmit, the registerUser service,
    the captcha plumbing, or the post-register navigate. This test exercises
    the full UI flow:

      1. Visit /create-account.
      2. Fill email + name + password and click \u521b\u5efa\u5e10\u6237 (create_account_button).
      3. Assert the post-register redirect to / lands on the authenticated
         home (the page renders the create-tournament \u521b\u5efa\u6bd4\u8d5b chrome,
         which only shows for an authenticated session).
      4. Assert localStorage has a `login` token \u2014 the UI's source of truth
         for an authenticated session.
      5. Independently confirm via the API that POST /api/token with the new
         credentials returns 200 \u2014 the user really was created in the DB.
      6. Clean up the user via psql in `finally` so the dev DB stays small.

    The dev backend has `captcha_secret=None`, so `verify_captcha_token`
    short-circuits to True; the frontend's HCaptchaInput renders nothing
    when VITE_HCAPTCHA_SITE_KEY is unset. The form posts an empty
    captcha_token which the backend accepts.
    """
    suffix = uuid.uuid4().hex[:8]
    new_email = f"e2e-newacct-{suffix}@local.test"
    new_name = f"E2E NewAcct {suffix}"
    new_password = f"e2e-newacct-Pw0rd-{suffix}!"
    try:
        anon_page.goto(f"{BASE_URL}/create-account", wait_until="domcontentloaded")
        # Email + name + password inputs. The form has two TextInputs (email,
        # name) and one PasswordInput. Address them by their type/order.
        anon_page.locator('input[name="email"], input[type="email"]').first.fill(new_email)
        # The second text input below the email is the name input. Use the
        # placeholder \u4f60\u7684\u540d\u79f0 (name_input_placeholder) to disambiguate.
        anon_page.locator('input[placeholder="\u4f60\u7684\u540d\u79f0"]').first.fill(new_name)
        anon_page.locator('input[type="password"]').first.fill(new_password)
        # \u521b\u5efa\u5e10\u6237 = create_account_button. Use exact=True so we don't match the
        # \u521b\u5efa\u8d26\u6237 link in the navbar (different glyph but visually similar).
        anon_page.get_by_role(
            "button", name="\u521b\u5efa\u5e10\u6237", exact=True
        ).first.click()
        # Post-register navigate goes to /. Wait for the URL to land there.
        anon_page.wait_for_url(f"{BASE_URL}/", timeout=15_000)
        # Authenticated home renders the create-tournament chrome.
        expect(anon_page.locator("body")).to_contain_text(
            "\u521b\u5efa\u6bd4\u8d5b", timeout=15_000
        )
        # localStorage must hold the login token \u2014 the UI's source of truth.
        token_blob = anon_page.evaluate(
            "() => window.localStorage.getItem('login')"
        )
        assert token_blob, (
            f"expected localStorage 'login' to be set after registration, got {token_blob!r}"
        )
        # Ground-truth check: the new account can authenticate via the API.
        r = requests.post(
            f"{API_URL}/api/token",
            data={
                "grant_type": "password",
                "username": new_email,
                "password": new_password,
            },
            timeout=15,
        )
        assert r.status_code == 200, (
            f"expected /api/token 200 for newly registered user, got "
            f"{r.status_code}: {r.text[:200]}"
        )
        assert "access_token" in r.json(), (
            f"expected access_token in /api/token response, got {r.json()!r}"
        )
    finally:
        _delete_user_by_email(new_email)


def test_login_with_valid_credentials(anon_page: Page) -> None:
    """A2: logging in with the seeded E2E account lands on the home page."""
    anon_page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    anon_page.locator('input[name="email"], input[type="email"]').first.fill(E2E_EMAIL)
    anon_page.locator('input[type="password"]').first.fill(E2E_PASSWORD)
    anon_page.get_by_role("button", name="\u767b\u5f55").first.click()
    anon_page.wait_for_url(f"{BASE_URL}/", timeout=10_000)
    expect(anon_page.locator("body")).to_contain_text("\u6bd4\u8d5b", timeout=10_000)
    expect(anon_page.locator("body")).to_contain_text("\u521b\u5efa\u6bd4\u8d5b", timeout=10_000)


def test_login_with_invalid_password_stays_logged_out(anon_page: Page) -> None:
    """A3: a bad password surfaces a failure and the user stays on /login."""
    anon_page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    anon_page.locator('input[name="email"], input[type="email"]').first.fill(E2E_EMAIL)
    anon_page.locator('input[type="password"]').first.fill("definitely-wrong-password-xyz")
    anon_page.get_by_role("button", name="\u767b\u5f55").first.click()
    anon_page.wait_for_selector("text=操作失败", timeout=10_000)
    assert anon_page.url.rstrip("/").endswith("/login"), f"unexpected url: {anon_page.url}"


def test_auth_session_persists_across_reload(page: Page) -> None:
    """A4: a logged-in user stays logged in after a hard reload."""
    expect(page.locator("body")).to_contain_text("\u6bd4\u8d5b", timeout=10_000)
    page.reload(wait_until="domcontentloaded")
    expect(page.locator("body")).to_contain_text("\u6bd4\u8d5b", timeout=10_000)
    assert not page.url.rstrip("/").endswith("/login")
    expect(page.locator("body")).to_contain_text("\u7528\u6237", timeout=10_000)


def test_logout_returns_to_landing(page: Page) -> None:
    """A5: clicking the real \u767b\u51fa button on /user logs the user out, redirects
    to /login, and the public landing page renders for an anonymous visitor.

    Drives the actual UI logout flow (the IconLogout button in the user
    profile details tab) so a regression in the click handler, the
    `localStorage.removeItem('login')` call, or the post-logout redirect
    target surfaces here.
    """
    page.goto(f"{BASE_URL}/user", wait_until="domcontentloaded")
    # The logout button is rendered in the details tab with the
    # translated label \u767b\u51fa; the exact=True name match avoids the
    # \u9000\u51fa\u767b\u5f55 / \u767b\u5f55 ambiguity.
    logout_btn = page.get_by_role("button", name="\u767b\u51fa", exact=True)
    expect(logout_btn).to_be_visible(timeout=10_000)
    logout_btn.click()
    # The post-logout navigate redirects to /login.
    page.wait_for_url("**/login", timeout=10_000)
    assert page.url.rstrip("/").endswith("/login"), (
        f"expected redirect to /login after logout, got {page.url}"
    )
    # The login token must be cleared from localStorage.
    token = page.evaluate("() => window.localStorage.getItem('login')")
    assert token is None, f"expected login token cleared, got {token!r}"
    # And the public landing page (no token) renders the marketing
    # affordances for an anonymous visitor.
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    body = page.locator("body").inner_text()
    assert "\u767b\u5f55" in body, f"expected '\u767b\u5f55' in body, got: {body[:500]}"
    assert "\u521b\u5efa\u5e10\u6237" in body, f"expected '\u521b\u5efa\u5e10\u6237' in body, got: {body[:500]}"


def test_protected_route_redirects_anonymous_to_login(anon_page: Page) -> None:
    """A6: visiting /clubs while logged out bounces to /login."""
    anon_page.goto(f"{BASE_URL}/clubs", wait_until="domcontentloaded")
    anon_page.wait_for_url("**/login", timeout=10_000)
    assert anon_page.url.rstrip("/").endswith("/login"), (
        f"expected redirect to /login, got {anon_page.url}"
    )
