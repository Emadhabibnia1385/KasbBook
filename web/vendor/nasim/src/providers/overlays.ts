'use client';

import { useEffect, useEffectEvent, useSyncExternalStore } from 'react';

// Open dialogs and sheets, topmost last: registered so Telegram's BackButton can close the top.
type Entry = { close: () => void };

let stack: readonly Entry[] = [];
const listeners = new Set<() => void>();

function publish(next: readonly Entry[]) {
  stack = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Adds a layer; the returned function removes it. */
export function registerOverlay(close: () => void): () => void {
  const entry: Entry = { close };
  publish([...stack, entry]);
  return () => publish(stack.filter((item) => item !== entry));
}

/** Closes the topmost layer. Returns false when nothing was open. */
export function closeTopOverlay(): boolean {
  const top = stack.at(-1);
  if (!top) return false;
  top.close();
  return true;
}

/** How many layers are open, and a way to close the top one. */
export function useOverlayStack(): { count: number; closeTop: () => boolean } {
  const count = useSyncExternalStore(
    subscribe,
    () => stack.length,
    () => 0,
  );
  return { count, closeTop: closeTopOverlay };
}

/** Registers a layer while `isOpen`. `BottomSheet` and `ConfirmDialog` already do this. */
export function useRegisterOverlay(isOpen: boolean, close: () => void): void {
  const latest = useEffectEvent(close);
  useEffect(() => {
    if (isOpen) return registerOverlay(() => latest());
  }, [isOpen]);
}
