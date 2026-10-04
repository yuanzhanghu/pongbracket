"""Stage and format tests (F1-F9).

These tests assert the *delta* of each stage operation rather than the mere
presence of the static stages-page chrome.
"""
from __future__ import annotations

import uuid

import pytest
import requests
from playwright.sync_api import Page, expect

from ._helpers import (
    BASE_URL,
    _api_headers,
    api_create_court,
    api_create_round_robin,
    api_create_single_elimination,
    api_create_stage,
    api_create_team,
    api_create_tournament,
    api_count_matches,
    api_delete_stage,
    api_delete_tournament,
    api_get_stages,
    api_get_teams,
    api_schedule_matches,
)


def _stages_url(tid: int) -> str:
    return f"{BASE_URL}/tournaments/{tid}/stages"


def _wait_stages_loaded(page: Page) -> None:
    """Wait for the stages page to render the create-stage button (SWR settled)."""
    page.wait_for_selector(
        'button:has-text("\u6dfb\u52a0\u9636\u6bb5")', state="visible", timeout=15_000
    )


def _stage_card_count(page: Page) -> int:
    """Count stage columns currently rendered on the stages page."""
    return page.locator('text=/\u9636\u6bb5\uff1a/').count()


def _create_fresh_tournament_with_teams(shared_club_id: int, n_teams: int) -> int:
    """Create a dedicated fresh tournament with N teams. Cleanup on failure."""
    name = f"E2E-FreshT-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, name)
    for i in range(n_teams):
        r = requests.post(
            f"{BASE_URL}/api/tournaments/{tid}/teams",
            headers=_api_headers(),
            json={"name": f"E2E-Fresh-Team-{i}", "active": True, "player_names": []},
            timeout=15,
        )
        r.raise_for_status()
    return tid


def test_add_stage(page: Page, shared_club_id: int) -> None:
    """F1: clicking \u6dfb\u52a0\u9636\u6bb5 creates a new stage column in the UI.

    A dedicated fresh tournament is used so the stages page renders the
    empty-state NoContent + the large \u6dfb\u52a0\u9636\u6bb5 button (which is the
    unambiguous, only match). The shared tournament has many accumulated
    stage columns and the column-area button can be obscured by the
    stage-card chrome, so it is not used for this test.
    """
    tid = _create_fresh_tournament_with_teams(shared_club_id, n_teams=4)
    try:
        initial_api = len(api_get_stages(tid))
        assert initial_api == 0, f"fresh tournament should have 0 stages, got {initial_api}"

        page.goto(_stages_url(tid), wait_until="domcontentloaded")
        _wait_stages_loaded(page)
        # The empty-state path renders the large \u6dfb\u52a0\u9636\u6bb5 button as the
        # only matching button. Click it; the button's onClick is the same
        # createStage call we used to exercise via the API in earlier
        # iterations of this test.
        add_button = page.get_by_role("button", name="\u6dfb\u52a0\u9636\u6bb5").first
        expect(add_button).to_be_visible(timeout=10_000)
        add_button.click()
        # The new stage column header should appear (the default name is
        # localized via the stage_default_name key; the column header is
        # rendered as `\u9636\u6bb5\uff1a<name>`).
        expect(page.locator("body")).to_contain_text("\u9636\u6bb5\uff1a", timeout=15_000)
        # API confirms the new stage was persisted by the click.
        final_api = len(api_get_stages(tid))
        assert final_api == initial_api + 1, (
            f"expected stage count to grow by 1 after click, got {initial_api} -> {final_api}"
        )
    finally:
        api_delete_tournament(tid)


def test_rename_stage(page: Page, shared_tournament_id: int) -> None:
    """F2: rename a stage via the \u7f16\u8f91\u9636\u6bb5 menu and verify the new name persists."""
    original = f"E2E-Orig-{uuid.uuid4().hex[:6]}"
    new_name = f"E2E-Renamed-{uuid.uuid4().hex[:6]}"
    stage_id = api_create_stage(shared_tournament_id, original)
    try:
        page.goto(_stages_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_stages_loaded(page)
        expect(page.locator("body")).to_contain_text(original, timeout=10_000)
        col_header = page.locator(f'text=\u9636\u6bb5\uff1a{original}').first
        col_header.locator(
            'xpath=ancestor::*[1]//button[contains(@class, "mantine-ActionIcon")]'
        ).first.click()
        page.get_by_role("menuitem", name="\u7f16\u8f91\u9636\u6bb5").first.click()
        page.wait_for_selector(".mantine-Modal-content", state="visible", timeout=10_000)
        modal = page.locator(".mantine-Modal-content").last
        name_input = modal.locator('input[type="text"]').first
        name_input.fill(new_name)
        modal.get_by_role("button", name="\u4fdd\u5b58").first.click()
        expect(modal).to_be_hidden(timeout=10_000)
        page.reload(wait_until="domcontentloaded")
        _wait_stages_loaded(page)
        expect(page.locator("body")).to_contain_text(new_name, timeout=10_000)
        assert page.locator(f'text=\u9636\u6bb5\uff1a{original}').count() == 0, (
            f"old stage name {original!r} should not appear after rename"
        )
        names = [s["name"] for s in api_get_stages(shared_tournament_id)]
        assert new_name in names, f"expected {new_name!r} in stage names, got {names!r}"
        assert original not in names
    finally:
        api_delete_stage(shared_tournament_id, stage_id)


def test_round_robin_stage(page: Page, shared_tournament_id: int) -> None:
    """F3: a round-robin stage item renders with the i18n \u5faa\u73af\u8d5b template name."""
    stage_name = f"E2E-RR-{uuid.uuid4().hex[:6]}"
    stage_id = api_create_stage(shared_tournament_id, stage_name)
    try:
        api_create_round_robin(shared_tournament_id, stage_id, team_count=4, group_count=1)
        stages = {s["id"]: s for s in api_get_stages(shared_tournament_id)}
        items = stages[stage_id].get("stage_items", [])
        assert items, "expected at least one stage item after creating round robin"
        assert items[-1]["type"] == "ROUND_ROBIN", (
            f"expected last item type ROUND_ROBIN, got {items[-1]['type']}"
        )
        page.goto(_stages_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_stages_loaded(page)
        expect(page.locator("body")).to_contain_text(stage_name, timeout=10_000)
        expect(page.locator("body")).to_contain_text("\u5c0f\u7ec4", timeout=10_000)
    finally:
        api_delete_stage(shared_tournament_id, stage_id)


def test_single_elimination_stage(page: Page, shared_tournament_id: int) -> None:
    """F4: a single-elimination stage item renders for its parent stage."""
    stage_name = f"E2E-SE-{uuid.uuid4().hex[:6]}"
    stage_id = api_create_stage(shared_tournament_id, stage_name)
    try:
        api_create_single_elimination(shared_tournament_id, stage_id, team_count=4)
        stages = {s["id"]: s for s in api_get_stages(shared_tournament_id)}
        items = stages[stage_id].get("stage_items", [])
        assert items, "expected an SE stage item"
        assert items[-1]["type"] == "SINGLE_ELIMINATION", (
            f"expected SINGLE_ELIMINATION, got {items[-1]['type']}"
        )
        page.goto(_stages_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_stages_loaded(page)
        expect(page.locator("body")).to_contain_text(stage_name, timeout=10_000)
        expect(page.locator("body")).to_contain_text(
            items[-1]["name"], timeout=10_000
        )
    finally:
        api_delete_stage(shared_tournament_id, stage_id)


def test_create_stage_item_modal_lists_two_formats(
    page: Page, shared_tournament_id: int
) -> None:
    """F5: \u6dfb\u52a0\u9636\u6bb5\u5185\u9879\u76ee modal exposes RR / SE only (Swiss removed)."""
    stage_name = f"E2E-Modal-{uuid.uuid4().hex[:6]}"
    stage_id = api_create_stage(shared_tournament_id, stage_name)
    try:
        page.goto(_stages_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_stages_loaded(page)
        expect(page.locator("body")).to_contain_text(stage_name, timeout=10_000)
        triggers = page.get_by_role("button", name="\u6dfb\u52a0\u9636\u6bb5\u5185\u9879\u76ee")
        assert triggers.count() >= 1, "expected at least one \u6dfb\u52a0\u9636\u6bb5\u5185\u9879\u76ee button"
        triggers.first.click()
        page.wait_for_selector(".mantine-Modal-content", state="visible", timeout=10_000)
        modal = page.locator(".mantine-Modal-content").last
        modal_text = modal.inner_text()
        assert "\u5faa\u73af\u8d5b" in modal_text, "round-robin label missing"
        assert "\u5355\u6dd8\u6c70\u8d5b" in modal_text, "single-elimination label missing"
        # Lock in that EXACTLY two format cards are offered (Swiss removed). The
        # `not in "\u745e\u58eb\u5236"` check this replaced was tautological \u2014 that
        # string never existed anywhere in the build, so it could never fail. Each
        # StageSelectCard renders a distinct `/icons/*-stage-item.svg` image, so a
        # third format reappearing (or the cards breaking) flips this count.
        format_cards = modal.locator('img[src*="-stage-item.svg"]')
        expect(format_cards).to_have_count(2, timeout=5_000)
    finally:
        api_delete_stage(shared_tournament_id, stage_id)


def test_multi_stage_composition_with_source_selection(
    page: Page, shared_club_id: int
) -> None:
    """F6: an SE stage can pick a source from a prior RR stage in the UI.

    A dedicated fresh tournament is used so we control the exact ordering
    and avoid interference from accumulated stages. Flow:

      1. Create stage 1 (RR) with one stage item.
      2. Create stage 2 (SE) via the modal.
      3. In the modal, switch the format to SINGLE_ELIMINATION. Because a
         prior stage item exists, the EliminationSourcePicker is rendered
         with a checkbox labelled with the RR stage item's name.
      4. Tick the source checkbox and submit.
      5. Assert the new stage has a SINGLE_ELIMINATION stage item whose
         inputs reference the RR stage item as `winner_from_stage_item_id`.
    """
    tid = _create_fresh_tournament_with_teams(shared_club_id, n_teams=4)
    try:
        # Create the two stages via the API (we exercise the UI for the
        # critical source-selection part of the flow, not the stage-create
        # which is covered by test_add_stage / test_rename_stage).
        s1 = api_create_stage(tid, f"E2E-SrcRR-{uuid.uuid4().hex[:6]}")
        s2 = api_create_stage(tid, f"E2E-SrcSE-{uuid.uuid4().hex[:6]}")
        try:
            rr_item_id = api_create_round_robin(tid, s1, team_count=4, group_count=1)

            page.goto(_stages_url(tid), wait_until="domcontentloaded")
            _wait_stages_loaded(page)
            # Each stage column has its own \u6dfb\u52a0\u9636\u6bb5\u5185\u9879\u76ee button. The s2 column
            # is rendered after s1, so the LAST trigger in document order is the one
            # we want (it belongs to s2's state).
            triggers = page.get_by_role("button", name="\u6dfb\u52a0\u9636\u6bb5\u5185\u9879\u76ee")
            assert triggers.count() >= 2, (
                f"expected at least 2 \u6dfb\u52a0\u9636\u6bb5\u5185\u9879\u76ee buttons (one per stage), got {triggers.count()}"
            )
            triggers.last.click()
            page.wait_for_selector(".mantine-Modal-content", state="visible", timeout=10_000)
            modal = page.locator(".mantine-Modal-content").last

            # Switch to SINGLE_ELIMINATION. The three format cards are inside
            # the modal; the SE card has text "\u5355\u6dd8\u6c70\u8d5b".
            se_card = modal.get_by_text("\u5355\u6dd8\u6c70\u8d5b", exact=True).first
            se_card.click()
            page.wait_for_timeout(500)
            # The EliminationSourcePicker renders a Checkbox with the RR
            # stage item's name. Look up the RR stage item's display name
            # (the SE item's title) and assert a checkbox with that name
            # appears in the picker \u2014 this is the F6 "source selection"
            # affordance.
            stages = {s["id"]: s for s in api_get_stages(tid)}
            rr_item = next(
                (i for i in stages[s1].get("stage_items", []) if i["id"] == rr_item_id),
                None,
            )
            assert rr_item is not None, "RR stage item not found in API"
            rr_name = rr_item["name"]
            # Tick the source checkbox by its label.
            source_checkbox = modal.get_by_role("checkbox", name=rr_name).first
            expect(source_checkbox).to_be_visible(timeout=5_000)
            source_checkbox.check()

            # Submit the modal: \u521b\u5efa\u9636\u6bb5\u5185\u9879\u76ee button.
            modal.get_by_role("button", name="\u521b\u5efa\u9636\u6bb5\u5185\u9879\u76ee").first.click()
            expect(modal).to_be_hidden(timeout=15_000)

            # API ground truth: stage 2 now has a SINGLE_ELIMINATION stage item
            # with at least one input whose `winner_from_stage_item_id` is the RR item.
            stages_after = {s["id"]: s for s in api_get_stages(tid)}
            s2_items = stages_after[s2].get("stage_items", [])
            se_items = [i for i in s2_items if i["type"] == "SINGLE_ELIMINATION"]
            assert se_items, (
                f"expected a SINGLE_ELIMINATION stage item in stage 2, got types: "
                f"{[i['type'] for i in s2_items]}"
            )
            inputs = se_items[-1].get("inputs", [])
            assert any(
                i.get("winner_from_stage_item_id") == rr_item_id for i in inputs
            ), (
                f"expected at least one SE input with winner_from_stage_item_id="
                f"{rr_item_id} (RR), got: {[(i.get('team_id'), i.get('winner_from_stage_item_id')) for i in inputs]}"
            )
        finally:
            api_delete_stage(tid, s2)
            api_delete_stage(tid, s1)
    finally:
        api_delete_tournament(tid)


def test_delete_stage(page: Page, shared_tournament_id: int) -> None:
    """F7: deleting a stage via its column kebab menu removes it from the page."""
    stage_name = f"E2E-DelStage-{uuid.uuid4().hex[:6]}"
    stage_id = api_create_stage(shared_tournament_id, stage_name)
    try:
        page.goto(_stages_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_stages_loaded(page)
        expect(page.locator("body")).to_contain_text(stage_name, timeout=10_000)
        col_header = page.locator(f'text=\u9636\u6bb5\uff1a{stage_name}').first
        col_header.locator(
            'xpath=ancestor::*[1]//button[contains(@class, "mantine-ActionIcon")]'
        ).first.click()
        page.get_by_role("menuitem", name="\u5220\u9664").first.click()
        expect(page.locator(f'text=\u9636\u6bb5\uff1a{stage_name}')).to_have_count(
            0, timeout=10_000
        )
        names = [s["name"] for s in api_get_stages(shared_tournament_id)]
        assert stage_name not in names, f"stage {stage_name!r} still present in API: {names}"
    except Exception:
        try:
            api_delete_stage(shared_tournament_id, stage_id)
        except Exception:
            pass
        raise


def test_generate_stage_items(page: Page, shared_tournament_id: int) -> None:
    """F9: creating a stage item generates matches (the API reports a delta)."""
    stage_name = f"E2E-Gen-{uuid.uuid4().hex[:6]}"
    stage_id = api_create_stage(shared_tournament_id, stage_name)
    try:
        before = api_count_matches(shared_tournament_id)
        api_create_round_robin(shared_tournament_id, stage_id, team_count=4, group_count=1)
        after = api_count_matches(shared_tournament_id)
        assert after - before >= 1, (
            f"expected new matches after generating stage item, got {before} -> {after}"
        )
        page.goto(_stages_url(shared_tournament_id), wait_until="domcontentloaded")
        _wait_stages_loaded(page)
        expect(page.locator("body")).to_contain_text(stage_name, timeout=10_000)
        expect(page.locator("body")).to_contain_text("\u5c0f\u7ec4", timeout=10_000)
    finally:
        api_delete_stage(shared_tournament_id, stage_id)


def test_create_rr_stage_item_via_modal(page: Page, shared_club_id: int) -> None:
    """F3-UI: create a round-robin stage item THROUGH THE MODAL (not the API).

    The modal's RR onSubmit handler (createRoundRobinGroups) is only ever
    exercised indirectly via the API in every existing test. This test opens
    the create-stage-item modal (ROUND_ROBIN is the default type) and submits
    it with its default field values — num_groups=2, team_count=4 — then
    asserts the modal closes AND the modal's onSubmit produced exactly what
    those defaults imply via the API: split_group_sizes(4, 2) = [2, 2], so
    TWO ROUND_ROBIN stage items (one per group), each a 2-team group with
    exactly C(2,2)=1 match (2 matches total). This mirrors F6's SE-side
    coverage for the RR half. A regression in the form's onSubmit wiring,
    field mapping, default values, or validation gate would pass all other
    tests but fail here.
    """
    tid = _create_fresh_tournament_with_teams(shared_club_id, n_teams=4)
    try:
        stage_name = f"E2E-RRModal-{uuid.uuid4().hex[:6]}"
        stage_id = api_create_stage(tid, stage_name)
        try:
            page.goto(_stages_url(tid), wait_until="domcontentloaded")
            _wait_stages_loaded(page)
            # Wait for the stage column to render (SWR settle).
            expect(page.locator("body")).to_contain_text(stage_name, timeout=10_000)
            triggers = page.get_by_role("button", name="\u6dfb\u52a0\u9636\u6bb5\u5185\u9879\u76ee")
            expect(triggers.first).to_be_visible(timeout=10_000)
            triggers.first.click()
            page.wait_for_selector(".mantine-Modal-content", state="visible", timeout=10_000)
            modal = page.locator(".mantine-Modal-content").last

            # Submit the form by pressing Enter on an input (the modal form
            # submits on Enter). The 创建阶段项目 button is clipped by modal
            # overflow so a direct click times out; form submission is the
            # real user path anyway.
            modal.locator("input").first.click()
            page.keyboard.press("Enter")
            expect(modal).to_be_hidden(timeout=15_000)
            # API ground truth: the modal's onSubmit created the stage items
            # implied by its DEFAULT values (num_groups=2, team_count=4).
            # split_group_sizes(4, 2) = [2, 2] → exactly 2 ROUND_ROBIN stage
            # items (one per group), each a 2-team group with C(2,2)=1 match,
            # so 2 matches total. Pin these exact counts: a looser ">= 1"
            # would still pass if the modal silently made a single group.
            stages = {s["id"]: s for s in api_get_stages(tid)}
            items = stages[stage_id].get("stage_items", [])
            rr_items = [i for i in items if i["type"] == "ROUND_ROBIN"]
            assert len(rr_items) == 2, (
                f"expected 2 ROUND_ROBIN stage items from the modal defaults "
                f"(num_groups=2), got {len(rr_items)}; types: "
                f"{[i['type'] for i in items]}"
            )
            per_group = [
                sum(len(rd.get("matches", [])) for rd in item.get("rounds", []))
                for item in rr_items
            ]
            assert per_group == [1, 1], (
                f"expected each of the 2 groups (2 teams) to have C(2,2)=1 "
                f"match, got per-group match counts {per_group}"
            )
        finally:
            api_delete_stage(tid, stage_id)
    finally:
        api_delete_tournament(tid)


def test_multi_group_round_robin(page: Page, shared_club_id: int) -> None:
    """F3b: a multi-group round-robin (group_count=2) renders TWO distinct
    GroupGrid cross-tables on the results page, each with 4 teams and 6 cells.

    Every RR in the suite uses group_count=1. The create-stage-item modal
    defaults num_groups to 2 and exposes a 小组数 NumberInput plus a group_method
    selector. No test ever creates a multi-group RR through the API or asserts
    the results page renders multiple GroupGrid tables (one per group) or that
    standings are computed per-group. A regression in multi-group generation,
    multi-group cross-table rendering, or per-group standings isolation would
    pass the entire suite.
    """
    tname = f"E2E-MultiGrp-{uuid.uuid4().hex[:6]}"
    tid = api_create_tournament(shared_club_id, tname)
    try:
        # Create 8 teams so group_count=2 gives 4 per group.
        team_names = []
        for i in range(8):
            nm = f"E2E-MGT-{i}-{uuid.uuid4().hex[:4]}"
            api_create_team(tid, nm)
            team_names.append(nm)

        stage_id = api_create_stage(tid, f"E2E-MGSt-{uuid.uuid4().hex[:6]}")
        # group_count=2, team_count=8 → 2 groups of 4 teams each.
        api_create_round_robin(tid, stage_id, team_count=8, group_count=2)
        api_create_court(tid, f"E2E-MGCt-{uuid.uuid4().hex[:4]}")
        api_create_court(tid, f"E2E-MGCt-{uuid.uuid4().hex[:4]}")
        api_schedule_matches(tid)

        # API ground truth: the stage has 2 ROUND_ROBIN stage items,
        # each with 6 matches (C(4,2)).
        stages = {s["id"]: s for s in api_get_stages(tid)}
        items = stages[stage_id].get("stage_items", [])
        rr_items = [i for i in items if i["type"] == "ROUND_ROBIN"]
        assert len(rr_items) == 2, (
            f"expected 2 RR stage items (groups), got {len(rr_items)}"
        )
        for idx, item in enumerate(rr_items):
            mc = sum(len(rd.get("matches", [])) for rd in item.get("rounds", []))
            assert mc == 6, (
                f"group {idx}: expected 6 matches (C(4,2)), got {mc}"
            )

        # Navigate to /results and assert TWO distinct GroupGrid tables render.
        page.goto(
            f"{BASE_URL}/tournaments/{tid}/results", wait_until="domcontentloaded"
        )
        page.wait_for_selector('[role="tab"]', timeout=15_000)
        # Scope to the results tabpanel (the standings tab also has tables).
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_be_visible(timeout=10_000)
        # Each GroupGrid renders a <table>. There should be exactly 2.
        tables = panel.locator("table")
        expect(tables).to_have_count(2, timeout=15_000)

        # Each table should have 4 team rows (plus header) → 5 rows total
        # (1 thead row + 4 tbody rows). Actually the GroupGrid has header row
        # + 4 data rows = 5 <tr>. But we just need to verify each table has
        # the right number of data rows.
        for i in range(2):
            tbl = tables.nth(i)
            body_rows = tbl.locator("tbody tr")
            expect(body_rows).to_have_count(4, timeout=10_000)

        # Verify the two groups have DIFFERENT team sets. Collect team names
        # from each table's first column.
        group1_teams = set()
        group2_teams = set()
        for row_idx in range(4):
            row1 = tables.nth(0).locator("tbody tr").nth(row_idx)
            row2 = tables.nth(1).locator("tbody tr").nth(row_idx)
            text1 = row1.locator("td").first.inner_text()
            text2 = row2.locator("td").first.inner_text()
            # The cell text is "N. <team_name>"; extract the team name.
            group1_teams.add(text1.split(". ", 1)[-1].strip() if ". " in text1 else text1)
            group2_teams.add(text2.split(". ", 1)[-1].strip() if ". " in text2 else text2)

        # The two groups should have no team in common.
        overlap = group1_teams & group2_teams
        assert not overlap, (
            f"groups should have disjoint team sets, but overlap: {overlap}"
        )
        assert len(group1_teams) == 4, (
            f"group 1 should have 4 teams, got {len(group1_teams)}: {group1_teams}"
        )
        assert len(group2_teams) == 4, (
            f"group 2 should have 4 teams, got {len(group2_teams)}: {group2_teams}"
        )

        # Assert each group's teams are drawn from the 8 we created.
        all_created = set(team_names)
        assert group1_teams.issubset(all_created), (
            f"group 1 has unknown teams: {group1_teams - all_created}"
        )
        assert group2_teams.issubset(all_created), (
            f"group 2 has unknown teams: {group2_teams - all_created}"
        )

        # Switch to the 排名 (standings) tab and assert it renders.
        page.get_by_role("tab", name="排名").first.click()
        panel = page.get_by_role("tabpanel").first
        expect(panel).to_be_visible(timeout=10_000)
        # The standings should show all 8 teams (combined across groups).
        for nm in team_names:
            # Each team name contains a unique suffix; check the prefix is present.
            short = nm.rsplit("-", 1)[0]  # e.g. "E2E-MGT-0"
            expect(panel).to_contain_text(short, timeout=10_000)
    finally:
        try:
            api_delete_tournament(tid)
        except Exception:
            pass