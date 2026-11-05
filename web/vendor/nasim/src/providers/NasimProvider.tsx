'use client';

import { I18nProvider, RouterProvider } from '@heroui/react';
import { type ReactNode, useMemo } from 'react';
import { NasimContext } from './NasimContext';
import { isExternalHref } from './links';
import { installReactAriaStrings } from './reactAriaStrings';
import { ThemeProvider, type ThemeProviderProps } from './ThemeProvider';
import { ToastRegion } from './ToastRegion';

/** What a link can ask of the host router; Next's `push` and `replace` take both. */
export type NasimNavigateOptions = { replace?: boolean; scroll?: boolean };

/** Takes an in-app address (`/services?tab=a`) and moves there without a page load. */
export type NasimNavigate = (
  href: string,
  options?: NasimNavigateOptions,
) => void;

// Lets `routerOptions` on Link, LinkButton and menu items carry what the host router understands.
declare module 'react-aria-components' {
  interface RouterConfig {
    routerOptions: NasimNavigateOptions;
  }
}

// React Aria reads its string dictionary on first use, so this runs when the module loads.
installReactAriaStrings();

export type NasimProviderProps = Omit<ThemeProviderProps, 'children'> & {
  children: ReactNode;
  /** The host router's push: in-app links then navigate without a page load. Keep it stable. */
  navigate?: NasimNavigate;
  /** The address a link shows (`href` attribute), for a router with a base path. Keep it stable. */
  useHref?: (href: string) => string;
  /** The host app provides back navigation (Telegram's BackButton): pages omit their back arrow. */
  nativeBack?: boolean;
};

// Wrap the app once: Persian locale and strings, links, theme, tenant accent, toast region.
export function NasimProvider({
  children,
  navigate,
  useHref: hostHref,
  nativeBack = false,
  ...theme
}: NasimProviderProps) {
  const context = useMemo(() => ({ nativeBack }), [nativeBack]);
  // The host function runs for every link, so it may be a hook; an external address ignores it.
  const useHref = useMemo(
    () =>
      hostHref &&
      ((href: string) => {
        const shown = hostHref(href);
        return isExternalHref(href) ? href : shown;
      }),
    [hostHref],
  );
  const content = (
    <ThemeProvider {...theme}>
      <NasimContext value={context}>
        {children}
        <ToastRegion />
      </NasimContext>
    </ThemeProvider>
  );
  return (
    <I18nProvider locale="fa-IR">
      {navigate ? (
        <RouterProvider navigate={navigate} useHref={useHref}>
          {content}
        </RouterProvider>
      ) : (
        content
      )}
    </I18nProvider>
  );
}
