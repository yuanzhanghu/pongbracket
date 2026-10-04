import useSWR, { SWRResponse } from 'swr';

import {
  LeaderboardResponse,
  MyRatingEventsResponse,
  MyRatingsResponse,
  RatingCategoriesResponse,
  ScorersResponse,
  SettlementResponse,
  SettlementReviewsResponse,
  TrustedManagersResponse,
} from '@openapi';
import { createAxios, handleRequestError } from './adapter';

const fetcher = (url: string) =>
  createAxios()
    .get(url)
    .then((res: { data: any }) => res.data);

// ---------------------------------------------------------------------------
// Rating categories
// ---------------------------------------------------------------------------

export function getRatingCategories(): SWRResponse<RatingCategoriesResponse> {
  return useSWR('rating-categories', fetcher);
}

export async function createRatingCategory(name: string, key: string, algorithm: string) {
  return createAxios()
    .post('rating-categories', { name, key, algorithm })
    .catch((response: any) => handleRequestError(response));
}

export async function updateRatingCategory(category_id: number, name: string, algorithm: string) {
  return createAxios()
    .put(`rating-categories/${category_id}`, { name, algorithm })
    .catch((response: any) => handleRequestError(response));
}

export async function removeRatingCategory(category_id: number) {
  return createAxios()
    .delete(`rating-categories/${category_id}`)
    .catch((response: any) => handleRequestError(response));
}

export function getLeaderboard(category_id: number): SWRResponse<LeaderboardResponse> {
  return useSWR(`rating-categories/${category_id}/leaderboard`, fetcher);
}

// ---------------------------------------------------------------------------
// Rating settings + seeding (per tournament)
// ---------------------------------------------------------------------------

export async function seedTeamRating(tournament_id: number, team_id: number, rating: number) {
  return createAxios().put(`tournaments/${tournament_id}/teams/${team_id}/seed-rating`, {
    rating,
  });
}

// ---------------------------------------------------------------------------
// Settlement
// ---------------------------------------------------------------------------

export function getSettlementStatus(tournament_id: number | null): SWRResponse<SettlementResponse> {
  return useSWR(
    tournament_id == null ? null : `tournaments/${tournament_id}/settlement-status`,
    fetcher
  );
}

export async function settlementRequest(tournament_id: number) {
  return createAxios().post(`tournaments/${tournament_id}/settlement-request`);
}

// ---------------------------------------------------------------------------
// Joining / leaving (logged-in user, individual tournaments)
// ---------------------------------------------------------------------------

export async function requestToJoin(tournament_id: number, trust_creator: boolean) {
  return createAxios().post(`tournaments/${tournament_id}/join-requests`, { trust_creator });
}

export async function leaveTournament(tournament_id: number) {
  return createAxios().post(`tournaments/${tournament_id}/leave`);
}

export function getMyJoinStatus(tournament_id: number | null): SWRResponse<any> {
  return useSWR(
    tournament_id == null ? null : `tournaments/${tournament_id}/my-join-status`,
    fetcher
  );
}

// ---------------------------------------------------------------------------
// Direct-add participants (owner pulls in accounts that trust them)
// ---------------------------------------------------------------------------

export function getAddableParticipants(tournament_id: number | null): SWRResponse<any> {
  return useSWR(
    tournament_id == null ? null : `tournaments/${tournament_id}/addable-participants`,
    fetcher
  );
}

export async function addParticipant(tournament_id: number, user_id: number) {
  return createAxios().post(`tournaments/${tournament_id}/participants`, { user_id });
}

// ---------------------------------------------------------------------------
// Scorers (per tournament)
// ---------------------------------------------------------------------------

export function getScorers(tournament_id: number | null): SWRResponse<ScorersResponse> {
  return useSWR(tournament_id == null ? null : `tournaments/${tournament_id}/scorers`, fetcher);
}

export async function addScorer(tournament_id: number, user_email: string) {
  return createAxios().post(`tournaments/${tournament_id}/scorers`, { user_email });
}

export async function removeScorer(tournament_id: number, user_id: number) {
  return createAxios().delete(`tournaments/${tournament_id}/scorers/${user_id}`);
}

// ---------------------------------------------------------------------------
// Trusted managers (current user)
// ---------------------------------------------------------------------------

export function getTrustedManagers(): SWRResponse<TrustedManagersResponse> {
  return useSWR('me/trusted-managers', fetcher);
}

export async function addTrustedManager(manager_email: string) {
  return createAxios().post('me/trusted-managers', { manager_email });
}

export async function removeTrustedManager(manager_id: number) {
  return createAxios().delete(`me/trusted-managers/${manager_id}`);
}

// ---------------------------------------------------------------------------
// My ratings (current user)
// ---------------------------------------------------------------------------

export function getMyRatings(): SWRResponse<MyRatingsResponse> {
  return useSWR('me/ratings', fetcher);
}

export function getMyRatingEvents(category_id: number | null): SWRResponse<MyRatingEventsResponse> {
  return useSWR(category_id == null ? null : `me/ratings/${category_id}/events`, fetcher);
}

// ---------------------------------------------------------------------------
// Admin: approve initial ratings & settle (one action per tournament)
// ---------------------------------------------------------------------------

export function getSettlementReviews(): SWRResponse<SettlementReviewsResponse> {
  return useSWR('admin/settlement-reviews', fetcher);
}

export async function approveAndSettle(
  tournament_id: number,
  adjustments: { player_rating_id: number; initial_rating: number }[]
) {
  return createAxios().post(`admin/settlements/${tournament_id}/approve-and-settle`, {
    adjustments,
  });
}
