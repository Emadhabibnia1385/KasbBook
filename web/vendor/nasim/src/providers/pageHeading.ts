'use client';

import { useLayoutEffect, useSyncExternalStore } from 'react';

// The title of the page on screen, told by its PageHeader, so a bar above need not repeat it.
let heading: string | undefined;
const listeners = new Set<() => void>();

function publish(next: string | undefined) {
  heading = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Announces a page's title while it is on screen; `PageHeader` does it for its h1. */
export function useAnnouncePageHeading(title: string | undefined): void {
  useLayoutEffect(() => {
    if (title === undefined) return;
    publish(title);
    return () => {
      if (heading === title) publish(undefined);
    };
  }, [title]);
}

/** The title the page on screen announced, if it has a PageHeader. */
export function usePageHeading(): string | undefined {
  return useSyncExternalStore(
    subscribe,
    () => heading,
    () => undefined,
  );
}
