import { Grid, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import TeamCreateModal from '@components/modals/team_create_modal';
import { AddParticipant } from '@components/rating/add_participant';
import { getTableState } from '@components/tables/table';
import TeamsTable from '@components/tables/teams';
import { teamNamingContext } from '@components/utils/team_naming';
import { Pagination, capitalize, getTournamentIdFromRouter } from '@components/utils/util';
import { FullTeamWithPlayers } from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getTeamsPaginated, getTournamentById } from '@services/adapter';
import { getRatingCategories } from '@services/rating';

export default function TeamsPage() {
  const tableState = getTableState('created');
  const { t } = useTranslation();
  const { tournamentData } = getTournamentIdFromRouter();
  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const tournament = swrTournamentResponse.data != null ? swrTournamentResponse.data.data : null;
  const swrCategoriesResponse = getRatingCategories();
  const categories = swrCategoriesResponse.data != null ? swrCategoriesResponse.data.data : [];
  const categoryName =
    tournament != null && tournament.rating_category_id != null
      ? (categories.find((c) => c.id === tournament.rating_category_id)?.name ??
        `#${tournament.rating_category_id}`)
      : null;

  // Team order is fixed (headers aren't sortable): rating tournaments list by rating
  // (highest first), everything else by the manual order adjustable with the up/down
  // arrows on each row.
  const isRanking =
    tournament != null && tournament.is_individual && tournament.rating_category_id != null;
  const pagination: Pagination = {
    limit: tableState.pageSize,
    offset: tableState.pageSize * (tableState.page - 1),
    sort_by: isRanking ? 'rating' : 'sort_order',
    sort_direction: isRanking ? 'desc' : 'asc',
  };
  const swrTeamsResponse = getTeamsPaginated(tournamentData.id, pagination);

  const teams: FullTeamWithPlayers[] =
    swrTeamsResponse.data != null ? swrTeamsResponse.data.data.teams : [];
  const teamCount = swrTeamsResponse.data != null ? swrTeamsResponse.data.data.count : 1;

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <Grid justify="space-between" mb="1rem">
        <Grid.Col span="auto">
          <Title>{capitalize(t('teams_title', { context: teamNamingContext(tournament) }))}</Title>
        </Grid.Col>
        <Grid.Col span="content">
          <Grid align="flex-end">
            {tournament == null ||
            !(tournament.is_individual && tournament.rating_category_id != null) ? (
              <Grid.Col span="auto">
                <TeamCreateModal
                  swrTeamsResponse={swrTeamsResponse}
                  tournament_id={tournamentData.id}
                />
              </Grid.Col>
            ) : null}
          </Grid>
        </Grid.Col>
      </Grid>
      <TeamsTable
        swrTeamsResponse={swrTeamsResponse}
        tournamentData={tournamentData}
        tournament={tournament}
        categoryName={categoryName}
        teams={teams}
        tableState={tableState}
        teamCount={teamCount}
      />
      {tournament != null && tournament.is_individual && tournament.settled_seq == null ? (
        <AddParticipant
          tournamentId={tournamentData.id}
          swrTeamsResponse={swrTeamsResponse}
          rated={isRanking}
        />
      ) : null}
    </TournamentLayout>
  );
}
