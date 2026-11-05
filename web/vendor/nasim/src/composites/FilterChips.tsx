'use client';

import { ToggleButton, ToggleButtonGroup } from '@heroui/react';

type FilterChipsProps = {
  /** What is being filtered («وضعیت سرویس»): it names the group. */
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
};

// One of a few filters, always one chosen: a radio group drawn as chips that wrap when narrow.
export function FilterChips({
  label,
  value,
  onChange,
  options,
}: FilterChipsProps) {
  return (
    <ToggleButtonGroup
      aria-label={label}
      isDetached
      disallowEmptySelection
      selectionMode="single"
      selectedKeys={[value]}
      onSelectionChange={(keys) => {
        const [next] = keys;
        if (next !== undefined) onChange(String(next));
      }}
      className="flex-wrap gap-2"
    >
      {options.map((option) => (
        <ToggleButton
          key={option.value}
          id={option.value}
          className="min-h-11 sm:min-h-10"
        >
          {option.label}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
