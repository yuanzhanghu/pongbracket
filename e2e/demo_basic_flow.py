"""Drive the FULL 个人赛（非积分赛）lifecycle through the real UI and emit a
self-contained HTML walkthrough (screenshots embedded as base64).

Run from the e2e directory:  cd e2e && python3 demo_basic_flow.py [--lang zh|en|fr]
Output: ../basic_flow_demo.html (zh) or ../basic_flow_demo.<lang>.html

This is the non-rated sibling of demo_rating_flow.py. A non-rated individual
tournament is is_individual=True with rating_category_id=None, so the flow drops
everything rating-specific (initial-rating seeding, the 积分 column, settlement,
the category leaderboard) and ends at the in-tournament 排名 (standings):

  create individual NON-rated tournament -> player joins instantly (no approval)
  -> owner adds THEMSELVES via the picker -> review the member list -> add a
  scorer -> round-robin + single-elimination scheduling -> one-tap score entry ->
  final standings.

The walkthrough is produced in one of three languages. `--lang` both drives the
UI in that language (by seeding i18next's localStorage key before the first
paint) and picks the narration below; every text-matching Playwright selector
resolves its expected label through the app's own i18next catalogue.
"""
from __future__ import annotations

import argparse
import base64
import html
import uuid
from functools import partial

import requests
from playwright.sync_api import expect, sync_playwright

from tests._helpers import (
    BASE_URL,
    E2E_EMAIL,
    E2E_PASSWORD,
    _api_headers,
    api_create_court,
    api_create_round_robin,
    api_create_single_elimination_from_sources,
    api_create_stage,
    api_get_stages,
    api_rename_stage_item,
    api_schedule_matches,
    api_update_match_score,
)
from tests.test_rating import (
    _apply_to_join,
    _force_cleanup_rated,
    _register_account,
)
from ui_strings import LANGUAGES, language_init_script, ui_string

STEPS: list[dict] = []

# Everything this walkthrough says in its own voice: the page chrome, the demo
# data that ends up inside the screenshots (tournament / stage / court names)
# and the per-step narration. Widget labels are NOT in here — those come from
# the app's catalogue via ui_string() so they can never drift.
#
# The zh column is byte-identical to the wording basic.html has always had; do
# not reword it, or the Chinese guide changes for no reason.
STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        "doc_title": "个人赛（非积分）完整流程演示 · 加华积分网",
        "header_title": "个人赛（非积分）完整流程演示",
        "header_sub": "普通个人赛 · 从建赛到最终排名的端到端界面走查（不涉及积分结算）",
        "toc_title": "流程步骤",
        "back_label": "← 返回使用指南",
        "tournament_name": "演示 个人赛（非积分）",
        "stage_group": "循环赛阶段",
        "stage_knockout": "淘汰赛阶段",
        "group_name": "小组1",
        "bracket_name": "单淘汰赛",
        "court_1": "球场 1",
        "court_2": "球场 2",
        "s1_title": "1. 创建个人赛（不计积分）",
        "s1_desc": (
            "“创建比赛”弹窗中「个人赛」默认已勾选，其下会出现「参与积分」选项——保持它"
            "「不勾选」即为普通个人赛：选手仍以个人身份参赛，但赛后不会产生或结算任何积分。"
        ),
        "s2_title": "2. 用户参赛（登录即自动加入）",
        "s2_desc": (
            "登录的访客打开赛事结果页，点击「参赛」即立即加入（开赛前可随时退出，无需创建者批准）。"
            "个人赛的「参赛人员」即选手本人，一旦开赛即不再显示「参赛 / 退出」。"
        ),
        "s3_title": "3. 创建者把自己加入参赛名单",
        "s3_desc": (
            "创建者可参加自己举办的比赛：用「直接添加参赛者」选择已授权的账号（含创建者本人）。"
            "非积分个人赛还额外保留「添加参赛人员」按钮，可直接输入名称手动添加。"
        ),
        "s4_title": "4. 参赛成员一览",
        "s4_desc": (
            "参赛人员列表：创建者本人 + 自动加入的 A/B/C 共 4 人。非积分赛没有「积分」列，"
            "也没有初始分/待审核状态；可在此继续直接添加或删除成员。"
        ),
        "s5_title": "5. 添加记分员",
        "s5_desc": (
            "创建者可按邮箱添加「记分员」——记分员可读取赛事（含私有）并录入比分，但不能管理赛事；"
            "被加为记分员会自动关注该赛事。"
        ),
        "s6_title": "6. 循环赛 + 淘汰赛安排",
        "s6_desc": (
            "第一阶段为 4 人单循环（C(4,2)=6 场），第二阶段为按循环赛排名播种的单淘汰赛。"
            "非积分赛的赛制安排与积分赛完全相同。"
        ),
        "s7_title": "7. 录入分数和结果",
        "s7_desc": (
            "「录入分数和结果」标签把循环赛渲染成方格表（每格是两人对局的比分），"
            "淘汰赛渲染成对阵图；有录入权限者点击任一格/对阵位即可打开记分弹窗。"
        ),
        "s7b_title": "7b. 一键录入比分",
        "s7b_desc": (
            "记分弹窗按「胜 / 负」列出可选比分，一键点击即可（如 2:0）；不需要选择赛制（几局几胜），"
            "也不记录每局小分。还可标记「弃权」或「清除比分」。"
        ),
        "s8_title": "8. 排名（最终名次）",
        "s8_desc": (
            "「排名」标签按循环赛积分与淘汰赛结果给出最终名次。非积分赛到此结束——"
            "不涉及积分结算，也不会写入任何积分排行榜。"
        ),
    },
    "en": {
        "doc_title": "Individual tournament (unrated) — full walkthrough · Jiahua Rating Network",
        "header_title": "Individual tournament (unrated) — full walkthrough",
        "header_sub": (
            "A plain individual tournament · an end-to-end tour of the interface, from creating "
            "the tournament to the final rankings (no rating settlement involved)"
        ),
        "toc_title": "Steps",
        "back_label": "← Back to the user guide",
        "tournament_name": "Demo — individual tournament (unrated)",
        "stage_group": "Round-robin stage",
        "stage_knockout": "Knockout stage",
        "group_name": "Group 1",
        "bracket_name": "Knockout",
        "court_1": "Table 1",
        "court_2": "Table 2",
        "s1_title": "1. Create an unrated individual tournament",
        "s1_desc": (
            "“Individual tournament” is ticked by default in the Create Tournament dialog, which "
            "reveals a “Counts towards rating” option — leave it unticked and you get a plain "
            "individual tournament: players still enter as individuals, but nothing is rated or "
            "settled afterwards."
        ),
        "s2_title": "2. Players join (being signed in is enough)",
        "s2_desc": (
            "A signed-in visitor opens the tournament's results page and clicks “Join” to be "
            "entered straight away — no approval from the organiser, and they can leave again at "
            "any time before play starts. In an individual tournament a “participant” is the player "
            "themselves; once the tournament is under way, “Join / Leave tournament” is no longer "
            "shown."
        ),
        "s3_title": "3. The organiser adds themselves to the field",
        "s3_desc": (
            "Organisers may play in the tournaments they run: “Add a participant directly” lists "
            "every account that has authorised it, the organiser's own included. An unrated "
            "individual tournament also keeps the “Add Participant” button, so an entry can still be "
            "created by simply typing a name."
        ),
        "s4_title": "4. The entrant list",
        "s4_desc": (
            "The participant list: the organiser plus players A, B and C who joined by themselves "
            "— four "
            "in all. An unrated tournament has no rating column and no initial rating or "
            "pending-review state; entrants can still be added or removed from here."
        ),
        "s5_title": "5. Add a scorer",
        "s5_desc": (
            "The organiser can add a scorer by email address. A scorer can open the tournament "
            "(even a private one) and enter scores, but cannot administer it; being made a scorer "
            "also starts following the tournament automatically."
        ),
        "s6_title": "6. Round-robin + knockout format",
        "s6_desc": (
            "The first stage is a four-player round robin (C(4,2) = 6 matches); the second is a "
            "single-elimination bracket seeded from the round-robin standings. Setting the format "
            "up is exactly the same as in a rated tournament."
        ),
        "s7_title": "7. Scores & Results",
        "s7_desc": (
            "The “Scores & Results” tab renders the round robin as a grid (each cell holds the "
            "score of one head-to-head match) and the knockout stage as a bracket. Anyone allowed "
            "to record scores opens the score dialog by clicking a cell or a bracket slot."
        ),
        "s7b_title": "7b. One-tap score entry",
        "s7b_desc": (
            "The score dialog lists the possible results grouped by winner and loser, so recording "
            "one is a single tap (2:0, for example). There is no best-of format to choose and no "
            "per-game points to type in. The same dialog also records a walkover (“Forfeit "
            "(walkover)”) or wipes the result (“Clear score”)."
        ),
        "s8_title": "8. Rankings (final placings)",
        "s8_desc": (
            "The “Rankings” tab turns the round-robin points and the knockout results into the "
            "final placings. That is where an unrated tournament ends — nothing is settled, and "
            "nothing is written to any rating leaderboard."
        ),
    },
    "fr": {
        "doc_title": (
            "Tournoi individuel (hors classement) — procédure complète · Jiahua Rating Network"
        ),
        "header_title": "Tournoi individuel (hors classement) — procédure complète",
        "header_sub": (
            "Un tournoi individuel ordinaire · visite guidée de l’interface, de la création du "
            "tournoi au classement final (sans clôture des cotes)"
        ),
        "toc_title": "Étapes",
        "back_label": "← Retour au guide d’utilisation",
        "tournament_name": "Démo — tournoi individuel (hors classement)",
        "stage_group": "Phase de poule",
        "stage_knockout": "Phase à élimination directe",
        "group_name": "Poule 1",
        "bracket_name": "Élimination directe",
        "court_1": "Table 1",
        "court_2": "Table 2",
        "s1_title": "1. Créer un tournoi individuel hors classement",
        "s1_desc": (
            "« Tournoi individuel » est coché par défaut dans la fenêtre de création, ce qui fait "
            "apparaître l’option « Compte pour la cote » : laissez-la décochée et vous obtenez un "
            "tournoi individuel ordinaire — les joueurs concourent bien à titre individuel, mais "
            "aucune cote n’est produite ni clôturée à l’issue du tournoi."
        ),
        "s2_title": "2. Les joueurs s’inscrivent (il suffit d’être connecté)",
        "s2_desc": (
            "Un visiteur connecté ouvre la page des résultats du tournoi et clique sur "
            "« Participer » pour être inscrit immédiatement : aucune validation de l’organisateur "
            "n’est nécessaire et il peut se retirer à tout moment avant le début. Dans un tournoi "
            "individuel, le « participant » est le joueur lui-même ; une fois le tournoi lancé, "
            "« Participer / Quitter le tournoi » n’apparaît plus."
        ),
        "s3_title": "3. L’organisateur s’ajoute à la liste des participants",
        "s3_desc": (
            "L’organisateur peut jouer dans le tournoi qu’il organise : « Ajouter un participant "
            "directement » propose tous les comptes qui l’y ont autorisé, y compris le sien. Un "
            "tournoi individuel hors classement conserve en outre le bouton « Ajouter un "
            "participant », qui permet de créer une inscription en saisissant simplement un nom."
        ),
        "s4_title": "4. La liste des inscrits",
        "s4_desc": (
            "La liste des participants : l’organisateur et les joueurs A, B et C inscrits "
            "d’eux-mêmes, "
            "soit quatre au total. Un tournoi hors classement n’a pas de colonne de cote, ni cote "
            "initiale, ni statut « en validation » ; on peut toujours y ajouter ou en retirer des "
            "participants."
        ),
        "s5_title": "5. Ajouter un marqueur",
        "s5_desc": (
            "L’organisateur peut ajouter un marqueur à partir de son adresse e-mail. Un marqueur "
            "peut consulter le tournoi (même privé) et saisir les scores, mais ne peut pas "
            "l’administrer ; il se met de plus automatiquement à suivre le tournoi."
        ),
        "s6_title": "6. Poule + tableau à élimination directe",
        "s6_desc": (
            "La première phase est une poule de quatre joueurs (C(4,2) = 6 matchs) ; la seconde "
            "est un tableau à élimination directe dont les places sont attribuées d’après le "
            "classement de la poule. La configuration du format est identique à celle d’un tournoi "
            "classé."
        ),
        "s7_title": "7. Résultats",
        "s7_desc": (
            "L’onglet « Résultats » affiche la poule sous forme de grille (chaque case contient le "
            "score d’une confrontation) et la phase finale sous forme de tableau. Les personnes "
            "autorisées à saisir les scores ouvrent la fenêtre de saisie en cliquant sur une case "
            "ou sur une position du tableau."
        ),
        "s7b_title": "7b. Saisie du score en un clic",
        "s7b_desc": (
            "La fenêtre de saisie liste les scores possibles, regroupés par vainqueur et par "
            "perdant : un seul clic suffit (2:0, par exemple). Il n’y a ni format à choisir "
            "(nombre de manches gagnantes) ni points de chaque manche à saisir. La même fenêtre "
            "permet aussi de déclarer un « Forfait » ou d’« Effacer le score »."
        ),
        "s8_title": "8. Classement final",
        "s8_desc": (
            "L’onglet « Barèmes de classement » établit les places finales à partir des points de "
            "la poule et des résultats du tableau. Un tournoi hors classement s’arrête là : "
            "aucune clôture de cote, aucune écriture dans un classement des cotes."
        ),
    },
}


def _out_path(lang: str) -> str:
    return "../basic_flow_demo.html" if lang == "zh" else f"../basic_flow_demo.{lang}.html"


def _guide_href(lang: str) -> str:
    return "/guide/index.html" if lang == "zh" else f"/guide/index.html?lng={lang}"


def _token(email: str, pw: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/token",
        data={"grant_type": "password", "username": email, "password": pw},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _ctx(browser, token: str, lang: str):
    ctx = browser.new_context(base_url=BASE_URL, viewport={"width": 1440, "height": 900})
    ctx.add_init_script(
        "window.localStorage.setItem('login', '%s');" % ('{"access_token":"%s"}' % token)
        + language_init_script(lang)
    )
    return ctx


def _create_unrated_individual_tournament(club_id: int) -> int:
    """Create an individual, NON-rated tournament (is_individual=True, no
    rating category). Returns the new tournament id."""
    auth = _api_headers()
    tname = f"E2E-Basic-{uuid.uuid4().hex[:6]}"
    requests.post(
        f"{BASE_URL}/api/tournaments",
        headers=auth,
        json={
            "name": tname,
            "club_id": club_id,
            "dashboard_public": True,
            "dashboard_endpoint": "",
            "players_can_be_in_multiple_teams": False,
            "auto_assign_courts": True,
            "start_time": "2030-01-01T00:00:00Z",
            "duration_minutes": 10,
            "margin_minutes": 5,
            "is_individual": True,
            # rating_category_id omitted -> non-rated.
        },
        timeout=15,
    ).raise_for_status()
    r2 = requests.get(f"{BASE_URL}/api/tournaments?filter_=ALL", headers=auth, timeout=15)
    r2.raise_for_status()
    return next(t["id"] for t in r2.json()["data"] if t["name"] == tname)


def shot(page, title: str, desc: str, full_page: bool = True) -> None:
    page.wait_for_timeout(600)
    png = page.screenshot(full_page=full_page)
    STEPS.append(
        {
            "n": len(STEPS) + 1,
            "title": title,
            "desc": desc,
            "b64": base64.b64encode(png).decode("ascii"),
        }
    )
    print(f"  [{len(STEPS):02d}] {title}")


def run(lang: str) -> None:
    s = STRINGS[lang]
    ui = partial(ui_string, lang)  # the label the UI itself renders for an i18next key

    owner_token = _token(E2E_EMAIL, E2E_PASSWORD)
    owner = requests.get(f"{BASE_URL}/api/users/me", headers=_api_headers(), timeout=15).json()[
        "data"
    ]
    owner_name = owner["name"]

    clubs = requests.get(f"{BASE_URL}/api/clubs", headers=_api_headers(), timeout=15).json()["data"]
    club_id = clubs[0]["id"]

    applicants = [_register_account(f"basic{c}") for c in "ABC"]  # all auto-join on apply
    tid = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        octx = _ctx(browser, owner_token, lang)
        opage = octx.new_page()
        try:
            # ---- 1. Create an individual, NON-rated tournament (UI modal) ----
            opage.goto(BASE_URL, wait_until="domcontentloaded")
            opage.get_by_role("button", name=ui("create_tournament_button")).first.click()
            modal = opage.locator(".mantine-Modal-content").last
            expect(modal).to_be_visible(timeout=10_000)
            modal.get_by_placeholder(ui("tournament_name_input_placeholder")).first.fill(
                s["tournament_name"]
            )
            # 个人赛 is checked by default, so 参与积分 is already shown — leave it
            # UNCHECKED (non-rated).
            expect(
                modal.get_by_text(ui("rated_checkbox_label"), exact=True)
            ).to_be_visible(timeout=5_000)
            shot(opage, s["s1_title"], s["s1_desc"], full_page=False)
            opage.keyboard.press("Escape")
            # Create reliably via the API (the modal screenshot already shows the UI).
            tid = _create_unrated_individual_tournament(club_id)

            # ---- 2. A prospective player views the public results page ----
            actx = _ctx(browser, applicants[0]["token"], lang)
            apage = actx.new_page()
            apage.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
            expect(
                apage.get_by_role("button", name=ui("join_tournament_button"), exact=True)
            ).to_be_visible(timeout=15_000)
            shot(apage, s["s2_title"], s["s2_desc"], full_page=False)
            actx.close()
            for a in applicants:
                _apply_to_join(tid, a["token"])

            # ---- 3. Owner adds THEMSELVES via the hosted-account picker ----
            opage.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
            picker = opage.locator(
                "fieldset", has=opage.get_by_text(ui("add_participant_legend"), exact=True)
            ).first
            expect(picker).to_be_visible(timeout=15_000)
            search = picker.get_by_placeholder(ui("search_by_name_or_email_placeholder"))
            search.click()
            search.fill(owner_name)
            opt = opage.get_by_role("option", name=owner_name, exact=False).first
            expect(opt).to_be_visible(timeout=10_000)
            shot(opage, s["s3_title"], s["s3_desc"])
            opt.click()
            picker.get_by_role("button", name=ui("add_button"), exact=True).click()
            opage.wait_for_timeout(1500)

            # ---- 4. Review the participant/member list (no 积分 column) ----
            opage.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
            expect(
                opage.get_by_text(ui("add_participant_legend"), exact=True)
            ).to_be_visible(timeout=15_000)
            shot(opage, s["s4_title"], s["s4_desc"])

            # ---- 5. Add a scorer ----
            scorer = _register_account("basicSC")
            opage.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
            expect(
                opage.get_by_text(ui("scorers_manager_legend"), exact=True)
            ).to_be_visible(timeout=15_000)
            opage.get_by_label(ui("add_scorer_label"), exact=True).fill(scorer["email"])
            shot(opage, s["s5_title"], s["s5_desc"])
            opage.get_by_role("button", name=ui("add_button"), exact=True).first.click()
            opage.wait_for_timeout(1200)

            # ---- 6. Round-robin + single-elimination scheduling ----
            s1 = api_create_stage(tid, s["stage_group"])
            rr_item = api_create_round_robin(tid, s1, team_count=4, group_count=1)
            # The backend always auto-names groups 小组1, 小组2, ... regardless of
            # the UI language, so rename it for the language being documented.
            api_rename_stage_item(tid, rr_item, s["group_name"])
            s2 = api_create_stage(tid, s["stage_knockout"])
            api_create_single_elimination_from_sources(
                tid,
                s2,
                sources=[{"stage_item_id": rr_item, "positions": 4}],
                take="top",
                name=s["bracket_name"],
            )
            api_create_court(tid, s["court_1"])
            api_create_court(tid, s["court_2"])
            api_schedule_matches(tid)
            opage.goto(f"{BASE_URL}/tournaments/{tid}/stages", wait_until="domcontentloaded")
            opage.wait_for_timeout(1500)
            shot(opage, s["s6_title"], s["s6_desc"])

            # Score all 6 RR matches via the API for a deterministic spread.
            for i, st in enumerate(api_get_stages(tid)):
                if st["id"] != s1:
                    continue
                for it in st.get("stage_items", []):
                    if it["id"] != rr_item:
                        continue
                    for rd in it.get("rounds", []):
                        for j, m in enumerate(rd.get("matches", [])):
                            # Alternate winners so the standings show a real spread.
                            games = [[11, 5], [11, 5]] if j % 2 == 0 else [[5, 11], [5, 11]]
                            api_update_match_score(tid, m["id"], rd["id"], games, best_of=3)

            # ---- 7. Results page: cross-table + bracket ----
            opage.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
            opage.wait_for_selector('[role="tab"]', timeout=15_000)
            opage.wait_for_timeout(1200)
            shot(opage, s["s7_title"], s["s7_desc"])

            # ---- 7b. Open the one-tap score modal on a round-robin cell ----
            cell = opage.locator("table button").first
            expect(cell).to_be_visible(timeout=10_000)
            cell.click()
            expect(
                opage.get_by_text(ui("edit_match_modal_title"), exact=True)
            ).to_be_visible(timeout=15_000)
            shot(opage, s["s7b_title"], s["s7b_desc"], full_page=False)
            opage.keyboard.press("Escape")

            # ---- 8. Final standings (in-tournament 排名) ----
            opage.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
            opage.wait_for_selector('[role="tab"]', timeout=15_000)
            opage.get_by_role("tab", name=ui("rankings_title")).click()
            opage.wait_for_timeout(1200)
            shot(opage, s["s8_title"], s["s8_desc"])
        finally:
            octx.close()
            browser.close()
            if tid is not None:
                _force_cleanup_rated(tid, [])


def write_html(path: str, lang: str) -> None:
    s = STRINGS[lang]
    cards = []
    for step in STEPS:
        cards.append(
            f"""
    <section class="step">
      <h2>{html.escape(step['title'])}</h2>
      <p class="desc">{html.escape(step['desc'])}</p>
      <img alt="{html.escape(step['title'])}" src="data:image/png;base64,{step['b64']}"/>
    </section>"""
        )
    doc = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(s['doc_title'])}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
         background:#f4f6fa; color:#1d2733; line-height:1.6; }}
  header {{ background:linear-gradient(135deg,#0f9d6b,#0a6b53); color:#fff; padding:2.4rem 1.5rem; }}
  header .wrap {{ max-width:1080px; margin:0 auto; }}
  header h1 {{ margin:0 0 .4rem; font-size:1.9rem; }}
  header p {{ margin:0; opacity:.9; }}
  main {{ max-width:1080px; margin:0 auto; padding:1.5rem; }}
  .toc {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:1rem 1.4rem; margin:1.2rem 0; }}
  .toc h3 {{ margin:.2rem 0 .6rem; font-size:1rem; color:#475569; }}
  .toc ul {{ margin:0; padding-left:0; list-style:none; columns:2; }}
  .toc a {{ color:#0f9d6b; text-decoration:none; }}
  .toc a:hover {{ text-decoration:underline; }}
  .step {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:1.2rem 1.4rem 1.6rem;
           margin:1.2rem 0; box-shadow:0 1px 3px rgba(16,24,40,.05); scroll-margin-top:1rem; }}
  .step h2 {{ margin:.1rem 0 .5rem; font-size:1.25rem; }}
  .desc {{ margin:.2rem 0 1rem; color:#475569; }}
  .step img {{ width:100%; height:auto; border:1px solid #dbe3ee; border-radius:8px; display:block; }}
  footer {{ max-width:1080px; margin:0 auto; padding:1rem 1.5rem 3rem; color:#94a3b8; font-size:.85rem; }}
</style>
</head>
<body>
<header><div class="wrap">
  <h1>{html.escape(s['header_title'])}</h1>
  <p>{html.escape(s['header_sub'])}</p>
</div></header>
<main>
  <div class="toc">
    <h3>{html.escape(s['toc_title'])}</h3>
    <ul>
      {''.join(f'<li><a href="#step{step["n"]}">{html.escape(step["title"])}</a></li>' for step in STEPS)}
    </ul>
  </div>
  {''.join(c.replace('<section class="step">', f'<section class="step" id="step{step["n"]}">') for c, step in zip(cards, STEPS))}
</main>
<footer><a href="{_guide_href(lang)}" style="color:#0f9d6b;text-decoration:none;">{html.escape(s['back_label'])}</a></footer>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"\nWrote {path} ({len(doc)//1024} KB, {len(STEPS)} steps)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the unrated-individual walkthrough.")
    parser.add_argument(
        "--lang",
        choices=LANGUAGES,
        default="zh",
        help="language to drive the UI in and to write the walkthrough in (default: zh)",
    )
    args = parser.parse_args()
    run(args.lang)
    write_html(_out_path(args.lang), args.lang)
