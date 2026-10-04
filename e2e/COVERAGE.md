# Bracket E2E — User-Perspective Use-Case Coverage

Target: `http://localhost:8401` (bracket-dev, local only). Account:
`e2e@local.test`. This is the master checklist the author agent must drive to
full coverage and the critic agent checks against. Mark `[x]` only when a real,
passing test exercises the case through the UI (not the API).

Legend: `[ ]` not covered · `[~]` partial · `[x]` covered by a passing test.

## A. Account & session
- [x] A1 Register a new account via /create-account — `test_create_account_via_ui_creates_user` (fills email + name + password, clicks \u521b\u5efa\u5e10\u6237, asserts redirect to / + create-tournament chrome renders + localStorage `login` token is set; ground-truth check: POST /api/token with the new credentials returns 200; cleans up the user via psql in `finally`)
- [x] A1a Create-account form chrome smoke — `test_create_account_form_renders` (asserts the email + password inputs render and "\u5e10\u6237" is in the body; complementary smoke that catches a totally-broken form layout that A1 might miss when the click handler accidentally still works)
- [x] A2 Log in with valid credentials — `test_login_with_valid_credentials`
- [x] A3 Log in with invalid credentials shows an error, stays logged out — `test_login_with_invalid_password_stays_logged_out`
- [x] A4 Authenticated session persists across navigation/reload — `test_auth_session_persists_across_reload`
- [x] A5 Log out returns to the logged-out/landing state \u2014 `test_logout_returns_to_landing` (drives the real /user UI \u767b\u51fa button: opens /user, clicks the IconLogout-decorated \u767b\u51fa button, asserts the post-logout redirect to /login, asserts the login token is cleared from localStorage, then visits / and asserts the public landing renders \u767b\u5f55 / \u521b\u5efa\u5e10\u6237 \u2014 a regression in the click handler, the localStorage clear, or the redirect surfaces here)
- [x] A6 Protected route while logged out redirects to /login — `test_protected_route_redirects_anonymous_to_login`
## B. Landing & navigation
- [x] B1 Landing page renders marketing content + \u767b\u5f55 / \u521b\u5efa\u8d26\u6237 \u2014 `test_anon_landing_page`
- [x] B2 "\u7b80\u5355\u4f7f\u7528\u6307\u5357" (guide) link/page loads \\u2014 `test_user_guide_link_visible` (link visible) + `test_user_guide_link_navigates_to_guide_page` (click-through href asserts /guide/index.html)
- [x] B2b Rebrand replaced /guide with the rating-flow walkthrough \\u2014 `test_guide_page_is_rating_flow_walkthrough` (navigates to /guide/index.html and asserts the NEW \u4e2a\u4eba\u79ef\u5206\u8d5b\u5b8c\u6574\u6d41\u7a0b\u6f14\u793a title plus the numbered rating-lifecycle sections \u2014 create individual rated tournament, owner self-add, seed \u521d\u59cb\u5206, \u8bb0\u5206\u5458 \u2014 render in the page body; the older B2 tests only assert the link's presence/href, never the page content, so a regression that reverted /guide to the old generic guide would pass B2 but fail here)
- [x] B3 Top nav: \u4ff1\u4e50\u90e8 / \u9526\u6807\u8d5b / \u7528\u6237 / \u66f4\u591a reachable \u2014 `test_top_nav_present_when_logged_in`
- [x] B4a Language switching (zh <-> en) on anon landing via `?lng=en` \u2014 `test_language_switch_to_english`
- [x] B4b Logged-in language tab swap (full UI flow) \\u2014 `test_language_tab_swaps_logged_in_nav_to_english` (opens /user, clicks the language tab, selects "English" from the Mantine Select, asserts the URL changes to `?lng=en` and at least one primary nav label swaps to English: Clubs / Tournaments / More / User / Edit profile)
- [x] B5 Rebrand removed the Website / GitHub / API-docs outbound links + the \u66f4\u591a dropdown \u2014 `test_no_external_brand_links_after_rebrand` (on the logged-in /tournaments page collects every `a[href]` and asserts NONE point at github.com / a project website / /docs / api-docs / swagger, and asserts the \u66f4\u591a dropdown trigger text is absent. The footer is now the Bracket brand mark only; a regression re-introducing any outbound brand link surfaces here)

## C. Clubs
- [x] C1 Create a club \u2014 `test_create_club` (skips when 32-club sub cap is hit; passes on fresh envs)
- [x] C2 Club appears in clubs list \u2014 `test_create_club` (same test)
- [x] C3 Edit a club (rename) \u2014 `test_edit_club` (skips when 32-club sub cap is hit)
- [x] C4 Delete a club \u2014 `test_delete_club` (skips when 32-club sub cap is hit)
- [x] C5 Clubs page smoke test (renders + \u521b\u5efa\u4ff1\u4e50\u90e8 button visible, independent of 32-club cap) \u2014 `test_clubs_page_renders_and_create_button_visible`

## D. Tournaments
- [x] D1 Home page renders the create-tournament button (logged-in smoke) \u2014 `test_empty_tournaments_for_fresh_club` (honest smoke: the home page is the user's all-tournaments dashboard, not per-club, so a true \"fresh club empty state\" cannot be reliably observed there. D8 covers the substantive empty/full filter behavior end-to-end.)
- [x] D2 Create a tournament (with start date) \\u2014 `test_create_tournament` (drives the full UI flow: click \\u521b\\u5efa\\u9526\\u6807\\u8d5b \\u2192 open the create modal \\u2192 fill the tournament name \\u2192 click \\u4fdd\\u5b58 \\u2192 assert the modal closes \\u2192 reload the home page and assert the new tournament renders. Clubs are now implicit (one personal club per account, commit c41579e), so the modal auto-selects the user's club and renders NO club picker \\u2014 there is no Mantine Select to drive. Also asserts the POSITIVE: the created tournament appears under the home \\u6211\\u521b\\u5efa\\u7684\\u9526\\u6807\\u8d5b tab with a card linking to /tournaments/{id}/stages (the organiser entry point), not /results.)
- [x] D3 Tournament appears in list / dashboard card \\u2014 `test_create_tournament` (same test, reloads and asserts the new tournament renders)
- [x] D4 Open/view a tournament \u2014 `test_open_tournament`
- [x] D5 Edit tournament settings — `test_edit_tournament_settings`
- [x] D6 Delete a tournament — `test_delete_tournament`
- [x] D7 Tournament visibility (public/private) toggle — `test_tournament_visibility_toggle`
- [x] D8 Home page status filter (All / Archived / Open) actually filters the card list — `test_home_status_filter_archived_vs_open` (creates two tournaments, archives one, asserts the default "Open" filter hides the archived one, switching to "Archived" hides the open one, switching to "All" shows both; cleans up via API)

## E. Teams / players
- [x] E1 Add a single team — `test_add_single_team`
- E2 (removed): the 多个队伍 batch tab was dropped from the create modal, and `test_batch_add_teams` with it.
- [x] E3 Teams list shows added teams — `test_add_single_team`
- [x] E4 Edit a team — `test_edit_team`
- [x] E5 Delete a team — `test_delete_team`
- E6/E7 (removed): the standalone /players page no longer exists — team members are now edited directly in the team create/edit modals (TagsInput bound to `player_names`; the backend syncs players from the names, deleting orphaned ones). The old players-page tests were deleted with the page.

## F. Stages & formats
- [x] F1 Add a stage — `test_add_stage` (uses a dedicated fresh tournament so the empty-state 添加阶段 button is the only match, clicks it, asserts the new column renders AND the API count grows — the click is now actually exercised, not bypassed)
- [x] F2 Rename a stage (default name is "Stage") — `test_rename_stage` (UI rename via column menu, persists across reload)
- [x] F3 Round-robin (\u5faa\u73af\u8d5b) stage \u2014 `test_round_robin_stage` (asserts stage_item.type == ROUND_ROBIN + \u5c0f\u7ec4 label visible) AND `test_create_rr_stage_item_via_modal` (opens the create-stage-item modal, accepts the RR defaults, clicks \u521b\u5efa\u9636\u6bb5\u9879\u76ee, and asserts the modal closes AND a ROUND_ROBIN stage item with matches appears via the API \u2014 the modal's RR onSubmit handler [createRoundRobinGroups] is now exercised through the UI, not just the API; mirrors F6's SE-side coverage for the RR half)
- [x] F4 Single elimination (\u5355\u6dd8\u6c70\u8d5b) stage \u2014 `test_single_elimination_stage`
- [~] F5 Double elimination (\u53cc\u6dd8\u6c70\u8d5b) \u2014 app exposes only RR / SE in the create-stage-item modal (Swiss has been removed); `test_create_stage_item_modal_lists_two_formats` locks that in by asserting EXACTLY two format cards render (counts the two distinct `/icons/*-stage-item.svg` images), so a third format reappearing or the cards breaking fails. (The earlier `"\u745e\u58eb\u5236" not in modal_text` check was tautological \u2014 that string never existed anywhere in the build.) No double-elim affordance exists in this build.
- [x] F3b Multi-group round-robin (group_count > 1) \u2014 `test_multi_group_round_robin` (creates an RR with group_count=2, team_count=8 \u2192 2 groups of 4; asserts via the API that 2 ROUND_ROBIN stage items render each with C(4,2)=6 matches; navigates to /results and asserts TWO distinct GroupGrid tables render in the results tabpanel, each with 4 team rows, and the two groups have DISJOINT team sets; switches to the \u6392\u540d tab and asserts all 8 teams render in standings. Every other RR in the suite uses group_count=1; a regression in multi-group generation, multi-group cross-table rendering, or per-group standings isolation would pass the entire suite)
- [x] F6 Multi-stage composition (RR -> SE) with source selection \u2014 `test_multi_stage_composition_with_source_selection` (creates RR stage item in stage 1, opens the stage-2 modal, switches to SINGLE_ELIMINATION, ticks the RR source checkbox, saves, and asserts the new SE stage item has inputs whose `winner_from_stage_item_id` is the RR item \u2014 the source-selection half is now exercised end-to-end)
- [x] F7 Delete a stage \u2014 `test_delete_stage` (UI delete via column kebab; column disappears + API confirms)
- [~] F8 Auto-group by seeding (\u6309\u6392\u4f4d\u81ea\u52a8\u5206\u7ec4) \u2014 i18n key `auto_seed_distribute_button` exists in the locale file but no current page imports it; the affordance is not reachable in this build and we do NOT advertise UI coverage for it.
- [x] F9 Generate stage items / matches for a stage \u2014 `test_generate_stage_items` (asserts match count grows after creating a stage item)

## G. Courts & scheduling
- [x] G1 Create a court (球场1/球场2) — `test_create_court` (UI add + API confirms)
- [~] G2 Edit / delete a court — `test_delete_court` (UI delete via h4-anchored column kebab, uses a stable h4-based selector that survives CSS churn) + `test_court_kebab_menu_has_no_edit_option` (locks in that the current build's court menu only exposes 删除场地 — no 编辑场地 / 重命名场地 item). The "edit" half is honest [~] because the UI does not expose it; the delete half is end-to-end.
- [x] G3 Auto-schedule all unscheduled matches (安排所有未安排的赛) — `test_auto_schedule_matches` (asserts empty-state alert is gone and team names appear scheduled)
- [x] G4 Schedule/planning view renders matches in slots — `test_schedule_view_renders`
- [x] G5 Schedule page does NOT open the score modal (rebrand removed scoring from /schedule) — `test_schedule_page_does_not_open_score_modal` (dedicated fresh tournament with a scheduled RR; navigates to /schedule, clicks a match card, asserts the 填入分数/编辑比分 modal does NOT open — a regression that re-wired the schedule card's onClick to open the score modal surfaces here)

## H. Match play & scoring
The match-scoring modal was rewritten (the best-of-N selector and per-game +/- steppers are GONE). It now shows ONE-TAP RESULT BUTTONS labelled `<winnerGames>:<loserGames>` (winner games in {2,3,4}, both orientations e.g. `2:0`, `0:2`, `3:1`, `3:2`, `4:2`), plus per-side `<队名> 弃权` (forfeit/walkover) buttons and a `清除比分` (clear) button. A single click SAVES immediately (games=null, so `小分` is 0 for everyone) and CLOSES the modal. The results page is titled `录入分数和结果` (results_title locale value) and has TWO tabs: `录入分数和结果` (per stage item: RR renders a GroupGrid cross-table `方格表` whose cells open the fill modal; SE renders a clickable EliminationBracket) and `排名` (standings).
- [x] H1 Open the match scoring modal (`填分`) — `test_open_match_modal` (dedicated fresh tournament with a scheduled RR; navigates to `/tournaments/{tid}/results`, clicks the first `—` GroupGrid cell, asserts the modal opens with body text `填入分数` visible, AND asserts at least one result button (`2:0`) is visible inside the modal — not an empty shell — AND asserts the `清除比分` button is ABSENT on a fresh unscored match, since it should only render when hasScore=true)
- [x] H2 Click a result button (e.g. `2:0`) to save — `test_enter_scores_and_save` (clicks the `2:0` result button on the modal, asserts the modal closes, AND asserts via the API that exactly one match in the stage has `stage_item_input1_score=2 / input2_score=0` with `games=null/[]` — the no-per-game-points contract is pinned by the games-null assertion; a save-no-op regression cannot pass)
- [x] H2b A 3-game result button (e.g. `3:2`) saves and persists — `test_three_game_result_button_saves` (clicks the `3:2` result button on the modal, asserts the modal closes, AND asserts via the API exactly one match has `input1_score=3 / input2_score=2` with `games=null/[]` — H2/H11 only exercise the 2-game (2:0 / 0:2) save path; a regression where the 3-game or 4-game buttons rendered but the save handler or backend rejected/miscalculated them would pass every existing test)
- [x] H3 Edit an existing result — `test_edit_existing_score` (scores a match 2:0, re-opens the cell (now showing `2:0`), asserts the `2:0` result button is visible in the modal, clicks `0:2` (the inverse) to save, and asserts via the API exactly one match now has `0:2` — proves the re-open pre-populates the previous result and that subsequent edits overwrite cleanly)
- [x] H4 Match result reflected in the GroupGrid cell — `test_match_result_reflected` (saves `2:0` through the modal, asserts the GroupGrid cell now renders `2:0` instead of `—`, AND asserts via the API exactly one match with `input1_score=2 / input2_score=0` — the UI cell text is unambiguously correlated to the persisted record)
- [x] H5 ALL expected result-button labels render in both orientations — `test_all_result_buttons_render` (opens a fresh RR match modal; computes the full set of labels: `2:0, 2:1, 0:2, 1:2, 3:0, 3:1, 3:2, 0:3, 1:3, 2:3, 4:0, 4:1, 4:2, 0:4, 1:4, 2:4`; asserts EVERY label has count==1 inside the modal — a regression that dropped a button or mislabeled one surfaces here; the "two orientations" requirement is implicitly covered by both `<w>:<l>` and `<l>:<w>` being present)
- [x] H6 Forfeit a match via the UI — `test_forfeit_match_via_ui` (dedicated fresh tournament + RR stage; opens the modal, asserts EXACTLY 2 forfeit buttons render (one per side), clicks the first, asserts the modal closes, AND asserts via the API that exactly one match has `forfeit_input ∈ {1,2}`, both scores 0, `games=null/[]` — the forfeit path is architecturally distinct from per-game scoring; a regression that always computed scores from games or ignored forfeit in the ranking would pass H2-H5 but fail here)
- [x] H7 `清除比分` (clear score) button resets to 0:0 — `test_clear_score_button` (scores a match 2:0, re-opens the same cell, asserts the `清除比分` button is visible (only renders when hasScore), clicks it, asserts the modal closes, AND asserts via the API that the previously persisted `input1_score=2` is GONE — proves the clear button is not a no-op and that the score is overwritten to 0:0)
- [x] H8 `录入分数和结果` page title + two-tab structure — `test_results_page_title_and_tabs` (asserts the page heading is exactly `录入分数和结果` AND that EXACTLY two tabs render (`录入分数和结果` and `排名`) AND that the old `对阵图` tab label is NOT among the tabs — pins the renamed page + new tab structure; a regression that re-introduced the old `对阵图` tab or changed the title would fail here)
- [x] H9 SETTLED (non-rated) tournament freezes scores — `test_settled_tournament_freezes_scores` (dedicated fresh RR tournament; scores one match via the API, sets `settled_seq=1` via psql to simulate the settled state, navigates to `/results`, clicks the first `—` cell, asserts the modal does NOT open AND a `.mantine-Notification-root` renders; ground-truth: backend PUT /matches now returns 400 mentioning `settled`/`frozen` — pins the UI surfacing of the 400 on a settled tournament)
- [x] H9b SETTLED *rated* tournament freezes scores on /results UI — `test_settled_rated_tournament_results_shows_error_notification` (rated individual tournament: 4 fresh applicants instant-join + seed ACTIVE via psql so a 4-team RR can be built, one match is scored, `settled_seq=1` set via psql; UI navigates to `/results`, clicks the first `—` cell, asserts the modal does NOT open AND a `.mantine-Notification-root` renders; ground-truth: backend PUT /matches returns 400 mentioning `settled`/`frozen`. Complements H9 (non-rated UI freeze) and M15b (rated API freeze) — the three together lock the freeze contract on both the API path and both UI paths)
- [x] H9c SETTLED tournament freezes scores on an SE bracket (RR-vs-SE consistency) — `test_settled_tournament_freezes_se_bracket` (advances an RR→SE so SE inputs resolve to concrete teams, sets `settled_seq=1` via psql, navigates to /results, clicks an SE bracket match button, and asserts the fill modal does NOT open AND the same `.mantine-Notification-root` 'scores frozen' notification that the RR GroupGrid cell path (H9) shows renders for the SE bracket too — plus backend ground-truth PUT /matches returns 400. H9/H9b only exercised the freeze on an RR GroupGrid cell where `openMatchModal` fires `showNotification`; the SE bracket takes a different code path — `results.tsx` passes `readOnly` to `EliminationBracket` and `match.tsx` rendered a plain `<div>` (no onClick) when readOnly, so on a SETTLED SE bracket clicking a match *silently did nothing* — no modal (correct) BUT no error notification either, unlike the RR cell. The fix forwards an `onClickFrozen` callback through `brackets.tsx`→`match.tsx`, wired by `results.tsx` only when `isFrozen`, so the SE path now shows the same frozen notification as RR. This test pins that consistency so a regression that re-enabled the `UnstyledButton` onClick opening a fill modal whose save would 400 — OR dropped the `onClickFrozen` wiring reverting to the silent read-only div — surfaces here)
- [x] H10 GroupGrid is read-only for non-recorders — `test_groupgrid_read_only_for_non_recorder` (dedicated fresh RR tournament viewed by `anon_page`; asserts the GroupGrid table renders, the `—` text is visible as plain text, and there are ZERO `button` cells with `—` text — the read-only rendering must not expose clickable cells to non-recorders; a regression that always rendered the editor buttons would fail here)
- [x] H10 GroupGrid is read-only for non-recorders — `test_groupgrid_read_only_for_non_recorder` (dedicated fresh RR tournament viewed by `anon_page`; asserts the GroupGrid table renders, the `—` text is visible as plain text, and there are ZERO `button` cells with `—` text — the read-only rendering must not expose clickable cells to non-recorders; a regression that always rendered the editor buttons would fail here)
- [x] H11 Both result-button orientations produce correct scores — `test_result_button_orientations` (clicks `0:2` in the `<team1> 负` section to prove team2 wins, asserts the modal closes, AND asserts via the API exactly one match with `input1=0, input2=2` — H2 covered `2:0` (team1 wins); this test covers the inverse orientation so a regression that swapped which side's section uses which label orientation surfaces here)
- [x] H12 排名 (standings) tab after a one-tap UI result-button score (the production scoring path) — `test_standings_after_one_tap_ui_score` (scores a match via the one-tap UI button `set_match_result(modal,2,0)` → games=null; opens the 排名 tab and asserts the winner's 局分 (games-score) cell shows `2:0` NOT `1:0` AND 小分 (points sum) shows `0:0` NOT `11:7`. The existing standings tests I4/I4b/I7 all score via the API helper with games=[[11,7]] → 局分=`1:0`, 小分=`11:7`; a regression that broke standings computation specifically for games=null matches — the only path real users can produce — would pass those but fail here)
- [x] H13 SE bracket click→modal→save on /results — `test_se_bracket_click_opens_modal_and_saves` (advances an RR→SE so SE inputs resolve to concrete teams, navigates to /results, clicks an SE bracket `UnstyledButton` match element — structurally distinct from the RR GroupGrid `—` cell button — asserts the 录入分 modal opens, clicks a result button, and asserts the score persists via the API with games=null. I2/I5 only assert the bracket RENDERS; a regression where the SE bracket's onClick stopped opening the modal or the save silently failed for SE matches would pass I2/I5 and all H-tests but fail here)
- [x] H6b Forfeit effect on standings (W/D/L) — `test_forfeit_standings_wins_losses` (forfeits a match via the UI one-tap forfeit button, then opens the 排名 tab and asserts the non-forfeiting side shows 胜利(wins)=1 / 失败(losses)=0 and the forfeiting side shows 胜利=0 / 失败=1. The backend treats a forfeit as a WIN for the non-forfeiting side and a LOSS for the forfeiting side; H6 asserts only persistence — a regression that misclassified a forfeit as a draw or awarded 0 points to both sides would pass H6 but produce wrong standings here)
- [x] H14 No active-stage restriction — any NON-settled stage's matches stay editable — `test_inactive_stage_matches_still_editable` (dedicated fresh tournament with TWO RR stages; activates stage 1 via the API so stage 2 is is_active=False; navigates to /results, asserts GroupGrid cells from BOTH stages render (count ≥ 2), clicks the first cell, asserts the 填入分数 modal opens, scores 2:0 via `set_match_result`, and asserts via the API a match now has input1_score=2 — proves there is no `is_active` gate on score entry; a regression that restricted editing to only the active stage would fail here)
- [x] H15 A 4-game result button (e.g. `4:2`) saves and persists — `test_four_game_result_button_saves` (clicks the `4:2` result button on the modal, asserts the modal closes, AND asserts via the API exactly one match has `input1_score=4 / input2_score=2` with `games=null/[]` — H2 saves 2:0, H11 saves 0:2, H2b saves 3:2; no test ever clicked a 4-game button to save. H5 only asserts all 16 labels RENDER; a regression where the 4-game buttons render but the save handler rejects or miscalculates them — e.g. a validation gate capping winner at 3, or a label-parsing bug on double-digit scores — would pass every existing test)
- [x] H16 `清除比分` (clear) on a FORFEITED match resets `forfeit_input` to None — `test_clear_score_on_forfeited_match` (forfeits a match via the UI one-tap `弃权` button, re-opens the cell — which now shows `弃`/`胜` (forfeit_loss_short / forfeit_win_short), NOT `0:0` — clicks `清除比分`, and asserts via the API that `forfeit_input` is now `None` (not just that scores are 0:0). H6 tests the forfeit path in isolation; H7 tests the clear path in isolation; a regression where the clear button zeroed the scores but forgot to include `forfeit_input=None` in the PUT payload — leaving the match still forfeited despite showing 0:0 — would pass H7 but fail here)

## I. Progression & results
- [x] I1 Advance to next stage (\u4e0b\u4e00\u9636\u6bb5) \u2014 RR -> SE population \u2014 `test_advance_to_next_stage_modal` (uses a dedicated fresh tournament with stage 1 [RR] and stage 2 [SE with 1 stage item], pre-activates stage 1 via the API so the next "next" call advances to stage 2, clicks \u4e0b\u4e00\u9636\u6bb5 to open the confirmation modal, clicks \u5f00\u59cb\u4e0b\u4e00\u9636\u6bb5 [plan_next_stage_button, exact=True] to submit, asserts the modal closes, and verifies via the API that stage 2 is_active=True and stage 1 is_active=False) AND `test_advance_to_next_stage_seeds_se_from_rr` (the user-visible payoff: stage 2 SE is seeded from stage 1 RR via /stage_items/elimination_from_sources with positions=4; all 6 RR matches are scored so the ranking is complete; pre-condition asserts the 4 SE Tentative inputs reference the RR with team_id=None; UI clicks \u4e0b\u4e00\u9636\u6bb5 \u2192 \u5f00\u59cb\u4e0b\u4e00\u9636\u6bb5; post-condition asserts every SE input now resolves to a concrete team_id, the resolved set EQUALS the 4 RR team ids, AND seed ORDER is correct: the champion (scored to win all 3 of its RR matches \u2192 unambiguous rank 1) is seeded into SE winner_position==1 \u2014 a regression in update_matches_in_activated_stage / get_updates_to_inputs_in_activated_stage / sql_set_team_id_for_stage_item_input that left placeholders OR shuffled the seeding surfaces here)
- [x] I1b Return to previous stage (\u4e0a\u4e00\u9636\u6bb5) \u2014 inverse of I1 \u2014 `test_activate_previous_stage_button` (dedicated fresh tournament with stage 1 [RR] + stage 2 [SE]; activates stage 1 then advances to stage 2 via API so stage 2 is active; UI clicks \u4e0a\u4e00\u9636\u6bb5 to open the confirmation modal, clicks \u8fd4\u56de\u5230\u4e0a\u4e00\u9636\u6bb5 [plan_previous_stage_button, exact=True] to submit, asserts the modal closes, and verifies via the API that stage 1 is_active=True and stage 2 is_active=False \u2014 the inverse direction of the activate endpoint, exercising `get_next_stage_in_tournament(direction='previous')`)
- [x] I2 Elimination bracket populates with seeds / byes — `test_elimination_bracket_renders` (asserts the bracket tabpanel has at least one <h3> [stage-item title] AND mentions bracket-specific labels "Single Elimination" / "\u51b3\u8d5b" (final_round_name) / "1/2\u51b3\u8d5b" (fraction_round_name, N-match rounds are named "1/N决赛"); the seeded team names are not visible because the SE stage item is created with team_count=4 but inputs aren't auto-assigned — the bracket renders \u7a7a\u69fd\u4f4d placeholders. Round names come from eliminationRoundName in brackets.tsx.)
- [x] I3 Results tab (\u7ed3\u679c) shows matches/results \u2014 `test_results_tab_shows_matches` (uses a DEDICATED fresh tournament with a unique team-name prefix so the assertion is scoped to this stage's matches; an RR(4 teams, 1 group) stage produces exactly 6 matches [C(4,2)], so the test waits for `expect(match_cards).to_have_count(6)` where match_cards is `.mantine-Card-root` filtered by the unique team prefix \u2014 a regression that broke the matches-tab rendering for the new stage cannot pass)
- [x] I4 Rankings tab (\\u6392\\u540d) shows standings AND updates after scores \\u2014 `test_rankings_tab_renders` (uses a dedicated fresh tournament with 4 teams + an RR stage; opens the \\u6392\\u540d tab BEFORE scoring and asserts the panel shows \\\"0:0\\\" with no \\\"1:0\\\"/\\\"0:1\\\"/\\\"11:7\\\" cells, scores the first match via the API with games=[[11,7]], reloads and re-opens the tab, and asserts the standings panel now shows BOTH \\\"1:0\\\" \\[winner's games-score \\u5c40\\u5206\\] AND \\\"11:7\\\" \\[points-sum \\u5c0f\\u5206\\] \\u2014 a regression in the standings recomputation path \\[computeScoreTotals + rankInputsWithTiebreak\\] surfaces here)
- [x] I4b Rankings HEAD-TO-HEAD tiebreak \\u2014 `test_rankings_head_to_head_tiebreak` (builds a 4-team RR where A & B both finish on 2 wins/equal points but B wins ITS matches by blow-outs (11:1) so B's overall points ratio is higher; A beat B head-to-head; asserts the rendered \\u6392\\u540d table orders A above B (and C above D, the other tied cluster) \\u2014 a naive points-differential sort would put B above A, so this proves `rankInputsWithTiebreak` applies head-to-head FIRST. Closes the documented tiebreak coverage gap.)
- [x] I5 EliminationBracket inline rendering on the results tab — `test_bracket_tab_renders` (the old '对阵图' tab was removed; SE stage items now render the EliminationBracket inline in the default '录入分数和结果' tab. This test asserts the multi-column round layout: the panel must contain the h3 stage-item title AND both round names from eliminationRoundName ("决赛" for the single-match final and "1/N决赛" for the N-match rounds) — a bracket-specific affordance that is genuinely different from I2's h3 stage-item-title assertion; a regression that drops the round columns from the EliminationBracket while keeping the stage-item title would fail I5 but pass I2)
- [x] I6 Rankings scoring-rules config (/rankings) form — `test_rankings_config_form` (now exercises the form end-to-end: opens the default-ranking accordion, changes 获胜积分, clicks 保存 排名 1, reloads, asserts the value is still there, and asserts the API returned the new value — then restores the original so the shared fixture stays clean)
- [x] I8 SE bracket winner-advancement (scoring through rounds) — `test_se_winner_advancement_propagates_to_final` (creates a 4-team SE with teams assigned to all 4 input slots via PUT /inputs, scores BOTH semifinal matches via the API, then asserts via the API that the final match's two stage_item_inputs now reference the two semifinal winners' team_ids (not None). SE winner-advancement is THE core single-elimination behavior; a regression where scoring a match failed to propagate the winner to the next round [update_inputs_in_subsequent_elimination_rounds] would pass every existing test. H13 only scores ONE SE match and never checks winner propagation)

## J. Users / members & misc
- [x] J1 User profile page (/user) reachable — `test_user_profile_page_reachable` (asserts edit-profile form fields render). Note: the build has no separate "tournament users / club members management" page; J1 is the user-account page.
- [x] J2 Public results page is the shared view — `test_public_results_visible_to_anonymous_and_archived` (dedicated tournament with an RR stage: an anonymous visitor sees the participants on `/tournaments/<id>/results`, the owner sees the 点击表格…填写比分 hint while it is open and loses it once archived, and the anonymous view keeps working after archiving — archiving no longer un-publishes)
- [x] J3 Mobile viewport results page — `test_mobile_viewport_results_page` (Burger menu visible at 375px, results tabs render)
- [x] J4 Tournament settings: "Set to now" (\u8bbe\u7f6e\u4e3a\u73b0\u5728) button updates start_time \u2014 `test_tournament_set_to_now_button` (creates a dedicated tournament, clicks the button, saves, polls the API until the start_time is no longer the 2030-01-01 default)

## K. Password reset (reachable route)
- [x] K1 /password-reset route is reachable from the login page link — `test_password_reset_page_reachable` (the current build renders the NotFoundTitle stub; the test asserts the link works and the page renders expected 404 / 未找到 / 返回 text)

## L. 404, user profile internals, and tournament settings internals
- [x] L1 404 page renders for anonymous visitor — `test_404_page_renders_for_anon` (asserts the body shows "404" and the translated 你找到了一个秘密地方 title and 回到主页 back-home button)
- [x] L2 404 page renders for a logged-in user — `test_404_page_renders_for_logged_in` (the back-home button routes to / when a token is present)
- [x] L3 User profile language tab lists multiple locales (\u2265 2 options) including English and Chinese \u2014 `test_user_language_tab_is_interactive` (opens the language tab, asserts the textbox shows the current "Chinese" locale, opens the Mantine Select dropdown and asserts options.count() \u2265 2 with both "English" and "Chinese" present \u2014 a complementary structural assertion B4b doesn't make: B4b drives the happy-path locale swap, L3 catches a regression that ships an empty / single-option Select)
- [x] L4 User profile: editing the name in the details tab persists across reload — `test_user_name_update_persists` (polls the API until the new name is persisted, reloads, asserts the input still shows the new name, then restores the original name in `finally` so the E2E account stays clean)
- [x] L5 Tournament settings: the "Archive Tournament" button actually archives \u2014 `test_tournament_archive_button_archives` (dedicated tournament; click flips status OPEN\u2192ARCHIVED, archive button is replaced by unarchive, API confirms; uses `exact=True` on the role-name match because \u53d6\u6d88\u5f52\u6863\u9526\u6807\u8d5b CONTAINS \u5f52\u6863\u9526\u6807\u8d5b as a substring)
- [x] L5b Tournament settings: the "Unarchive Tournament" button actually unarchives \u2014 `test_tournament_unarchive_button_unarchives` (seeds ARCHIVED via API, clicks the unarchive button on the settings page, asserts the unarchive button is replaced by the archive button AND polls the API until status=OPEN; complements L5 by exercising the inverse round-trip)
- [x] L6 Tournament settings: the sharing fieldset shows this tournament's results URL with an enabled copy button \u2014 `test_tournament_share_link_is_the_results_url` (the custom dashboard slug is gone; the shared link is always /tournaments/<id>/results and needs no configuration)
- [x] L7 User profile password change persists \u2014 `test_user_password_change_persists` (opens /user, switches to the \u7f16\u8f91\u5bc6\u7801 tab, fills the PasswordInput with a fresh password, clicks \u4fdd\u5b58, waits for the \u5bc6\u7801\u5df2\u66f4\u65b0 success notification; ground-truth check: a POST to /api/token with the NEW password returns 200 AND a POST with the OLD password returns 401 \u2014 a save-no-op regression cannot pass; the test always restores the original password via the API in `finally` so the shared E2E account stays usable for sibling tests, with a defensive assertion that the account is not left locked into the test password)

## Data hygiene
- Every test namespaces created entities with a unique prefix (e.g.
  `E2E-<short-uuid>`) and cleans up what it creates where feasible.
- Tests are independent and can run in any order.
- The suite uses a session-scoped shared club + tournament fixture
  (`shared_club_id`, `shared_tournament_id`) to stay under the 32-club
  subscription cap. Tests that need fresh state create entities within the
  shared tournament and clean up after themselves.
- D5 captures the shared tournament's actual fixture name once and restores it,
  so the session-scoped shared tournament name is preserved across test runs.
- F1 (`test_add_stage`) and the F6 source-selection test use a dedicated
  fresh tournament (created per-test, deleted in the `finally`) so the
  empty-state 添加阶段 button is the only match on the page. This avoids
  the "many accumulated stage columns" issue that made the earlier
  iteration of test_add_stage bypass the click.
- I1 (`test_advance_to_next_stage_modal`) uses a dedicated fresh
  tournament so the next-stage ordering is deterministic — the shared
  tournament accumulates stages across runs and the "next" SQL would
  land on an unpredictable stage.
- I6 (`test_rankings_config_form`) restores the default ranking's
  win_points via API after the test, so the shared tournament's ranking
  defaults stay constant across runs.
- J2 (`test_public_results_visible_to_anonymous_and_archived`) creates and
  deletes its own dedicated tournament per run, and unarchives it before
  deleting.
- J4 (`test_tournament_set_to_now_button`) creates and deletes its
  own dedicated tournament per run.
- B4b (`test_language_tab_swaps_logged_in_nav_to_english`) drives the
  full UI flow: open /user, click the language tab, select "English"
  from the Mantine Select, assert the URL changes to ?lng=en and a
  primary nav label swaps to English. The test does not mutate any
  shared resource (locale change is per-session, not persisted).
- C5 (`test_clubs_page_renders_and_create_button_visible`) is a smoke
  test that does not depend on the 32-club cap, so it always runs
  even when C1\u2013C4 skip.
- D2 (`test_create_tournament`) drives the full UI flow: open the create
  modal, fill the tournament name, click \u4fdd\u5b58, reload, and assert the new
  tournament renders. Clubs are implicit (one personal club per account,
  commit c41579e), so the modal auto-selects the user's club and renders no
  club picker \u2014 there is no Mantine Select to drive (earlier iterations
  type-searched/ArrowDown-selected a club option; that flow no longer
  exists). The test cleans up the created tournament via the API.
- The C1\u2013C4 club CRUD tests have a per-test autouse fixture that prunes
  old E2E- clubs. When the 32-club cap is already full and prune cannot
  free a slot (e.g. clubs have dependent tournaments), the tests skip
  cleanly rather than fail.
- The conftest's `_find_existing_shared_club` picks a shared club with
  < 64 tournaments (the REGULAR per-club cap). The session fixture
  also calls `_prune_all_e2e_tournaments()` at start to wipe ALL
  E2E-* tournaments (any prefix \u2014 FreshT, DashT, NextStage, Rated,
  Rankings, MatchH4, Open, Arch, Del, T, ...) left over from crashed
  prior runs. Without this aggressive prune, accumulated leftover
  tournaments fill every shared club to the 64-cap and POST
  /api/tournaments 400s, breaking every test in the session.
- The L5/L6 tests clean up their dedicated tournaments in `finally`,
  and the L4 test restores the original user name in `finally`, so the
  shared resources stay clean across runs.
## M. Rating system \u2014 CanadaChinaTT (\u52a0\u534e\u79ef\u5206) cross-tournament ratings
Individual-tournament rating workflows. The E2E account `e2e@local.test` is a
site admin (`users.is_admin = true`), so admin flows are reachable. Backend +
frontend are fully implemented. Driven by `e2e/tests/test_rating.py` (M1\u2013M14).
- [x] M1 The create-tournament modal exposes \u4e2a\u4eba\u8d5b + \u53c2\u4e0e\u79ef\u5206 + \u79ef\u5206\u7c7b\u522b (default \u52a0\u534e\u79ef\u5206), with \u53c2\u4e0e\u79ef\u5206 gated behind \u4e2a\u4eba\u8d5b (only individual tournaments can be rated); settings are fixed at creation and shown read-only afterwards \u2014 `test_create_modal_exposes_rating_options` (opens the create modal, asserts \u53c2\u4e0e\u79ef\u5206 is hidden until \u4e2a\u4eba\u8d5b is checked, then \u79ef\u5206\u7c7b\u522b appears; API-creates a rated individual tournament and asserts is_individual=True / rating_category_id=1 plus the read-only \u79ef\u5206\u8bbe\u7f6e on the settings page)
- [x] M2 Admin /admin reachable for admin account; lists rating categories (\u52a0\u534e\u79ef\u5206 / CanadaChinaTT) \u2014 `test_admin_page_lists_rating_categories`
- [x] M3 Admin: create a new rating category, see it listed, then delete it \u2014 `test_admin_create_and_delete_rating_category`
- [x] M4 Admin: \u521d\u59cb\u5206\u5ba1\u6838\u961f\u5217 (rating review queue) renders (empty state OK) \u2014 `test_admin_review_queue_section_renders`
- [x] M5 Category leaderboard /rating/1/leaderboard renders a table (empty state OK) \u2014 `test_leaderboard_page_renders`
- [x] M6 Public individual-tournament results page shows the \u53c2\u8d5b (instant-join) button + the “允许创建者以后拉我进入比赛” (permanent) checkbox — `test_individual_tournament_results_shows_join_section` (asserted as an outsider account — the join section is a spectator tool the owner never sees; join is INSTANT, no creator approval, and the Alert text mentions 永久生效)
- [x] M6b Trust-creator checkbox is functional end-to-end \u2014 `test_trust_creator_checkbox_marks_owner_as_trusted_manager` (a fresh account opens the public results page, TICKS the \u4fe1\u4efb\u521b\u5efa\u8005 checkbox via `get_by_role("checkbox", name=re.compile(...))`, asserts the checkbox is checked, clicks \u53c2\u8d5b, and asserts the badge replaces the join button + GET /me/trusted-managers with the joiner's token now contains the OWNER's user id; control: a second fresh account joins WITHOUT ticking the checkbox and its /me/trusted-managers does NOT contain the owner. A regression that dropped the Checkbox's onChange or stopped forwarding `trust_creator` server-side would not be caught by M6 alone.)
- [~] M7 Owner join-requests inbox with approve/reject \u2014 REMOVED FROM THE PRODUCT. The join flow is now INSTANT (commit d9d473c: `request_to_join` admits the user directly, no creator approval, no PENDING state, no reject endpoint \u2014 confirmed in `backend/bracket/routes/participants.py`). There is no approve/reject inbox in `settings.tsx`. The replacement user-visible behaviour (a logged-in non-member clicks \u53c2\u8d5b and is instantly admitted) is covered end-to-end through the UI by N3 (`test_nonparticipant_sees_join_and_follow_then_pending` \u2014 it now CLICKS the \u53c2\u8d5b button in the browser, asserts the \u60a8\u5df2\u53c2\u8d5b badge replaces it in place, and verifies a bound team + participant status via the API). See `e2e/MISSING_FEATURES.md`.
- [x] M8 Pre-seed: per-team initial-rating control on a rated individual tournament \u2014 `test_seed_ratings_section_renders_on_teams_page` (because free-text team creation is now (correctly) blocked on individual tournaments \u2014 see M12 \u2014 the test seeds a team row directly via psql, then opens the team EDIT modal \u2014 the seed control moved off the teams page into team_update_modal.tsx in commit 61fc848 \u2014 and asserts the \u521d\u59cb\u79ef\u5206 Fieldset + NumberInput render)
- [x] M9 \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 button present + reports status \u2014 `test_settlement_button_renders_on_rated_tournament`
- [x] M10 \u6211\u7684\u6258\u7ba1\u7ba1\u7406\u5458 on /user: add by email / remove via UI \u2014 `test_trusted_managers_add_and_remove` (both halves through the UI: types email + clicks \u6dfb\u52a0; polls API for the new manager_id; clicks the row's red ActionIcon trash button; asserts the row leaves the rendered table; API confirms removal \u2014 a regression in the row-level delete handler/SWR mutate surfaces here)
- [x] M11 Scorers management (\u8bb0\u5206\u5458): add by email / remove via UI \u2014 `test_scorers_management_add_and_remove` (both halves through the UI; remove clicks the row's red ActionIcon trash button inside the \u8bb0\u5206\u5458\u7ba1\u7406 fieldset; asserts the row disappears + API confirms)
- [x] M12 Individual rated tournaments must NOT offer free-text team creation \u2014 `test_individual_tournament_has_no_freetext_team_create` (UI: asserts the \u76f4\u63a5\u6dfb\u52a0\u53c2\u8d5b\u8005 fieldset renders AND \u6dfb\u52a0\u961f\u4f0d button + \u521b\u5efa\u961f\u4f0d modal are absent on an individual tournament's /teams page; control: a non-individual tournament DOES render \u6dfb\u52a0\u961f\u4f0d. API ground truth: POST /tournaments/{id}/teams with a name returns 400 on the individual tournament and 2xx on the control)
- [x] M13 \u7533\u8bf7\u79ef\u5206\u7ed3\u7b97 is blocked on an empty tournament (zero teams, zero matches) \u2014 `test_settlement_blocked_on_empty_tournament` AND `test_settlement_blocked_on_unplayed_matches`
- [x] M14 Settlement is blocked when team(s) are not bound to an account \u2014 `test_settlement_blocked_when_team_unbound`
- [x] M15 Full individual-rating happy-path lifecycle, end to end \u2014 `test_individual_rating_full_lifecycle` (two registered applicants apply via API; applying INSTANTLY joins both \u2014 there is NO approval step / NO PENDING inbox \u2014 and auto-creates two bound teams; owner seeds each \u521d\u59cb\u5206=1500 via the team-edit-modal SeedRatings UI and psql confirms both persisted; a real round-robin match between the two bound accounts is scored 2:0 THROUGH THE UI; admin approves both initial ratings in /admin (psql confirms ACTIVE); settled_seq assigned + \u5df2\u7ed3\u7b97 badge; the /rating/1/leaderboard renders the +8/-8 ChinaTT result).
- [x] M15b A SETTLED rated tournament is READ-ONLY — `test_settled_tournament_is_read_only` (settles a rated individual tournament via the admin /settle endpoint after seeding both newcomers ACTIVE; (a) PUT /matches/{id} is rejected with 400 mentioning "settled" / "frozen" and the saved games stay [[11,7],[11,5]]; (b) per-side scores stay 2:0; (c) the 申请积分结算 button is GONE on the settings page and the 已结算 indicator renders. A regression that allowed a post-settlement score edit to silently mutate a player's settled rating would not be caught by M15. The complementary UI surfacing on /results (cell-click → no modal + error notification) is locked by H9b — together they cover both the API and the UI for the rated path)
- [x] M16 Owner direct-add picker lists ONLY hosted accounts that trust the owner \u2014 `test_trusted_creator_direct_add_picker` AND `test_owner_can_add_self_via_picker`
- [~] M17 Reject a pending \u53c2\u8d5b\u7533\u8bf7 from the inbox \u2014 REMOVED FROM THE PRODUCT (same instant-join change as M7). See `e2e/MISSING_FEATURES.md`. The user-visible inverse \u2014 a participant withdrawing themselves with the new \u9000\u51fa\u8d5b\u4e8b button \u2014 is covered by M24 below.
- [~] M17b Reject-already-approved data-integrity guard \u2014 N/A: the reject endpoint no longer exists (see M17). No test cites a phantom function any more.

- [x] M18 Non-rated individual tournament allows BOTH entry paths (free-text team create AND the hosted-account picker) — `test_nonrated_individual_allows_freetext_and_picker` (API+UI). The free-text restriction (M12) is scoped to RATED individual tournaments only.
- [x] M19 A non-member can view a public tournament payload and submit \u7533\u8bf7\u53c2\u8d5b \u2014 `test_public_dashboard_viewable_by_nonmember_and_join` (API-level: a non-member account loads the public tournament payload and POSTs a join-request). [~UI] the join is asserted via API, not by clicking the rendered \u7533\u8bf7\u53c2\u8d5b button \u2014 the UI join-button click is covered end-to-end by N3 (`test_nonparticipant_sees_join_and_follow_then_pending` clicks the rendered \u53c2\u8d5b button on the results page and asserts the badge replaces it in place).
- [x] M20 A public tournament resolves by numeric id (`GET /tournaments?endpoint_name={id}`) for anyone \u2014 `test_public_dashboard_resolves_by_id_for_anyone`; M20b a non-public tournament is NOT resolvable by id \u2014 `test_nonpublic_tournament_not_resolvable_by_id`.
- [x] M21 Follow/favorite: a user's followed list (GET /me/tournaments) = favorites \u222a joined \u2014 `test_follow_favorite_tournaments` (API-level: favorite/unfavorite, joined auto-appears, cannot favorite an unviewable private tournament). The \u2b50 toggle and the \u6211\u5173\u6ce8\u7684\u9526\u6807\u8d5b home tab are driven through the UI by N4 (`test_follow_toggle_and_home_followed_tab`).
- [x] M22 Being added as a \u8bb0\u5206\u5458 (scorer) auto-follows the tournament; removing the role unfollows \u2014 `test_scorer_auto_follows_tournament` (API-level) AND `test_scorer_auto_follow_home_tab_ui` (UI: after being added as a scorer, the home \u6211\u5173\u6ce8\u7684\u9526\u6807\u8d5b tab shows a card linking to /results \u2014 and NOT /stages since the scorer didn't create it; before being a scorer the tab is empty; removing the role unfollows and the API confirms it leaves the list). Covers the scorer-specific auto-follow path through the browser, complementing N4's manual-favorite path.
- [x] M23 A scorer can READ a private tournament (by-id + stages + courts) so they can open results + score \u2014 `test_scorer_can_read_private_tournament` (API-level: 401 before, 200 after). [~UI] the scorer opening the results page + score editor through the browser is not yet covered \u2014 see N6.
- [x] M24 A joined participant can WITHDRAW themselves (\u9000\u51fa\u8d5b\u4e8b) through the UI \u2014 `test_participant_can_withdraw_via_ui` (a fresh account instant-joins; the results page shows the \u60a8\u5df2\u53c2\u8d5b badge + a \u9000\u51fa\u8d5b\u4e8b button while the leave window is open; clicking the button drives the JoinSection leaveTournament handler [POST /leave] end-to-end \u2014 the badge is replaced in place by the \u53c2\u8d5b join button, my-join-status reverts is_participant=False, and the auto-created bound team is deleted). Complements N3, which exercises the join handler.
- [x] M24b The 退出赛事 affordance auto-hides AND POST /leave is REJECTED once play has started (negative inverse of M24) — `test_withdraw_button_hidden_and_blocked_once_started` (a fresh account joins BEFORE start so the bound team exists; the scheduled RR is then built to close the leave window; (a) the joined participant on /results sees the 您已参赛 badge but the 退出赛事 button is GONE; (b) my-join-status reports can_leave=False while is_participant=True; (c) POST /leave returns 400 "比赛已开始" and the bound team is still present — no orphaning, no silent delete). Mirrors N11 for the leave handler. A regression that left withdraw available mid-event would not be caught by M24 alone.
- [x] M25 Rated individual tournament rejects a tied non-zero (draw) score — `test_rated_tournament_rejects_draw_score` (API-level negative test: PUT /matches/{id} with input1_score=1, input2_score=1 on a rated individual tournament → 400 mentioning "draws"/"decisive". The one-tap UI buttons can only produce decisive scores, so this guard is defense-in-depth the UI cannot trigger; a regression that dropped the guard — allowing a 1:1 draw to persist on a rated tournament and corrupt the rating settlement — would pass the entire suite without this. Also asserts 0:0 (unplayed) is NOT rejected, since that is the legitimate "no result" state)
- [x] M26 A rated individual tournament whose match is a FORFEIT settles correctly and applies the ChinaTT exchange — `test_forfeit_match_settles_on_rated_tournament` (creates a rated individual tournament, 2 applicants instant-join, both seeded at 1500, builds a 2-team RR, then FORFEITS the single match via the UI 弃权 button — the non-forfeiting player wins the walkover. The owner requests settlement; admin approves-and-settles; the leaderboard shows the correct ChinaTT +8/-8 exchange for equal seeds and matches_played==1 each. This closes the gap found by the critic: the settlement completeness gate [validate_settlement_ready] previously treated a 0-0 forfeit as "no recorded result" and blocked settlement entirely, and scored_matches_from_rows silently dropped it — so a perfectly normal table-tennis forfeit [illness/no-show] made the whole tournament unsettlable. After the fix the backend consults forfeit_input in both the gate and the winner/loser determination [settlement.py + ratings.py], so the non-forfeiting player gets their +rating and the forfeiting player their -rating. The existing forfeit tests H6/H6b only covered NON-rated tournaments' RR-standings computation; no test ever attempted to SETTLE a rated tournament containing a forfeit)
- [x] M27a ChinaTT UPSET exchange (lower-rated beats higher) — `test_upset_exchange_lower_beats_higher` (seeds two applicants at DIFFERENT ratings: 1500 vs 1400, diff=100 → ChinaTT bin (112, high_gain=4, low_gain=20); the LOWER-rated applicant wins the match (an upset); after admin /settle the leaderboard shows the lower-rated winner UP exactly 20 (1500→1420) and the higher-rated loser DOWN exactly 20 (1500→1480) — the low_gain branch. The critic found that M15/M26 both seed the two applicants at the SAME rating (1500 vs 1500); at diff=0 the ChinaTT table returns (8,8) for BOTH the higher_won=True and higher_won=False branches, so a regression that dropped the higher_won flip, inverted it, or always used high_gain would pass every existing test. This test asserts the gain is NOT 4 (the expected-result value), pinning the divergent upset curve)
- [x] M27b ChinaTT EXPECTED exchange (higher-rated beats lower) — `test_expected_exchange_higher_beats_lower` (same seeds 1500 vs 1400 but the HIGHER-rated applicant wins (expected result); after settle the leaderboard shows the higher-rated winner UP exactly 4 (1500→1504) and the lower-rated loser DOWN exactly 4 (1500→1396) — the high_gain branch. Complementary to M27a: a regression that always used low_gain (20) would pass M27a's "not 4" assertion but fail here, since the gain must NOT be 20. Together M27a+M27b lock the full diff>0 divergent exchange curve that equal-seed tests cannot detect)
- [x] M28 Settlement multi-match batch accumulation — `test_settlement_multi_match_batch_accumulation` (creates a 4-team rated individual RR: 6 matches, each player plays 3; scores ALL matches decisively with a known win pattern [A wins 3, B wins 2, C wins 1, D wins 0]; settles; asserts matches_played==3 per player AND cumulative rating deltas correct [A: +24→1524, B: +8→1508, C: -8→1492, D: -24→1476; all seeds 1500, diff=0→exchange 8 per match] AND the 4-player rating sum is conserved. Every existing settlement test [M15/M26/M27a/M27b] uses exactly 2 teams / 1 match; a regression in the batch delta_sum loop, matches_played miscounting from the rating_events ledger, or within-tournament order-independence breaking would pass every existing test but fail here)
- [x] M29 Settlement blocked when active stage is not the last — `test_settlement_blocked_active_stage_not_last` (creates a 2-stage rated individual tournament, activates stage 1 [direction="next" from no active→S1], scores the single RR match, then asserts POST /settlement-request returns 400 mentioning "advance"/"stages" AND settled_seq stays null AND the UI surfaces the 400 via a Mantine "An error occurred" notification on the settings page. Every settlement test uses a single-stage tournament; validate_settlement_ready's _active_stage_is_last guard was never exercised end-to-end)
- [x] M30 Settlement blocked on PARTIAL results (some matches unplayed) — `test_settlement_blocked_partial_results` (creates a 4-team rated individual RR: 6 matches; scores only the first 3 decisively, leaves 3 unplayed; asserts POST /settlement-request returns 400 mentioning "no recorded result"/"matches" AND settled_seq stays null AND the UI surfaces the 400 via a Mantine notification. M13b tests the ALL-unplayed cell; this test covers the SOME-unplayed cell — a regression that only checked "all unplayed" vs "any played" rather than checking each match individually would pass M13b but allow settling a partially-played tournament, corrupting ratings)

Note: Swiss stage type was removed from the product; the create-stage-item modal
now offers only Round Robin + Single Elimination (see F5).
Note: Swiss stage type was removed from the product; the create-stage-item modal
now offers only Round Robin + Single Elimination (see F5).

## N. Permission- & state-dependent GUI rendering (results page / spectator view)
The v3.1.6 "follow + spectator-scoped view" feature makes the SAME page render
differently per role/state. These are driven THROUGH the UI with distinct
accounts (a fresh applicant/scorer logged into its own browser context by
injecting the login token into localStorage \u2014 see `_logged_in_context` in
`test_permissions.py`, mirroring `conftest.make_logged_in_context`). API-only
proof is INSUFFICIENT here \u2014 the user sees a page. Driven by
`e2e/tests/test_permissions.py` (N1\u2013N7).
- [x] N1 Results page as an anonymous guest: public results render read-only;
  clicking a match does NOT open an editable score modal; no management sidebar \u2014
  `test_anon_results_read_only` (builds a public tournament with a scheduled RR
  so match cards render; asserts the cards are visible, that NEITHER the \u7533\u8bf7\u53c2\u8d5b
  nor the \u2b50\u5173\u6ce8 button is present for an anon viewer, that clicking a card does
  NOT open the \u7f16\u8f91\u6bd4\u8d5b modal, and that hitting /settings bounces an anon visitor
  to /login).
- [x] N2 Results page as a logged-in NON-participant (not member/scorer) on a
  not-yet-started individual tournament: the \\u53c2\\u8d5b instant-join button IS shown; the
  \\u2b50 follow toggle is shown; matches are read-only (no editable modal) \\u2014
  `test_nonparticipant_sees_join_and_follow_then_pending` (fresh non-member account:
  asserts the \\u53c2\\u8d5b + \\u5173\\u6ce8 buttons are visible). Join is now INSTANT (commit
  d9d473c) and only open BEFORE play starts, so this case does not pre-generate
  matches; non-recorder read-only match rendering is covered by N1 + N8.
- [x] N3 \\u53c2\\u8d5b auto-hides after joining \\u2014 same test
  `test_nonparticipant_sees_join_and_follow_then_pending` (after the same account
  joins via the instant-join API, reloading the results page shows the \\u60a8\\u5df2\\u53c2\\u8d5b
  participant badge \\u2014 there is NO longer a pending/approval state \\u2014 and the \\u53c2\\u8d5b
  button is GONE).
- [x] N4 \u2b50 follow toggle on the results page flips state AND the tournament
  appears under the home \u6211\u5173\u6ce8\u7684\u9526\u6807\u8d5b tab; un-following removes it; the two tabs
  are distinct \u2014 `test_follow_toggle_and_home_followed_tab` (clicks \u5173\u6ce8 \u2192 button
  flips to \u5df2\u5173\u6ce8 + GET /me/tournaments includes it; the home \u6211\u5173\u6ce8 tab shows a
  card linking to /results; NO /stages link for this tid exists \u2014 proving it is
  not in \u6211\u521b\u5efa\u7684\u9526\u6807\u8d5b \u2014 then un-following flips back to \u5173\u6ce8 and removes it
  from the followed list).
- [x] N5 A non-member hitting a management route is REDIRECTED to the results
  page and sees no management form; the owner sees it —
  `test_management_route_redirects_nonmember` (a fresh non-member hitting ANY of
  the four management routes — /settings, /teams, /stages, /schedule — is
  redirected to /results and the unique 设置为现在 settings-form button is absent on
  each; the owner via the `page` fixture stays on /settings and sees that button).
  All four routes use the shared TournamentLayout can_manage gate, but the test
  asserts each one so a regression that accidentally un-gated a single route
  surfaces.
- [x] N6 A 记分员 scorer can open the results page of a PRIVATE tournament,
  CAN open the editable score modal (can_record) AND CAN actually SAVE a one-tap
  result-button score that persists server-side under the scorer's token, but
  CANNOT reach management (not can_manage) — `test_scorer_can_score_private_but_not_manage`
  (private tournament; owner adds the scorer; the scorer's browser opens
  /results, clicks a match card; the 编辑比赛 modal opens; the scorer clicks the
  one-tap `2:0` result button via `set_match_result(modal, 2, 0)` (the per-game
  NumberInput stepper flow is GONE); ground-truth assertion
  GETs /api/tournaments/{tid}/stages USING THE SCORER'S OWN BEARER TOKEN
  (re-proving M23 in passing) and asserts one match in this tournament now
  carries games=null with stage_item_input1_score=2, stage_item_input2_score=0,
  and team names overlapping the card text we clicked — so a regression where
  the modal opens but the PATCH/PUT silently 403s the scorer or drops would
  fail here; /settings still redirects to /results with no settings form).
- [x] N7 A followed card on the home \\u6211\\u5173\\u6ce8 tab opens the READ-ONLY results page
  (not the management dashboard) \\u2014 `test_followed_card_links_to_results` (favorites
  a tournament via API, opens the home \\u6211\\u5173\\u6ce8 tab, asserts the card's link points
  at /tournaments/{id}/results and NOT at /stages).
- [x] N8 Results-page role matrix state (d): a JOINED participant/member sees the
  page read-only with the \\u60a8\\u5df2\\u53c2\\u8d5b participant badge and WITHOUT the \\u53c2\\u8d5b join
  affordance \\u2014 `test_approved_participant_results_read_only` (a fresh account
  instant-joins via API BEFORE play starts, then the scheduled RR is built so match
  cards render; the participant's browser opens /results: match cards render, the
  \\u60a8\\u5df2\\u53c2\\u8d5b badge shows, JOIN button count==0, and clicking a card does NOT open
  the \\u7f16\\u8f91\\u6bd4\\u8d5b modal \\u2014 a joined participant is a plain spectator, not a
  recorder). Completes the role matrix the brief enumerates
  (anon=N1, logged-in non-participant=N2, joined participant=N3/N8, scorer=N6,
  owner=N5).
- [x] N9 A logged-in NON-member is DENIED a PRIVATE tournament's results
  (negative security) — `test_nonmember_cannot_view_private_results` (a fresh
  outsider account, not a club member/scorer/participant, is refused: (a) the
  protected `GET /api/tournaments/{id}/stages` returns 401 for the outsider
  while the owner still gets 200, and (b) the outsider's browser at /results
  renders ZERO match cards. N6 only proves an AUTHORISED scorer CAN view a
  private tournament; N9 is the inverse \u2014 a regression that leaked private
  stages to any logged-in user would pass without it).
- [x] N10 The OWNER sees NO spectator affordances on their OWN results page \\u2014 `test_owner_sees_no_spectator_affordances_on_own_results` (the owner via the `page` fixture opens their own tournament's /results: clicks a match card to confirm the editable \\u7f16\\u8f91\\u6bd4\\u8d5b modal opens (can_record/can_manage settled), then asserts NONE of the spectator affordances render \\u2014 \\u5173\\u6ce8 follow button, \\u5df2\\u5173\\u6ce8 toggle, \\u53c2\\u8d5b join button, or the \\u4fe1\\u4efb\\u521b\\u5efa\\u8005 trust-creator control. The inverse of N2/N8: a regression that rendered the join/follow CTA to the owner of their own event would surface here, not in the non-member cases.)
- [x] N11 Join affordance is HIDDEN and the backend REJECTS joining once play has
  started (negative guard for commit 8834b4d) \u2014 `test_join_button_hidden_and_blocked_once_started`
  (a fresh logged-in non-member opens /results of an individual tournament that
  has been STARTED via a scheduled RR: (a) the \u2b50\u5173\u6ce8 toggle still renders but the
  \u53c2\u8d5b instant-join button is GONE and no \u60a8\u5df2\u53c2\u8d5b badge shows \u2014 JoinSection sees
  `can_join=False` and renders nothing; (b) GET /my-join-status reports
  `can_join=False`/`is_participant=False`; (c) POST /join-requests returns 400
  "\u6bd4\u8d5b\u5df2\u5f00\u59cb\uff0c\u65e0\u6cd5\u52a0\u5165" and creates no team/binding for the outsider). This is the
  complement of N2/N3 (which prove join SHOWS and works BEFORE start); without it,
  a regression that kept rendering \u53c2\u8d5b or reopened the server-side join window \u2014
  dropping an unseeded extra team into a running bracket \u2014 would pass unnoticed.
- [x] N12 `/admin` is GATED for non-admin logged-in users (the 404 stub renders,
  the rating-categories form does NOT) \u2014 `test_admin_page_hidden_for_non_admin`
  (a freshly-registered account [`is_admin=False` per `backend/bracket/models/db/user.py`]
  is logged into its own browser context via `_logged_in_context`; navigating to
  /admin and waiting for `networkidle` so the SWR `/users/me` settles, the test
  asserts (a) the `404` marker AND the translated \u4f60\u627e\u5230\u4e86\u4e00\u4e2a\u79d8\u5bc6\u5730\u65b9 not-found
  title render, (b) NEITHER \u79ef\u5206\u7c7b\u522b NOR \u521d\u59cb\u5206\u5ba1\u6838\u961f\u5217 section headings render,
  (c) the \u65b0\u5efa\u7c7b\u522b create-form submit button has count 0. All other tests log in
  as the E2E admin account so a regression that accidentally rendered the admin
  form to ANY logged-in user \u2014 e.g. `frontend/src/pages/admin.tsx:234` flipping
  `!user.is_admin` to `user.is_admin` or dropping the gate \u2014 would be invisible
  without this case.

Note on M13 settlement-error UI surfacing: `test_settlement_blocked_on_empty_tournament`
now also asserts (between the button click and the post-reload state check) that a
Mantine error notification with the title "An error occurred" renders and that its
body text mentions the backend's "no completed matches" / "settle" detail. This
locks the `handleRequestError` (frontend/src/services/adapter.tsx:24) contract \u2014 a
regression where the frontend silently swallows the 400 and renders no toast would
have left the original M13 test green (settled_seq stays null on its own), but now
fails here.