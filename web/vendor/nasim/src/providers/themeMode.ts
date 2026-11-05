// Server-safe: a layout reads the saved choice with these before any client code runs.
export type ColorScheme = 'light' | 'dark';
/** Where the scheme comes from: the device, a fixed choice, or Telegram. */
export type ThemeMode = 'system' | 'light' | 'dark' | 'telegram';

export const THEME_MODES: ThemeMode[] = ['system', 'light', 'dark', 'telegram'];

/** The cookie that carries the saved choice to the server, so the first byte is in the right theme. */
export const THEME_COOKIE = 'nasim-theme';

/** The mode a saved value stands for, or undefined when it is none of them (a stale or foreign cookie). */
export function parseThemeMode(
  value: string | null | undefined,
): ThemeMode | undefined {
  return THEME_MODES.find((mode) => mode === value);
}

const ONE_YEAR_SECONDS = 365 * 24 * 60 * 60;

/**
 * The `document.cookie` value that saves a choice for a year on the whole site, or (null) removes it.
 * `SameSite=Lax` keeps it off cross-site requests; `Secure` is for https only, as a browser refuses it
 * on http.
 */
export function themeCookie(mode: ThemeMode | null, secure: boolean): string {
  const attributes = mode
    ? `Path=/; Max-Age=${ONE_YEAR_SECONDS}`
    : 'Path=/; Max-Age=0';
  return `${THEME_COOKIE}=${mode ?? ''}; ${attributes}; SameSite=Lax${secure ? '; Secure' : ''}`;
}
