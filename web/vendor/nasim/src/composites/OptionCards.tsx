'use client';

import { Label, Radio, RadioGroup } from '@heroui/react';
import type { ReactNode } from 'react';
import { tv } from 'tailwind-variants';

const optionCards = tv({
  slots: {
    // The group's own spacing between radios is a margin; the cards are spaced with a gap instead.
    group: 'gap-2 [&_[data-slot=radio]]:mt-0!',
    radio: 'w-full',
    card: [
      'w-full gap-3 rounded-2xl border border-border bg-surface px-4 py-3 text-start',
      'transition-colors motion-reduce:transition-none',
      'data-[selected=true]:border-accent data-[selected=true]:bg-accent-soft',
      'data-[focus-visible=true]:outline-2 data-[focus-visible=true]:outline-solid data-[focus-visible=true]:outline-offset-2 data-[focus-visible=true]:outline-focus',
    ],
    control: 'size-5',
    icon: 'grid size-9 shrink-0 place-items-center rounded-full bg-default text-muted [&>svg]:size-5',
    text: 'flex min-w-0 flex-1 flex-col gap-0.5',
    title: 'font-medium text-foreground',
    description:
      'text-sm font-normal text-muted text-pretty whitespace-pre-line',
    meta: 'shrink-0 text-sm font-semibold text-foreground',
  },
});

export type OptionCard = {
  value: string;
  title: string;
  /** A line under the title; a node when it is drawn some way of its own (a font's sample). */
  description?: ReactNode;
  /** What is said at the end of the card: a price, a fee. */
  meta?: ReactNode;
  icon?: ReactNode;
  isDisabled?: boolean;
};

type OptionCardsProps = {
  /** What is being chosen («روش پرداخت»): it names the group. */
  label: string;
  /** Name the group for a screen reader only, when the screen has a heading of its own for it. */
  hideLabel?: boolean;
  value: string | null;
  onChange: (value: string) => void;
  options: OptionCard[];
  isInvalid?: boolean;
  /** Lays the cards out some other way than one under the other (a grid). */
  className?: string;
};

// One of a few choices that need more than a word, as radio cards (a package with its price).
export function OptionCards({
  label,
  hideLabel,
  value,
  onChange,
  options,
  isInvalid,
  className,
}: OptionCardsProps) {
  const slots = optionCards();
  return (
    <RadioGroup
      value={value}
      onChange={onChange}
      isInvalid={isInvalid}
      variant="secondary"
      className={slots.group({ className })}
    >
      <Label className={hideLabel ? 'sr-only' : undefined}>{label}</Label>
      {options.map((option) => (
        <Radio
          key={option.value}
          value={option.value}
          isDisabled={option.isDisabled}
          className={slots.radio()}
        >
          <Radio.Content className={slots.card()}>
            <Radio.Control className={slots.control()}>
              <Radio.Indicator />
            </Radio.Control>
            {option.icon ? (
              <span aria-hidden className={slots.icon()}>
                {option.icon}
              </span>
            ) : null}
            <span className={slots.text()}>
              <span className={slots.title()}>{option.title}</span>
              {option.description ? (
                <span className={slots.description()}>
                  {option.description}
                </span>
              ) : null}
            </span>
            {option.meta ? (
              <span className={slots.meta()}>{option.meta}</span>
            ) : null}
          </Radio.Content>
        </Radio>
      ))}
    </RadioGroup>
  );
}
