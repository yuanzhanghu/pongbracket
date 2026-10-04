# Missing / unimplemented features surfaced by the E2E suite

Features that the guide, i18n strings, or COVERAGE.md imply but the **current
local build (http://localhost:8401)** does not actually implement. These are
**recorded, not implemented** — the E2E suite marks the corresponding COVERAGE
item `[~]` and asserts the current (stub/absent) reality so a future
implementation will make the honest test fail and prompt an upgrade.

| ID | Feature | Where it's expected | Evidence it's missing | COVERAGE |
|----|---------|---------------------|------------------------|----------|
| MF1 | **Double elimination** bracket format | Create-stage-item modal (alongside Round Robin / Single Elimination) | The modal exposes only RR / SE (Swiss was removed); no double-elim option. `test_create_stage_item_modal_lists_two_formats` locks the two actual options in. | F5 `[~]` |
| MF2 | **Auto-group by seeding** (按排位自动分组) | A button on the stages page to distribute teams into groups by seed | i18n key `auto_seed_distribute_button` exists in the locale file, but **no page imports/renders it** — the control is unreachable in this build. | F8 `[~]` |
| MF3 | **Edit / rename a court** | Court card kebab menu (next to 删除场地) | The kebab menu only exposes 删除场地; there is no 编辑场地 / 重命名场地 item. `test_court_kebab_menu_has_no_edit_option` locks this in. Delete works end-to-end. | G2 `[~]` (delete is `[x]`) |
| MF4 | **Password reset** flow | `/password-reset` (linked from the login page) | The route renders the `NotFoundTitle` **404 stub**, not a reset form. `test_password_reset_page_reachable` asserts the link works and the page renders 404 / \u672a\u627e\u5230 text. | K1 (link `[x]`, feature stubbed) |
| MF5 | **Join-request approve/reject inbox** | Owner's tournament /settings page (a PENDING applicants inbox with approve + \u62d2\u7edd buttons) | The join flow was changed to INSTANT join (commit d9d473c): `backend/bracket/routes/participants.py` `request_to_join` admits the user directly with "no creator approval, no rejection"; there is no `approve_join_request` / `reject_join_request` endpoint and no inbox in `settings.tsx`. Earlier COVERAGE entries M7/M17/M17b cited tests for this removed workflow that never existed in the suite. The replacement instant-join is covered end-to-end through the UI by N3. | M7 `[~]`, M17 `[~]`, M17b `[~]` |
| MF6 | **\u968f\u673a\u586b\u5206 (fill random scores) button** | Results page (`/tournaments/{id}/results`), top-right next to the title | The button is hard-gated to a single hardcoded account `test6@ai1to1.com` (`frontend/src/pages/tournaments/[id]/results.tsx:41` `RANDOM_SCORES_ACCOUNT`; `showFillRandomScores = swrUserResponse.data?.data?.email === RANDOM_SCORES_ACCOUNT`). The E2E account (`e2e@local.test`) \u2014 and any normal user \u2014 never sees the button, so it is unreachable through the UI for testing. A regression in the fill-random-scores handler would not be caught. | (no COVERAGE id \u2014 noted as a dev-only affordance) |

## Usability rough edges (not missing features, but worth noting)
- **Create-tournament club picker** (Mantine `Select`) becomes unreliable once a
  club accumulates many (~60+) tournaments — the option list is `limit={20}` and
  searchable, so `test_create_tournament` type-searches the club name to select
  it deterministically. A real user with many tournaments would hit the same
  friction.

## How to clear an entry
When a feature is implemented, replace the COVERAGE `[~]` with a real `[x]` test
that drives the new affordance end-to-end, and delete the row here.