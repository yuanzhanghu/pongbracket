import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import Backend from 'i18next-http-backend';
import { initReactI18next } from 'react-i18next';

// Injected by Vite at build time (see vite.config.ts). Changes every build so
// returning users fetch fresh locale files instead of a stale cached copy.
declare const __BUILD_ID__: string;

i18n
  .use(Backend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    // Default this deployment to Chinese. An explicit `?lng=` wins, then the
    // language picked from the header switcher (kept in localStorage); the
    // browser's own language is still ignored.
    fallbackLng: 'zh',
    detection: {
      order: ['querystring', 'localStorage'],
      caches: ['localStorage'],
    },
    defaultNS: 'common',
    // Run detection inside init() instead of on a `setTimeout(0)`, so the language
    // is resolved and cached before the `?lng=` clean-up below (and before React
    // mounts). All plugins are registered above, which is the only reason i18next
    // defers init in the first place.
    initAsync: false,
    backend: {
      loadPath: `/locales/{{lng}}/{{ns}}.json?v=${__BUILD_ID__}`,
    },
    interpolation: {
      escapeValue: false,
    },
  });

// `?lng=` is a one-shot entry point (the user guide links to `/?lng=fr`). Detection
// ranks it above localStorage, so leaving it in the address bar would re-apply it on
// every reload and silently undo a later switch in the header. Detection has run and
// cached its result by now, so the parameter has done its job and can go — before
// React mounts, so the router never sees it.
const initialUrl = new URL(window.location.href);
if (initialUrl.searchParams.has('lng')) {
  initialUrl.searchParams.delete('lng');
  window.history.replaceState(
    window.history.state,
    '',
    `${initialUrl.pathname}${initialUrl.search}${initialUrl.hash}`
  );
}

/** Base code of the active language, with any region stripped ("zh-CN" -> "zh"). */
export function languageCode() {
  return (i18n.resolvedLanguage ?? i18n.language ?? 'zh').split('-')[0];
}

export default i18n;
