import { Button, PasswordInput, Select, Tabs, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { showNotification } from '@mantine/notifications';
import { BiGlobe } from '@react-icons/all-files/bi/BiGlobe';
import { IconCheck, IconHash, IconLogout, IconUser } from '@tabler/icons-react';
import { useNavigate } from 'react-router';
import { useSWRConfig } from 'swr';

import { LANGUAGES } from '@components/utils/language_switcher';
import { UserPublic } from '@openapi';
import { performLogout, performLogoutAndRedirect } from '@services/local_storage';
import { updatePassword, updateUser } from '@services/user';

export default function UserForm({ user, t, i18n }: { user: UserPublic; t: any; i18n: any }) {
  const navigate = useNavigate();
  const { mutate } = useSWRConfig();
  const details_form = useForm({
    initialValues: {
      name: user != null ? user.name : '',
      email: user != null ? (user.email ?? '') : '',
      password: '',
    },

    validate: {
      name: (value) =>
        value !== ''
          ? value.includes('@')
            ? t('name_no_at_validation')
            : null
          : t('empty_name_validation'),
      // Email is optional; validate the format only when one is given.
      email: (value) =>
        value === '' || /^\S+@\S+$/.test(value) ? null : t('invalid_email_validation'),
    },
  });
  const password_form = useForm({
    initialValues: {
      password: '',
    },

    validate: {
      password: (value) => (value.length >= 4 ? null : t('too_short_password_validation')),
    },
  });

  // Same list as the header switcher, so the two pickers can never drift apart.
  // Labels are endonyms and stay untranslated on purpose.
  const locales = LANGUAGES.map(({ code, label }) => ({ value: code, label }));

  // `i18n.language` may carry a region ("en-US") or a language we no longer offer,
  // either of which would render the Select blank. Match on the base language, the
  // same way the header switcher does.
  const current = i18n.resolvedLanguage ?? i18n.language ?? '';
  const activeLanguage =
    LANGUAGES.find((l) => current === l.code || current.startsWith(`${l.code}-`))?.code ??
    LANGUAGES[0].code;

  const changeLanguage = (newLocale: string | null) => {
    // `changeLanguage` already re-renders and persists the choice; the old
    // `?lng=` navigation only existed to re-trigger detection, and a leftover
    // parameter would outrank the stored choice on the next load.
    i18n.changeLanguage(newLocale);
  };

  return (
    <Tabs defaultValue="details">
      <Tabs.List>
        <Tabs.Tab value="details" leftSection={<IconUser size="1.0rem" />}>
          {t('edit_details_tab_title')}
        </Tabs.Tab>
        <Tabs.Tab value="password" leftSection={<IconHash size="1.0rem" />}>
          {t('edit_password_tab_title')}
        </Tabs.Tab>
        <Tabs.Tab value="language" leftSection={<BiGlobe size="1.0rem" />}>
          {t('edit_language_tab_title')}
        </Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="details" pt="xs">
        <form
          onSubmit={details_form.onSubmit(async (values) => {
            if (user == null) return;
            const response = await updateUser(user.id, values);
            // Errors already surface via handleRequestError (red toast);
            // confirm success explicitly like the password form does.
            if ((response as any)?.status === 200) {
              showNotification({
                color: 'green',
                title: t('profile_saved_title'),
                message: '',
                icon: <IconCheck />,
              });
              await mutate('users/me');
            }
          })}
        >
          <TextInput
            withAsterisk
            mt="1.0rem"
            label={t('name_input_label')}
            {...details_form.getInputProps('name')}
          />
          <TextInput
            mt="1.0rem"
            label={t('email_optional_input_label')}
            type="email"
            {...details_form.getInputProps('email')}
          />
          <Button fullWidth style={{ marginTop: 20 }} color="green" type="submit">
            {t('save_button')}
          </Button>
          <Button
            fullWidth
            style={{ marginTop: 20 }}
            color="red"
            variant="outline"
            leftSection={<IconLogout />}
            onClick={() => performLogoutAndRedirect(t, navigate)}
          >
            {t('logout_title')}
          </Button>
        </form>
      </Tabs.Panel>
      <Tabs.Panel value="password" pt="xs">
        <form
          onSubmit={password_form.onSubmit(async (values) => {
            if (user != null) {
              const response = await updatePassword(user.id, values.password);
              if ((response as any)?.status === 200) {
                showNotification({
                  color: 'green',
                  title: t('password_saved_title'),
                  message: t('password_saved_relogin_message'),
                  icon: <IconCheck />,
                  autoClose: 10000,
                });
                password_form.reset();
                // Changing the password retires every token issued before it, this
                // browser's included, so stay ahead of the 401 and send the user to
                // the login page instead of letting the next request bounce them.
                performLogout();
                navigate('/login', { replace: true });
              }
            }
          })}
        >
          <PasswordInput
            withAsterisk
            mt="1.0rem"
            label={t('password_input_label')}
            placeholder={t('password_input_placeholder')}
            {...password_form.getInputProps('password')}
          />
          <Button fullWidth style={{ marginTop: 20 }} color="green" type="submit">
            {t('save_button')}
          </Button>
        </form>
      </Tabs.Panel>
      <Tabs.Panel value="language" pt="xs">
        <Select
          allowDeselect={false}
          value={activeLanguage}
          label={t('language')}
          data={locales}
          onChange={async (lng) => changeLanguage(lng)}
        />
      </Tabs.Panel>
    </Tabs>
  );
}
