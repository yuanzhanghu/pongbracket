"""Read the frontend's own i18next catalogues from Python.

The demo/capture scripts drive the real UI, and many of their Playwright
selectors match on visible text ("添加", "参赛", ...). Those selectors only work
while the UI is in Chinese. Instead of duplicating a second translation table
here, look the very same i18next key up in
``frontend/public/locales/<lng>/common.json`` — the file the app itself loads —
so a selector always matches whatever the UI renders in the active language.

Usage:

    from ui_strings import ui_string
    page.get_by_role("button", name=ui_string(lang, "add_button"), exact=True)
"""
from __future__ import annotations

import functools
import json
import pathlib

# The languages this deployment offers (mirrors frontend/src/components/utils/
# language_switcher.tsx).
LANGUAGES = ("zh", "en", "fr")

_LOCALES = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "public" / "locales"


@functools.cache
def _catalogue(lang: str) -> dict:
    with open(_LOCALES / lang / "common.json", encoding="utf-8") as fh:
        return json.load(fh)


def ui_string(lang: str, key: str) -> str:
    """The on-screen text the app renders for i18next `key` in `lang`."""
    catalogue = _catalogue(lang)
    try:
        return catalogue[key]
    except KeyError:
        raise KeyError(f"no i18next key {key!r} in {lang}/common.json") from None


def language_init_script(lang: str) -> str:
    """JS to seed i18next's language before the app's first paint.

    i18n.ts configures the detector with order ['querystring', 'localStorage']
    and caches the choice in localStorage, so writing the `i18nextLng` key from
    an init script makes the very first render come up in `lang`.
    """
    return f"window.localStorage.setItem('i18nextLng', {json.dumps(lang)});"
