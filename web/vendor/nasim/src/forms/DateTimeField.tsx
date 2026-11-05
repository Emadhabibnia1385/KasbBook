'use client';

import {
  Calendar,
  DateField,
  DatePicker,
  Description,
  FieldError,
  I18nProvider,
  Label,
  TimeField,
} from '@heroui/react';
import { type CalendarDateTime, Time } from '@internationalized/date';
import { useMemo } from 'react';
import { Button } from '../primitives';
import { t } from '../strings';
import {
  type Binding,
  type FieldProps,
  WithBinding,
  describes,
} from './binding';
import { fromJalaliValue, toJalaliValue } from './jalali';

type DateTimeFieldProps = FieldProps &
  Binding<string> & {
    /** Names the calendar popover. */
    calendarLabel: string;
    /** Names the time box inside it. */
    timeLabel: string;
    /** The text of the button that empties the field. */
    clearLabel: string;
  };

// A date and a 24-hour time in the Persian calendar with Persian digits. The value stays the
// Gregorian local `YYYY-MM-DDTHH:mm` a form validates and converts, or '' for no date.
export function DateTimeField({
  label,
  description,
  isRequired,
  isDisabled,
  className,
  'data-testid': testId,
  calendarLabel,
  timeLabel,
  clearLabel,
  ...binding
}: DateTimeFieldProps) {
  return (
    <WithBinding<string> binding={binding as Binding<string>}>
      {(field) => (
        <Picker
          label={label}
          description={description}
          isRequired={isRequired}
          isDisabled={isDisabled}
          className={className}
          testId={testId}
          calendarLabel={calendarLabel}
          timeLabel={timeLabel}
          clearLabel={clearLabel}
          value={field.value ?? ''}
          onChange={field.onChange}
          onBlur={field.onBlur}
          isInvalid={field.isInvalid}
          errorMessage={field.errorMessage}
        />
      )}
    </WithBinding>
  );
}

type PickerProps = Pick<
  DateTimeFieldProps,
  | 'label'
  | 'description'
  | 'isRequired'
  | 'isDisabled'
  | 'className'
  | 'calendarLabel'
  | 'timeLabel'
  | 'clearLabel'
> & {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  isInvalid: boolean;
  errorMessage?: string | null;
  testId?: string;
};

function Picker({
  label,
  description,
  isRequired,
  isDisabled,
  className,
  testId,
  calendarLabel,
  timeLabel,
  clearLabel,
  value,
  onChange,
  onBlur,
  isInvalid,
  errorMessage,
}: PickerProps) {
  // A stable object per value: a fresh one each render makes the controlled picker re-emit (render loop).
  const current = useMemo(() => toJalaliValue(value), [value]);
  return (
    <I18nProvider locale="fa-IR-u-ca-persian">
      <DatePicker<CalendarDateTime>
        {...describes(description)}
        value={current}
        onChange={(next) => onChange(fromJalaliValue(next))}
        onBlur={onBlur}
        granularity="minute"
        hourCycle={24}
        isInvalid={isInvalid}
        isRequired={isRequired}
        isDisabled={isDisabled}
        validationBehavior="aria"
        className={['flex w-full flex-col gap-1', className]
          .filter(Boolean)
          .join(' ')}
        data-testid={testId}
      >
        {() => (
          <>
            <Label>{label}</Label>
            {description ? <Description>{description}</Description> : null}
            <DateField.Group fullWidth>
              <DateField.Input>
                {(segment) => <DateField.Segment segment={segment} />}
              </DateField.Input>
              <DateField.Suffix>
                {current ? (
                  // slot={null}: not the calendar trigger the picker offers its first button
                  <Button
                    slot={null}
                    variant="tertiary"
                    size="sm"
                    onPress={() => onChange('')}
                  >
                    {clearLabel}
                  </Button>
                ) : null}
                <DatePicker.Trigger>
                  <DatePicker.TriggerIndicator />
                </DatePicker.Trigger>
              </DateField.Suffix>
            </DateField.Group>
            <FieldError>{errorMessage}</FieldError>
            <DatePicker.Popover className="flex min-w-72 flex-col gap-3">
              <Calendar aria-label={calendarLabel}>
                <Calendar.Header>
                  {/* HeroUI names this button in English; with no aria-label its name is its text. */}
                  <Calendar.YearPickerTrigger aria-label={undefined}>
                    <Calendar.YearPickerTriggerHeading />
                    <span className="sr-only">، {t.calendar.selectYear}</span>
                    <Calendar.YearPickerTriggerIndicator />
                  </Calendar.YearPickerTrigger>
                  <Calendar.NavButton slot="previous" />
                  <Calendar.NavButton slot="next" />
                </Calendar.Header>
                {/* Narrow weekday names (ش ی د س چ پ ج): full Persian names do not fit seven columns. */}
                <Calendar.Grid weekdayStyle="narrow">
                  <Calendar.GridHeader>
                    {(day) => <Calendar.HeaderCell>{day}</Calendar.HeaderCell>}
                  </Calendar.GridHeader>
                  <Calendar.GridBody>
                    {(date) => <Calendar.Cell date={date} />}
                  </Calendar.GridBody>
                </Calendar.Grid>
                <Calendar.YearPickerGrid>
                  <Calendar.YearPickerGridBody>
                    {({ year }) => <Calendar.YearPickerCell year={year} />}
                  </Calendar.YearPickerGridBody>
                </Calendar.YearPickerGrid>
              </Calendar>
              <div className="flex items-center justify-between gap-3">
                <Label>{timeLabel}</Label>
                <TimeField
                  aria-label={timeLabel}
                  granularity="minute"
                  hourCycle={24}
                  isDisabled={!current}
                  value={
                    current ? new Time(current.hour, current.minute) : null
                  }
                  // Driven by the field value, not the picker's internal time state (that pairing loops).
                  onChange={(time) => {
                    if (current && time)
                      onChange(
                        fromJalaliValue(
                          current.set({ hour: time.hour, minute: time.minute }),
                        ),
                      );
                  }}
                >
                  <TimeField.Group variant="secondary">
                    <TimeField.Input>
                      {(segment) => <TimeField.Segment segment={segment} />}
                    </TimeField.Input>
                  </TimeField.Group>
                </TimeField>
              </div>
            </DatePicker.Popover>
          </>
        )}
      </DatePicker>
    </I18nProvider>
  );
}
