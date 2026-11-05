'use client';

import {
  createContext,
  type ReactNode,
  use,
  useCallback,
  useLayoutEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from 'react';
import { paletteCss, paletteSchemes, type Palette } from '../palette';
import {
  type ColorScheme,
  parseThemeMode,
  type ThemeMode,
  themeCookie,
} from './themeMode';

const STORAGE_KEY = 'nasim-theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';
const SCHEMES: ColorScheme[] = ['light', 'dark'];
const DEFAULT_FONT = 'vazirmatn'; // the page's font with no data-font (fonts.css)

type ThemeContextValue = {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  /** The scheme applied to <html> right now. */
  scheme: ColorScheme;
  /** Feeds the scheme "telegram" mode follows; call it from a layout effect. */
  setScheme: (scheme: ColorScheme) => void;
  /** The mode that follows the host: "telegram" where the app starts in it, else "system". */
  automatic: ThemeMode;
  /** The scheme `automatic` shows right now (the device's or Telegram's). */
  automaticScheme: ColorScheme;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored(): ThemeMode | null {
  try {
    return parseThemeMode(localStorage.getItem(STORAGE_KEY)) ?? null;
  } catch {
    return null;
  }
}

function subscribeToDevice(onChange: () => void) {
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

const deviceScheme = (): ColorScheme =>
  window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
const lightScheme = (): ColorScheme => 'light';

// The saved choice only changes through setMode, so there is nothing to subscribe to; a store
// still keeps the hydration pass on what the server rendered (no saved choice) before it is read.
const neverChanges = () => () => {};
const noChoice = (): ThemeMode | null => null;

export type ThemeProviderProps = {
  children: ReactNode;
  /** "telegram" inside the Mini App, "system" on the website. A saved choice wins. */
  defaultMode?: ThemeMode;
  /** Read and save the choice in localStorage (default true); off where Telegram decides. */
  persist?: boolean;
  /** The external scheme, if known at first render, so the first paint is right. */
  initialScheme?: ColorScheme;
  /**
   * The saved choice as the server read it from the `THEME_COOKIE` cookie (`parseThemeMode`), so
   * the server render and the first client render agree. Used until the browser's own is read.
   */
  initialMode?: ThemeMode;
  /** The reseller's brand colour as #rrggbb. */
  accent?: string;
  /** The reseller's font id, one of the `data-font` rules in fonts.css; none is Vazirmatn. */
  font?: string;
  /** The product's own colours (`Palette`); rendered as a stylesheet, on the server too. */
  palette?: Palette;
};

// The one theme controller (class, data-theme, accent, font on <html>); never HeroUI's useTheme.
export function ThemeProvider({
  children,
  defaultMode = 'system',
  persist = true,
  initialScheme,
  initialMode,
  accent,
  font,
  palette,
}: ThemeProviderProps) {
  const stored = useSyncExternalStore(
    neverChanges,
    persist ? readStored : noChoice,
    noChoice,
  );
  const [picked, setPicked] = useState<ThemeMode | null>(null);
  const mode =
    picked ?? stored ?? (persist ? initialMode : undefined) ?? defaultMode;
  const [external, setScheme] = useState<ColorScheme | undefined>(
    initialScheme,
  );
  const device = useSyncExternalStore(
    subscribeToDevice,
    deviceScheme,
    lightScheme,
  );
  const scheme =
    mode === 'light' || mode === 'dark'
      ? mode
      : mode === 'telegram'
        ? (external ?? device)
        : device;

  useLayoutEffect(() => {
    const root = document.documentElement;
    const before = {
      classes: SCHEMES.filter((c) => root.classList.contains(c)),
      theme: root.dataset.theme,
    };
    root.classList.remove(...SCHEMES);
    root.classList.add(scheme);
    root.dataset.theme = scheme;
    return () => {
      root.classList.remove(scheme);
      root.classList.add(...before.classes);
      if (before.theme === undefined) delete root.dataset.theme;
      else root.dataset.theme = before.theme;
    };
  }, [scheme]);

  // The accent is fitted against the palette's surfaces when the product has one. Its maths is a
  // chunk of its own: an app that never passes an accent never downloads it.
  const schemes = useMemo(
    () => (palette ? paletteSchemes(palette) : undefined),
    [palette],
  );
  useLayoutEffect(() => {
    if (!accent) return;
    let undo: (() => void) | undefined;
    let unmounted = false;
    void import('./accent').then(({ applyAccent }) => {
      if (!unmounted)
        undo = applyAccent(accent, document.documentElement, schemes);
    });
    return () => {
      unmounted = true;
      undo?.();
    };
  }, [accent, schemes]);

  useLayoutEffect(() => {
    if (!font || font === DEFAULT_FONT) return;
    const root = document.documentElement;
    root.dataset.font = font;
    return () => {
      delete root.dataset.font;
    };
  }, [font]);

  const setMode = useCallback(
    (next: ThemeMode) => {
      setPicked(next);
      if (!persist) return;
      // Going back to the default is forgetting the choice, so nothing stale outlives it.
      const kept = next === defaultMode ? null : next;
      try {
        if (kept) localStorage.setItem(STORAGE_KEY, kept);
        else localStorage.removeItem(STORAGE_KEY);
      } catch {
        // private mode: the choice lasts for this visit only
      }
      try {
        document.cookie = themeCookie(kept, location.protocol === 'https:');
      } catch {
        // cookies blocked: the next visit starts from the default
      }
    },
    [persist, defaultMode],
  );

  const automatic: ThemeMode =
    defaultMode === 'telegram' ? 'telegram' : 'system';
  const automaticScheme =
    automatic === 'telegram' ? (external ?? device) : device;
  const value = useMemo(
    () => ({ mode, setMode, scheme, setScheme, automatic, automaticScheme }),
    [mode, setMode, scheme, automatic, automaticScheme],
  );
  return (
    <ThemeContext value={value}>
      {palette ? (
        <style href="nasim-palette" precedence="high">
          {paletteCss(palette)}
        </style>
      ) : null}
      {children}
    </ThemeContext>
  );
}

export function useTheme(): ThemeContextValue {
  const value = use(ThemeContext);
  if (!value) throw new Error('useTheme needs <NasimProvider> above it');
  return value;
}
