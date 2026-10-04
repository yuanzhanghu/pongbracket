import { Button, Menu } from '@mantine/core';
import { IconCheck, IconLanguage } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';

// Languages this deployment offers. Each label is written in its own language so
// the menu stays readable no matter which language the UI is currently in.
export const LANGUAGES = [
  { code: 'zh', label: '中文' },
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
];

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  // `?lng=` may carry a region ("en-US"), so match on the base language too.
  const current = i18n.resolvedLanguage ?? i18n.language ?? '';
  const active = LANGUAGES.find((l) => current === l.code || current.startsWith(`${l.code}-`));

  function changeLanguage(code: string) {
    i18n.changeLanguage(code);
    // `?lng=` outranks the stored choice on the next load, so a leftover one (the
    // user page adds it when switching there) would silently undo this switch.
    if (searchParams.has('lng')) {
      const remaining = new URLSearchParams(searchParams);
      remaining.delete('lng');
      setSearchParams(remaining, { replace: true });
    }
  }

  return (
    <Menu withinPortal position="bottom-end" transitionProps={{ exitDuration: 0 }}>
      <Menu.Target>
        <Button variant="default" size="compact-sm" leftSection={<IconLanguage size={16} />}>
          {(active ?? LANGUAGES[0]).label}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        {LANGUAGES.map((language) => (
          <Menu.Item
            key={language.code}
            onClick={() => changeLanguage(language.code)}
            rightSection={language.code === active?.code ? <IconCheck size={14} /> : null}
          >
            {language.label}
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
