import useSWR, { SWRResponse } from 'swr';

import { ShowcaseResponse } from '@openapi';
import { createAxios, handleRequestError } from './adapter';

const fetcher = (url: string) =>
  createAxios()
    .get(url)
    .then((res: { data: any }) => res.data);

/** The Ra drop-in series with its placements. Public: works without a login. */
export function getShowcase(): SWRResponse<ShowcaseResponse> {
  return useSWR('showcase', fetcher);
}

/** Correct one tournament's placement; an empty list restores the automatic one. */
export async function updateShowcaseRanking(tournament_id: number, team_ids: number[]) {
  return createAxios()
    .put(`tournaments/${tournament_id}/showcase-ranking`, { team_ids })
    .catch((response: any) => {
      handleRequestError(response);
      return response;
    });
}
