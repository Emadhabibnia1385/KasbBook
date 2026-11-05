'use client';

import { SearchField } from '@heroui/react';
import { t } from '../strings';

type SearchBoxProps = {
  /** What is searched: it names the box for a screen reader, as there is no visible label. */
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

// A search box outside a form: the clear button and Escape empty it; the button is labelled.
export function SearchBox({
  label,
  value,
  onChange,
  placeholder,
}: SearchBoxProps) {
  return (
    <SearchField fullWidth aria-label={label} value={value} onChange={onChange}>
      <SearchField.Group>
        <SearchField.SearchIcon />
        <SearchField.Input placeholder={placeholder ?? label} />
        <SearchField.ClearButton aria-label={t.common.clearSearch} />
      </SearchField.Group>
    </SearchField>
  );
}
