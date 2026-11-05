/// <reference path="./react-aria-i18n.d.ts" />
import enUS from 'react-aria-components/i18n/en-US';
import { t } from '../strings';

// React Aria has no override API: its strings global holds every package, so Persian overlays it.
const LOCALE = Symbol.for('react-aria.i18n.locale');
const STRINGS = Symbol.for('react-aria.i18n.strings');

type Dictionary = Record<string, Record<string, unknown>>;

export function buildPersianStrings(): Dictionary {
  const persian: Dictionary = t.reactAria;
  const merged: Dictionary = {};
  for (const [pkg, english] of Object.entries(enUS)) {
    merged[pkg] = { ...english, ...persian[pkg] };
  }
  // Upstream asks for "link-preview" but ships the strings under "previewtrigger".
  merged['@react-aria/link-preview'] ??=
    merged['@react-aria/previewtrigger'] ?? {};
  return merged;
}

/** Call before the first React Aria component renders; later calls do nothing. */
export function installReactAriaStrings(): void {
  // React Aria reads the global only in a browser, so a server render keeps its English strings.
  if (typeof window === 'undefined') return;
  const target = window as unknown as Record<symbol, unknown>;
  if (target[STRINGS]) return;
  try {
    target[LOCALE] = 'fa-IR';
    target[STRINGS] = buildPersianStrings();
  } catch {
    // Read-only window: React Aria keeps its English strings.
  }
}
