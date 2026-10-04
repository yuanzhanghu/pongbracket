import { Group, ThemeIcon, Title, Tooltip } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { HiArchiveBoxArrowDown } from 'react-icons/hi2';
import { Navigate } from 'react-router';

import { TournamentLinks } from '@components/navbar/_main_links';
import { responseIsValid } from '@components/utils/util';
import Layout from '@pages/_layout';
import { checkForAuthError, getTournamentById } from '@services/adapter';
import { tokenPresent } from '@services/local_storage';
import { getMyJoinStatus } from '@services/rating';

export default function TournamentLayout({ children, tournament_id, allowAnonymous = false }: any) {
  const { t } = useTranslation();

  const tournamentResponse = getTournamentById(tournament_id);
  // Whether the viewer can manage this tournament (a member of its club). Only
  // queried for logged-in users; anonymous/non-members are spectators.
  const swrJoinStatus = getMyJoinStatus(tokenPresent() ? tournament_id : null);
  const canManage = swrJoinStatus.data?.data?.can_manage === true;

  // Public (spectator) pages opt out of the redirect-to-login so anonymous
  // visitors can view a tournament the owner marked public.
  if (!allowAnonymous) {
    // Anonymous visitors are sent to /login by checkForAuthError.
    checkForAuthError(tournamentResponse);
    if (tokenPresent()) {
      // Wait until we know the viewer's management access before rendering a
      // management page, so we never flash organiser UI to a non-manager.
      if (swrJoinStatus.data == null) {
        return null;
      }
      // A logged-in non-manager (participant / follower) may only view results —
      // every other tournament page bounces there.
      if (!canManage) {
        return <Navigate to={`/tournaments/${tournament_id}/results`} replace />;
      }
    }
  }

  // Guests / non-managers get NO tournament sidebar — just the page content.
  const tournamentLinks = canManage ? <TournamentLinks tournament_id={tournament_id} /> : null;
  const breadcrumbs = responseIsValid(tournamentResponse) ? (
    <Group gap="xs" miw="25rem">
      <Title order={2} maw="20rem">
        /
      </Title>
      <Title order={2} maw="20rem" lineClamp={1}>
        {tournamentResponse.data?.data.name}
      </Title>

      <Tooltip label={`${t('archived_header_label')}`}>
        <ThemeIcon
          color="yellow"
          variant="light"
          style={{
            visibility: tournamentResponse.data?.data.status === 'ARCHIVED' ? 'visible' : 'hidden',
          }}
        >
          <HiArchiveBoxArrowDown />
        </ThemeIcon>
      </Tooltip>
    </Group>
  ) : null;

  return (
    <Layout additionalNavbarLinks={tournamentLinks} breadcrumbs={breadcrumbs}>
      {children}
    </Layout>
  );
}
