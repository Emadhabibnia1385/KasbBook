'use client';

import { useSyncExternalStore } from 'react';

// Tailwind's `sm` and `md` minimum widths, minus a hair so the two queries never both match.
const QUERIES = {
  sm: '(max-width: 639.98px)',
  md: '(max-width: 767.98px)',
} as const;

type Breakpoint = keyof typeof QUERIES;

// One stable subscribe function per query: a new one each render would resubscribe each render.
function subscriber(query: string) {
  return (onChange: () => void) => {
    const list = window.matchMedia(query);
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  };
}

const SUBSCRIBE: Record<Breakpoint, (onChange: () => void) => () => void> = {
  sm: subscriber(QUERIES.sm),
  md: subscriber(QUERIES.md),
};
const NEVER = () => () => {};

/**
 * Whether the viewport is narrower than a Tailwind breakpoint (`"sm"` 640 px, `"md"` 768 px). The
 * server, and the first client render, say no, so the markup matches and the narrow layout swaps in
 * after hydration; only one layout is ever in the DOM. `undefined` never listens and is always false.
 */
export function useIsNarrow(below?: Breakpoint): boolean {
  return useSyncExternalStore(
    below ? SUBSCRIBE[below] : NEVER,
    () => (below ? window.matchMedia(QUERIES[below]).matches : false),
    () => false,
  );
}
