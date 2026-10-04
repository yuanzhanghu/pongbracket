import {
  ActionIcon,
  Anchor,
  Button,
  Fieldset,
  Group,
  NumberInput,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { showNotification } from '@mantine/notifications';
import { MdDelete } from '@react-icons/all-files/md/MdDelete';
import { IconCheck, IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { GenericSkeletonThreeRows } from '@components/utils/skeletons';
import NotFoundTitle from '@pages/404';
import { checkForAuthError, getUser, handleRequestError } from '@services/adapter';
import {
  approveAndSettle,
  createRatingCategory,
  getRatingCategories,
  getSettlementReviews,
  removeRatingCategory,
} from '@services/rating';
import { getAdminUsers } from '@services/user';
import Layout from './_layout';

function CategoriesSection() {
  const { t } = useTranslation();
  const swrCategories = getRatingCategories();
  const categories = swrCategories.data != null ? swrCategories.data.data : [];

  const form = useForm({
    initialValues: { name: '', key: '', algorithm: 'elo' },
    validate: {
      name: (value) => (value.length > 0 ? null : t('empty_name_validation')),
      key: (value) => (value.length > 0 ? null : t('empty_key_validation')),
      algorithm: (value) => (value.length > 0 ? null : t('empty_algorithm_validation')),
    },
  });

  return (
    <Stack>
      <Title order={3}>{t('admin_rating_categories_title')}</Title>
      {categories.length > 0 ? (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('name_table_header')}</Table.Th>
              <Table.Th>{t('key_table_header')}</Table.Th>
              <Table.Th>{t('algorithm_table_header')}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {categories.map((category) => (
              <Table.Tr key={category.id}>
                <Table.Td>{category.name}</Table.Td>
                <Table.Td>{category.key}</Table.Td>
                <Table.Td>{category.algorithm}</Table.Td>
                <Table.Td>
                  <Group justify="flex-end">
                    {/* The built-in 加华积分 category anchors the rating system
                        and cannot be deleted (the backend rejects it too). */}
                    {category.key === 'CanadaChinaTT' ? (
                      <Text fz="sm" c="dimmed">
                        {t('builtin_label')}
                      </Text>
                    ) : (
                      <ActionIcon
                        color="red"
                        variant="subtle"
                        onClick={async () => {
                          await removeRatingCategory(category.id);
                          await swrCategories.mutate();
                        }}
                      >
                        <MdDelete />
                      </ActionIcon>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : null}

      <form
        onSubmit={form.onSubmit(async (values) => {
          const response = await createRatingCategory(values.name, values.key, values.algorithm);
          if ((response as any)?.status === 200 || (response as any)?.status === 201) {
            form.reset();
            await swrCategories.mutate();
          }
        })}
      >
        <Group align="flex-end">
          <TextInput label={t('name_input_label')} {...form.getInputProps('name')} />
          <TextInput label={t('key_input_label')} {...form.getInputProps('key')} />
          <TextInput label={t('algorithm_input_label')} {...form.getInputProps('algorithm')} />
          <Button type="submit" leftSection={<IconPlus size={18} />}>
            {t('create_rating_category_button')}
          </Button>
        </Group>
      </form>
    </Stack>
  );
}

function SettlementReviewCard({
  review,
  onSettled,
}: {
  review: any;
  onSettled: () => Promise<any>;
}) {
  const { t } = useTranslation();
  const [adjusted, setAdjusted] = useState<Record<number, number | string>>({});

  return (
    <Fieldset legend={`${review.tournament_name} · ${review.category_name}`} radius="md">
      <Stack>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('player_table_header')}</Table.Th>
              <Table.Th>{t('initial_rating_table_header')}</Table.Th>
              <Table.Th>{t('adjusted_initial_rating_table_header')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {review.players.map((player: any) => (
              <Table.Tr key={player.player_rating_id}>
                <Table.Td>{player.user_name}</Table.Td>
                <Table.Td>{Math.round(player.initial_rating)}</Table.Td>
                <Table.Td>
                  <NumberInput
                    value={adjusted[player.player_rating_id] ?? ''}
                    placeholder={`${Math.round(player.initial_rating)}`}
                    onChange={(value) =>
                      setAdjusted((prev) => ({ ...prev, [player.player_rating_id]: value }))
                    }
                  />
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Group justify="flex-end">
          {/* One link per card (each card is a single tournament) so the admin
              can open its results to judge the proposed initial ratings. */}
          <Anchor
            href={`/tournaments/${review.tournament_id}/results`}
            target="_blank"
            rel="noopener noreferrer"
            fz="sm"
          >
            {t('view_tournament_link')}
          </Anchor>
          <Button
            color="green"
            leftSection={<IconCheck size={18} />}
            onClick={async () => {
              const adjustments = review.players
                .map((player: any) => {
                  const raw = adjusted[player.player_rating_id];
                  const parsed =
                    raw == null || raw === ''
                      ? null
                      : typeof raw === 'string'
                        ? parseFloat(raw)
                        : raw;
                  return parsed != null && !Number.isNaN(parsed)
                    ? { player_rating_id: player.player_rating_id, initial_rating: parsed }
                    : null;
                })
                .filter((a: any) => a != null);
              const response = await approveAndSettle(review.tournament_id, adjustments).catch(
                (exc: any) => {
                  handleRequestError(exc);
                  return null;
                }
              );
              if ((response as any)?.status === 200) {
                const result = (response as any)?.data?.data;
                showNotification({
                  color: 'green',
                  title:
                    result?.settled_seq != null
                      ? t('settled_with_seq', { seq: result.settled_seq })
                      : t('settled_title'),
                  message: t('settlement_approved_message'),
                  icon: <IconCheck />,
                });
                await onSettled();
              }
            }}
          >
            {t('approve_and_settle_button')}
          </Button>
        </Group>
      </Stack>
    </Fieldset>
  );
}

function ReviewQueueSection() {
  const { t } = useTranslation();
  const swrReviews = getSettlementReviews();
  const reviews = swrReviews.data != null ? swrReviews.data.data : [];

  return (
    <Stack mt="xl">
      <Title order={3}>{t('admin_review_queue_title')}</Title>
      {reviews.length < 1 ? (
        <Text fz="sm" c="dimmed">
          {t('admin_review_queue_empty')}
        </Text>
      ) : (
        reviews.map((review) => (
          <SettlementReviewCard
            key={review.tournament_id}
            review={review}
            onSettled={() => swrReviews.mutate()}
          />
        ))
      )}
    </Stack>
  );
}

function UsersSection() {
  const { t } = useTranslation();
  const swrUsers = getAdminUsers();
  const users = swrUsers.data != null ? swrUsers.data.data : [];
  const swrCategories = getRatingCategories();
  const categories = swrCategories.data != null ? swrCategories.data.data : [];
  const [sortCategoryId, setSortCategoryId] = useState<number | null>(null);

  // Default sort: the built-in 加华积分 category; clicking another rating
  // column (e.g. 光板积分) re-sorts by that category instead.
  const defaultSortId = categories.find((c) => c.key === 'CanadaChinaTT')?.id ?? null;
  const activeSortId = sortCategoryId ?? defaultSortId;

  const sortedUsers = [...users].sort((a, b) => {
    if (activeSortId != null) {
      const ratingA = a.ratings[activeSortId];
      const ratingB = b.ratings[activeSortId];
      if (ratingA != null && ratingB != null && ratingA !== ratingB) {
        return ratingB - ratingA;
      }
      // Rated users come before unrated ones; equal ratings fall through to name.
      if (ratingA != null && ratingB == null) return -1;
      if (ratingA == null && ratingB != null) return 1;
    }
    return a.name.localeCompare(b.name);
  });

  return (
    <Stack>
      <Text fz="sm" c="dimmed">
        {t('admin_user_count', { count: users.length })}
      </Text>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t('username_table_header')}</Table.Th>
            {categories.map((category) => (
              <Table.Th
                key={category.id}
                style={{ cursor: 'pointer' }}
                onClick={() => setSortCategoryId(category.id)}
              >
                {category.name}
                {activeSortId === category.id ? ' ▼' : ''}
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sortedUsers.map((user) => (
            <Table.Tr key={user.user_id}>
              <Table.Td>{user.name}</Table.Td>
              {categories.map((category) => (
                <Table.Td key={category.id}>
                  {user.ratings[category.id] != null ? (
                    user.ratings[category.id]
                  ) : (
                    <Text fz="sm" c="dimmed" span>
                      —
                    </Text>
                  )}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

export default function AdminPage() {
  const { t } = useTranslation();
  const swrUserResponse = getUser();
  checkForAuthError(swrUserResponse);
  const user = swrUserResponse.data != null ? swrUserResponse.data.data : null;

  let content = <GenericSkeletonThreeRows />;

  if (!swrUserResponse.isLoading) {
    if (user == null || !user.is_admin) {
      content = <NotFoundTitle />;
    } else {
      content = (
        <Tabs defaultValue="rating">
          <Tabs.List>
            <Tabs.Tab value="rating">{t('admin_rating_tab')}</Tabs.Tab>
            <Tabs.Tab value="users">{t('admin_users_tab')}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="rating" pt="md">
            <Stack>
              <CategoriesSection />
              <ReviewQueueSection />
            </Stack>
          </Tabs.Panel>
          <Tabs.Panel value="users" pt="md">
            <UsersSection />
          </Tabs.Panel>
        </Tabs>
      );
    }
  }

  return <Layout>{content}</Layout>;
}
