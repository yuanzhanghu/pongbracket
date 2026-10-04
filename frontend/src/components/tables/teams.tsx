import { ActionIcon, Center, Group, Pagination, Stack, Table, Tooltip } from '@mantine/core';
import { MdArrowDownward } from '@react-icons/all-files/md/MdArrowDownward';
import { MdArrowUpward } from '@react-icons/all-files/md/MdArrowUpward';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import DeleteButton from '@components/buttons/delete';
import PlayerList from '@components/info/player_list';
import TeamUpdateModal from '@components/modals/team_update_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import RequestErrorAlert from '@components/utils/error_alert';
import { TableSkeletonSingleColumn } from '@components/utils/skeletons';
import { teamNamingContext } from '@components/utils/team_naming';
import { TournamentMinimal } from '@components/utils/tournament';
import { FullTeamWithPlayers, TeamsWithPlayersResponse, Tournament } from '@openapi';
import { deleteTeam, moveTeam } from '@services/team';
import TableLayout, { TableState, ThNotSortable } from './table';

// Score cell for individual rating tournaments: initial (PENDING) seeds carry a
// trailing *, official (ACTIVE) ratings don't, and an unset rating shows "—".
function ratingLabel(team: FullTeamWithPlayers): string {
  if (team.rating == null) return '—';
  return team.rating_status === 'ACTIVE' ? `${team.rating}` : `${team.rating}*`;
}

export default function TeamsTable({
  tournamentData,
  tournament,
  categoryName,
  swrTeamsResponse,
  teams,
  tableState,
  teamCount,
}: {
  tournamentData: TournamentMinimal;
  tournament?: Tournament | null;
  categoryName?: string | null;
  swrTeamsResponse: SWRResponse<TeamsWithPlayersResponse>;
  teams: FullTeamWithPlayers[];
  tableState: TableState;
  teamCount: number;
}) {
  const { t } = useTranslation();
  if (swrTeamsResponse.error) return <RequestErrorAlert error={swrTeamsResponse.error} />;

  if (swrTeamsResponse.isLoading) {
    return <TableSkeletonSingleColumn />;
  }

  // Only individual rating tournaments expose a per-participant rating column.
  const showRating =
    tournament != null && tournament.is_individual && tournament.rating_category_id != null;

  const teamContext = teamNamingContext(tournament);
  // A participant in an individual tournament is a single person, so it has no members.
  const showMembers = tournament == null || !tournament.is_individual;

  // Rating tournaments are ordered by rating and can't be reordered manually; every
  // other tournament can reorder teams with the up/down arrows (greyed out otherwise).
  const canReorder = tournament != null && !showRating;

  // Every column is sized here and the table gets that exact total width: with
  // `layout="fixed"` and the default full-width table, name and members would
  // otherwise each stretch to half the viewport. The action column stacks its two
  // buttons, so it only has to fit the wider single label ("Supprimer").
  const COLUMN_WIDTHS = { order: 80, actions: 145, name: 200, rating: 90, members: 200 };
  const tableWidth =
    COLUMN_WIDTHS.order +
    COLUMN_WIDTHS.actions +
    COLUMN_WIDTHS.name +
    (showRating ? COLUMN_WIDTHS.rating : 0) +
    (showMembers ? COLUMN_WIDTHS.members : 0);

  const totalPages = Math.max(1, Math.ceil(teamCount / tableState.pageSize));
  const isLastPage = tableState.page >= totalPages;

  const handleMove = async (teamId: number, direction: 'up' | 'down') => {
    await moveTeam(tournamentData.id, teamId, direction);
    await swrTeamsResponse.mutate();
  };

  // Order is fixed server-side (by rating or manual order), so render teams as returned.
  const rows = teams.map((team, index) => {
    const isFirst = tableState.page === 1 && index === 0;
    const isLast = isLastPage && index === teams.length - 1;
    return (
      <Table.Tr key={team.id}>
        <Table.Td>
          <Group gap="0.25rem" wrap="nowrap">
            <Tooltip label={t('move_up')} disabled={!canReorder}>
              <ActionIcon
                variant="default"
                size="md"
                disabled={!canReorder || isFirst}
                onClick={() => handleMove(team.id, 'up')}
                aria-label={t('move_up')}
              >
                <MdArrowUpward size={16} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label={t('move_down')} disabled={!canReorder}>
              <ActionIcon
                variant="default"
                size="md"
                disabled={!canReorder || isLast}
                onClick={() => handleMove(team.id, 'down')}
                aria-label={t('move_down')}
              >
                <MdArrowDownward size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Table.Td>
        <Table.Td>
          <Stack gap={4}>
            <TeamUpdateModal
              tournament_id={tournamentData.id}
              tournament={tournament}
              team={team}
              swrTeamsResponse={swrTeamsResponse}
            />
            <DeleteButton
              onClick={async () => {
                await deleteTeam(tournamentData.id, team.id);
                await swrTeamsResponse.mutate();
              }}
              title={t('delete_button')}
            />
          </Stack>
        </Table.Td>
        <Table.Td>{team.name}</Table.Td>
        {showRating ? <Table.Td>{ratingLabel(team)}</Table.Td> : null}
        {showMembers ? (
          <Table.Td>
            <PlayerList team={team} />
          </Table.Td>
        ) : null}
      </Table.Tr>
    );
  });

  if (rows.length < 1) return <NoContent title={t('no_teams_title', { context: teamContext })} />;

  return (
    <>
      <TableLayout w={tableWidth} horizontalSpacing="sm">
        <Table.Thead>
          <Table.Tr>
            <ThNotSortable w={COLUMN_WIDTHS.order}>{t('order_table_header')}</ThNotSortable>
            <ThNotSortable w={COLUMN_WIDTHS.actions}>{null}</ThNotSortable>
            <ThNotSortable w={COLUMN_WIDTHS.name}>{t('name_table_header')}</ThNotSortable>
            {showRating ? (
              <ThNotSortable w={COLUMN_WIDTHS.rating}>
                {categoryName ?? t('team_rating_table_header')}
              </ThNotSortable>
            ) : null}
            {showMembers ? (
              <ThNotSortable w={COLUMN_WIDTHS.members}>{t('members_table_header')}</ThNotSortable>
            ) : null}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>{rows}</Table.Tbody>
      </TableLayout>

      <Center mt="1rem">
        <Pagination
          value={tableState.page}
          onChange={tableState.setPage}
          total={1 + teamCount / tableState.pageSize}
          size="lg"
        />
      </Center>
    </>
  );
}
