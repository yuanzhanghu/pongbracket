import { Container, Table, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';

import { GenericSkeletonThreeRows } from '@components/utils/skeletons';
import Layout from '@pages/_layout';
import { getLeaderboard } from '@services/rating';

export default function LeaderboardPage() {
  const { t } = useTranslation();
  const params = useParams();
  const categoryId = parseInt((params as any).category_id, 10);
  const swrLeaderboard = getLeaderboard(categoryId);
  const entries = swrLeaderboard.data != null ? swrLeaderboard.data.data : [];

  return (
    <Layout>
      <Container>
        <Title mb="lg">{t('rating_leaderboard_title')}</Title>
        {swrLeaderboard.isLoading ? (
          <GenericSkeletonThreeRows />
        ) : (
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('rank_table_header')}</Table.Th>
                <Table.Th>{t('person_name_table_header')}</Table.Th>
                <Table.Th>{t('current_rating_label')}</Table.Th>
                <Table.Th>{t('matches_played_table_header')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {entries.map((entry, index) => (
                <Table.Tr key={entry.user_id}>
                  <Table.Td>{index + 1}</Table.Td>
                  <Table.Td>{entry.name}</Table.Td>
                  <Table.Td>{Math.round(entry.current_rating)}</Table.Td>
                  <Table.Td>{entry.matches_played}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Container>
    </Layout>
  );
}
