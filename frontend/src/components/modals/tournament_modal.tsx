import {
  Button,
  Checkbox,
  Grid,
  Image,
  Modal,
  NumberInput,
  Select,
  TextInput,
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { GoPlus } from '@react-icons/all-files/go/GoPlus';
import { IconCalendar, IconCalendarTime } from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import SaveButton from '@components/buttons/save';
import { assert_not_none } from '@components/utils/assert';
import { Club, Tournament, TournamentsResponse } from '@openapi';
import { getBaseApiUrl, getClubs } from '@services/adapter';
import { getRatingCategories } from '@services/rating';
import { createTournament } from '@services/tournament';
import dayjs from 'dayjs';

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

function GeneralTournamentForm({
  setOpened,
  swrTournamentsResponse,
  clubs,
}: {
  setOpened: any;
  swrTournamentsResponse: SWRResponse<TournamentsResponse>;
  clubs: Club[];
}) {
  const { t } = useTranslation();
  const ratingCategories = getRatingCategories().data?.data ?? [];
  const form = useForm({
    initialValues: {
      start_time: dayjs(),
      name: '',
      club_id: null,
      dashboard_public: true,
      players_can_be_in_multiple_teams: false,
      auto_assign_courts: true,
      duration_minutes: 10,
      margin_minutes: 5,
      is_individual: true,
      rated: false,
      rating_category_id: null as string | null,
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

  // Clubs are implicit: a tournament is always created under the user's own
  // (hidden) personal club, so the club is auto-selected and never shown.
  useEffect(() => {
    if (clubs.length > 0 && form.values.club_id == null) {
      form.setFieldValue('club_id', `${clubs[0].id}` as any);
    }
  }, [clubs]);

  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        // Only individual tournaments may be rated; settings are fixed at creation.
        const ratingCategoryId =
          values.is_individual && values.rated
            ? values.rating_category_id != null
              ? parseInt(values.rating_category_id, 10)
              : (ratingCategories[0]?.id ?? null)
            : null;
        await createTournament(
          parseInt(assert_not_none(values.club_id as unknown as string), 10),
          values.name,
          values.dashboard_public,
          values.players_can_be_in_multiple_teams,
          values.auto_assign_courts,
          values.start_time,
          values.duration_minutes,
          values.margin_minutes,
          values.is_individual,
          ratingCategoryId
        );
        await swrTournamentsResponse.mutate();
        setOpened(false);
      })}
    >
      <TextInput
        withAsterisk
        label={t('name_input_label')}
        placeholder={t('tournament_name_input_placeholder')}
        {...form.getInputProps('name')}
      />

      <Grid mt="1rem">
        <Grid.Col span={{ sm: 9 }}>
          <DateTimePicker
            leftSection={<IconCalendar size="1.1rem" stroke={1.5} />}
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
            {t('now_button')}
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

      <Checkbox
        mt="md"
        label={t('individual_tournament_checkbox_label')}
        description={t('individual_tournament_checkbox_description')}
        {...form.getInputProps('is_individual', { type: 'checkbox' })}
        onChange={(event) => {
          const checked = event.currentTarget.checked;
          form.setFieldValue('is_individual', checked);
          if (checked) {
            form.setFieldValue('players_can_be_in_multiple_teams', false);
          } else {
            form.setFieldValue('rated', false);
            form.setFieldValue('rating_category_id', null);
          }
        }}
      />
      {form.values.is_individual && (
        <Checkbox
          mt="md"
          label={t('rated_checkbox_label')}
          description={t('rated_checkbox_description')}
          {...form.getInputProps('rated', { type: 'checkbox' })}
          onChange={(event) => {
            const checked = event.currentTarget.checked;
            form.setFieldValue('rated', checked);
            form.setFieldValue(
              'rating_category_id',
              checked && ratingCategories[0] != null ? `${ratingCategories[0].id}` : null
            );
          }}
        />
      )}
      {form.values.is_individual && form.values.rated && (
        <Select
          mt="md"
          label={t('rating_category_label')}
          data={ratingCategories.map((c) => ({ value: `${c.id}`, label: c.name }))}
          {...form.getInputProps('rating_category_id')}
        />
      )}

      <Checkbox
        mt="md"
        label={t('dashboard_public_description')}
        {...form.getInputProps('dashboard_public', { type: 'checkbox' })}
      />
      {/* Team members are a team-tournament concept; an individual participant is
          one person, so the setting has nothing to apply to. */}
      {!form.values.is_individual && (
        <Checkbox
          mt="md"
          label={t('miscellaneous_label')}
          {...form.getInputProps('players_can_be_in_multiple_teams', { type: 'checkbox' })}
        />
      )}
      <Checkbox
        mt="md"
        label={t('auto_assign_courts_label')}
        {...form.getInputProps('auto_assign_courts', { type: 'checkbox' })}
      />

      <Button fullWidth mt={8} color="green" type="submit">
        {t('save_button')}
      </Button>
    </form>
  );
}

export default function TournamentModal({
  swrTournamentsResponse,
}: {
  swrTournamentsResponse: SWRResponse<TournamentsResponse>;
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);
  const operation_text = t('create_tournament_button');
  const swrClubsResponse = getClubs();
  const clubs = swrClubsResponse.data?.data || [];

  return (
    <>
      <Modal opened={opened} onClose={() => setOpened(false)} title={operation_text} size="50rem">
        <GeneralTournamentForm
          setOpened={setOpened}
          swrTournamentsResponse={swrTournamentsResponse}
          clubs={clubs}
        />
      </Modal>
      <SaveButton
        mx="0px"
        fullWidth
        onClick={() => setOpened(true)}
        leftSection={<GoPlus size={24} />}
        title={operation_text}
      />
    </>
  );
}
