import { DatesProvider } from '@mantine/dates';
import 'dayjs/locale/fr';
import 'dayjs/locale/zh-cn';
import { ReactNode, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';

import { currentTitleClaim } from '@components/utils/util';
import { languageCode } from '../../../i18n';

// dayjs only ships English locale data by default, so without these imports
// @mantine/dates spells month and weekday names in English for every language.
const DAYJS_LOCALES: Record<string, string> = { zh: 'zh-cn', en: 'en', fr: 'fr' };

/**
 * Keeps `<title>` and `<html lang>` in sync with the active language for every
 * route, including the ones that render no app shell (login, 404, the public
 * public results pages). Mounted once, above the router's `<Routes>`.
 */
export function DocumentHead() {
  const { t, i18n } = useTranslation();
  const { pathname } = useLocation();
  const language = i18n.resolvedLanguage ?? i18n.language ?? 'zh';

  // Drives screen-reader voice selection, browser translation prompts and hyphenation.
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  // React finishes rendering the whole tree before running any effect, so by the
  // time this runs the routed page has already claimed its own title if it wants
  // one. Re-evaluating the claim (instead of skipping) also re-localizes it when
  // the language changes while the page itself does not re-render.
  useEffect(() => {
    const claim = currentTitleClaim();
    document.title = claim != null ? claim() : t('site_name');
  }, [t, language, pathname]);

  return null;
}

/** Gives the `@mantine/dates` calendars month and weekday names in the active language. */
export function LocalizedDatesProvider({ children }: { children: ReactNode }) {
  // Subscribes this component to language changes; `languageCode` then reports the new one.
  useTranslation();
  const locale = DAYJS_LOCALES[languageCode()] ?? 'zh-cn';

  return <DatesProvider settings={{ locale }}>{children}</DatesProvider>;
}
