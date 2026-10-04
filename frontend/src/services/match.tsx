import { showNotification } from '@mantine/notifications';

import { MatchBody, MatchRescheduleBody } from '@openapi';
import i18n from '../../i18n';
import { createAxios, handleRequestError } from './adapter';

export async function deleteMatch(tournament_id: number, match_id: number) {
  return createAxios()
    .delete(`tournaments/${tournament_id}/matches/${match_id}`)
    .catch((response: any) => handleRequestError(response));
}

export async function updateMatch(tournament_id: number, match_id: number, match: MatchBody) {
  return createAxios()
    .put(`tournaments/${tournament_id}/matches/${match_id}`, match)
    .catch((response: any) => handleRequestError(response));
}

export async function rescheduleMatch(
  tournament_id: number,
  match_id: number,
  match: MatchRescheduleBody
) {
  return createAxios()
    .post(`tournaments/${tournament_id}/matches/${match_id}/reschedule`, match)
    .catch((response: any) => handleRequestError(response))
    .then((response: any) => {
      if (response != null && response.status === 200) {
        showNotification({
          color: 'green',
          title: i18n.t('match_rescheduled_title'),
          message: '',
        });
      }
    });
}

export async function scheduleMatches(tournament_id: number) {
  return createAxios()
    .post(`tournaments/${tournament_id}/schedule_matches`)
    .catch((response: any) => handleRequestError(response));
}
