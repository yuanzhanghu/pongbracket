# PongBracket · 加华积分网

**PongBracket** is a table-tennis tournament and cross-tournament rating system. It is the code
behind **[加华积分网 (Jiahua Rating Network)](https://bracket.ai1to1.com)**, a site where clubs and
players in the Canadian-Chinese table-tennis community run tournaments and keep a shared rating.

- 🌐 Live site: <https://bracket.ai1to1.com>
- 📖 使用指南 / User guide: <https://bracket.ai1to1.com/guide/index.html>
  - 个人积分赛完整流程演示 (rated individual tournament, end to end):
    [中文](https://bracket.ai1to1.com/guide/rating.html) ·
    [English](https://bracket.ai1to1.com/guide/rating.en.html) ·
    [Français](https://bracket.ai1to1.com/guide/rating.fr.html)
  - 个人赛（非积分）完整流程演示 (non-rated tournament):
    [中文](https://bracket.ai1to1.com/guide/basic.html) ·
    [English](https://bracket.ai1to1.com/guide/basic.en.html) ·
    [Français](https://bracket.ai1to1.com/guide/basic.fr.html)

## Where this comes from

PongBracket is a fork of **[evroon/bracket](https://github.com/evroon/bracket)**, an open-source
tournament system by Erik Vroon and contributors, written in async Python
([FastAPI](https://fastapi.tiangolo.com)) with a [Vite](https://vite.dev/) +
[Mantine](https://mantine.dev/) frontend. The upstream git history is preserved here as-is; all
changes made for 加华积分网 sit on top of it. Many thanks to the upstream authors. Please see the
[upstream repository](https://github.com/evroon/bracket) and its
[documentation](https://docs.bracketapp.nl) for the original project.

Like upstream, this project is licensed under the **GNU AGPL-3.0** (see [LICENSE](LICENSE)).

## What this fork adds

**Cross-tournament rating (加华积分 / CanadaChinaTT)**
- A rating pool that spans tournaments. Ratings change match by match using the
  [ChinaTT (开球网)](http://www.kaiqiu.wang) exchange table: an upset earns more than an
  expected win.
- Rating options are set when a tournament is created and can't be changed afterwards. Players
  join in one click. Initial ratings are reviewed by a site admin, and a tournament is settled
  with one button.
- 我的积分 (My rating) page with points history and a rating curve. Leaderboards show ratings per
  category.

**Table-tennis-oriented tournament flow**
- Individual tournaments: each participant is an account. Non-rated tournaments can also use
  free-text participant names.
- Round-robin groups auto-created and auto-seeded from a participant total (小组1, 小组2, …). Ties
  are broken with the ITTF group rules.
- Knockout stages built from group finishers, with rank-weighted spreading so players from the same
  group stay apart, automatic byes, and seeding from the top or bottom finishers.
- Single-elimination bracket view with connector lines. Swiss stages are removed.
- One-tap score entry: the score modal is a grid of `X:Y` result buttons, plus forfeit and
  clear-score options.
- 填分和结果 (Scores & results) page: a group grid plus a clickable bracket in one view, with
  standings showing 局分 (games) and 小分 (points).

**Roles, sharing and spectators**
- Scorer (记分员) role: someone who can enter scores for a tournament without owning it.
- Public, read-only results for spectators without logging in, and a public showcase page for
  series placements.
- Follow/favorite tournaments, a "joinable tournaments" tab, and archived tournaments.
- Clubs are implicit (one personal club per account). Users log in by name or email, and email is
  optional.

**Localization**
- Full Simplified Chinese / English / French coverage across the UI, the API messages and the
  guide screenshots, with a language switcher.

**Testing**
- Backend unit and integration tests (pytest), plus a Playwright end-to-end suite in [`e2e/`](e2e)
  covering the user-facing workflows. The checklist is in [`e2e/COVERAGE.md`](e2e/COVERAGE.md).

The design notes for the rating system (in Chinese) are in
[`design_CanadaChinaTT.html`](design_CanadaChinaTT.html).

## Running locally

```bash
git clone https://github.com/yuanzhanghu/pongbracket.git
cd pongbracket
docker compose up -d --build
```

This builds the frontend and backend and starts a throwaway Postgres instance. Then open
<http://localhost:8401>. The default admin login is the upstream one: `test@example.org` /
`aeGhoe1ahng2Aezai0Dei6Aih6dieHoo`. **Change it before exposing an instance to anyone else.**

For hot-reload development, run `./run.sh`. It starts the backend on `:4002` and the Vite dev
server pointed at it. You need `uv` and `pnpm` installed.

Tests:

```bash
cd backend && uv run pytest                 # backend (needs a Postgres test DB, see backend/ci.env)
python3 -m pytest e2e/tests -q              # E2E, against the local instance on :8401
```

Deployment notes for the production setup (nginx behind Cloudflare) are in
[`deploy/README.md`](deploy/README.md).

## Privacy

This repository contains source code only. No production database, user data or credentials are
included. The upstream history is unchanged, and this fork's work is squashed into a single
snapshot commit.

## License

[GNU Affero General Public License v3.0](LICENSE), inherited from
[evroon/bracket](https://github.com/evroon/bracket). If you run a modified version as a network
service, the AGPL requires you to offer its source to your users.
