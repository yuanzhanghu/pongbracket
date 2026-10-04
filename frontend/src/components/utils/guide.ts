import type { i18n as I18n } from 'i18next';

// The user guide and the landing screenshots are pre-rendered per language
// (e2e/demo_*_flow.py and e2e/capture_landing_shots.py generate them). Chinese
// keeps the bare file name, the other languages carry a language suffix:
// basic.html / basic.en.html, stages.png / stages.en.png.
const GUIDE_LANGUAGES = ['zh', 'en', 'fr'];

// `?lng=` may carry a region ("en-US"), so match on the base language too.
function guideLanguage(i18n: I18n): string {
  const current = i18n.resolvedLanguage ?? i18n.language ?? '';
  return GUIDE_LANGUAGES.find((l) => current === l || current.startsWith(`${l}-`)) ?? 'zh';
}

/** The guide entry page, carrying the active language so it opens in it. */
export function guideIndexHref(i18n: I18n): string {
  const lang = guideLanguage(i18n);
  return lang === 'zh' ? '/guide/index.html' : `/guide/index.html?lng=${lang}`;
}

/** A landing screenshot (`stages`, `schedule`, ...) in the active language. */
export function guideShot(name: string, i18n: I18n): string {
  const lang = guideLanguage(i18n);
  return lang === 'zh' ? `/guide/${name}.png` : `/guide/${name}.${lang}.png`;
}
