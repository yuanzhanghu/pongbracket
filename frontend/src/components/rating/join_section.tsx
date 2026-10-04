import { Alert, Badge, Button, Checkbox, Group, Stack } from '@mantine/core';
import { useForm } from '@mantine/form';
import { showNotification } from '@mantine/notifications';
import { IconCheck, IconInfoCircle, IconLogout } from '@tabler/icons-react';
import { Trans, useTranslation } from 'react-i18next';

import { handleRequestError } from '@services/adapter';
import { tokenPresent } from '@services/local_storage';
import { getMyJoinStatus, leaveTournament, requestToJoin } from '@services/rating';

export function JoinSection({ tournamentId }: { tournamentId: number }) {
  // Only logged-in visitors can join.
  if (!tokenPresent()) {
    return null;
  }

  const { t } = useTranslation();
  const swrJoinStatus = getMyJoinStatus(tournamentId);
  const status = swrJoinStatus.data != null ? swrJoinStatus.data.data : null;

  const form = useForm({
    initialValues: { trust_creator: false },
  });

  // Wait for status before deciding — avoids briefly flashing the 参赛 form on a
  // tournament that has already started or isn't joinable.
  if (status == null) {
    return null;
  }

  // Already participating: confirm membership and offer self opt-out only while
  // the leave window is open (not started, not settled).
  if (status.is_participant) {
    return (
      <Group justify="center" my="md">
        <Badge color="green" size="lg">
          {t('already_joined_badge')}
        </Badge>
        {status.can_leave ? (
          <Button
            size="xs"
            variant="outline"
            color="red"
            leftSection={<IconLogout size={16} />}
            onClick={async () => {
              const response = await leaveTournament(tournamentId).catch((exc: any) => {
                handleRequestError(exc);
                return null;
              });
              if ((response as any)?.status === 200 || (response as any)?.status === 201) {
                showNotification({
                  color: 'green',
                  title: t('left_tournament_title'),
                  message: '',
                  icon: <IconCheck />,
                });
                await swrJoinStatus.mutate();
              }
            }}
          >
            {t('leave_tournament_button')}
          </Button>
        ) : null}
      </Group>
    );
  }

  // Not joinable right now (team/non-rated tournament, already started, or
  // settled): show nothing — no 参赛 button, no 信任创建者 option.
  if (!status.can_join) {
    return null;
  }

  return (
    <Group justify="center" my="md">
      <Stack style={{ maxWidth: '48rem', width: '100%' }} px="1rem">
        <Alert icon={<IconInfoCircle size={16} />} color="blue" radius="md">
          <Trans i18nKey="join_alert_description" components={{ strong: <strong /> }} />
        </Alert>
        <form
          onSubmit={form.onSubmit(async (values) => {
            const response = await requestToJoin(tournamentId, values.trust_creator).catch(
              (exc: any) => {
                handleRequestError(exc);
                return null;
              }
            );
            if ((response as any)?.status === 200 || (response as any)?.status === 201) {
              showNotification({
                color: 'green',
                title: t('joined_tournament_title'),
                message: t('joined_tournament_message'),
                icon: <IconCheck />,
              });
              await swrJoinStatus.mutate();
            }
          })}
        >
          <Checkbox
            label={t('trust_creator_checkbox_label')}
            {...form.getInputProps('trust_creator', { type: 'checkbox' })}
          />
          <Button mt="md" type="submit" color="green">
            {t('join_tournament_button')}
          </Button>
        </form>
      </Stack>
    </Group>
  );
}
