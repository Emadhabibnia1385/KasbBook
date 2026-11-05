'use client';

import {
  CloseButton as HeroCloseButton,
  type CloseButtonProps,
} from '@heroui/react';
import { t } from '../strings';

// HeroUI labels its close button "Close"; screen-reader users here get Persian.
export function CloseButton(props: CloseButtonProps) {
  return <HeroCloseButton aria-label={t.common.close} {...props} />;
}
