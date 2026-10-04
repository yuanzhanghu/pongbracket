import { Autocomplete, Button, Checkbox, Modal, TagsInput, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconUsersPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import SaveButton from '@components/buttons/save';
import { useTeamNamingContext } from '@components/utils/team_naming';
import { TeamsWithPlayersResponse } from '@openapi';
import { handleRequestError } from '@services/adapter';
import { addParticipant, getAddableParticipants } from '@services/rating';
import { createTeam } from '@services/team';

function TeamForm({
  tournament_id,
  swrTeamsResponse,
  setOpened,
}: {
  tournament_id: number;
  swrTeamsResponse: SWRResponse<TeamsWithPlayersResponse>;
  setOpened: any;
}) {
  const { t } = useTranslation();
  const teamContext = useTeamNamingContext(tournament_id);
  const isIndividual = teamContext === 'individual';

  // In an individual tournament the name is a person, so it completes from the accounts
  // the owner may add directly: users who trust them, and every account for a site admin
  // (`addable-participants`, which only exists for individual tournaments).
  const swrAddable = getAddableParticipants(isIndividual ? tournament_id : null);
  const addable: { user_id: number; name: string }[] =
    swrAddable.data != null ? swrAddable.data.data : [];

  // Picking a suggestion binds that account to the tournament instead of creating a
  // name-only row. Two accounts sharing a name cannot be told apart in a free-text box,
  // so such a name binds nothing and falls back to a name-only participant — the
  // 直接添加参赛者 picker below the table keys on the account itself and still handles it.
  const userIdByName = new Map<string, number | null>();
  addable.forEach((participant) => {
    userIdByName.set(
      participant.name,
      userIdByName.has(participant.name) ? null : participant.user_id
    );
  });

  const form = useForm({
    initialValues: {
      name: '',
      active: true,
      player_names: [] as string[],
    },
    validate: {
      name: (value) => (value.length > 0 ? null : t('too_short_name_validation')),
    },
  });

  const nameInputProps = {
    withAsterisk: true,
    label: t('name_input_label'),
    placeholder: t('team_name_input_placeholder', { context: teamContext }),
    ...form.getInputProps('name'),
  };

  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        const userId = userIdByName.get(values.name.trim()) ?? null;
        if (userId != null) {
          await addParticipant(tournament_id, userId).catch((exc: any) => handleRequestError(exc));
        } else {
          await createTeam(tournament_id, values.name, values.active, values.player_names);
        }
        await Promise.all([swrTeamsResponse.mutate(), swrAddable.mutate()]);
        setOpened(false);
      })}
    >
      {isIndividual ? (
        <Autocomplete {...nameInputProps} data={addable.map((p) => p.name)} limit={25} />
      ) : (
        <TextInput {...nameInputProps} />
      )}

      <Checkbox
        mt="md"
        label={t('active_teams_checkbox_label', { context: teamContext })}
        {...form.getInputProps('active', { type: 'checkbox' })}
      />

      {/* A participant in an individual tournament is one person: it has no members. */}
      {teamContext == null ? (
        <TagsInput
          label={t('team_member_select_title')}
          placeholder={t('team_member_select_placeholder')}
          mt={12}
          {...form.getInputProps('player_names')}
        />
      ) : null}
      <Button fullWidth style={{ marginTop: 10 }} color="green" type="submit">
        {t('save_button')}
      </Button>
    </form>
  );
}

export default function TeamCreateModal({
  tournament_id,
  swrTeamsResponse,
}: {
  tournament_id: number;
  swrTeamsResponse: SWRResponse<TeamsWithPlayersResponse>;
}) {
  const { t } = useTranslation();
  const teamContext = useTeamNamingContext(tournament_id);
  const [opened, setOpened] = useState(false);
  return (
    <>
      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title={t('create_team_modal_title', { context: teamContext })}
      >
        <TeamForm
          swrTeamsResponse={swrTeamsResponse}
          tournament_id={tournament_id}
          setOpened={setOpened}
        />
      </Modal>

      <SaveButton
        onClick={() => setOpened(true)}
        leftSection={<IconUsersPlus size={24} />}
        title={t('add_team_button', { context: teamContext })}
        mb={0}
      />
    </>
  );
}
