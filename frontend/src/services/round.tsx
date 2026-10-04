import { createAxios, handleRequestError } from './adapter';

export async function createRound(tournament_id: number, stage_item_id: number) {
  return createAxios()
    .post(`tournaments/${tournament_id}/rounds`, {
      stage_item_id,
    })
    .catch((response: any) => handleRequestError(response));
}

export async function deleteRound(tournament_id: number, round_id: number) {
  return createAxios()
    .delete(`tournaments/${tournament_id}/rounds/${round_id}`)
    .catch((response: any) => handleRequestError(response));
}

export async function updateRound(
  tournament_id: number,
  round_id: number,
  name: string,
  is_draft: boolean
) {
  return createAxios()
    .put(`tournaments/${tournament_id}/rounds/${round_id}`, { name, is_draft })
    .catch((response: any) => handleRequestError(response));
}
