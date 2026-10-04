import { Box, Button, Divider, Group, Modal, Stack, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import DeleteButton from '@components/buttons/delete';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { TournamentMinimal } from '@components/utils/tournament';
import {
  MatchBody,
  MatchWithDetails,
  RoundWithMatches,
  StagesWithStageItemsResponse,
} from '@openapi';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { deleteMatch, updateMatch } from '@services/match';

// Possible final results, expressed as the winner's games count. Score entry is a
// single tap on one of these — the match format (best-of) is no longer chosen and
// per-game points (小分) are not recorded, so games stay null and 小分 = 0.
const WINNER_GAMES = [2, 3, 4];

function MatchDeleteButton({
  tournamentData,
  match,
  swrStagesResponse,
  swrUpcomingMatchesResponse,
}: {
  tournamentData: TournamentMinimal;
  match: MatchWithDetails;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrUpcomingMatchesResponse: SWRResponse | null;
}) {
  const { t } = useTranslation();
  return (
    <DeleteButton
      fullWidth
      onClick={async () => {
        await deleteMatch(tournamentData.id, match.id);
        await swrStagesResponse.mutate();
        if (swrUpcomingMatchesResponse != null) await swrUpcomingMatchesResponse.mutate();
      }}
      style={{ marginTop: '1rem' }}
      size="sm"
      title={t('remove_match_button')}
    />
  );
}

function MatchModalForm({
  tournamentData,
  match,
  swrStagesResponse,
  swrUpcomingMatchesResponse,
  setOpened,
  round,
}: {
  tournamentData: TournamentMinimal;
  match: MatchWithDetails | null;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrUpcomingMatchesResponse: SWRResponse | null;
  setOpened: any;
  round: RoundWithMatches | null;
}) {
  if (match == null) {
    return null;
  }

  const { t } = useTranslation();
  const anyMatch = match as any;

  const stageItemsLookup = getStageItemLookup(swrStagesResponse);
  const matchesLookup = getMatchLookup(swrStagesResponse);
  const team1Name = formatMatchInput1(t, stageItemsLookup, matchesLookup, match);
  const team2Name = formatMatchInput2(t, stageItemsLookup, matchesLookup, match);

  const currentForfeit = anyMatch.forfeit_input != null ? Number(anyMatch.forfeit_input) : null;
  const score1 = Number(anyMatch.stage_item_input1_score) || 0;
  const score2 = Number(anyMatch.stage_item_input2_score) || 0;
  const hasScore = currentForfeit == null && (score1 > 0 || score2 > 0);

  // Persist a chosen result. Games are left null (no per-game points recorded), so the
  // match score is taken directly from these games-won counts.
  async function saveResult(s1: number, s2: number, forfeit: number | null) {
    if (match == null) return;
    const body: MatchBody = {
      round_id: match.round_id,
      stage_item_input1_score: s1,
      stage_item_input2_score: s2,
      court_id: match.court_id || null,
      custom_duration_minutes: anyMatch.custom_duration_minutes ?? null,
      custom_margin_minutes: anyMatch.custom_margin_minutes ?? null,
      games: null,
      best_of: Number(anyMatch.best_of) || 3,
      forfeit_input: forfeit,
    };
    // updateMatch swallows errors into a red toast and returns undefined; only
    // refresh and close the modal when the save actually succeeded, so a rejected
    // save (e.g. a settled, score-frozen tournament) doesn't look like it worked.
    const res: any = await updateMatch(tournamentData.id, match.id, body);
    if (res == null || res.status !== 200) return;
    await swrStagesResponse.mutate();
    if (swrUpcomingMatchesResponse != null) await swrUpcomingMatchesResponse.mutate();
    setOpened(false);
  }

  const ResultButton = ({ a, b }: { a: number; b: number }) => {
    const selected = hasScore && score1 === a && score2 === b;
    return (
      <Button
        variant={selected ? 'filled' : 'light'}
        color={selected ? 'green' : 'blue'}
        size="md"
        radius="md"
        w={68}
        px={0}
        onClick={() => saveResult(a, b, null)}
      >
        {`${a}:${b}`}
      </Button>
    );
  };

  return (
    <>
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap">
          <Text fw={700} size="md" truncate="end">
            {team1Name}
          </Text>
          <Text c="dimmed" size="sm">
            {t('versus_separator')}
          </Text>
          <Text fw={700} size="md" truncate="end" ta="right">
            {team2Name}
          </Text>
        </Group>

        <Divider my="xs" />

        <Box>
          <Text size="sm" c="dimmed" mb={6}>
            {t('result_team_wins', { name: team1Name })}
          </Text>
          <Group gap="xs">
            {WINNER_GAMES.flatMap((w) =>
              Array.from({ length: w }, (_, l) => <ResultButton key={`a-${w}-${l}`} a={w} b={l} />)
            )}
          </Group>
        </Box>

        <Box mt="sm">
          <Text size="sm" c="dimmed" mb={6}>
            {t('result_team_loses', { name: team1Name })}
          </Text>
          <Group gap="xs">
            {WINNER_GAMES.flatMap((w) =>
              Array.from({ length: w }, (_, l) => <ResultButton key={`b-${w}-${l}`} a={l} b={w} />)
            )}
          </Group>
        </Box>

        <Divider my="xs" label={t('forfeit_label')} labelPosition="center" />

        <Group gap="xs" grow>
          <Button
            variant={currentForfeit === 1 ? 'filled' : 'light'}
            color="red"
            size="sm"
            onClick={() => saveResult(0, 0, 1)}
          >
            {t('forfeit_option', { name: team1Name })}
          </Button>
          <Button
            variant={currentForfeit === 2 ? 'filled' : 'light'}
            color="red"
            size="sm"
            onClick={() => saveResult(0, 0, 2)}
          >
            {t('forfeit_option', { name: team2Name })}
          </Button>
        </Group>

        {(hasScore || currentForfeit != null) && (
          <Button variant="subtle" color="gray" size="sm" onClick={() => saveResult(0, 0, null)}>
            {t('clear_score_button')}
          </Button>
        )}
      </Stack>

      {round && round.is_draft && (
        <MatchDeleteButton
          swrStagesResponse={swrStagesResponse}
          swrUpcomingMatchesResponse={swrUpcomingMatchesResponse}
          tournamentData={tournamentData}
          match={match}
        />
      )}
    </>
  );
}

export default function MatchModal({
  tournamentData,
  match,
  swrStagesResponse,
  swrUpcomingMatchesResponse,
  opened,
  setOpened,
  round,
}: {
  tournamentData: TournamentMinimal;
  match: MatchWithDetails | null;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrUpcomingMatchesResponse: SWRResponse | null;
  opened: boolean;
  setOpened: any;
  round: RoundWithMatches | null;
}) {
  const { t } = useTranslation();

  return (
    <>
      <Modal opened={opened} onClose={() => setOpened(false)} title={t('edit_match_modal_title')}>
        <MatchModalForm
          swrStagesResponse={swrStagesResponse}
          swrUpcomingMatchesResponse={swrUpcomingMatchesResponse}
          tournamentData={tournamentData}
          match={match}
          setOpened={setOpened}
          round={round}
        />
      </Modal>
    </>
  );
}
