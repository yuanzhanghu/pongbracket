import {
  Button,
  Center,
  Checkbox,
  Fieldset,
  Image,
  Modal,
  NumberInput,
  TagsInput,
  Text,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { BiEditAlt } from '@react-icons/all-files/bi/BiEditAlt';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { DropzoneButton } from '@components/utils/file_upload';
import { teamNamingContext } from '@components/utils/team_naming';
import { FullTeamWithPlayers, TeamsWithPlayersResponse, Tournament } from '@openapi';
import { getBaseApiUrl, removeTeamLogo, requestSucceeded } from '@services/adapter';
import { seedTeamRating } from '@services/rating';
import { updateTeam } from '@services/team';

function TeamLogo({ team }: { team: FullTeamWithPlayers | null }) {
  const { t } = useTranslation();
  if (team == null || team.logo_path == null) return null;
  return (
    <Image
      radius="md"
      alt={t('team_logo_alt')}
      src={`${getBaseApiUrl()}/static/team-logos/${team.logo_path}`}
    />
  );
}

export default function TeamUpdateModal({
  tournament_id,
  tournament,
  team,
  swrTeamsResponse,
}: {
  tournament_id: number;
  tournament?: Tournament | null;
  team: FullTeamWithPlayers;
  swrTeamsResponse: SWRResponse<TeamsWithPlayersResponse>;
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);

  // Initial-rating preset lives in the edit modal for individual rating
  // tournaments. An ACTIVE (official) rating can't be reseeded; a PENDING/unset
  // one can, until the tournament is settled.
  const isRatedIndividual =
    tournament != null && tournament.is_individual && tournament.rating_category_id != null;
  const teamContext = teamNamingContext(tournament);
  const ratingActive = team.rating_status === 'ACTIVE';
  const showSeed = isRatedIndividual && tournament?.settled_seq == null;

  const form = useForm({
    initialValues: {
      name: team.name,
      active: team.active,
      player_names: team.players.map((player) => player.name),
      rating: team.rating ?? ('' as number | string),
    },

    validate: {
      name: (value) => (value.length > 0 ? null : t('too_short_name_validation')),
    },
  });

  return (
    <>
      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title={t('edit_team_title', { context: teamContext })}
      >
        <form
          onSubmit={form.onSubmit(async (values) => {
            const result = await updateTeam(
              tournament_id,
              team.id,
              values.name,
              values.active,
              values.player_names
            );
            if (!requestSucceeded(result)) {
              return;
            }
            // Persist the initial rating (if editable and provided).
            if (showSeed && !ratingActive && values.rating !== '' && values.rating != null) {
              const parsed =
                typeof values.rating === 'string' ? parseFloat(values.rating) : values.rating;
              if (!Number.isNaN(parsed)) {
                await seedTeamRating(tournament_id, team.id, parsed);
              }
            }
            await swrTeamsResponse.mutate();
            setOpened(false);
          })}
        >
          <TextInput
            withAsterisk
            label={t('name_input_label')}
            placeholder={t('team_name_input_placeholder', { context: teamContext })}
            {...form.getInputProps('name')}
          />

          <Checkbox
            mt="md"
            label={t('active_team_checkbox_label', { context: teamContext })}
            {...form.getInputProps('active', { type: 'checkbox' })}
          />

          {/* A participant in an individual tournament is one person: it has no members.
              The names already on the team stay untouched — the form still submits them. */}
          {teamContext == null ? (
            <TagsInput
              label={t('team_member_select_title')}
              placeholder={t('team_member_select_placeholder')}
              mt={12}
              {...form.getInputProps('player_names')}
            />
          ) : null}

          {showSeed ? (
            <Fieldset legend={t('initial_rating_title')} mt={12} radius="md">
              {ratingActive ? (
                <Text fz="sm">{t('official_rating_locked_note', { rating: team.rating })}</Text>
              ) : (
                <NumberInput
                  label={t('initial_rating_input_label')}
                  placeholder={t('initial_rating_input_placeholder')}
                  min={0}
                  max={4000}
                  {...form.getInputProps('rating')}
                />
              )}
            </Fieldset>
          ) : null}

          <Fieldset legend={t('logo_settings_title')} mt={12} radius="md">
            <DropzoneButton
              tournamentId={tournament_id}
              teamId={team.id}
              swrResponse={swrTeamsResponse}
              variant="team"
            />
            <Center my="lg">
              <div style={{ width: '50%' }}>
                <TeamLogo team={team} />
              </div>
            </Center>
            <Button
              variant="outline"
              color="red"
              fullWidth
              onClick={async () => {
                await removeTeamLogo(tournament_id, team.id);
                await swrTeamsResponse.mutate();
              }}
            >
              {t('remove_logo')}
            </Button>
          </Fieldset>

          <Button fullWidth style={{ marginTop: 10 }} color="green" type="submit">
            {t('save_button')}
          </Button>
        </form>
      </Modal>

      <Button
        color="green"
        size="xs"
        onClick={() => setOpened(true)}
        leftSection={<BiEditAlt size={20} />}
      >
        {t('edit_button')}
      </Button>
    </>
  );
}
