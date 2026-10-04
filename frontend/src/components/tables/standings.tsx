import { Table, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { EmptyTableInfo } from '@components/no_content/empty_table_info';
import { formatStageItemInput } from '@components/utils/stage_item_input';
import { StageItemInputFinal, StageItemWithRounds } from '@openapi';
import { ThNotSortable } from './table';
import TableLayoutLarge from './table_large';

// Rank inputs by points, breaking ties with the table-tennis group rules among the
// tied players only: head-to-head wins -> games (局分) ratio -> points (小分) ratio.
function rankInputsWithTiebreak(
  inputs: StageItemInputFinal[],
  stageItem: StageItemWithRounds
): StageItemInputFinal[] {
  const matches: any[] = ((stageItem as any).rounds || [])
    .filter((r: any) => !r.is_draft)
    .flatMap((r: any) => r.matches || []);

  const sub = (ids: Set<number>) => {
    const wins: any = {},
      gw: any = {},
      gl: any = {},
      pw: any = {},
      pl: any = {};
    ids.forEach((i) => {
      wins[i] = 0;
      gw[i] = 0;
      gl[i] = 0;
      pw[i] = 0;
      pl[i] = 0;
    });
    for (const m of matches) {
      const i1 = m.stage_item_input1_id,
        i2 = m.stage_item_input2_id;
      if (i1 == null || i2 == null || !ids.has(i1) || !ids.has(i2)) continue;
      const s1 = m.stage_item_input1_score || 0,
        s2 = m.stage_item_input2_score || 0;
      gw[i1] += s1;
      gl[i1] += s2;
      gw[i2] += s2;
      gl[i2] += s1;
      if (s1 > s2) wins[i1] += 1;
      else if (s2 > s1) wins[i2] += 1;
      const gms: number[][] = Array.isArray(m.games) ? m.games : [];
      let p1 = 0,
        p2 = 0;
      for (const g of gms) {
        p1 += g[0] || 0;
        p2 += g[1] || 0;
      }
      pw[i1] += p1;
      pl[i1] += p2;
      pw[i2] += p2;
      pl[i2] += p1;
    }
    return { wins, gw, gl, pw, pl };
  };
  const ratio = (w: number, l: number) => (l > 0 ? w / l : w > 0 ? Infinity : 0);

  const sorted = [...inputs].sort((a, b) => parseFloat(b.points) - parseFloat(a.points));
  const result: StageItemInputFinal[] = [];
  let i = 0;
  while (i < sorted.length) {
    let j = i;
    while (j < sorted.length && parseFloat(sorted[j].points) === parseFloat(sorted[i].points))
      j += 1;
    const cluster = sorted.slice(i, j);
    if (cluster.length > 1) {
      const ids = new Set<number>(cluster.map((c) => c.id as unknown as number));
      const { wins, gw, gl, pw, pl } = sub(ids);
      cluster.sort((a: any, b: any) => {
        if (wins[b.id] !== wins[a.id]) return wins[b.id] - wins[a.id];
        const rg = ratio(gw[b.id], gl[b.id]) - ratio(gw[a.id], gl[a.id]);
        if (rg !== 0) return rg;
        return ratio(pw[b.id], pl[b.id]) - ratio(pw[a.id], pl[a.id]);
      });
    }
    result.push(...cluster);
    i = j;
  }
  return result;
}

// Overall games (局分) and points (小分) totals per input, across all non-draft matches.
function computeScoreTotals(stageItem: StageItemWithRounds) {
  const matches: any[] = ((stageItem as any).rounds || [])
    .filter((r: any) => !r.is_draft)
    .flatMap((r: any) => r.matches || []);

  const totals: Record<number, { gw: number; gl: number; pw: number; pl: number }> = {};
  const ensure = (i: number) => (totals[i] = totals[i] || { gw: 0, gl: 0, pw: 0, pl: 0 });
  for (const m of matches) {
    const i1 = m.stage_item_input1_id,
      i2 = m.stage_item_input2_id;
    if (i1 == null || i2 == null) continue;
    const s1 = m.stage_item_input1_score || 0,
      s2 = m.stage_item_input2_score || 0;
    const t1 = ensure(i1),
      t2 = ensure(i2);
    t1.gw += s1;
    t1.gl += s2;
    t2.gw += s2;
    t2.gl += s1;
    const gms: number[][] = Array.isArray(m.games) ? m.games : [];
    let p1 = 0,
      p2 = 0;
    for (const g of gms) {
      p1 += g[0] || 0;
      p2 += g[1] || 0;
    }
    t1.pw += p1;
    t1.pl += p2;
    t2.pw += p2;
    t2.pl += p1;
  }
  return totals;
}

export function StandingsTableForStageItem({
  teams_with_inputs,
  stageItem,
  fontSizeInPixels,
  stageItemsLookup,
  maxTeamsToDisplay,
  teamContext,
}: {
  teams_with_inputs: StageItemInputFinal[];
  stageItem: StageItemWithRounds;
  fontSizeInPixels: number;
  stageItemsLookup: any;
  maxTeamsToDisplay: number;
  teamContext?: 'individual';
}) {
  const { t } = useTranslation();
  const scoreTotals = computeScoreTotals(stageItem);

  const rows = rankInputsWithTiebreak(teams_with_inputs, stageItem)
    .slice(0, maxTeamsToDisplay)
    .map((team_with_input, index) => {
      const totals = scoreTotals[team_with_input.id as unknown as number] || {
        gw: 0,
        gl: 0,
        pw: 0,
        pl: 0,
      };
      return (
        <Table.Tr key={team_with_input.id}>
          <Table.Td style={{ width: '2rem' }}>{index + 1}</Table.Td>
          <Table.Td style={{ width: '20rem' }}>
            <Text truncate="end" lineClamp={1} inherit>
              {formatStageItemInput(team_with_input, stageItemsLookup)}
            </Text>
          </Table.Td>
          <Table.Td style={{ whiteSpace: 'nowrap' }}>{team_with_input.points}</Table.Td>
          <Table.Td style={{ whiteSpace: 'nowrap' }}>{`${totals.gw}:${totals.gl}`}</Table.Td>
          <Table.Td style={{ whiteSpace: 'nowrap' }}>{`${totals.pw}:${totals.pl}`}</Table.Td>
          <Table.Td style={{ whiteSpace: 'nowrap' }}>{team_with_input.wins}</Table.Td>
          <Table.Td style={{ whiteSpace: 'nowrap' }}>{team_with_input.losses}</Table.Td>
        </Table.Tr>
      );
    });

  if (rows.length < 1)
    return <EmptyTableInfo entity_name={t('teams_title', { context: teamContext })} />;

  return (
    <TableLayoutLarge display_mode="presentation">
      <Table.Thead>
        <Table.Tr>
          <ThNotSortable>#</ThNotSortable>
          <ThNotSortable>{t('name_table_header')}</ThNotSortable>
          <ThNotSortable>{t('points_table_header')}</ThNotSortable>
          <ThNotSortable>{t('games_score_label')}</ThNotSortable>
          <ThNotSortable>{t('points_score_label')}</ThNotSortable>
          <ThNotSortable>{t('win_distribution_text_win')}</ThNotSortable>
          <ThNotSortable>{t('win_distribution_text_losses')}</ThNotSortable>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>{rows}</Table.Tbody>
    </TableLayoutLarge>
  );
}
