import { Anchor, Badge, Button, Fieldset, Group, Stack, Text } from '@mantine/core';
import { showNotification } from '@mantine/notifications';
import { IconCheck } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { Tournament } from '@openapi';
import { handleRequestError } from '@services/adapter';
import { getSettlementStatus, settlementRequest } from '@services/rating';

export function SettlementSection({ tournament }: { tournament: Tournament }) {
  const { t } = useTranslation();
  const swrStatus = getSettlementStatus(tournament.id);
  const status = swrStatus.data != null ? swrStatus.data.data : null;

  if (tournament.rating_category_id == null) {
    return null;
  }

  const alreadySettled = tournament.settled_seq != null;
  // The owner already requested settlement; it's parked in the admin queue.
  const requested = status != null && status.settlement_requested === true;

  return (
    <Fieldset legend={t('rating_settlement_legend')} mt="lg" radius="md">
      <Stack gap="sm">
        <Anchor href={`/rating/${tournament.rating_category_id}/leaderboard`} fz="sm">
          {t('view_rating_leaderboard_link')}
        </Anchor>
        {alreadySettled ? (
          <Group gap="xs">
            <Badge color="green">{t('settled_badge')}</Badge>
            <Text fz="sm">{t('settlement_seq_label', { seq: tournament.settled_seq })}</Text>
          </Group>
        ) : requested ? (
          <Group gap="xs">
            <Badge color="yellow">{t('settlement_pending_admin_badge')}</Badge>
            <Text fz="sm" c="dimmed">
              {t('settlement_already_requested_description')}
            </Text>
          </Group>
        ) : (
          <Text fz="sm" c="dimmed">
            {status != null ? status.message : t('settlement_not_requested_description')}
          </Text>
        )}

        {status != null && !alreadySettled && !requested && status.pending_review_count > 0 ? (
          <Text fz="sm" c="orange">
            {t('settlement_pending_review_count', { count: status.pending_review_count })}
          </Text>
        ) : null}

        {!alreadySettled && !requested ? (
          <Button
            color="green"
            leftSection={<IconCheck size={20} />}
            onClick={async () => {
              const response = await settlementRequest(tournament.id).catch((exc: any) => {
                handleRequestError(exc);
                return null;
              });
              await swrStatus.mutate();

              const result = (response as any)?.data?.data;
              if (result != null) {
                showNotification({
                  color: result.status === 'SETTLED' ? 'green' : 'yellow',
                  title:
                    result.status === 'SETTLED'
                      ? t('settled_with_seq', { seq: result.settled_seq })
                      : t('settlement_submitted_pending_review'),
                  message: result.message,
                  icon: <IconCheck />,
                });
              }
            }}
          >
            {t('request_settlement_button')}
          </Button>
        ) : null}
      </Stack>
    </Fieldset>
  );
}
