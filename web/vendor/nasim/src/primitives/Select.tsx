'use client';

import { Select as HeroSelect, type SelectProps } from '@heroui/react';
import { t } from '../strings';

// The placeholder defaults to Persian (HeroUI's is English), also when a field passes undefined.
export function Select<
  T extends object,
  M extends 'single' | 'multiple' = 'single',
>({ placeholder = t.common.selectPlaceholder, ...props }: SelectProps<T, M>) {
  return <HeroSelect<T, M> placeholder={placeholder} {...props} />;
}

Select.Trigger = HeroSelect.Trigger;
Select.Value = HeroSelect.Value;
Select.Indicator = HeroSelect.Indicator;
Select.ClearButton = HeroSelect.ClearButton;
Select.Popover = HeroSelect.Popover;
