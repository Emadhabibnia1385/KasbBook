'use client';

import { buttonVariants, type ButtonProps } from '@heroui/react';
import { Link, type LinkProps } from 'react-aria-components';

type LinkButtonProps = Omit<LinkProps, 'className'> &
  Pick<ButtonProps, 'variant' | 'size' | 'fullWidth' | 'isIconOnly'> & {
    className?: string;
  };

// A link that looks like a button; with NasimProvider's router bridge `href` navigates in-app.
// A link that opens a new tab never hands the new page this one's window.
export function LinkButton({
  variant,
  size,
  fullWidth,
  isIconOnly,
  className,
  target,
  rel,
  ...props
}: LinkButtonProps) {
  return (
    <Link
      {...props}
      target={target}
      rel={rel ?? (target === '_blank' ? 'noopener noreferrer' : undefined)}
      className={buttonVariants({
        variant,
        size,
        fullWidth,
        isIconOnly,
        className,
      })}
    />
  );
}
