import {
  Alert,
  Button,
  Center,
  Checkbox,
  Container,
  CopyButton,
  Divider,
  Fieldset,
  Grid,
  Image,
  NumberInput,
  SimpleGrid,
  Text,
  TextInput,
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { showNotification } from '@mantine/notifications';
import { MdDelete } from '@react-icons/all-files/md/MdDelete';
import { MdUnarchive } from '@react-icons/all-files/md/MdUnarchive';
import {
  IconCalendar,
  IconCalendarTime,
  IconCheck,
  IconCopy,
  IconPencil,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { MdArchive } from 'react-icons/md';
import { useNavigate } from 'react-router';
import { SWRResponse } from 'swr';

import { ScorersManager } from '@components/rating/scorers_manager';
import { SettlementSection } from '@components/rating/settlement_section';
import { assert_not_none } from '@components/utils/assert';
import { DropzoneButton } from '@components/utils/file_upload';
import { GenericSkeletonThreeRows } from '@components/utils/skeletons';
import { getBaseURL, getTournamentIdFromRouter } from '@components/utils/util';
import { Tournament, TournamentResponse } from '@openapi';
import NotFoundTitle from '@pages/404';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import {
  getBaseApiUrl,
  getTournamentById,
  handleRequestError,
  removeTournamentLogo,
} from '@services/adapter';
import { getMyJoinStatus, getRatingCategories } from '@services/rating';
import {
  archiveTournament,
  deleteTournament,
  unarchiveTournament,
  updateTournament,
} from '@services/tournament';
import dayjs from 'dayjs';

// Organizer-facing hint: whether new players can currently discover and join
// this tournament from the 可以参赛的比赛 tab, and if not, why.
function JoinWindowInfo({ tournament }: { tournament: Tournament }) {
  const { t } = useTranslation();
  const swrJoinStatus = getMyJoinStatus(tournament.id);
  const hasMatches = swrJoinStatus.data?.data?.has_matches === true;

  if (!tournament.is_individual) return null;

  const reasons: string[] = [];
  if (tournament.status === 'ARCHIVED') reasons.push(t('join_closed_reason_archived'));
  if (tournament.settled_seq != null) reasons.push(t('join_closed_reason_settled'));
  if (hasMatches) reasons.push(t('join_closed_reason_has_matches'));
  if (dayjs(tournament.start_time).isBefore(dayjs().startOf('day')))
    reasons.push(t('join_closed_reason_date_passed'));
  if (!tournament.dashboard_public)
    reasons.push(
      t('join_closed_reason_not_public', { setting: t('dashboard_public_description') })
    );

  if (reasons.length === 0) {
    return (
      <Alert color="green" title={t('join_window_open_title')} mt="lg" radius="md">
        {t('join_window_open_description', { tab: t('joinable_tournaments_tab_title') })}
      </Alert>
    );
  }
  return (
    <Alert color="orange" title={t('join_window_closed_title')} mt="lg" radius="md">
      {reasons.map((reason) => (
        <Text fz="sm" key={reason}>
          · {reason}
        </Text>
      ))}
    </Alert>
  );
}

function RatingSettingsInfo({ tournament }: { tournament: Tournament }) {
  const { t } = useTranslation();
  const swrCategoriesResponse = getRatingCategories();
  const categories = swrCategoriesResponse.data != null ? swrCategoriesResponse.data.data : [];
  const category = categories.find((c) => c.id === tournament.rating_category_id);

  return (
    <Fieldset legend={t('rating_settings_title')} mt="lg" radius="md">
      <Text fz="sm" c="dimmed" mb="md">
        {t('rating_settings_description')}
      </Text>
      <Text fz="sm">
        {t('rating_settings_type_line', {
          type: tournament.is_individual
            ? t('tournament_type_individual')
            : t('tournament_type_team'),
        })}
      </Text>
      <Text fz="sm" mt="xs">
        {tournament.rating_category_id != null
          ? t('rating_settings_rated_yes', {
              category: category != null ? category.name : tournament.rating_category_id,
            })
          : t('rating_settings_rated_no')}
      </Text>
    </Fieldset>
  );
}

export function TournamentLogo({ tournament }: { tournament: Tournament | null }) {
  const { t } = useTranslation();
  if (tournament == null || tournament.logo_path == null) return null;
  return (
    <Image
      radius="md"
      alt={t('tournament_logo_alt')}
      src={`${getBaseApiUrl()}/static/tournament-logos/${tournament.logo_path}`}
    />
  );
}

function ArchiveTournamentButton({
  t,
  tournament,
  swrTournamentResponse,
}: {
  t: any;
  tournament: Tournament;
  swrTournamentResponse: SWRResponse<TournamentResponse>;
}) {
  return (
    <Button
      variant="outline"
      mt="sm"
      color="orange"
      size="lg"
      leftSection={<MdArchive size={36} />}
      onClick={async () => {
        await archiveTournament(tournament.id).catch((response: any) =>
          handleRequestError(response)
        );
        await swrTournamentResponse.mutate();
      }}
    >
      {t('archive_tournament_button')}
    </Button>
  );
}

function UnarchiveTournamentButton({
  t,
  tournament,
  swrTournamentResponse,
}: {
  t: any;
  tournament: Tournament;
  swrTournamentResponse: SWRResponse<TournamentResponse>;
}) {
  return (
    <Button
      variant="outline"
      mt="sm"
      color="orange"
      size="lg"
      leftSection={<MdUnarchive size={36} />}
      onClick={async () => {
        await unarchiveTournament(tournament.id).catch((response: any) =>
          handleRequestError(response)
        );
        await swrTournamentResponse.mutate();
      }}
    >
      {t('unarchive_tournament_button')}
    </Button>
  );
}

function GeneralTournamentForm({
  tournament,
  swrTournamentResponse,
}: {
  tournament: Tournament;
  swrTournamentResponse: SWRResponse<TournamentResponse>;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const form = useForm({
    initialValues: {
      start_time: dayjs(tournament.start_time),
      name: tournament.name,
      club_id: `${tournament.club_id}`,
      dashboard_public: tournament.dashboard_public,
      players_can_be_in_multiple_teams: tournament.players_can_be_in_multiple_teams,
      auto_assign_courts: tournament.auto_assign_courts,
      duration_minutes: tournament.duration_minutes,
      margin_minutes: tournament.margin_minutes,
    },

    validate: {
      name: (value) => (value.length > 0 ? null : t('too_short_name_validation')),
      club_id: (value) => (value != null ? null : t('club_choose_title')),
      start_time: (value) => (value != null ? null : t('start_time_choose_title')),
      duration_minutes: (value) =>
        value != null && value > 0 ? null : t('duration_minutes_choose_title'),
      margin_minutes: (value) =>
        value != null && value > 0 ? null : t('margin_minutes_choose_title'),
    },
  });

  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        assert_not_none(values.club_id);

        const response = await updateTournament(
          tournament.id,
          values.name,
          values.dashboard_public,
          values.players_can_be_in_multiple_teams,
          values.auto_assign_courts,
          dayjs(values.start_time).toISOString(),
          values.duration_minutes,
          values.margin_minutes
        );

        await swrTournamentResponse.mutate();

        if ((response as any)?.status === 200) {
          showNotification({
            color: 'green',
            title: t('tournament_saved_title'),
            message: '',
            icon: <IconCheck />,
          });
        }
      })}
    >
      <TextInput
        withAsterisk
        label={t('name_input_label')}
        placeholder={t('tournament_name_input_placeholder')}
        {...form.getInputProps('name')}
      />

      {/* Clubs are implicit (one hidden personal club per account); the club binding
          stays in the form values but is not user-editable. */}
      <Fieldset legend={t('planning_of_matches_legend')} mt="lg" radius="md">
        <Text fz="sm">{t('planning_of_matches_description')}</Text>
        <Grid>
          <Grid.Col span={{ sm: 9 }}>
            <DateTimePicker
              rightSection={<IconCalendar size="1.1rem" stroke={1.5} />}
              mx="auto"
              {...form.getInputProps('start_time')}
            />
          </Grid.Col>
          <Grid.Col span={{ sm: 3 }}>
            <Button
              fullWidth
              color="indigo"
              leftSection={<IconCalendarTime size="1.1rem" stroke={1.5} />}
              onClick={() => {
                form.setFieldValue('start_time', dayjs());
              }}
            >
              {t('set_to_new_button')}
            </Button>
          </Grid.Col>
        </Grid>

        <Grid>
          <Grid.Col span={{ sm: 6 }}>
            <NumberInput
              label={t('match_duration_label')}
              mt="lg"
              {...form.getInputProps('duration_minutes')}
            />
          </Grid.Col>
          <Grid.Col span={{ sm: 6 }}>
            <NumberInput
              label={t('time_between_matches_label')}
              mt="lg"
              {...form.getInputProps('margin_minutes')}
            />
          </Grid.Col>
        </Grid>
      </Fieldset>
      <Fieldset legend={t('share_settings_title')} mt="lg" radius="md">
        <Text fz="sm">{t('share_link_label')}</Text>
        <Grid>
          <Grid.Col span={{ sm: 9 }}>
            <TextInput readOnly value={`${getBaseURL()}/tournaments/${tournament.id}/results`} />
          </Grid.Col>
          <Grid.Col span={{ sm: 3 }}>
            <CopyButton value={`${getBaseURL()}/tournaments/${tournament.id}/results`}>
              {({ copied, copy }) => (
                <Button
                  leftSection={<IconCopy size="1.1rem" stroke={1.5} />}
                  fullWidth
                  color={copied ? 'teal' : 'indigo'}
                  onClick={copy}
                >
                  {copied ? t('copied_url_button') : t('copy_url_button')}
                </Button>
              )}
            </CopyButton>
          </Grid.Col>
        </Grid>

        <Checkbox
          mt="lg"
          label={t('dashboard_public_description')}
          {...form.getInputProps('dashboard_public', { type: 'checkbox' })}
        />

        <DropzoneButton
          tournamentId={tournament.id}
          swrResponse={swrTournamentResponse}
          variant="tournament"
        />
        <Center my="lg">
          <div style={{ width: '50%' }}>
            <TournamentLogo tournament={tournament} />
          </div>
        </Center>
        <Button
          variant="outline"
          color="red"
          fullWidth
          onClick={async () => {
            await removeTournamentLogo(tournament.id);
            await swrTournamentResponse.mutate();
          }}
        >
          {t('remove_logo')}
        </Button>
      </Fieldset>
      <Fieldset legend={t('miscellaneous_title')} mt="lg" radius="md">
        {/* Team members are a team-tournament concept; an individual participant is
            one person, so the setting has nothing to apply to. */}
        {!tournament.is_individual ? (
          <Checkbox
            label={t('miscellaneous_label')}
            {...form.getInputProps('players_can_be_in_multiple_teams', { type: 'checkbox' })}
          />
        ) : null}
        <Checkbox
          mt="md"
          label={t('auto_assign_courts_label')}
          {...form.getInputProps('auto_assign_courts', { type: 'checkbox' })}
        />
      </Fieldset>

      <Button
        fullWidth
        mt={24}
        size="md"
        color="green"
        type="submit"
        leftSection={<IconPencil size={36} />}
      >
        {t('save_button')}
      </Button>

      <Divider mt="2rem" mb="1rem" size="2px" />
      {/* Single column on phones: side-by-side buttons clip their labels at 390px. */}
      <SimpleGrid cols={{ base: 1, xs: 2 }}>
        <Button
          variant="outline"
          mt="sm"
          color="red"
          size="lg"
          leftSection={<MdDelete size={36} />}
          onClick={async () => {
            await deleteTournament(tournament.id)
              .then(async () => {
                await navigate('/');
              })
              .catch((response: any) => handleRequestError(response));
          }}
        >
          {t('delete_tournament_button')}
        </Button>

        {tournament.status === 'OPEN' ? (
          <ArchiveTournamentButton
            tournament={tournament}
            t={t}
            swrTournamentResponse={swrTournamentResponse}
          />
        ) : (
          <UnarchiveTournamentButton
            tournament={tournament}
            t={t}
            swrTournamentResponse={swrTournamentResponse}
          />
        )}
      </SimpleGrid>
    </form>
  );
}

export default function SettingsPage() {
  const { tournamentData } = getTournamentIdFromRouter();
  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const tournamentDataFull =
    swrTournamentResponse.data != null ? swrTournamentResponse.data.data : null;

  let content = <NotFoundTitle />;

  if (swrTournamentResponse.isLoading) {
    content = <GenericSkeletonThreeRows />;
  }

  if (tournamentDataFull != null) {
    content = (
      <>
        <JoinWindowInfo tournament={tournamentDataFull} />
        <GeneralTournamentForm
          tournament={tournamentDataFull}
          swrTournamentResponse={swrTournamentResponse}
        />
        <RatingSettingsInfo tournament={tournamentDataFull} />
        <SettlementSection tournament={tournamentDataFull} />
        <ScorersManager tournamentId={tournamentDataFull.id} />
      </>
    );
  }

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <Container>{content}</Container>
    </TournamentLayout>
  );
}
