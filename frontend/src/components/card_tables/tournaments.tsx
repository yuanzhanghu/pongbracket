import { Badge, Card, Group, Image, Text, UnstyledButton } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { EmptyTableInfo } from '@components/no_content/empty_table_info';
import { DateTime } from '@components/utils/datetime';
import RequestErrorAlert from '@components/utils/error_alert';
import PreloadLink from '@components/utils/link';
import { TableSkeletonSingleColumn } from '@components/utils/skeletons';
import { Tournament, TournamentsResponse } from '@openapi';
import { getBaseApiUrl } from '@services/adapter';
import classes from './tournaments.module.css';

// Local SVG placeholder for tournaments without a logo. placehold.co has no CJK
// glyphs (Chinese names rendered as just their ASCII prefix) and its URL broke on
// unencoded names; an inline SVG uses the browser's own fonts instead.
function placeholderLogo(name: string) {
  const trimmed = name.trim();
  const escaped = trimmed.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const fontSize = trimmed.length > 12 ? 16 : 22;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="318" height="160">` +
    `<rect width="100%" height="100%" fill="#e9ecef"/>` +
    `<text x="50%" y="50%" font-family="sans-serif" font-size="${fontSize}" fill="#868e96" ` +
    `text-anchor="middle" dominant-baseline="middle">${escaped}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export function TournamentLogo({ tournament }: { tournament: Tournament }) {
  const { t } = useTranslation();
  return (
    <Image
      radius="md"
      alt={t('tournament_logo_alt')}
      src={`${getBaseApiUrl()}/static/tournament-logos/${tournament.logo_path}`}
      fallbackSrc={placeholderLogo(tournament.name)}
      height={160}
    />
  );
}

export default function TournamentsCardTable({
  swrTournamentsResponse,
  linkTo = 'stages',
}: {
  swrTournamentsResponse: SWRResponse<TournamentsResponse>;
  linkTo?: 'stages' | 'results';
}) {
  const { t } = useTranslation();

  if (swrTournamentsResponse.error) {
    return <RequestErrorAlert error={swrTournamentsResponse.error} />;
  }
  if (swrTournamentsResponse.isLoading) {
    return <TableSkeletonSingleColumn />;
  }

  const tournaments: Tournament[] =
    swrTournamentsResponse.data != null ? swrTournamentsResponse.data.data : [];

  const rows = tournaments
    // Newest first, so the tournament someone just created (or the next one
    // coming up) is at the top instead of buried alphabetically.
    .slice()
    .sort(
      (t1: Tournament, t2: Tournament) =>
        t2.start_time.localeCompare(t1.start_time) || t2.id - t1.id
    )
    .map((tournament) => (
      <Group key={tournament.id} className={classes.card}>
        <UnstyledButton
          component={PreloadLink}
          href={`/tournaments/${tournament.id}/${linkTo}`}
          w="100%"
        >
          <Card shadow="sm" padding="lg" radius="md" w="100%" className={classes.cardBody}>
            <Card.Section>
              <TournamentLogo tournament={tournament} />
            </Card.Section>

            <Group justify="space-between" mt="sm" mb={0}>
              <Text fw={500} lineClamp={1}>
                {tournament.name}
              </Text>
            </Group>

            <Card.Section className={classes.section}>
              <Text fw={500} size="sm">
                <DateTime datetime={tournament.start_time} />
              </Text>
              {tournament.status === 'ARCHIVED' ? (
                <Badge color="yellow" variant="outline">
                  {t('archived_label')}
                </Badge>
              ) : null}
            </Card.Section>
          </Card>
        </UnstyledButton>
      </Group>
    ));

  if (rows.length < 1) return <EmptyTableInfo entity_name={t('tournaments_title')} />;

  return (
    <Group gap="sm" style={{ width: '100%' }}>
      {rows}
    </Group>
  );
}
