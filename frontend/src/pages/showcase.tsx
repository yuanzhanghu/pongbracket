import {
  ActionIcon,
  Anchor,
  Button,
  Container,
  Group,
  Modal,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconChevronDown, IconChevronUp, IconPencil } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { NoContent } from '@components/no_content/empty_table_info';
import { DateOnly } from '@components/utils/datetime';
import { GenericSkeletonThreeRows } from '@components/utils/skeletons';
import { ShowcaseEntry, ShowcaseParticipant } from '@openapi';
import Layout from '@pages/_layout';
import { getShowcase, updateShowcaseRanking } from '@services/showcase';

// The table always has the same ten placement columns; a smaller evening leaves the
// tail empty, a bigger one is cut off after the tenth place.
const PLACES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

/**
 * Reorder the participants of one tournament by hand.
 *
 * A drop-in evening is often called before the last matches are played, so the
 * standings the scores produce are not always the result everyone went home with.
 */
function RankingEditorModal({
  entry,
  onClose,
  onSaved,
}: {
  entry: ShowcaseEntry | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  // Start from what the page shows, with anyone missing from it (a participant who
  // played no match) appended, so every name can be dragged into place.
  const initialOrder = (): ShowcaseParticipant[] => {
    if (entry == null) return [];
    const ranked = entry.ranking.map((participant) => participant.team_id);
    return [
      ...entry.ranking,
      ...entry.participants.filter((participant) => !ranked.includes(participant.team_id)),
    ];
  };
  const [order, setOrder] = useState<ShowcaseParticipant[]>(initialOrder);
  const [saving, setSaving] = useState(false);

  function move(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= order.length) return;
    const next = [...order];
    [next[index], next[target]] = [next[target], next[index]];
    setOrder(next);
  }

  async function save(team_ids: number[]) {
    if (entry == null) return;
    setSaving(true);
    try {
      await updateShowcaseRanking(entry.tournament_id, team_ids);
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal opened={entry != null} onClose={onClose} title={t('showcase_edit_title')}>
      <Text c="dimmed" fz="sm" mb="md">
        {t('showcase_edit_hint')}
      </Text>
      <Stack gap="xs">
        {order.map((participant, index) => (
          <Group key={participant.team_id} justify="space-between" wrap="nowrap">
            <Text>{`${index + 1}. ${participant.name}`}</Text>
            <Group gap={4} wrap="nowrap">
              <ActionIcon
                variant="default"
                disabled={index === 0}
                onClick={() => move(index, -1)}
                aria-label={t('move_up')}
              >
                <IconChevronUp size={16} />
              </ActionIcon>
              <ActionIcon
                variant="default"
                disabled={index === order.length - 1}
                onClick={() => move(index, 1)}
                aria-label={t('move_down')}
              >
                <IconChevronDown size={16} />
              </ActionIcon>
            </Group>
          </Group>
        ))}
      </Stack>
      <Group justify="space-between" mt="lg">
        <Button
          variant="subtle"
          color="gray"
          loading={saving}
          disabled={!entry?.is_manual}
          onClick={() => save([])}
        >
          {t('showcase_reset_button')}
        </Button>
        <Button
          loading={saving}
          onClick={() => save(order.map((participant) => participant.team_id))}
        >
          {t('save_button')}
        </Button>
      </Group>
    </Modal>
  );
}

export default function ShowcasePage() {
  const { t } = useTranslation();
  const swrShowcase = getShowcase();
  const entries: ShowcaseEntry[] = swrShowcase.data?.data ?? [];
  const [editing, setEditing] = useState<ShowcaseEntry | null>(null);

  const rows = entries.map((entry) => (
    <Table.Tr key={entry.tournament_id}>
      <Table.Td style={{ whiteSpace: 'nowrap' }}>
        <Group gap="xs" wrap="nowrap">
          <Tooltip label={entry.name}>
            {/* Anchor carries its own md font size; inherit so the date reads exactly
                like the names beside it whatever size the table is set to. */}
            <Anchor
              component={Link}
              to={`/tournaments/${entry.tournament_id}/results`}
              fz="inherit"
            >
              <DateOnly datetime={entry.start_time} />
            </Anchor>
          </Tooltip>
          {entry.can_manage ? (
            <ActionIcon
              variant="subtle"
              color="gray"
              onClick={() => setEditing(entry)}
              aria-label={t('edit_button')}
            >
              <IconPencil size={16} />
            </ActionIcon>
          ) : null}
        </Group>
      </Table.Td>
      {PLACES.map((place) => {
        const participant = entry.ranking[place - 1];
        if (participant == null && place === 1 && !entry.has_automatic_ranking) {
          return (
            <Table.Td key={place} c="dimmed" fz="sm">
              {t('showcase_unsupported_format')}
            </Table.Td>
          );
        }
        return (
          <Table.Td key={place} style={{ whiteSpace: 'nowrap' }}>
            {participant?.name ?? ''}
          </Table.Td>
        );
      })}
    </Table.Tr>
  ));

  return (
    <Layout>
      <Container size="xl" px="xs">
        <Title order={2} mb="xs">
          {t('showcase_title')}
        </Title>
        <Text c="dimmed" mb="lg">
          {t('showcase_subtitle')}
        </Text>
        {swrShowcase.isLoading ? (
          <GenericSkeletonThreeRows />
        ) : entries.length < 1 ? (
          <NoContent title={t('showcase_no_tournaments')} />
        ) : (
          <Table.ScrollContainer minWidth={0} scrollAreaProps={{ type: 'auto' }}>
            {/* type auto keeps the horizontal scrollbar on screen whenever the table is
                wider than the page, rather than Mantine's default of showing it only
                while the pointer is over the table — on a phone that bar is the only
                hint that places six to ten are off to the right. */}
            {/* Shrink-wrap: with width auto every column is only as wide as the longest
                name in it, instead of the table stretching across the page and spreading
                the leftover width over ten columns. Narrow screens scroll instead. */}
            <Table
              striped
              highlightOnHover
              withTableBorder
              horizontalSpacing={6}
              fz="sm"
              style={{ width: 'auto' }}
            >
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('date_table_header')}</Table.Th>
                  {PLACES.map((place) => (
                    <Table.Th key={place}>{place}</Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>{rows}</Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Container>
      <RankingEditorModal
        // Remount per tournament, so the editor's list starts from the row clicked.
        key={editing?.tournament_id ?? 'none'}
        entry={editing}
        onClose={() => setEditing(null)}
        onSaved={() => swrShowcase.mutate()}
      />
    </Layout>
  );
}
