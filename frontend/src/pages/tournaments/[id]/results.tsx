import { Button, Container, Group, Stack, Table, Tabs, Text, Title } from '@mantine/core';
import { showNotification } from '@mantine/notifications';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { EliminationBracket } from '@components/brackets/brackets';
import PlayerList from '@components/info/player_list';
import MatchModal from '@components/modals/match_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { JoinSection } from '@components/rating/join_section';
import { GroupGrid } from '@components/tables/group_grid';
import { StandingsContent } from '@components/tables/standings_content';
import { FavoriteButton } from '@components/utils/favorite_button';
import { teamNamingContext } from '@components/utils/team_naming';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import { MatchWithDetails } from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getStages, getTeams, getTournamentById, getUser } from '@services/adapter';
import { tokenPresent } from '@services/local_storage';
import { getStageItemLookup } from '@services/lookups';
import { updateMatch } from '@services/match';
import { getMyJoinStatus } from '@services/rating';

// The only account that gets the "fill random scores" helper button.
const RANDOM_SCORES_ACCOUNT = 'test6@ai1to1.com';

export default function ResultsPage() {
  const [modalOpened, modalSetOpened] = useState(false);
  const [match, setMatch] = useState<MatchWithDetails | null>(null);
  const [fillingScores, setFillingScores] = useState(false);

  const { t } = useTranslation();
  const { tournamentData } = getTournamentIdFromRouter();
  // Spectators (not logged in) can view a tournament the owner marked public.
  // They only get published rounds (no drafts) and a read-only view.
  const isAnonymous = !tokenPresent();
  const swrStagesResponse = getStages(tournamentData.id, isAnonymous);
  const swrUserResponse = getUser();
  const showFillRandomScores = swrUserResponse.data?.data?.email === RANDOM_SCORES_ACCOUNT;
  // Only club members and authorised scorers may edit scores. Everyone else
  // (spectators, plain participants/followers) gets a read-only view.
  const swrJoinStatus = getMyJoinStatus(isAnonymous ? null : tournamentData.id);
  const canRecord = swrJoinStatus.data?.data?.can_record === true;
  // The 关注 (follow) and 申请参赛 / 信任创建者 (join) affordances are spectator
  // tools — hide them for the tournament's own owner/manager.
  const canManage = swrJoinStatus.data?.data?.can_manage === true;
  const swrTournament = getTournamentById(tournamentData.id);
  const tournament = swrTournament.data != null ? swrTournament.data.data : null;
  // A settled tournament has its scores frozen on the backend (the match update
  // would 400). Treat it as non-editable so we never open a fill modal that can
  // only fail.
  const isFrozen = tournament != null && (tournament as any).settled_seq != null;
  // An archived tournament rejects every write (`disallow_archived_tournament`),
  // so it reads as a plain record: no scoring hint, no clickable cells. Unlike a
  // settled tournament there is nothing to explain on click — the page simply
  // offers no way in.
  const isArchived = tournament != null && (tournament as any).status === 'ARCHIVED';
  const canEditScores = canRecord && !isArchived;

  // Participant list for the spectator-facing tab. The teams endpoint is open on
  // a public tournament, so non-organisers (and anonymous visitors) can see
  // who is competing. Individual tournaments use single-person teams, so the
  // team name IS the participant — the members column only adds information for
  // team tournaments. Must stay above the early return below (hook order).
  const swrTeamsResponse = getTeams(tournamentData.id === -1 ? undefined : tournamentData.id);
  const teams: any[] = swrTeamsResponse.data?.data?.teams ?? [];
  const showMembersColumn = tournament != null && !tournament.is_individual;
  // Rating column, same convention as the organiser's teams table: only rating
  // tournaments have one; an official (ACTIVE) rating shows as-is, an
  // organiser-configured initial seed (PENDING) carries a trailing *, and no
  // rating at all shows "-".
  const showRatingColumn =
    tournament != null &&
    tournament.is_individual &&
    (tournament as any).rating_category_id != null;
  // 赛前积分: before settlement this is the account's current rating (PENDING
  // seeds carry a *); after settlement it is the ledger's pre-event rating.
  const preRatingLabel = (team: any): string => {
    if (isFrozen && team.settled_pre_rating != null) return `${team.settled_pre_rating}`;
    if (team.rating == null) return '-';
    return team.rating_status === 'ACTIVE' ? `${team.rating}` : `${team.rating}*`;
  };
  // 结算后积分 (+/-delta): only once the tournament is settled; '-' before that.
  const settledRatingCell = (team: any) => {
    if (!isFrozen || team.settled_post_rating == null || team.settled_pre_rating == null) {
      return '-';
    }
    const delta = team.settled_post_rating - team.settled_pre_rating;
    const deltaText = delta >= 0 ? `+${delta}` : `${delta}`;
    return (
      <>
        {team.settled_post_rating}{' '}
        <Text component="span" fz="sm" c={delta > 0 ? 'green' : delta < 0 ? 'red' : 'dimmed'}>
          ({deltaText})
        </Text>
      </>
    );
  };
  // Participants are listed by 赛前积分; once settled, by 结算后积分.
  const sortedTeams = [...teams].sort((a: any, b: any) => {
    const key = (team: any) => (isFrozen ? (team.settled_post_rating ?? -1) : (team.rating ?? -1));
    return key(b) - key(a);
  });

  const stageItemsLookup = responseIsValid(swrStagesResponse)
    ? getStageItemLookup(swrStagesResponse)
    : [];

  if (!responseIsValid(swrStagesResponse)) return null;

  function openMatchModal(matchToOpen: MatchWithDetails) {
    // Only members/scorers may edit scores; everyone else views read-only.
    if (!canEditScores) return;
    // Frozen (settled) tournament: report the error up front instead of opening a
    // fill modal whose save would be rejected.
    if (isFrozen) {
      showNotification({
        color: 'red',
        title: t('scores_frozen_title'),
        message: t('scores_frozen_message'),
        autoClose: 6000,
      });
      return;
    }
    setMatch(matchToOpen);
    modalSetOpened(true);
  }

  function modalSetOpenedAndUpdateMatch(opened: boolean) {
    if (!opened) {
      setMatch(null);
    }
    modalSetOpened(opened);
  }

  // Fill every unplayed match (both sides known, no score yet) with a random
  // games-won result. Per-game points (小分) are not recorded.
  async function fillRandomScores() {
    setFillingScores(true);
    try {
      const stageItems: any[] = Object.values(stageItemsLookup);
      const matches: any[] = stageItems.flatMap((si: any) =>
        (si.rounds || []).flatMap((r: any) => r.matches || [])
      );
      for (const m of matches) {
        if (m.stage_item_input1?.team == null || m.stage_item_input2?.team == null) continue;
        if (m.stage_item_input1_score > 0 || m.stage_item_input2_score > 0) continue;
        const winnerGames = Math.floor(m.best_of / 2) + 1 || 2;
        const loserGames = Math.floor(Math.random() * winnerGames);
        const firstWins = Math.random() < 0.5;
        // eslint-disable-next-line no-await-in-loop
        await updateMatch(tournamentData.id, m.id, {
          round_id: m.round_id,
          games: null,
          best_of: m.best_of,
          forfeit_input: null,
          stage_item_input1_score: firstWins ? winnerGames : loserGames,
          stage_item_input2_score: firstWins ? loserGames : winnerGames,
          court_id: m.court_id || null,
          custom_duration_minutes: m.custom_duration_minutes,
          custom_margin_minutes: m.custom_margin_minutes,
        });
      }
      await swrStagesResponse.mutate();
    } finally {
      setFillingScores(false);
    }
  }

  // Keep stage order (stages come back ordered by creation, so the group stage
  // precedes the elimination stage) — never reorder by name.
  const stageItems: any[] =
    swrStagesResponse.data?.data?.flatMap((stage: any) => stage.stage_items) ?? [];

  return (
    // Results is the universally-viewable (spectator/participant) page, so it
    // always allows non-managers — never gate or redirect it.
    <TournamentLayout tournament_id={tournamentData.id} allowAnonymous>
      <MatchModal
        swrStagesResponse={swrStagesResponse}
        swrUpcomingMatchesResponse={null}
        tournamentData={tournamentData}
        match={match}
        opened={modalOpened}
        setOpened={modalSetOpenedAndUpdateMatch}
        round={null}
      />
      {/* The header breadcrumb shows the tournament name only from the md
          breakpoint up (_layout.tsx hides it on smaller screens), so narrow
          screens render the name here instead of a page title. */}
      <Group justify="flex-end" wrap="nowrap">
        <Title order={2} hiddenFrom="md" mr="auto">
          {tournament != null ? tournament.name : ''}
        </Title>
        <Group>
          {!canManage ? <FavoriteButton tournamentId={tournamentData.id} /> : null}
          {showFillRandomScores ? (
            <Button loading={fillingScores} variant="outline" onClick={fillRandomScores}>
              {t('fill_random_scores_button')}
            </Button>
          ) : null}
        </Group>
      </Group>
      {tournament != null && tournament.is_individual && !canManage ? (
        <JoinSection tournamentId={tournamentData.id} />
      ) : null}
      <Tabs defaultValue="results" mt="md">
        <Tabs.List>
          <Tabs.Tab value="results">{t('results_title')}</Tabs.Tab>
          <Tabs.Tab value="standings">{t('rankings_title')}</Tabs.Tab>
          <Tabs.Tab value="participants">{t('participants_tab_title')}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="results" pt="md">
          {canEditScores && stageItems.length > 0 ? (
            <Text fw={700} mb="md">
              {t('tap_cell_to_score_hint')}
            </Text>
          ) : null}
          {stageItems.length < 1 ? (
            <NoContent title={t('no_round_found_title')} />
          ) : (
            <Stack gap="xl">
              {stageItems.map((si: any) => (
                <div key={si.id}>
                  <Title order={3} mb="sm">
                    {si.name}
                  </Title>
                  {si.type === 'SINGLE_ELIMINATION' ? (
                    <EliminationBracket
                      stageItem={si}
                      tournamentData={tournamentData}
                      swrStagesResponse={swrStagesResponse}
                      readOnly={!canEditScores || isFrozen}
                      onClickFrozen={
                        isFrozen
                          ? () =>
                              showNotification({
                                color: 'red',
                                title: t('scores_frozen_title'),
                                message: t('scores_frozen_message'),
                                autoClose: 6000,
                              })
                          : undefined
                      }
                    />
                  ) : (
                    <GroupGrid
                      stageItem={si}
                      stageItemsLookup={stageItemsLookup}
                      openMatchModal={canEditScores ? openMatchModal : null}
                    />
                  )}
                </div>
              ))}
            </Stack>
          )}
        </Tabs.Panel>
        <Tabs.Panel value="standings" pt="md">
          {/* The standings table inherits its font size (TableLayoutLarge uses
              fontSize: 'inherit'); pin it to the same sm size as the plain
              Mantine table in the participants tab. */}
          <Container px="0rem" style={{ fontSize: 'var(--mantine-font-size-sm)' }}>
            <StandingsContent
              swrStagesResponse={swrStagesResponse}
              fontSizeInPixels={16}
              maxTeamsToDisplay={100}
              teamContext={teamNamingContext(tournament)}
            />
          </Container>
        </Tabs.Panel>
        <Tabs.Panel value="participants" pt="md">
          {teams.length < 1 ? (
            <NoContent title={t('no_participants_title')} />
          ) : (
            <Table striped highlightOnHover maw="40rem">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w="3rem">#</Table.Th>
                  <Table.Th>{t('name_table_header')}</Table.Th>
                  {showRatingColumn ? <Table.Th>{t('rating_table_header')}</Table.Th> : null}
                  {showRatingColumn ? (
                    <Table.Th>{t('settled_rating_table_header')}</Table.Th>
                  ) : null}
                  {showMembersColumn ? <Table.Th>{t('members_table_header')}</Table.Th> : null}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sortedTeams.map((team: any, index: number) => (
                  <Table.Tr key={team.id}>
                    <Table.Td>{index + 1}</Table.Td>
                    <Table.Td>{team.name}</Table.Td>
                    {showRatingColumn ? <Table.Td>{preRatingLabel(team)}</Table.Td> : null}
                    {showRatingColumn ? <Table.Td>{settledRatingCell(team)}</Table.Td> : null}
                    {showMembersColumn ? (
                      <Table.Td>
                        <PlayerList team={team} />
                      </Table.Td>
                    ) : null}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Tabs.Panel>
      </Tabs>
    </TournamentLayout>
  );
}
