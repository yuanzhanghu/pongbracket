import {
  Anchor,
  Box,
  Button,
  Center,
  Container,
  Group,
  Paper,
  PasswordInput,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconArrowLeft } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import LanguageSwitcher from '@components/utils/language_switcher';
import { ClientOnly } from '@components/utils/react';
import { HCaptchaInput } from '@components/utils/util';
import { registerUser } from '@services/user';
import classes from './create_account.module.css';

export default function CreateAccountPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);

  async function registerAndRedirect(values: any) {
    const response = await registerUser(values, captchaToken);

    if (response != null && response.data != null && response.data.data != null) {
      localStorage.setItem('login', JSON.stringify(response.data.data));
      await navigate('/');
    }
  }

  const form = useForm({
    initialValues: {
      name: '',
      email: '',
      password: '',
    },

    validate: {
      name: (value) =>
        value.trim() !== ''
          ? value.includes('@')
            ? t('name_no_at_validation')
            : null
          : t('empty_name_validation'),
      // Email is optional (some users prefer not to share one); validate the
      // format only when something was entered.
      email: (value) =>
        value === '' || /^\S+@\S+$/.test(value) ? null : t('invalid_email_validation'),
      password: (value) => (value.length >= 4 ? null : t('too_short_password_validation')),
    },
  });

  return (
    <Container size={460} my={30}>
      <Group justify="flex-end">
        <LanguageSwitcher />
      </Group>
      <Title className={classes.title} ta="center">
        {t('create_account_title')}
      </Title>
      <Paper withBorder shadow="md" p={30} radius="md" mt="xl">
        <form
          onSubmit={form.onSubmit(async (values) => {
            await registerAndRedirect(values);
          })}
        >
          <TextInput
            label={t('name_input_label')}
            placeholder={t('name_input_placeholder')}
            required
            {...form.getInputProps('name')}
          />
          <TextInput
            label={t('email_optional_input_label')}
            placeholder={t('email_input_placeholder')}
            type="email"
            mt="lg"
            mb="lg"
            {...form.getInputProps('email')}
          />
          <PasswordInput
            label={t('password_input_label')}
            placeholder={t('password_input_placeholder')}
            required
            {...form.getInputProps('password')}
          />
          <Group justify="space-between" mt="lg" className={classes.controls}>
            <ClientOnly>
              <HCaptchaInput
                siteKey={import.meta.env.VITE_HCAPTCHA_SITE_KEY}
                setCaptchaToken={setCaptchaToken}
              />
            </ClientOnly>
            <Anchor c="dimmed" size="sm" className={classes.control}>
              <Center inline>
                <IconArrowLeft size={12} stroke={1.5} />
                <Box ml={5} onClick={() => navigate('/login')}>
                  {' '}
                  {t('back_to_login_nav')}
                </Box>
              </Center>
            </Anchor>
            <Button className={classes.control} type="submit">
              {t('create_account_button')}
            </Button>
          </Group>
        </form>
      </Paper>
    </Container>
  );
}
