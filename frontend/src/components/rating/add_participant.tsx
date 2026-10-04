import { Button, Fieldset, Group, Select, Text } from '@mantine/core';
import { IconUserPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { handleRequestError } from '@services/adapter';
import { addParticipant, getAddableParticipants } from '@services/rating';

/**
 * Owner-side direct add for an individual tournament: pick from accounts that have
 * already trusted the owner (`addable-participants`). In a rated tournament a
 * participant must be a registered account (no free-text team names), so this picker
 * is the only owner-side way to add someone; in a non-rated tournament the owner can
 * also create teams by name via the 添加队伍 button. Everyone else can self-apply.
 */
export function AddParticipant({
  tournamentId,
  swrTeamsResponse,
  rated,
}: {
  tournamentId: number;
  swrTeamsResponse: SWRResponse<any>;
  rated: boolean;
}) {
  const { t } = useTranslation();
  const swrAddable = getAddableParticipants(tournamentId);
  const addable = swrAddable.data != null ? swrAddable.data.data : [];
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <Fieldset legend={t('add_participant_legend')} mt="lg" radius="md">
      <Text fz="sm" c="dimmed" mb="sm">
        {rated ? t('add_participant_description_rated') : t('add_participant_description_unrated')}
      </Text>
      {addable.length < 1 ? (
        <Text fz="sm" c="dimmed">
          {t('no_addable_accounts')}
        </Text>
      ) : (
        <Group align="flex-end">
          <Select
            label={t('select_account_to_add_label')}
            placeholder={t('search_by_name_or_email_placeholder')}
            searchable
            data={addable.map((p: any) => ({
              value: `${p.user_id}`,
              label: p.name,
            }))}
            value={selected}
            onChange={setSelected}
            limit={25}
            style={{ minWidth: 320 }}
          />
          <Button
            color="green"
            leftSection={<IconUserPlus size={18} />}
            disabled={selected == null}
            onClick={async () => {
              if (selected == null) return;
              await addParticipant(tournamentId, Number(selected)).catch((exc: any) =>
                handleRequestError(exc)
              );
              setSelected(null);
              await Promise.all([swrAddable.mutate(), swrTeamsResponse.mutate()]);
            }}
          >
            {t('add_button')}
          </Button>
        </Group>
      )}
    </Fieldset>
  );
}
