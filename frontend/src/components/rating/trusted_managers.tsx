import { ActionIcon, Button, Group, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { MdDelete } from '@react-icons/all-files/md/MdDelete';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { handleRequestError } from '@services/adapter';
import { addTrustedManager, getTrustedManagers, removeTrustedManager } from '@services/rating';

export function TrustedManagers() {
  const { t } = useTranslation();
  const swrManagers = getTrustedManagers();
  const managers = swrManagers.data != null ? swrManagers.data.data : [];

  const form = useForm({
    initialValues: { email: '' },
    validate: {
      // The backend resolves the identifier as an email OR a unique user name.
      email: (value) => (value.trim() !== '' ? null : t('login_identifier_required')),
    },
  });

  return (
    <Stack mt="xl">
      <Title order={3}>{t('trusted_managers_title')}</Title>
      <Text fz="sm" c="dimmed">
        {t('trusted_managers_description')}
      </Text>

      {managers.length > 0 ? (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('person_name_table_header')}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {managers.map((manager) => (
              <Table.Tr key={manager.manager_id}>
                <Table.Td>{manager.name}</Table.Td>
                <Table.Td>
                  <Group justify="flex-end">
                    <ActionIcon
                      color="red"
                      variant="subtle"
                      onClick={async () => {
                        await removeTrustedManager(manager.manager_id).catch((exc: any) =>
                          handleRequestError(exc)
                        );
                        await swrManagers.mutate();
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
          const response = await addTrustedManager(values.email).catch((exc: any) => {
            handleRequestError(exc);
            return null;
          });
          if ((response as any)?.status === 200 || (response as any)?.status === 201) {
            form.reset();
            await swrManagers.mutate();
          }
        })}
      >
        <Group align="flex-end">
          <TextInput
            label={t('add_trusted_manager_label')}
            placeholder={t('login_identifier_label')}
            style={{ flex: 1 }}
            {...form.getInputProps('email')}
          />
          <Button type="submit" leftSection={<IconPlus size={18} />}>
            {t('add_button')}
          </Button>
        </Group>
      </form>
    </Stack>
  );
}
