import { Tournament } from '@openapi';
import { getTournamentById } from '@services/adapter';

/**
 * In an individual tournament a "team" is a single person, so every team-flavoured
 * label reads 参赛人员 (participant) instead of 队伍. The catalogues carry those
 * wordings as `<key>_individual`; pass the result of this helper as i18next's
 * `context` option — `undefined` keeps the plain team wording.
 */
export function teamNamingContext(tournament?: Tournament | null): 'individual' | undefined {
  return tournament?.is_individual === true ? 'individual' : undefined;
}

/**
 * Same, for components that only know the tournament id. The tournament is already
 * fetched by the surrounding page, so this hits the SWR cache instead of the network.
 */
export function useTeamNamingContext(tournamentId: number | null | undefined) {
  // The id comes from the router on pages that have one, so it is NaN everywhere else.
  const id = Number(tournamentId);
  const response = getTournamentById(tournamentId != null && Number.isFinite(id) ? id : null);
  return teamNamingContext(response.data?.data);
}
