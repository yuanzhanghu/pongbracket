import { ActionIcon, Button, Fieldset, Group, Table, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { MdDelete } from '@react-icons/all-files/md/MdDelete';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { handleRequestError } from '@services/adapter';
import { addScorer, getScorers, removeScorer } from '@services/rating';

export function ScorersManager({ tournamentId }: { tournamentId: number }) {
  const { t } = useTranslation();
  const swrScorers = getScorers(tournamentId);
  const scorers = swrScorers.data != null ? swrScorers.data.data : [];

  const form = useForm({
    initialValues: { email: '' },
    validate: {
      // The backend resolves the identifier as an email OR a unique user name.
      email: (value) => (value.trim() !== '' ? null : t('login_identifier_required')),
    },
  });

  return (
    <Fieldset legend={t('scorers_manager_legend')} mt="lg" radius="md">
      <Text fz="sm" c="dimmed" mb="md">
        {t('scorers_manager_description')}
      </Text>

      {scorers.length > 0 ? (
        <Table mb="md">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('person_name_table_header')}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {scorers.map((scorer) => (
              <Table.Tr key={scorer.user_id}>
                <Table.Td>{scorer.name}</Table.Td>
                <Table.Td>
                  <Group justify="flex-end">
                    <ActionIcon
                      color="red"
                      variant="subtle"
                      onClick={async () => {
                        await removeScorer(tournamentId, scorer.user_id).catch((exc: any) =>
                          handleRequestError(exc)
                        );
                        await swrScorers.mutate();
                      }}
                    >
                      <MdDelete />
                    </ActionIcon>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : null}

      <form
        onSubmit={form.onSubmit(async (values) => {
          const response = await addScorer(tournamentId, values.email).catch((exc: any) => {
            handleRequestError(exc);
            return null;
          });
          if ((response as any)?.status === 200 || (response as any)?.status === 201) {
            form.reset();
            await swrScorers.mutate();
          }
        })}
      >
        <Group align="flex-end">
          <TextInput
            label={t('add_scorer_label')}
            placeholder={t('login_identifier_label')}
            style={{ flex: 1 }}
            {...form.getInputProps('email')}
          />
          <Button type="submit" leftSection={<IconPlus size={18} />}>
            {t('add_button')}
          </Button>
        </Group>
      </form>
    </Fieldset>
  );
}
