import { Center, Group, Text, Title, UnstyledButton } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import PreloadLink from '@components/utils/link';

export function Brand() {
  const { t } = useTranslation();
  return (
    <Center mr="1rem" miw="12rem">
      <UnstyledButton component={PreloadLink} href="/">
        <Group>
          <Title order={2}>{t('site_name')}</Title>
        </Group>
      </UnstyledButton>
    </Center>
  );
}

export function BrandFooter() {
  const { t } = useTranslation();
  return (
    <Center mr="1rem">
      <Center>
        <Text size="lg" ml="0.75rem">
          {t('site_name')}
        </Text>
      </Center>
    </Center>
  );
}
