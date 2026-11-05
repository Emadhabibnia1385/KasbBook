import { chipVariants } from '@heroui/styles';
import type { ReactNode } from 'react';
import { tv } from 'tailwind-variants';
import {
  CheckIcon,
  DangerIcon,
  ErrorIcon,
  InfoIcon,
  NeutralIcon,
} from '../icons';

export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

// Soft pairs: coloured text always sits on its own tint (4.5:1 in both themes, tokens.test.ts).
const statusChip = tv({
  base: 'gap-1.5 font-semibold',
  variants: {
    tone: {
      success: 'bg-success-soft text-success-soft-foreground',
      warning: 'bg-warning-soft text-warning-soft-foreground',
      danger: 'bg-danger-soft text-danger-soft-foreground',
      info: 'bg-info-soft text-info-soft-foreground',
      neutral: 'bg-default text-default-foreground',
    },
  },
});

const ICONS = {
  success: CheckIcon,
  warning: ErrorIcon,
  danger: DangerIcon,
  info: InfoIcon,
  neutral: NeutralIcon,
} as const;

type StatusChipProps = {
  tone: StatusTone;
  /** The status in words: the chip is never colour alone. */
  label: string;
  size?: 'sm' | 'md' | 'lg';
  /** Replaces the tone's icon (a clock for «waiting», an hourglass for «expired»). */
  icon?: ReactNode;
  className?: string;
};

// A status as an icon and words on a soft tint. Server-renderable: plain markup, HeroUI's chip classes.
export function StatusChip({
  tone,
  label,
  size = 'md',
  icon,
  className,
}: StatusChipProps) {
  const slots = chipVariants({ variant: 'soft', size });
  const Icon = ICONS[tone];
  return (
    <span
      data-slot="chip"
      data-tone={tone}
      className={slots.base({ className: statusChip({ tone, className }) })}
    >
      <span aria-hidden className="inline-flex shrink-0">
        {icon ?? <Icon />}
      </span>
      <span data-slot="chip-label" className={slots.label()}>
        {label}
      </span>
    </span>
  );
}
