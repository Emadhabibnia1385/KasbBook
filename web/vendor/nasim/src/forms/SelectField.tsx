'use client';

import { Description, FieldError, Label, ListBox } from '@heroui/react';
import { Select } from '../primitives';
import {
  type Binding,
  type FieldProps,
  WithBinding,
  describes,
} from './binding';

type SelectFieldProps = FieldProps &
  Binding<string | null> & {
    options: { value: string; label: string; isDisabled?: boolean }[];
    /** Defaults to «انتخاب کنید». */
    placeholder?: string;
  };

// In a form the value is the chosen option's `value`, or undefined while nothing is chosen. Controlled,
// it is that string or null.
export function SelectField({
  label,
  description,
  isRequired,
  isDisabled,
  className,
  'data-testid': testId,
  options,
  placeholder,
  ...binding
}: SelectFieldProps) {
  return (
    <WithBinding<string | null> binding={binding as Binding<string | null>}>
      {(field) => (
        <Select
          fullWidth
          {...describes(description)}
          name={field.name}
          placeholder={placeholder}
          value={field.value ?? null}
          onChange={(key) => field.onChange(key === null ? null : String(key))}
          onBlur={field.onBlur}
          isInvalid={field.isInvalid}
          isRequired={isRequired}
          isDisabled={isDisabled}
          className={className}
          data-testid={testId}
          disabledKeys={options
            .filter((option) => option.isDisabled)
            .map((option) => option.value)}
          validationBehavior="aria"
        >
          <Label>{label}</Label>
          <Select.Trigger ref={field.inputRef}>
            <Select.Value />
            <Select.Indicator />
          </Select.Trigger>
          {description ? <Description>{description}</Description> : null}
          <FieldError>{field.errorMessage}</FieldError>
          <Select.Popover>
            <ListBox>
              {options.map((option) => (
                <ListBox.Item
                  key={option.value}
                  id={option.value}
                  textValue={option.label}
                >
                  {option.label}
                  <ListBox.ItemIndicator />
                </ListBox.Item>
              ))}
            </ListBox>
          </Select.Popover>
        </Select>
      )}
    </WithBinding>
  );
}
