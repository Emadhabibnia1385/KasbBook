'use client';

import { Description, Switch } from '@heroui/react';
import { type Binding, type FieldProps, WithBinding } from './binding';

type SwitchFieldProps = Omit<FieldProps, 'isRequired'> & Binding<boolean>;

export function SwitchField({
  label,
  description,
  isDisabled,
  className,
  'data-testid': testId,
  ...binding
}: SwitchFieldProps) {
  return (
    <WithBinding<boolean> binding={binding as Binding<boolean>}>
      {(field) => (
        <Switch
          name={field.name}
          isSelected={Boolean(field.value)}
          onChange={field.onChange}
          onBlur={field.onBlur}
          isDisabled={isDisabled}
          className={className}
          data-testid={testId}
        >
          <Switch.Content className="min-h-(--nasim-tap-target)">
            <Switch.Control>
              <Switch.Thumb />
            </Switch.Control>
            {label}
          </Switch.Content>
          {description ? <Description>{description}</Description> : null}
        </Switch>
      )}
    </WithBinding>
  );
}
