'use client';

import { type RefObject, useLayoutEffect, useRef } from 'react';

/** Ref for a bottom bar you draw: its height becomes --nasim-bottom-bar, which toasts clear. */
export function useBottomBar<T extends HTMLElement>(): RefObject<T | null> {
  const ref = useRef<T>(null);
  useLayoutEffect(() => {
    const bar = ref.current;
    if (!bar) return;
    const root = document.documentElement;
    const publish = () =>
      root.style.setProperty('--nasim-bottom-bar', `${bar.offsetHeight}px`);
    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(bar);
    return () => {
      observer.disconnect();
      root.style.removeProperty('--nasim-bottom-bar');
    };
  }, []);
  return ref;
}
