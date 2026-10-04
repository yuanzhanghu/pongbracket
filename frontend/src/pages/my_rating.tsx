import { LineChart } from '@mantine/charts';
import { Badge, Card, Container, SimpleGrid, Stack, Table, Tabs, Text, Title } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { DateTime, formatMonthDay } from '@components/utils/datetime';
import { GenericSkeletonThreeRows } from '@components/utils/skeletons';
import { MyRatingEventsResponse, MyRatingSummary, RatingEventWithNames } from '@openapi';
import { getMyRatingEvents, getMyRatings } from '@services/rating';
import { SWRResponse } from 'swr';
import Layout from './_layout';

function ResultBadge({ result }: { result: 'W' | 'L' }) {
  const { t } = useTranslation();

  return (
    <Badge color={result === 'W' ? 'green' : 'red'} variant="light">
      {result === 'W' ? t('match_result_win_short') : t('match_result_loss_short')}
    </Badge>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card withBorder padding="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="xl" fw={700}>
        {value}
      </Text>
    </Card>
  );
}

function CategoryRatingPanel({ category }: { category: MyRatingSummary }) {
  const { t } = useTranslation();
  const swrEvents: SWRResponse<MyRatingEventsResponse> = getMyRatingEvents(category.category_id);
  const events: RatingEventWithNames[] = swrEvents.data != null ? swrEvents.data.data : [];

  const chartData = events.map((e) => ({
    date: formatMonthDay(e.created),
    rating: e.rating_after,
  }));

  return (
    <Stack mt="md">
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <StatCard
          label={t('current_rating_label')}
          value={`${Math.round(category.current_rating)}`}
        />
        <StatCard
          label={t('yearly_avg_rating_label')}
          value={
            category.yearly_avg_rating != null
              ? `${Math.round(category.yearly_avg_rating)}`
              : t('no_data_placeholder')
          }
        />
        <StatCard label={t('peak_rating_label')} value={`${Math.round(category.peak_rating)}`} />
      </SimpleGrid>

      {category.status === 'PENDING' ? (
        <Text c="orange" size="sm">
          {t('initial_rating_pending_no_matches')}
        </Text>
      ) : swrEvents.isLoading ? (
        <GenericSkeletonThreeRows />
      ) : events.length === 0 ? (
        <Text c="dimmed">{t('no_matches_in_category')}</Text>
      ) : (
        <>
          <LineChart
            h={300}
            data={chartData}
            dataKey="date"
            series={[{ name: 'rating', label: t('rating_chart_series_label'), color: 'blue.6' }]}
            curveType="linear"
          />
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('date_table_header')}</Table.Th>
                <Table.Th>{t('opponent_table_header')}</Table.Th>
                <Table.Th>{t('tournament_table_header')}</Table.Th>
                <Table.Th>{t('result_table_header')}</Table.Th>
                <Table.Th>{t('rating_change_table_header')}</Table.Th>
                <Table.Th>{t('rating_after_table_header')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {[...events].reverse().map((event) => (
                <Table.Tr key={event.id}>
                  <Table.Td>
                    <DateTime datetime={event.created} />
                  </Table.Td>
                  <Table.Td>{event.opponent_name}</Table.Td>
                  <Table.Td>{event.tournament_name}</Table.Td>
                  <Table.Td>
                    <ResultBadge result={event.result} />
                  </Table.Td>
                  <Table.Td c={event.delta >= 0 ? 'green' : 'red'}>
                    {event.delta >= 0 ? `+${event.delta}` : event.delta}
                  </Table.Td>
                  <Table.Td>{event.rating_after}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  );
}

export default function MyRatingPage() {
  const { t } = useTranslation();
  const swrRatings = getMyRatings();
  const ratings: MyRatingSummary[] = swrRatings.data != null ? swrRatings.data.data : [];
  const [activeTab, setActiveTab] = useState<string | null>(null);

  const tab = activeTab ?? (ratings.length > 0 ? String(ratings[0].category_id) : null);

  return (
    <Layout>
      <Container>
        <Title mb="lg">{t('my_rating_title')}</Title>
        {swrRatings.isLoading ? (
          <GenericSkeletonThreeRows />
        ) : ratings.length === 0 ? (
          <Text c="dimmed">{t('my_rating_no_rated_tournaments')}</Text>
        ) : (
          <Tabs value={tab} onChange={setActiveTab}>
            <Tabs.List>
              {ratings.map((rating) => (
                <Tabs.Tab key={rating.category_id} value={String(rating.category_id)}>
                  {rating.category_name}
                  {rating.status === 'PENDING' ? (
                    <Badge ml="xs" color="orange" size="xs" variant="light">
                      {t('rating_status_pending_badge')}
                    </Badge>
                  ) : null}
                </Tabs.Tab>
              ))}
            </Tabs.List>
            {ratings.map((rating) => (
              <Tabs.Panel key={rating.category_id} value={String(rating.category_id)}>
                <CategoryRatingPanel category={rating} />
              </Tabs.Panel>
            ))}
          </Tabs>
        )}
      </Container>
    </Layout>
  );
}
