'use client';

import { useSyncExternalStore } from 'react';
import { OfflineIcon } from '../icons';
import { t } from '../strings';

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange);
  window.addEventListener('offline', onChange);
  return () => {
    window.removeEventListener('online', onChange);
    window.removeEventListener('offline', onChange);
  };
}

/** Whether the device has a connection; the server (and the first client render) say yes. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  );
}

type OfflineBannerProps = {
  /** Defaults to Nasim's own words. */
  children?: string;
};

// A polite strip above the page while the connection is down; nothing at all while it is up.
export function OfflineBanner({
  children = t.state.offline,
}: OfflineBannerProps) {
  const online = useOnline();
  if (online) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-2 border-b border-warning bg-warning-soft px-4 py-2 text-sm text-foreground"
    >
      <span aria-hidden className="text-warning-soft-foreground">
        <OfflineIcon />
      </span>
      {children}
    </div>
  );
}
