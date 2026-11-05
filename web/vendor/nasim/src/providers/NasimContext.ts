'use client';

import { createContext, use } from 'react';

type NasimContextValue = {
  /** The host app shows its own back control (Telegram's BackButton), so pages draw no arrow. */
  nativeBack: boolean;
};

export const NasimContext = createContext<NasimContextValue>({
  nativeBack: false,
});

/** True when the host provides back navigation: `PageHeader` then omits its in-page arrow. */
export function useNativeBack(): boolean {
  return use(NasimContext).nativeBack;
}
