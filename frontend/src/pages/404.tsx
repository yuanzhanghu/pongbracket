import { Button, Container, Group, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import LanguageSwitcher from '@components/utils/language_switcher';
import classes from '@pages/404.module.css';
import { tokenPresent } from '@services/local_storage';

export default function NotFoundPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <>
      <Group justify="flex-end" p="md">
        <LanguageSwitcher />
      </Group>
      <Container className={classes.root}>
        <div className={classes.label}>404</div>
        <Title className={classes.title}> {t('not_found_title')}</Title>
        <Text c="dimmed" size="lg" ta="center" className={classes.description}>
          {t('not_found_description')}
        </Text>
        <Group justify="center">
          <Button
            variant="subtle"
            size="md"
            onClick={() => (tokenPresent() ? navigate('/') : navigate('/login'))}
          >
            {t('back_home_nav')}
          </Button>
        </Group>
      </Container>
    </>
  );
}
