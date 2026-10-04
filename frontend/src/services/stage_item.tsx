import { createAxios, handleRequestError } from './adapter';

export async function createStageItem(
  tournament_id: number,
  stage_id: number,
  type: string,
  team_count: number
) {
  return createAxios()
    .post(`tournaments/${tournament_id}/stage_items`, { stage_id, type, team_count })
    .catch((response: any) => handleRequestError(response));
}

export async function createRoundRobinGroups(
  tournament_id: number,
  stage_id: number,
  group_count: number,
  team_count: number,
  method: 'snake' | 'block' = 'snake'
) {
  return createAxios()
    .post(`tournaments/${tournament_id}/stage_items/round_robin_groups`, {
      stage_id,
      group_count,
      team_count,
      method,
    })
    .catch((response: any) => handleRequestError(response));
}

export async function createEliminationFromSources(
  tournament_id: number,
  stage_id: number,
  name: string | null,
  sources: { stage_item_id: number; positions: number }[],
  take: 'top' | 'bottom' = 'top'
) {
  return createAxios()
    .post(`tournaments/${tournament_id}/stage_items/elimination_from_sources`, {
      stage_id,
      name,
      sources,
      take,
    })
    .catch((response: any) => handleRequestError(response));
}

export async function updateStageItem(
  tournament_id: number,
  stage_item_id: number,
  name: string,
  ranking_id: string
) {
  return createAxios()
    .put(`tournaments/${tournament_id}/stage_items/${stage_item_id}`, { name, ranking_id })
    .catch((response: any) => handleRequestError(response));
}

export async function deleteStageItem(tournament_id: number, stage_item_id: number) {
  return createAxios()
    .delete(`tournaments/${tournament_id}/stage_items/${stage_item_id}`)
    .catch((response: any) => handleRequestError(response));
}
