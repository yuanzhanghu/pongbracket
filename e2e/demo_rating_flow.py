"""Drive the FULL 加华积分 individual-rating lifecycle through the real UI and
emit a self-contained HTML walkthrough (screenshots embedded as base64).

Run from the e2e directory:  cd e2e && python3 demo_rating_flow.py [--lang zh|en|fr]
Output: ../rating_flow_demo.html (zh) or ../rating_flow_demo.<lang>.html

Flow shown:
  create individual rated tournament -> player joins instantly (no approval) ->
  owner adds THEMSELVES via the picker -> seed initial ratings for un-rated
  players -> review the member list -> add a scorer -> round-robin +
  single-elimination scheduling + scoring -> request settlement once (parked for
  admin) -> admin approves seeds & settles in one action -> category leaderboard.

The walkthrough is produced in one of three languages. `--lang` both drives the
UI in that language (by seeding i18next's localStorage key before the first
paint) and picks the narration below; every text-matching Playwright selector
resolves its expected label through the app's own i18next catalogue.
"""
from __future__ import annotations

import argparse
import base64
import html
import time
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
    api_get_tournament,
    api_rename_stage_item,
    api_schedule_matches,
    api_update_match_score,
)
from tests.test_rating import (
    _apply_to_join,
    _create_rated_individual_tournament,
    _force_cleanup_rated,
    _psql,
    _register_account,
)
from ui_strings import LANGUAGES, language_init_script, ui_string

STEPS: list[dict] = []

# Everything this walkthrough says in its own voice: the page chrome, the demo
# data that ends up inside the screenshots (tournament / stage / court names)
# and the per-step narration. Widget labels are NOT in here — those come from
# the app's catalogue via ui_string() so they can never drift.
#
# The zh column is byte-identical to the wording rating.html has always had; do
# not reword it, or the Chinese guide changes for no reason.
STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        "doc_title": "个人积分赛完整流程演示 · 加华积分网",
        "header_title": "个人积分赛完整流程演示",
        "header_sub": "加华积分（CanadaChinaTT）· 从建赛到积分排行榜的端到端界面走查",
        "toc_title": "流程步骤",
        "back_label": "← 返回系统首页",
        "tournament_name": "演示 加华积分 个人赛",
        "stage_group": "循环赛阶段",
        "stage_knockout": "淘汰赛阶段",
        "group_name": "小组1",
        "bracket_name": "单淘汰赛",
        "court_1": "球场 1",
        "court_2": "球场 2",
        "s1_title": "1. 创建个人积分赛",
        "s1_desc": (
            "“创建比赛”弹窗中「个人赛」默认已勾选，其下即有「参与积分」，勾选后出现「积分类别」"
            "（默认 加华积分 / CanadaChinaTT）。积分设置在创建时固定、之后只读。"
        ),
        "s2_title": "2. 用户参赛（登录即自动加入）",
        "s2_desc": (
            "登录的访客打开赛事结果页，点击「参赛」即立即加入（开赛前可随时退出，无需创建者批准、"
            "也不存在被拒绝；一旦开赛即不再显示「参赛 / 退出」）。勾选「允许创建者以后拉我进入比赛」"
            "后，该创建者今后的个人赛可直接把您加入；该授权可日后在「用户」页的"
            "「允许拉我进入比赛的人员」中随时删除。"
        ),
        "s3_title": "3. 创建者把自己加入参赛名单",
        "s3_desc": (
            "个人积分赛禁止自由文本建队，只能通过「直接添加参赛者」选择"
            "「已允许您把其拉进比赛」的账号。创建者本人也在可选列表中——创建者可以参加自己举办的比赛。"
        ),
        "s4_title": "4. 在「编辑参赛人员」中设置初始分",
        "s4_desc": (
            "尚无该类别积分的新选手，由创建者在每位参赛人员的「编辑参赛人员」弹窗里预设"
            "「初始积分」（例如 1500）。这些初始分需经管理员审核后才生效。"
        ),
        "s5_title": "5. 参赛成员一览（含积分列）",
        "s5_desc": (
            "参赛人员列表新增「积分类别」列：创建者本人 + 自动加入的 A/B/C 共 4 人，初始分带 * "
            "（待审核），正式分不带 *。可在此继续直接添加或删除成员。"
        ),
        "s6_title": "6. 添加记分员",
        "s6_desc": (
            "创建者可按邮箱添加「记分员」——记分员可读取赛事（含私有）并录入比分，但不能管理赛事；"
            "被加为记分员会自动关注该赛事。"
        ),
        "s7_title": "7. 循环赛 + 淘汰赛安排",
        "s7_desc": "第一阶段为 4 人单循环（C(4,2)=6 场），第二阶段为按循环赛排名播种的单淘汰赛。",
        "s8_title": "8. 录入分数和结果",
        "s8_desc": (
            "「录入分数和结果」标签把循环赛渲染成方格表（每格是两人对局的比分），"
            "淘汰赛渲染成对阵图；有录入权限者点击任一格/对阵位即可打开记分弹窗。"
        ),
        "s8b_title": "8b. 一键录入比分",
        "s8b_desc": (
            "记分弹窗按「胜 / 负」列出可选比分，一键点击即可（如 2:0）；不需要选择赛制（几局几胜），"
            "也不记录每局小分。还可标记「弃权」或「清除比分」。"
        ),
        "s9_title": "9. 申请积分结算（只按一次）",
        "s9_desc": (
            "新选手还有待审核的初始分时，创建者只需按一次「申请积分结算」：赛事即提交至管理员队列，"
            "页面显示「待管理员审核并结算」，无需再次操作。"
        ),
        "s9b_title": "9b. 管理员一键「批准并结算」",
        "s9b_desc": (
            "管理员在 /admin 看到该赛事及其全部待审初始分（可逐个调分），点一次「批准并结算」即"
            "把初始分置为生效（ACTIVE）并立即完成结算——一次审核同时通过初始分与积分结算。"
        ),
        "s10_title": "10. 积分排行榜（结算 #{seq}）",
        "s10_desc": (
            "类别排行榜（加华积分）展示各选手结算后的当前积分与对局数——本次比赛的结果已计入。"
        ),
    },
    "en": {
        "doc_title": "Rated individual tournament — full walkthrough · Jiahua Rating Network",
        "header_title": "Rated individual tournament — full walkthrough",
        "header_sub": (
            "Jiahua Rating (CanadaChinaTT) · an end-to-end tour of the interface, from creating "
            "the tournament to the rating leaderboard"
        ),
        "toc_title": "Steps",
        "back_label": "← Back to the home page",
        "tournament_name": "Demo — rated individual tournament",
        "stage_group": "Round-robin stage",
        "stage_knockout": "Knockout stage",
        "group_name": "Group 1",
        "bracket_name": "Knockout",
        "court_1": "Table 1",
        "court_2": "Table 2",
        "s1_title": "1. Create a rated individual tournament",
        "s1_desc": (
            "“Individual tournament” is ticked by default in the Create Tournament dialog, so "
            "“Counts towards rating” is shown right below it; ticking that in turn reveals "
            "“Rating category” (Jiahua Rating / "
            "CanadaChinaTT by default). Rating settings are fixed when the tournament is created "
            "and read-only from then on."
        ),
        "s2_title": "2. Players join (being signed in is enough)",
        "s2_desc": (
            "A signed-in visitor opens the tournament's results page and clicks “Join” to be "
            "entered straight away — no approval from the organiser and no way of being rejected. "
            "They can leave at any time before play starts, and once the tournament is under way "
            "“Join / Leave tournament” is no longer shown. Ticking “Let the creator add me to "
            "their tournaments from now on” lets that organiser enter you directly in their future "
            "individual tournaments; the authorisation can be withdrawn whenever you like under "
            "“People allowed to add me to tournaments” on the User page."
        ),
        "s3_title": "3. The organiser adds themselves to the field",
        "s3_desc": (
            "A rated individual tournament does not allow free-text entries: participants can only "
            "be picked with “Add a participant directly”, from the accounts that have allowed you "
            "to enter them. The organiser's own account is on that list too — organisers may play "
            "in the tournaments they run."
        ),
        "s4_title": "4. Set the initial rating from “Edit Participant”",
        "s4_desc": (
            "For newcomers who have no rating in this category yet, the organiser presets an "
            "“Initial rating” (1500, say) in each entry's “Edit Participant” dialog. Those "
            "initial ratings only take effect once an admin has reviewed them."
        ),
        "s5_title": "5. The entrant list (with the rating column)",
        "s5_desc": (
            "The participant list gains a rating column: the organiser plus players A, B and C who "
            "joined "
            "by themselves — four in all. An initial rating carries a trailing * (still under "
            "review), an official one does not. Entrants can still be added or removed from here."
        ),
        "s6_title": "6. Add a scorer",
        "s6_desc": (
            "The organiser can add a scorer by email address. A scorer can open the tournament "
            "(even a private one) and enter scores, but cannot administer it; being made a scorer "
            "also starts following the tournament automatically."
        ),
        "s7_title": "7. Round-robin + knockout format",
        "s7_desc": (
            "The first stage is a four-player round robin (C(4,2) = 6 matches); the second is a "
            "single-elimination bracket seeded from the round-robin standings."
        ),
        "s8_title": "8. Scores & Results",
        "s8_desc": (
            "The “Scores & Results” tab renders the round robin as a grid (each cell holds the "
            "score of one head-to-head match) and the knockout stage as a bracket. Anyone allowed "
            "to record scores opens the score dialog by clicking a cell or a bracket slot."
        ),
        "s8b_title": "8b. One-tap score entry",
        "s8b_desc": (
            "The score dialog lists the possible results grouped by winner and loser, so recording "
            "one is a single tap (2:0, for example). There is no best-of format to choose and no "
            "per-game points to type in. The same dialog also records a walkover (“Forfeit "
            "(walkover)”) or wipes the result (“Clear score”)."
        ),
        "s9_title": "9. Request the rating settlement (once only)",
        "s9_desc": (
            "While newcomers still have initial ratings awaiting review, the organiser only has to "
            "press “Request rating settlement” once: the tournament joins the admin queue and the "
            "page shows “Awaiting review and settlement by an admin”. There is nothing else to do."
        ),
        "s9b_title": "9b. The admin approves and settles in a single click",
        "s9b_desc": (
            "In /admin the administrator sees the tournament together with every initial rating "
            "awaiting review (each one can still be adjusted). One click on “Approve and settle” "
            "makes the initial ratings ACTIVE and settles the tournament immediately — a single "
            "review covers both the initial ratings and the rating settlement."
        ),
        "s10_title": "10. Rating leaderboard (settlement #{seq})",
        "s10_desc": (
            "The category leaderboard (Jiahua Rating) shows each player's current rating after "
            "settlement and how many matches they have played — this tournament's results are "
            "already included."
        ),
    },
    "fr": {
        "doc_title": "Tournoi individuel classé — procédure complète · Jiahua Rating Network",
        "header_title": "Tournoi individuel classé — procédure complète",
        "header_sub": (
            "Cote Jiahua (CanadaChinaTT) · visite guidée de l’interface, de la création du tournoi "
            "au classement des cotes"
        ),
        "toc_title": "Étapes",
        "back_label": "← Retour à l’accueil",
        "tournament_name": "Démo — tournoi individuel classé",
        "stage_group": "Phase de poule",
        "stage_knockout": "Phase à élimination directe",
        "group_name": "Poule 1",
        "bracket_name": "Élimination directe",
        "court_1": "Table 1",
        "court_2": "Table 2",
        "s1_title": "1. Créer un tournoi individuel classé",
        "s1_desc": (
            "« Tournoi individuel » est coché par défaut dans la fenêtre de création, « Compte "
            "pour la cote » s’affiche donc juste en dessous ; cocher cette dernière fait à son "
            "tour apparaître « Catégorie de "
            "cote » (cote Jiahua / CanadaChinaTT par défaut). Les paramètres de cote sont figés à "
            "la création du tournoi et deviennent ensuite non modifiables."
        ),
        "s2_title": "2. Les joueurs s’inscrivent (il suffit d’être connecté)",
        "s2_desc": (
            "Un visiteur connecté ouvre la page des résultats du tournoi et clique sur "
            "« Participer » pour être inscrit immédiatement : aucune validation de l’organisateur, "
            "et aucun refus possible. Il peut se retirer à tout moment avant le début, et "
            "« Participer / Quitter le tournoi » disparaît dès que le tournoi est lancé. En "
            "cochant « Autoriser le créateur à m’inscrire à ses tournois à l’avenir », ce créateur "
            "pourra vous inscrire directement à ses futurs tournois individuels ; cette "
            "autorisation se retire quand vous le souhaitez depuis « Personnes autorisées à "
            "m’inscrire à des tournois », sur la page Utilisateur."
        ),
        "s3_title": "3. L’organisateur s’ajoute à la liste des participants",
        "s3_desc": (
            "Un tournoi individuel classé n’autorise pas la saisie libre d’un nom : les "
            "participants se choisissent uniquement via « Ajouter un participant directement », "
            "parmi les comptes qui vous ont autorisé à les inscrire. Le compte de l’organisateur "
            "figure lui aussi dans cette liste — un organisateur peut jouer dans le tournoi qu’il "
            "organise."
        ),
        "s4_title": "4. Saisir la cote initiale depuis « Modifier le participant »",
        "s4_desc": (
            "Pour les nouveaux joueurs qui n’ont pas encore de cote dans cette catégorie, "
            "l’organisateur saisit une « Cote initiale » (1500, par exemple) dans la fenêtre "
            "« Modifier le participant » de chaque inscription. Ces cotes initiales ne prennent "
            "effet qu’après validation par un administrateur."
        ),
        "s5_title": "5. La liste des inscrits (avec la colonne de cote)",
        "s5_desc": (
            "La liste des participants reçoit une colonne de cote : l’organisateur et les joueurs "
            "A, B "
            "et C inscrits d’eux-mêmes, soit quatre au total. Une cote initiale porte un "
            "astérisque final (encore en validation), une cote officielle non. On peut toujours y "
            "ajouter ou en retirer des participants."
        ),
        "s6_title": "6. Ajouter un marqueur",
        "s6_desc": (
            "L’organisateur peut ajouter un marqueur à partir de son adresse e-mail. Un marqueur "
            "peut consulter le tournoi (même privé) et saisir les scores, mais ne peut pas "
            "l’administrer ; il se met de plus automatiquement à suivre le tournoi."
        ),
        "s7_title": "7. Poule + tableau à élimination directe",
        "s7_desc": (
            "La première phase est une poule de quatre joueurs (C(4,2) = 6 matchs) ; la seconde "
            "est un tableau à élimination directe dont les places sont attribuées d’après le "
            "classement de la poule."
        ),
        "s8_title": "8. Résultats",
        "s8_desc": (
            "L’onglet « Résultats » affiche la poule sous forme de grille (chaque case contient le "
            "score d’une confrontation) et la phase finale sous forme de tableau. Les personnes "
            "autorisées à saisir les scores ouvrent la fenêtre de saisie en cliquant sur une case "
            "ou sur une position du tableau."
        ),
        "s8b_title": "8b. Saisie du score en un clic",
        "s8b_desc": (
            "La fenêtre de saisie liste les scores possibles, regroupés par vainqueur et par "
            "perdant : un seul clic suffit (2:0, par exemple). Il n’y a ni format à choisir "
            "(nombre de manches gagnantes) ni points de chaque manche à saisir. La même fenêtre "
            "permet aussi de déclarer un « Forfait » ou d’« Effacer le score »."
        ),
        "s9_title": "9. Demander la clôture des cotes (une seule fois)",
        "s9_desc": (
            "Tant que des nouveaux joueurs ont une cote initiale en attente de validation, "
            "l’organisateur n’a qu’à cliquer une seule fois sur « Demander la clôture des "
            "cotes » : le tournoi rejoint la file des administrateurs et la page affiche « En "
            "attente de validation et de clôture par un administrateur ». Rien d’autre à faire."
        ),
        "s9b_title": "9b. L’administrateur valide et clôture en un seul clic",
        "s9b_desc": (
            "Dans /admin, l’administrateur voit le tournoi ainsi que toutes les cotes initiales en "
            "attente de validation (chacune reste ajustable). Un seul clic sur « Valider et "
            "clôturer » rend les cotes initiales actives (ACTIVE) et clôture aussitôt le tournoi — "
            "une seule validation couvre à la fois les cotes initiales et la clôture des cotes."
        ),
        "s10_title": "10. Classement des cotes (clôture n° {seq})",
        "s10_desc": (
            "Le classement de la catégorie (cote Jiahua) affiche la cote actuelle de chaque joueur "
            "après clôture ainsi que son nombre de matchs — les résultats de ce tournoi y sont "
            "déjà pris en compte."
        ),
    },
}


def _out_path(lang: str) -> str:
    return "../rating_flow_demo.html" if lang == "zh" else f"../rating_flow_demo.{lang}.html"


def _home_href(lang: str) -> str:
    return "/" if lang == "zh" else f"/?lng={lang}"


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
    owner_uid = owner["id"]

    # Find a club to host the tournament.
    clubs = requests.get(f"{BASE_URL}/api/clubs", headers=_api_headers(), timeout=15).json()["data"]
    club_id = clubs[0]["id"]

    applicants = [_register_account(f"demo{c}") for c in "ABC"]  # all auto-join on apply
    all_uids = [owner_uid] + [a["uid"] for a in applicants]
    tid = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        octx = _ctx(browser, owner_token, lang)
        opage = octx.new_page()
        try:
            # ---- 1. Create an individual rated tournament (UI modal) ----
            opage.goto(BASE_URL, wait_until="domcontentloaded")
            opage.get_by_role("button", name=ui("create_tournament_button")).first.click()
            modal = opage.locator(".mantine-Modal-content").last
            expect(modal).to_be_visible(timeout=10_000)
            modal.get_by_placeholder(ui("tournament_name_input_placeholder")).first.fill(
                s["tournament_name"]
            )
            # 个人赛 is checked by default, so 参与积分 is already shown.
            expect(
                modal.get_by_text(ui("rated_checkbox_label"), exact=True)
            ).to_be_visible(timeout=5_000)
            modal.get_by_text(ui("rated_checkbox_label"), exact=True).click()
            expect(
                modal.get_by_text(ui("rating_category_label"), exact=True)
            ).to_be_visible(timeout=5_000)
            shot(opage, s["s1_title"], s["s1_desc"], full_page=False)
            opage.keyboard.press("Escape")
            # Create reliably via the API (the modal screenshot already shows the UI).
            tid = _create_rated_individual_tournament(club_id)

            # ---- 2. A prospective player views the public results page ----
            actx = _ctx(browser, applicants[0]["token"], lang)
            apage = actx.new_page()
            apage.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
            expect(
                apage.get_by_role("button", name=ui("join_tournament_button"), exact=True)
            ).to_be_visible(timeout=15_000)
            shot(apage, s["s2_title"], s["s2_desc"], full_page=False)
            actx.close()
            # All applicants join instantly (via API, using their own tokens).
            for a in applicants:
                _apply_to_join(tid, a["token"])

            # ---- 4. Owner adds THEMSELVES via the hosted-account picker ----
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

            # ---- 5. Seed initial ratings via each team's edit modal ----
            opage.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
            teams = requests.get(
                f"{BASE_URL}/api/tournaments/{tid}/teams", headers=_api_headers(), timeout=15
            ).json()["data"]["teams"]

            def _seed_one(team_name: str) -> bool:
                """Open a team's edit modal and set its 初始积分 to 1500. Returns
                False (and closes the modal) if the rating is already official."""
                row = opage.locator("tr", has=opage.get_by_text(team_name, exact=True)).first
                row.get_by_role("button", name=ui("edit_button")).first.click()
                modal = opage.locator(".mantine-Modal-content").last
                expect(modal).to_be_visible(timeout=10_000)
                box = modal.get_by_placeholder(ui("initial_rating_input_placeholder"))
                if box.count() == 0:
                    opage.keyboard.press("Escape")
                    return False
                box.fill("1500")
                return True

            # Open the first participant's modal for the screenshot (seed field shown).
            _seed_one(teams[0]["name"])
            shot(opage, s["s4_title"], s["s4_desc"], full_page=False)
            opage.locator(".mantine-Modal-content").last.get_by_role(
                "button", name=ui("save_button")
            ).first.click()
            opage.wait_for_timeout(800)
            for tm in teams[1:]:
                if _seed_one(tm["name"]):
                    opage.locator(".mantine-Modal-content").last.get_by_role(
                        "button", name=ui("save_button")
                    ).first.click()
                    opage.wait_for_timeout(800)

            # ---- 6. Review the participant/member list (with the 积分 column) ----
            opage.goto(f"{BASE_URL}/tournaments/{tid}/teams", wait_until="domcontentloaded")
            expect(
                opage.get_by_text(ui("add_participant_legend"), exact=True)
            ).to_be_visible(timeout=15_000)
            shot(opage, s["s5_title"], s["s5_desc"])

            # ---- 7. Add a scorer ----
            scorer = _register_account("demoSC")
            opage.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
            expect(
                opage.get_by_text(ui("scorers_manager_legend"), exact=True)
            ).to_be_visible(timeout=15_000)
            opage.get_by_label(ui("add_scorer_label"), exact=True).fill(scorer["email"])
            shot(opage, s["s6_title"], s["s6_desc"])
            opage.get_by_role("button", name=ui("add_button"), exact=True).first.click()
            opage.wait_for_timeout(1200)

            # ---- 7. Round-robin + single-elimination scheduling & scoring ----
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
            shot(opage, s["s7_title"], s["s7_desc"])

            # Score all 6 RR matches via the API for a deterministic spread.
            for st in api_get_stages(tid):
                if st["id"] != s1:
                    continue
                for it in st.get("stage_items", []):
                    if it["id"] != rr_item:
                        continue
                    for rd in it.get("rounds", []):
                        for j, m in enumerate(rd.get("matches", [])):
                            games = [[11, 5], [11, 5]] if j % 2 == 0 else [[5, 11], [5, 11]]
                            api_update_match_score(tid, m["id"], rd["id"], games, best_of=3)

            # ---- 8. Results page: cross-table + inline bracket ----
            opage.goto(f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded")
            opage.wait_for_selector('[role="tab"]', timeout=15_000)
            opage.wait_for_timeout(1200)
            shot(opage, s["s8_title"], s["s8_desc"])

            # ---- 8b. Open the one-tap score modal on a round-robin cell ----
            cell = opage.locator("table button").first
            expect(cell).to_be_visible(timeout=10_000)
            cell.click()
            expect(
                opage.get_by_text(ui("edit_match_modal_title"), exact=True)
            ).to_be_visible(timeout=15_000)
            shot(opage, s["s8b_title"], s["s8b_desc"], full_page=False)
            opage.keyboard.press("Escape")

            # ---- 9. Owner requests settlement (just once) ----
            opage.goto(f"{BASE_URL}/tournaments/{tid}/settings", wait_until="domcontentloaded")
            btn = opage.get_by_role("button", name=ui("request_settlement_button"))
            expect(btn).to_be_visible(timeout=15_000)
            btn.click()
            opage.reload(wait_until="domcontentloaded")
            expect(
                opage.get_by_text(ui("settlement_pending_admin_badge"))
            ).to_be_visible(timeout=15_000)
            shot(opage, s["s9_title"], s["s9_desc"])

            # ---- 9b. Admin approves seeds AND settles in one action ----
            opage.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded")
            expect(
                opage.get_by_text(ui("admin_review_queue_title"), exact=True)
            ).to_be_visible(timeout=15_000)
            shot(opage, s["s9b_title"], s["s9b_desc"])
            opage.get_by_role("button", name=ui("approve_and_settle_button")).first.click()
            settled = None
            for _ in range(30):
                settled = api_get_tournament(tid).get("settled_seq")
                if settled is not None:
                    break
                time.sleep(0.5)

            # ---- 10. Category leaderboard ----
            opage.goto(f"{BASE_URL}/rating/1/leaderboard", wait_until="domcontentloaded")
            opage.wait_for_timeout(1500)
            shot(opage, s["s10_title"].format(seq=settled), s["s10_desc"])
        finally:
            octx.close()
            browser.close()
            if tid is not None:
                _force_cleanup_rated(tid, all_uids)


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
  header {{ background:linear-gradient(135deg,#1f6feb,#0a3d8f); color:#fff; padding:2.4rem 1.5rem; }}
  header .wrap {{ max-width:1080px; margin:0 auto; }}
  header h1 {{ margin:0 0 .4rem; font-size:1.9rem; }}
  header p {{ margin:0; opacity:.9; }}
  main {{ max-width:1080px; margin:0 auto; padding:1.5rem; }}
  .toc {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:1rem 1.4rem; margin:1.2rem 0; }}
  .toc h3 {{ margin:.2rem 0 .6rem; font-size:1rem; color:#475569; }}
  .toc ul {{ margin:0; padding-left:0; list-style:none; columns:2; }}
  .toc a {{ color:#1f6feb; text-decoration:none; }}
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
<footer><a href="{_home_href(lang)}" style="color:#1f6feb;text-decoration:none;">{html.escape(s['back_label'])}</a></footer>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"\nWrote {path} ({len(doc)//1024} KB, {len(STEPS)} steps)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the rated-individual walkthrough.")
    parser.add_argument(
        "--lang",
        choices=LANGUAGES,
        default="zh",
        help="language to drive the UI in and to write the walkthrough in (default: zh)",
    )
    args = parser.parse_args()
    run(args.lang)
    write_html(_out_path(args.lang), args.lang)
