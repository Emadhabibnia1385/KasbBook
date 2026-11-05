'use client';

import {
  Checkbox,
  CheckboxGroup,
  Description,
  FieldError,
  Label,
  Radio,
  RadioGroup,
} from '@heroui/react';
import type { ReactNode } from 'react';
import {
  type Binding,
  type FieldProps,
  WithBinding,
  describes,
} from './binding';

type ChoiceOption = {
  value: string;
  label: ReactNode;
  /** One line under the label, said to a screen reader with it. */
  description?: ReactNode;
  isDisabled?: boolean;
};

type ChoiceGroupProps = Omit<FieldProps, 'isRequired'> & {
  options: ChoiceOption[];
};

type RadioGroupFieldProps = ChoiceGroupProps & Binding<string>;
type CheckboxGroupFieldProps = ChoiceGroupProps & Binding<string[]>;
type CheckboxFieldProps = Omit<FieldProps, 'description' | 'label'> &
  Binding<boolean> & { children: ReactNode };

/** One of a few choices, each a radio with its label (and a line under it): a few words each. */
export function RadioGroupField({
  label,
  description,
  isDisabled,
  className,
  'data-testid': testId,
  options,
  ...binding
}: RadioGroupFieldProps) {
  return (
    <WithBinding<string> binding={binding as Binding<string>}>
      {(field) => (
        <RadioGroup
          {...describes(description)}
          name={field.name}
          value={field.value ?? ''}
          onChange={field.onChange}
          onBlur={field.onBlur}
          isInvalid={field.isInvalid}
          isDisabled={isDisabled}
          validationBehavior="aria"
          className={['flex flex-col gap-2', className]
            .filter(Boolean)
            .join(' ')}
          data-testid={testId}
        >
          <Label>{label}</Label>
          {description ? <Description>{description}</Description> : null}
          {options.map((option) => (
            <Radio
              key={option.value}
              value={option.value}
              isDisabled={option.isDisabled}
            >
              <Radio.Content>
                <Radio.Control>
                  <Radio.Indicator />
                </Radio.Control>
                <Label>{option.label}</Label>
              </Radio.Content>
              {option.description ? (
                <Description>{option.description}</Description>
              ) : null}
            </Radio>
          ))}
          <FieldError>{field.errorMessage}</FieldError>
        </RadioGroup>
      )}
    </WithBinding>
  );
}

/** Any of a few choices: the value is the list of chosen option values. */
export function CheckboxGroupField({
  label,
  description,
  isDisabled,
  className,
  'data-testid': testId,
  options,
  ...binding
}: CheckboxGroupFieldProps) {
  return (
    <WithBinding<string[]> binding={binding as Binding<string[]>}>
      {(field) => (
        <CheckboxGroup
          {...describes(description)}
          name={field.name}
          value={field.value ?? []}
          onChange={field.onChange}
          onBlur={field.onBlur}
          isInvalid={field.isInvalid}
          isDisabled={isDisabled}
          validationBehavior="aria"
          className={['flex flex-col gap-2', className]
            .filter(Boolean)
            .join(' ')}
          data-testid={testId}
        >
          <Label>{label}</Label>
          {description ? <Description>{description}</Description> : null}
          {options.map((option) => (
            <Checkbox
              key={option.value}
              value={option.value}
              isDisabled={option.isDisabled}
            >
              <Checkbox.Content>
                <Checkbox.Control>
                  <Checkbox.Indicator />
                </Checkbox.Control>
                <Label>{option.label}</Label>
              </Checkbox.Content>
              {option.description ? (
                <Description>{option.description}</Description>
              ) : null}
            </Checkbox>
          ))}
          <FieldError>{field.errorMessage}</FieldError>
        </CheckboxGroup>
      )}
    </WithBinding>
  );
}

/** One yes or no that is part of a form (consent, «I have read»): the label is its children. */
export function CheckboxField({
  children,
  isDisabled,
  className,
  'data-testid': testId,
  ...binding
}: CheckboxFieldProps) {
  return (
    <WithBinding<boolean> binding={binding as Binding<boolean>}>
      {(field) => (
        <div className="flex flex-col gap-1">
          <Checkbox
            name={field.name}
            isSelected={Boolean(field.value)}
            onChange={field.onChange}
            onBlur={field.onBlur}
            isInvalid={field.isInvalid}
            isDisabled={isDisabled}
            validationBehavior="aria"
            className={className}
            data-testid={testId}
          >
            <Checkbox.Content>
              <Checkbox.Control>
                <Checkbox.Indicator />
              </Checkbox.Control>
              <Label>{children}</Label>
            </Checkbox.Content>
          </Checkbox>
          {field.errorMessage ? (
            <p role="alert" className="text-sm text-danger">
              {field.errorMessage}
            </p>
          ) : null}
        </div>
      )}
    </WithBinding>
  );
}
