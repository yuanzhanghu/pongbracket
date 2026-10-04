import {
  Table,
  Text,
  UnstyledButton,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { formatStageItemInput } from '@components/utils/stage_item_input';
import { MatchWithDetails, StageItemWithRounds } from '@openapi';

// A round-robin group as a cross table (方格表): one row and one column per
// participant, each off-diagonal cell holding that pairing's head-to-head result.
// Clicking a cell opens the score modal for the underlying match.
export function GroupGrid({
  stageItem,
  stageItemsLookup,
  openMatchModal,
}: {
  stageItem: StageItemWithRounds;
  stageItemsLookup: any;
  openMatchModal: ((match: MatchWithDetails) => void) | null;
}) {
  const { t } = useTranslation();
  const theme = useMantineTheme();
  const isDark = useComputedColorScheme('light') === 'dark';
  // Gridlines and the diagonal cell must flip with the colour scheme — a pure
  // black grid is invisible on the dark-mode background.
  const lineColor = isDark ? theme.colors.dark[0] : '#000';
  const diagonalBg = isDark ? theme.colors.dark[4] : theme.colors.gray[2];
  const diagonalFg = isDark ? theme.colors.dark[1] : theme.colors.gray[5];

  const inputs = (stageItem.inputs || []).filter((input: any) => input?.team != null);

  // Map each unordered pair of input ids to its match.
  const pairKey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`);
  const matchByPair: Record<string, MatchWithDetails> = {};
  // Per-input games (局分) won/lost totals across all of this group's matches.
  const gamesTotals: Record<number, { gw: number; gl: number }> = {};
  const ensureTotals = (i: number) => (gamesTotals[i] = gamesTotals[i] || { gw: 0, gl: 0 });
  ((stageItem as any).rounds || []).forEach((round: any) => {
    (round.matches || []).forEach((match: MatchWithDetails) => {
      const i1 = match.stage_item_input1_id;
      const i2 = match.stage_item_input2_id;
      if (i1 == null || i2 == null) return;
      matchByPair[pairKey(i1, i2)] = match;
      const s1 = match.stage_item_input1_score || 0;
      const s2 = match.stage_item_input2_score || 0;
      const t1 = ensureTotals(i1);
      const t2 = ensureTotals(i2);
      t1.gw += s1;
      t1.gl += s2;
      t2.gw += s2;
      t2.gl += s1;
    });
  });

  if (inputs.length < 2) return null;

  const winColor = theme.colors.green[6];
  const loseColor = theme.colors.red[6];
  const drawColor = theme.colors.gray[6];

  // Let each column shrink to exactly its content width (a score like "2:0") —
  // the table itself is width:auto, so no fixed cell width is forced. Every cell
  // carries an explicit black border so both the column and row gridlines show
  // clearly (Mantine's withRowBorders wasn't rendering the horizontal lines).
  const border = `1px solid ${lineColor}`;
  const cellStyle = {
    width: '1%',
    whiteSpace: 'nowrap' as const,
    textAlign: 'center' as const,
    border,
  };

  const headerCells = inputs.map((_input: any, index: number) => (
    <Table.Th key={index} style={cellStyle}>
      {index + 1}
    </Table.Th>
  ));

  const rows = inputs.map((rowInput: any, rowIdx: number) => {
    const cells = inputs.map((colInput: any, colIdx: number) => {
      if (rowIdx === colIdx) {
        return (
          <Table.Td
            key={colIdx}
            style={{
              ...cellStyle,
              backgroundColor: diagonalBg,
              color: diagonalFg,
            }}
          >
            ×
          </Table.Td>
        );
      }

      const match = matchByPair[pairKey(rowInput.id, colInput.id)];
      if (match == null) {
        return (
          <Table.Td key={colIdx} style={cellStyle} c="dimmed">
            {' '}
          </Table.Td>
        );
      }

      const rowIsInput1 = match.stage_item_input1_id === rowInput.id;
      const sRow = rowIsInput1 ? match.stage_item_input1_score : match.stage_item_input2_score;
      const sCol = rowIsInput1 ? match.stage_item_input2_score : match.stage_item_input1_score;
      const forfeit = (match as any).forfeit_input;

      let content: string;
      let color: string | undefined;
      if (forfeit != null) {
        const rowForfeited = forfeit === (rowIsInput1 ? 1 : 2);
        content = rowForfeited ? t('forfeit_loss_short') : t('forfeit_win_short');
        color = rowForfeited ? loseColor : winColor;
      } else if (sRow > 0 || sCol > 0) {
        content = `${sRow}:${sCol}`;
        color = sRow > sCol ? winColor : sRow < sCol ? loseColor : drawColor;
      } else {
        content = '—';
        color = undefined;
      }

      const inner = (
        <Text fw={700} c={color} ta="center" fz="sm">
          {content}
        </Text>
      );

      return (
        // Same padding whether or not the cell is clickable, so archiving (which
        // drops the score modal) doesn't grow every cell of the table.
        <Table.Td key={colIdx} style={cellStyle} p={2}>
          {openMatchModal ? (
            <UnstyledButton
              style={{ width: '100%', display: 'block' }}
              onClick={() => openMatchModal(match)}
            >
              {inner}
            </UnstyledButton>
          ) : (
            inner
          )}
        </Table.Td>
      );
    });

    const tot = gamesTotals[rowInput.id] || { gw: 0, gl: 0 };
    return (
      <Table.Tr key={rowIdx}>
        <Table.Td style={{ whiteSpace: 'nowrap', width: '1%', border }}>
          <Text fz="sm" truncate="end" maw="11rem">
            {`${rowIdx + 1}. ${formatStageItemInput(rowInput, stageItemsLookup)}`}
          </Text>
        </Table.Td>
        {cells}
        <Table.Td style={cellStyle}>
          <Text fw={700} fz="sm">
            {rowInput.points}
          </Text>
        </Table.Td>
        <Table.Td style={cellStyle}>
          <Text fz="sm">{`${tot.gw}:${tot.gl}`}</Text>
        </Table.Td>
      </Table.Tr>
    );
  });

  // Shrink-wrap: the inline-block wrapper collapses to the table's intrinsic
  // (content) width instead of letting the table stretch to 100% of the panel,
  // so the score columns end up exactly as wide as a "2:0" needs.
  return (
    <div style={{ display: 'inline-block', maxWidth: '100%', overflowX: 'auto' }}>
      <Table
        withTableBorder
        withColumnBorders
        borderColor={lineColor}
        highlightOnHover
        striped={false}
        fz="sm"
        horizontalSpacing={4}
        verticalSpacing={4}
        style={{ width: 'auto', borderCollapse: 'collapse' }}
      >
        <Table.Thead>
          <Table.Tr>
            <Table.Th style={{ width: '1%', border }} />
            {headerCells}
            <Table.Th style={cellStyle}>{t('points_table_header')}</Table.Th>
            <Table.Th style={cellStyle}>{t('games_score_label')}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>{rows}</Table.Tbody>
      </Table>
    </div>
  );
}
