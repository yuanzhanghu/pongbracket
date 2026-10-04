import {
  Anchor,
  Button,
  Container,
  Group,
  Paper,
  PasswordInput,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { showNotification } from '@mantine/notifications';
import { IconCheck } from '@tabler/icons-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { guideIndexHref } from '@components/utils/guide';
import LanguageSwitcher from '@components/utils/language_switcher';
import { tokenPresent } from '@services/local_storage';
import { performLogin } from '@services/user';

export default function LoginPage() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  useEffect(() => {
    if (tokenPresent()) {
      navigate('/');
    }
  }, []);

  async function attemptLogin(email: string, password: string) {
    const success = await performLogin(email, password);
    if (success) {
      showNotification({
        color: 'green',
        title: t('login_success_title'),
        icon: <IconCheck />,
        message: '',
      });

      await navigate('/');
    }
  }

  const form = useForm({
    initialValues: {
      email: '',
      password: '',
    },

    validate: {
      // The login identifier may be an email address OR a user name (Chinese
      // names included) — only require it to be non-empty.
      email: (value) => (value.trim() !== '' ? null : t('login_identifier_required')),
      // Only require a non-empty password on the login form; the server is the
      // source of truth for credentials (length rules apply at registration).
      password: (value) => (value.length >= 1 ? null : t('invalid_password_validation')),
    },
  });

  return (
    <>
      <Group justify="flex-end" p="md">
        <LanguageSwitcher />
      </Group>
      <Title ta="center" mt={60}>
        <Text inherit variant="gradient" component="span">
          {t('welcome_title')}
        </Text>
      </Title>
      <Container size={480} my={40}>
        <Paper withBorder shadow="md" p={30} pt={8} mt={30} radius="md">
          {/*<Button*/}
          {/*  size="md"*/}
          {/*  fullWidth*/}
          {/*  mt="lg"*/}
          {/*  type="submit"*/}
          {/*  c="gray"*/}
          {/*  leftSection={<FaGithub size={20} />}*/}
          {/*>*/}
          {/*  Continue with GitHub*/}
          {/*</Button>*/}
          {/*<Button*/}
          {/*  size="md"*/}
          {/*  fullWidth*/}
          {/*  mt="lg"*/}
          {/*  type="submit"*/}
          {/*  c="indigo"*/}
          {/*  leftSection={<FaGoogle size={20} />}*/}
          {/*>*/}
          {/*  Continue with Google*/}
          {/*</Button>*/}
          {/*<Divider label="Or continue with email" labelPosition="center" my="lg" />*/}
          <form
            onSubmit={form.onSubmit(async (values) => attemptLogin(values.email, values.password))}
          >
            <TextInput
              label={t('login_identifier_label')}
              placeholder={t('login_identifier_placeholder')}
              required
              my="lg"
              type="text"
              name="email"
              {...form.getInputProps('email')}
            />
            <PasswordInput
              label={t('password_input_label')}
              placeholder={t('password_input_placeholder')}
              required
              mt="md"
              {...form.getInputProps('password')}
            />
            <Button fullWidth mt="xl" type="submit">
              {t('sign_in_title')}
            </Button>
          </form>
          <Text c="dimmed" size="sm" ta="center" mt={15}>
            <Anchor<'a'> onClick={() => navigate('/create-account')} size="sm">
              {t('create_account_button')}
            </Anchor>
            {/* 忘记密码 link hidden: the /password-reset page was never
                implemented (404), and email is optional now anyway. Restore it
                if a real reset flow lands. */}
            {' - '}
            <Anchor href={guideIndexHref(i18n)} target="_blank" size="sm">
              {t('user_guide_title')}
            </Anchor>
          </Text>
        </Paper>
      </Container>
    </>
  );
}
