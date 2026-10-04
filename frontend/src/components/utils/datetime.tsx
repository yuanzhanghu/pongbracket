import { format, parseISO } from 'date-fns';
import { enUS, fr, zhCN } from 'date-fns/locale';
import { languageCode } from '../../../i18n';

// Without a locale, date-fns spells `LLLL` month names in English whatever the UI
// language is, so French dates came out as "3 January 2026".
const DATE_LOCALES = { zh: zhCN, en: enUS, fr } as const;

export function dateLocale() {
  return DATE_LOCALES[languageCode() as keyof typeof DATE_LOCALES] ?? zhCN;
}

function dateFormat() {
  return languageCode() === 'zh' ? 'yyyy年M月d日 HH:mm' : 'd LLLL yyyy HH:mm';
}

// Month and day without the year, for chart axes. French writes the day first;
// Chinese and English both start with the month.
function monthDayFormat() {
  return languageCode() === 'fr' ? 'd/M' : 'M/d';
}

export function formatMonthDay(datetime: string) {
  return format(parseISO(datetime), monthDayFormat(), { locale: dateLocale() });
}

// The day on its own, for tables that list one row per event date.
function dateOnlyFormat() {
  return languageCode() === 'zh' ? 'yyyy年M月d日' : 'd LLLL yyyy';
}

export function DateOnly({ datetime }: { datetime: string }) {
  const date = parseISO(datetime);
  return (
    <time dateTime={datetime}>{format(date, dateOnlyFormat(), { locale: dateLocale() })}</time>
  );
}

export function DateTime({ datetime }: { datetime: string }) {
  const date = parseISO(datetime);
  return <time dateTime={datetime}>{format(date, dateFormat(), { locale: dateLocale() })}</time>;
}

export function Time({ datetime }: { datetime: string }) {
  const date = parseISO(datetime);
  return <time dateTime={datetime}>{format(date, 'HH:mm')}</time>;
}

export function formatTime(datetime: string) {
  return format(parseISO(datetime), 'HH:mm');
}

export function compareDateTime(datetime1: string, datetime2: string) {
  return parseISO(datetime1) > parseISO(datetime2);
}
