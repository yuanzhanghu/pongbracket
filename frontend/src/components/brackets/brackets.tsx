import {
  Alert,
  Button,
  Center,
  Container,
  Grid,
  Group,
  Skeleton,
  Stack,
  Switch,
  Title,
} from '@mantine/core';
import { GoPlus } from '@react-icons/all-files/go/GoPlus';
import { IoOptions } from '@react-icons/all-files/io5/IoOptions';
import { IconAlertCircle } from '@tabler/icons-react';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { MdOutlineAutoFixHigh } from 'react-icons/md';
import { SWRResponse } from 'swr';

import { NoContent } from '@components/no_content/empty_table_info';
import { BracketDisplaySettings } from '@components/utils/brackets';
import { TournamentMinimal } from '@components/utils/tournament';
import { Translator } from '@components/utils/types';
import { responseIsValid } from '@components/utils/util';
import {
  RoundWithMatches,
  StageItemWithRounds,
  StagesWithStageItemsResponse,
  Tournament,
} from '@openapi';
import { createRound } from '@services/round';
import classes from './brackets.module.css';
import Match from './match';
import RoundComponent from './round';

function AddRoundButton({
  t,
  tournamentData,
  stageItem,
  swrStagesResponse,
  swrUpcomingMatchesResponse,
  size,
}: {
  t: Translator;
  tournamentData: TournamentMinimal;
  stageItem: StageItemWithRounds;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrUpcomingMatchesResponse: SWRResponse | null;
  size: 'md' | 'lg';
}) {
  return (
    <Button
      color="green"
      size={size}
      leftSection={<GoPlus size={24} />}
      variant="outline"
      onClick={async () => {
        await createRound(tournamentData.id, stageItem.id);
        await swrStagesResponse.mutate();
        if (swrUpcomingMatchesResponse != null) await swrUpcomingMatchesResponse.mutate();
      }}
    >
      {t('add_round_button')}
    </Button>
  );
}

export function RoundsGridCols({
  stageItem,
  tournamentData,
  swrStagesResponse,
  swrUpcomingMatchesResponse,
  readOnly,
  displaySettings,
}: {
  stageItem: StageItemWithRounds;
  tournamentData: Tournament;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrUpcomingMatchesResponse: SWRResponse | null;
  readOnly: boolean;
  displaySettings: BracketDisplaySettings;
}) {
  const { t } = useTranslation();

  if (swrStagesResponse.isLoading) {
    return <LoadingSkeleton />;
  }
  if (!responseIsValid(swrStagesResponse)) {
    return <NoRoundsAlert readOnly={readOnly} />;
  }

  let result: React.JSX.Element[] | React.JSX.Element = stageItem.rounds
    .sort((r1: any, r2: any) => (r1.name > r2.name ? 1 : -1))
    .filter(
      (round: RoundWithMatches) =>
        round.matches.length > 0 || displaySettings.matchVisibility === 'all'
    )
    .map((round: RoundWithMatches) => (
      <RoundComponent
        key={round.id}
        tournamentData={tournamentData}
        round={round}
        swrStagesResponse={swrStagesResponse}
        swrUpcomingMatchesResponse={swrUpcomingMatchesResponse}
        readOnly={readOnly}
        displaySettings={displaySettings}
      />
    ));

  if (result.length < 1) {
    if (stageItem.rounds.length < 1) {
      result = (
        <Container mt="1rem">
          <Stack align="center">
            <NoContent title={t('no_round_description')} />
            {stageItem.rounds.length < 1 && (
              <AddRoundButton
                t={t}
                tournamentData={tournamentData}
                stageItem={stageItem}
                swrStagesResponse={swrStagesResponse}
                swrUpcomingMatchesResponse={swrUpcomingMatchesResponse}
                size="lg"
              />
            )}
          </Stack>
        </Container>
      );
    } else {
      result = (
        <Container mt="1rem">
          <Stack align="center">
            <NoContent title={t('no_round_found_title')} />
          </Stack>
        </Container>
      );
    }
  }

  const hideAddRoundButton = tournamentData == null || readOnly;

  return (
    <React.Fragment key={stageItem.id}>
      <div style={{ width: '100%' }}>
        <Grid grow>
          <Grid.Col span={6} mb="2rem">
            <Group>
              <Center>
                <Switch
                  size="md"
                  onLabel={<MdOutlineAutoFixHigh size={16} />}
                  offLabel={<IoOptions size={16} />}
                  checked={displaySettings.showManualSchedulingOptions === 'false'}
                  label={
                    displaySettings.showManualSchedulingOptions === 'true'
                      ? t('manual_scheduling_switch_label')
                      : t('automatic_scheduling_switch_label')
                  }
                  color="indigo"
                  onChange={(event) => {
                    displaySettings.setShowManualSchedulingOptions(
                      event.currentTarget.checked ? 'false' : 'true'
                    );
                  }}
                  miw="9rem"
                />
              </Center>
            </Group>
          </Grid.Col>
          <Grid.Col span={6}>
            <Group justify="right">
              {hideAddRoundButton ||
              displaySettings.showManualSchedulingOptions === 'false' ? null : (
                <AddRoundButton
                  t={t}
                  tournamentData={tournamentData}
                  stageItem={stageItem}
                  swrStagesResponse={swrStagesResponse}
                  swrUpcomingMatchesResponse={swrUpcomingMatchesResponse}
                  size="md"
                />
              )}
            </Group>
          </Grid.Col>
        </Grid>
      </div>
      <Group align="top">{result}</Group>
    </React.Fragment>
  );
}

// Name an elimination round by its size rather than "Round 01/02…": a round with
// N matches is the 1/N决赛 (32 matches → 1/32决赛, 4 → 1/4决赛, 2 → 1/2决赛), and the
// single-match round is the 决赛 (final).
function eliminationRoundName(t: Translator, matchCount: number): string {
  if (matchCount <= 1) return t('final_round_name');
  return t('fraction_round_name', { count: matchCount });
}

export function EliminationBracket({
  stageItem,
  tournamentData,
  swrStagesResponse,
  readOnly = true,
  onClickFrozen,
}: {
  stageItem: StageItemWithRounds;
  tournamentData: TournamentMinimal;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  readOnly?: boolean;
  // Forwarded to each Match so a frozen (settled) bracket surfaces the freeze
  // notification on click, consistent with the RR GroupGrid cell path.
  onClickFrozen?: () => void;
}) {
  const { t } = useTranslation();

  // Each round is a column (Round 01 = round of N, then halving to the final). Match cells
  // reuse the normal match formatting, so they show seed placeholders ("1st of A组",
  // "BYE") before activation and real names + scores after.
  const rounds = [...stageItem.rounds].sort((r1, r2) => (r1.name > r2.name ? 1 : -1));
  if (rounds.length < 1) {
    return <NoContent title={t('no_round_found_title')} />;
  }

  return (
    <div className={classes.bracket}>
      {rounds.map((round) => {
        // Group matches into the pairs that each feed one next-round match. Equal-height
        // columns + flex:1 pairs/slots place every match at its bracket position, so a
        // match lands centred between the two previous-round matches that feed it.
        const pairs: (typeof round.matches)[] = [];
        for (let i = 0; i < round.matches.length; i += 2) {
          pairs.push(round.matches.slice(i, i + 2));
        }
        return (
          <div key={round.id} className={classes.round}>
            <Title order={4} className={classes.title}>
              {eliminationRoundName(t, round.matches.length)}
            </Title>
            <div className={classes.matches}>
              {pairs.map((pair, pairIndex) => (
                <div key={pairIndex} className={classes.pair}>
                  {pair.map((match) => (
                    <div key={match.id} className={classes.slot}>
                      <Match
                        tournamentData={tournamentData}
                        swrStagesResponse={swrStagesResponse}
                        swrUpcomingMatchesResponse={null}
                        match={match}
                        round={round}
                        readOnly={readOnly}
                        onClickFrozen={onClickFrozen}
                      />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function NoRoundsAlert({ readOnly }: { readOnly: boolean }) {
  const { t } = useTranslation();
  if (readOnly) {
    return (
      <Alert
        icon={<IconAlertCircle size={16} />}
        title={t('no_round_found_title')}
        color="blue"
        radius="lg"
      >
        {t('no_round_found_description')}
      </Alert>
    );
  }
  return (
    <Container>
      <Alert
        icon={<IconAlertCircle size={16} />}
        title={t('no_round_found_title')}
        color="blue"
        radius="lg"
      >
        {t('no_round_found_in_stage_description')}
      </Alert>
    </Container>
  );
}

function LoadingSkeleton() {
  return (
    <Group>
      <div style={{ width: '400px', marginLeft: '1rem' }}>
        <Skeleton height={500} mb="xl" radius="xl" />
      </div>
      <div style={{ width: '400px', marginLeft: '1rem' }}>
        <Skeleton height={500} mb="xl" radius="xl" />
      </div>
    </Group>
  );
}
