'use client';

import { Spinner as HeroSpinner, type SpinnerProps } from '@heroui/react';
import type { ComponentProps } from 'react';
import { t } from '../strings';

// HeroUI labels its spinner "Loading"; screen-reader users here get Persian.
export function Spinner(
  props: SpinnerProps & Omit<ComponentProps<'span'>, 'color'>,
) {
  return <HeroSpinner aria-label={t.common.loading} {...props} />;
}
