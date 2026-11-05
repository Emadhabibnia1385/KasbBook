'use client';

import { Toast, useMediaQuery } from '@heroui/react';
import { t } from '../strings';
import { Spinner } from '../primitives/Spinner';

// Composed here: HeroUI's toast says "Close" in English; an action calls `toast.close(id)` itself.
export function ToastRegion() {
  const isPhone = useMediaQuery('(max-width: 768px)');
  return (
    <Toast.Provider aria-label={t.toast.region} placement="bottom">
      {({ toast }) => {
        const {
          title,
          description,
          indicator,
          isLoading,
          variant,
          actionProps,
        } = toast.content ?? {};
        const action = actionProps?.children ? (
          <Toast.ActionButton {...actionProps} />
        ) : null;
        return (
          <Toast toast={toast} variant={variant}>
            {indicator === null ? null : (
              <Toast.Indicator variant={variant}>
                {isLoading ? <Spinner color="current" size="sm" /> : indicator}
              </Toast.Indicator>
            )}
            <Toast.Content>
              {title ? <Toast.Title>{title}</Toast.Title> : null}
              {description ? (
                <Toast.Description>{description}</Toast.Description>
              ) : null}
              {isPhone ? action : null}
            </Toast.Content>
            {isPhone ? null : action}
            <Toast.CloseButton aria-label={t.common.close} />
          </Toast>
        );
      }}
    </Toast.Provider>
  );
}
