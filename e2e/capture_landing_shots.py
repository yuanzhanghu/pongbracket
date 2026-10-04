"""Re-capture the four screenshots the public landing page shows.

Run from the e2e directory:  cd e2e && python3 capture_landing_shots.py [--lang zh|en|fr]

Writes into ../frontend/public/guide/ using the same per-language naming
convention as the guide pages — the Chinese files keep the bare name, the others
carry a language suffix:

    stages.png      schedule.png      rankings.png      bracket.png      (zh)
    stages.en.png   schedule.en.png   rankings.en.png   bracket.en.png   (en)
    stages.fr.png   schedule.fr.png   rankings.fr.png   bracket.fr.png   (fr)

It builds a throwaway 8-player tournament (two round-robin groups feeding a
single-elimination bracket, three tables) through the API, drives the real UI in
the requested language, and deletes everything again in a finally block.

Demo player names are Chinese for zh and Latin-script for en/fr, so a visitor
does not land on screenshots of a product that looks like it is only for one
language.
"""
from __future__ import annotations

import argparse
import pathlib

import requests
from playwright.sync_api import expect, sync_playwright

from tests._helpers import (
    BASE_URL,
    E2E_EMAIL,
    E2E_PASSWORD,
    _api_headers,
    api_activate_next_stage,
    api_create_court,
    api_create_round_robin,
    api_create_single_elimination_from_sources,
    api_create_stage,
    api_create_teams,
    api_create_tournament,
    api_delete_tournament,
    api_get_stages,
    api_get_tournaments,
    api_rename_stage_item,
    api_schedule_matches,
    api_update_match_score,
)
from ui_strings import LANGUAGES, language_init_script, ui_string

GUIDE_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "public" / "guide"

# Everything that ends up rendered inside the screenshots and does NOT come from
# the app's own i18n catalogue: the tournament / stage / group / court names
# (stored rows, so the backend hands them back verbatim whatever the UI
# language) and the demo field.
DEMO: dict[str, dict] = {
    "zh": {
        "tournament": "市乒乓球公开赛",
        "stage_group": "小组循环赛",
        "stage_knockout": "淘汰赛",
        "groups": ["小组1", "小组2"],
        "bracket": "淘汰赛",
        "courts": ["台1", "台2", "台3"],
        "players": ["张伟", "周强", "王芳", "孙杰", "刘洋", "陈明", "李娜", "赵敏"],
    },
    "en": {
        "tournament": "City Table Tennis Open",
        "stage_group": "Group stage",
        "stage_knockout": "Knockout",
        "groups": ["Group 1", "Group 2"],
        "bracket": "Knockout",
        "courts": ["Table 1", "Table 2", "Table 3"],
        "players": [
            "Alex Turner",
            "Ben Carter",
            "Chloe Adams",
            "Daniel Reed",
            "Emma Fisher",
            "Jack Morgan",
            "Laura Bennett",
            "Owen Hayes",
        ],
    },
    "fr": {
        "tournament": "Open de tennis de table",
        "stage_group": "Phase de poules",
        "stage_knockout": "Phase finale",
        "groups": ["Poule 1", "Poule 2"],
        "bracket": "Élimination directe",
        "courts": ["Table 1", "Table 2", "Table 3"],
        "players": [
            "Camille Laurent",
            "Hugo Bernard",
            "Léa Moreau",
            "Thomas Girard",
            "Manon Dubois",
            "Lucas Petit",
            "Chloé Fontaine",
            "Antoine Rousseau",
        ],
    },
}

# Deterministic, varied round-robin results (2:0 / 2:1 / 0:2) so the standings
# table shows a real spread of points, games and small points.
_RR_PATTERNS = [
    [[11, 5], [11, 7]],
    [[9, 11], [11, 8], [11, 6]],
    [[6, 11], [8, 11]],
]
# Knockout results: alternate a clean 0:2 with a three-game 2:1.
_ELIM_PATTERNS = [
    [[7, 11], [9, 11]],
    [[11, 9], [9, 11], [11, 7]],
]


def _out(base: str, lang: str) -> pathlib.Path:
    return GUIDE_DIR / (f"{base}.png" if lang == "zh" else f"{base}.{lang}.png")


def _token(email: str, pw: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/token",
        data={"grant_type": "password", "username": email, "password": pw},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _ctx(browser, token: str, lang: str):
    # 1280x950 at 2x is the geometry the committed screenshots were taken with.
    ctx = browser.new_context(
        base_url=BASE_URL,
        viewport={"width": 1280, "height": 950},
        device_scale_factor=2,
    )
    ctx.add_init_script(
        "window.localStorage.setItem('login', '%s');" % ('{"access_token":"%s"}' % token)
        + language_init_script(lang)
    )
    return ctx


def _stage_items(tid: int, stage_id: int) -> list:
    for stage in api_get_stages(tid):
        if stage["id"] == stage_id:
            return stage.get("stage_items", [])
    return []


def _find_stage_item(tid: int, stage_item_id: int) -> dict:
    for stage in api_get_stages(tid):
        for item in stage.get("stage_items", []):
            if item["id"] == stage_item_id:
                return item
    raise RuntimeError(f"stage item {stage_item_id} disappeared")


def _score_round_robin(tid: int, group_ids: list) -> None:
    n = 0
    for group_id in group_ids:
        item = _find_stage_item(tid, group_id)
        for rd in item.get("rounds", []):
            for m in rd.get("matches", []):
                api_update_match_score(
                    tid, m["id"], rd["id"], _RR_PATTERNS[n % len(_RR_PATTERNS)], best_of=3
                )
                n += 1


def _score_elimination(tid: int, bracket_id: int) -> None:
    """Score the knockout rounds in order, re-reading the bracket between rounds
    so each round's slots are filled in by the previous round's winners first."""
    n = 0
    round_index = 0
    while True:
        rounds = _find_stage_item(tid, bracket_id).get("rounds", [])
        if round_index >= len(rounds):
            return
        rd = rounds[round_index]
        for m in rd.get("matches", []):
            # Byes and not-yet-resolved slots have no team on one of the sides.
            if (m.get("stage_item_input1") or {}).get("team") is None:
                continue
            if (m.get("stage_item_input2") or {}).get("team") is None:
                continue
            api_update_match_score(
                tid, m["id"], rd["id"], _ELIM_PATTERNS[n % len(_ELIM_PATTERNS)], best_of=3
            )
            n += 1
        round_index += 1


def _delete_leftovers(club_id: int, name: str) -> None:
    """Remove a tournament of the same name left behind by an interrupted run,
    so a re-run does not trip over the duplicate-name check."""
    for t in api_get_tournaments():
        if t.get("club_id") == club_id and t.get("name") == name:
            api_delete_tournament(t["id"])


def run(lang: str) -> None:
    demo = DEMO[lang]
    owner_token = _token(E2E_EMAIL, E2E_PASSWORD)
    clubs = requests.get(f"{BASE_URL}/api/clubs", headers=_api_headers(), timeout=15).json()["data"]
    club_id = clubs[0]["id"]

    _delete_leftovers(club_id, demo["tournament"])
    tid = api_create_tournament(club_id, demo["tournament"])
    try:
        api_create_teams(tid, demo["players"])

        stage_group = api_create_stage(tid, demo["stage_group"])
        api_create_round_robin(tid, stage_group, team_count=8, group_count=2)
        # The backend always names groups 小组1, 小组2, ... whatever the UI
        # language, because the name is a stored row and not an i18n key.
        group_ids = [item["id"] for item in _stage_items(tid, stage_group)]
        for group_id, group_name in zip(group_ids, demo["groups"]):
            api_rename_stage_item(tid, group_id, group_name)

        stage_knockout = api_create_stage(tid, demo["stage_knockout"])
        bracket_id = api_create_single_elimination_from_sources(
            tid,
            stage_knockout,
            sources=[{"stage_item_id": gid, "positions": 2} for gid in group_ids],
            take="top",
            name=demo["bracket"],
        )

        for court in demo["courts"]:
            api_create_court(tid, court)
        api_schedule_matches(tid)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = _ctx(browser, owner_token, lang)
            page = ctx.new_page()
            try:
                # --- schedule: courts x time, before the knockout slots resolve
                page.goto(f"{BASE_URL}/tournaments/{tid}/schedule", wait_until="domcontentloaded")
                expect(page.get_by_text(demo["courts"][0], exact=True).first).to_be_visible(
                    timeout=20_000
                )
                page.wait_for_timeout(1200)
                page.screenshot(path=str(_out("schedule", lang)), full_page=True)
                print(f"  wrote {_out('schedule', lang).name}")

                # Play the groups out, then advance so the qualifiers drop into
                # the bracket, then play the bracket out.
                _score_round_robin(tid, group_ids)
                api_activate_next_stage(tid)  # -> group stage
                api_activate_next_stage(tid)  # -> knockout stage
                _score_elimination(tid, bracket_id)

                # --- stages: the format builder with both stages filled in
                page.goto(f"{BASE_URL}/tournaments/{tid}/stages", wait_until="domcontentloaded")
                expect(page.get_by_text(demo["groups"][0], exact=True).first).to_be_visible(
                    timeout=20_000
                )
                page.wait_for_timeout(1500)
                page.screenshot(path=str(_out("stages", lang)), full_page=True)
                print(f"  wrote {_out('stages', lang).name}")

                # --- rankings: the standings tab of the results page
                page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
                page.wait_for_selector('[role="tab"]', timeout=20_000)
                page.get_by_role("tab", name=ui_string(lang, "rankings_title")).click()
                page.wait_for_timeout(1500)
                page.screenshot(path=str(_out("rankings", lang)), full_page=True)
                print(f"  wrote {_out('rankings', lang).name}")

                # --- bracket: just the knockout block of the results tab. The
                # innermost <div> holding the stage-item heading is the block we
                # want, hence .last (ancestors come first in document order).
                page.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
                page.wait_for_selector('[role="tab"]', timeout=20_000)
                heading = page.get_by_role("heading", name=demo["bracket"], exact=True)
                expect(heading.first).to_be_visible(timeout=20_000)
                page.wait_for_timeout(1500)
                page.locator("div", has=heading).last.screenshot(path=str(_out("bracket", lang)))
                print(f"  wrote {_out('bracket', lang).name}")
            finally:
                ctx.close()
                browser.close()
    finally:
        api_delete_tournament(tid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture the landing-page screenshots.")
    parser.add_argument(
        "--lang",
        choices=LANGUAGES,
        default="zh",
        help="language to drive the UI in and to name the output files for (default: zh)",
    )
    args = parser.parse_args()
    run(args.lang)
