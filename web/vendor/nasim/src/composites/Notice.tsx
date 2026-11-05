'use client';

import { Alert } from '@heroui/react';
import type { ReactNode } from 'react';
import { tv } from 'tailwind-variants';

const notice = tv({ base: 'border border-border' });

const STATUS = {
  info: 'accent',
  success: 'success',
  warning: 'warning',
  danger: 'danger',
  neutral: 'default',
} as const;

export type NoticeTone = keyof typeof STATUS;

type NoticeProps = {
  tone?: NoticeTone;
  title?: ReactNode;
  children?: ReactNode;
  /** "alert" for a failure that appears in answer to an action, "status" for good news. */
  role?: 'alert' | 'status';
  className?: string;
};

// An inline message: HeroUI's alert with its icon, a title and the words. Never colour alone.
export function Notice({
  tone = 'info',
  title,
  children,
  role,
  className,
}: NoticeProps) {
  return (
    <Alert status={STATUS[tone]} role={role} className={notice({ className })}>
      <Alert.Indicator />
      <Alert.Content>
        {title ? <Alert.Title>{title}</Alert.Title> : null}
        {children ? <Alert.Description>{children}</Alert.Description> : null}
      </Alert.Content>
    </Alert>
  );
}
