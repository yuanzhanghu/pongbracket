import { Alert, Center } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

export function ErrorAlert({ title, message }: { title: string; message: string }) {
  return (
    <Alert
      icon={<IconAlertCircle size={32} />}
      title={title}
      color="red"
      radius="lg"
      variant="outline"
      w="40rem"
    >
      {message}
    </Alert>
  );
}

export default function RequestErrorAlert({ error }: any) {
  const { t } = useTranslation();
  const status_code =
    error.response != null && error.response.data.status != null
      ? `${t('error_title')} [${error.response.data.status}]`
      : t('error_title');
  const message = `${status_code}: ${error.response ? error.response.data.detail : error.message}`;

  return (
    <Center>
      <ErrorAlert message={message} title={t('error_title')} />
    </Center>
  );
}
