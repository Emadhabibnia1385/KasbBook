'use client';

import { createContext, use } from 'react';

// FormRoot publishes "a submit is running" here; a stable form object cannot re-render readers.
export const SubmittingContext = createContext(false);

export function useSubmitting(): boolean {
  return use(SubmittingContext);
}
