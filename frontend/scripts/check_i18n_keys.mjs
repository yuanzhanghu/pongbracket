#!/usr/bin/env node
/**
 * Guards the translation catalogues against the two failures that are invisible at
 * runtime:
 *
 *  1. A `t('key')` / `<Trans i18nKey="key">` reference that no catalogue defines.
 *     With `fallbackLng: 'zh'` i18next silently renders the raw key name, so a page
 *     title reading "site_name" would ship without anything complaining.
 *  2. Key-set drift between the languages this deployment offers, which makes a
 *     string work in one language and turn into its key name in another.
 *
 * Run via `pnpm run check:i18n` (part of `pnpm test`, which CI runs).
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = join(frontendDir, 'src');

/** The languages the header switcher offers; these are the ones that must agree. */
const LANGUAGES = ['en', 'zh', 'fr'];

/** i18next's plural suffixes. Which of them a language uses is decided by CLDR. */
const PLURAL_SUFFIXES = ['zero', 'one', 'two', 'few', 'many', 'other'];

/**
 * Call sites that assemble their key at runtime, with the complete set of keys each
 * one can produce. Listing them here keeps the file itself under the static scan and
 * still verifies the generated keys, instead of skipping the file wholesale. A
 * template literal that is not listed here is an error, so a new dynamic call site
 * cannot slip through unnoticed.
 */
const DYNAMIC_KEYS = {
  'src/components/utils/file_upload.tsx': {
    'upload_placeholder_${variant}': ['upload_placeholder_tournament', 'upload_placeholder_team'],
  },
};

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(entry) ? [path] : [];
  });
}

function lineOf(source, index) {
  return source.slice(0, index).split('\n').length;
}

/** Reads the single quoted/backticked argument starting at `index`, if there is one. */
function readFirstArgument(source, index) {
  let cursor = index;
  while (/\s/.test(source[cursor])) cursor += 1;
  const quote = source[cursor];
  if (quote !== "'" && quote !== '"' && quote !== '`') return null;
  let end = cursor + 1;
  while (end < source.length && source[end] !== quote) {
    if (source[end] === '\\') end += 1;
    end += 1;
  }
  return { quote, text: source.slice(cursor + 1, end) };
}

/** Every key the code asks for, as `key -> ["file:line", ...]`. */
function collectReferences(files) {
  const references = new Map();
  const errors = [];

  const record = (key, location) => {
    if (!references.has(key)) references.set(key, []);
    references.get(key).push(location);
  };

  for (const file of files) {
    const relativePath = relative(frontendDir, file);
    const source = readFileSync(file, 'utf8');

    // `t(`, `i18n.t(`, but not `foo.t(` or `sqrt(`.
    for (const match of source.matchAll(/(?<![A-Za-z0-9_$.])(?:i18n\.)?t\(/g)) {
      const at = `${relativePath}:${lineOf(source, match.index)}`;
      const argument = readFirstArgument(source, match.index + match[0].length);

      if (argument == null) {
        errors.push(`${at}: t() called with a non-literal key; cannot be verified`);
        continue;
      }
      if (argument.quote === '`' && argument.text.includes('${')) {
        const declared = DYNAMIC_KEYS[relativePath]?.[argument.text];
        if (declared == null) {
          errors.push(
            `${at}: undeclared dynamic key \`${argument.text}\`; ` +
              'add it (with every key it can produce) to DYNAMIC_KEYS in scripts/check_i18n_keys.mjs'
          );
          continue;
        }
        declared.forEach((key) => record(key, at));
        continue;
      }
      record(argument.text, at);
    }

    for (const match of source.matchAll(/i18nKey=(?:"([^"]+)"|'([^']+)'|\{'([^']+)'\})/g)) {
      record(match[1] ?? match[2] ?? match[3], `${relativePath}:${lineOf(source, match.index)}`);
    }
  }

  return { references, errors };
}

function loadCatalogue(language) {
  const path = join(frontendDir, 'public', 'locales', language, 'common.json');
  return Object.keys(JSON.parse(readFileSync(path, 'utf8')));
}

/**
 * Collapses a plural set (`x_one`, `x_other`, ...) onto its base key, so languages
 * with different CLDR plural categories are not reported as drifting. The suffix is
 * only stripped when the language also defines the mandatory `_other` form.
 */
function baseKeys(keys) {
  const present = new Set(keys);
  return new Set(
    keys.map((key) => {
      const match = key.match(new RegExp(`^(.*)_(${PLURAL_SUFFIXES.join('|')})$`));
      return match != null && present.has(`${match[1]}_other`) ? match[1] : key;
    })
  );
}

const files = sourceFiles(srcDir);
const { references, errors } = collectReferences(files);
const resolvable = new Map(
  LANGUAGES.map((language) => [language, baseKeys(loadCatalogue(language))])
);

const missing = [];
for (const [key, locations] of [...references.entries()].sort()) {
  const absent = LANGUAGES.filter((language) => !resolvable.get(language).has(key));
  if (absent.length > 0) {
    missing.push(
      `  ${key}\n      missing from: ${absent.join(', ')}\n      used at: ${locations.join(', ')}`
    );
  }
}

const drift = [];
const everyKey = new Set(LANGUAGES.flatMap((language) => [...resolvable.get(language)]));
for (const key of [...everyKey].sort()) {
  // Already reported above, with its call sites, if the code references it.
  if (references.has(key)) continue;
  const absent = LANGUAGES.filter((language) => !resolvable.get(language).has(key));
  if (absent.length > 0) {
    const defined = LANGUAGES.filter((language) => resolvable.get(language).has(key));
    drift.push(`  ${key}\n      defined in: ${defined.join(', ')} — missing from: ${absent.join(', ')}`);
  }
}

const problems = [];
if (errors.length > 0) {
  problems.push(`Unverifiable t() call sites:\n${errors.map((e) => `  ${e}`).join('\n')}`);
}
if (missing.length > 0) {
  problems.push(`Keys referenced by the code but not translated:\n${missing.join('\n')}`);
}
if (drift.length > 0) {
  problems.push(
    `Catalogue key sets differ between ${LANGUAGES.join('/')}:\n${drift.join('\n')}\n` +
      '  (a key defined in only some languages renders as its own name in the others)'
  );
}

if (problems.length > 0) {
  console.error(`i18n check failed.\n\n${problems.join('\n\n')}\n`);
  process.exit(1);
}

console.log(
  `i18n check passed: ${references.size} keys referenced in ${files.length} files, ` +
    `${LANGUAGES.join('/')} catalogues in sync.`
);
