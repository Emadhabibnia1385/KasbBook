import { tv } from 'tailwind-variants';
import { formatNumber, t } from '../strings';

const stepper = tv({
  slots: {
    root: 'flex flex-col gap-2',
    bar: 'flex gap-1.5',
    segment:
      'h-1.5 flex-1 rounded-full bg-default data-[reached=true]:bg-accent',
    label: 'text-sm text-muted',
  },
});

type StepperProps = {
  /** The names of the steps, in order («گزینه‌ها», «روش پرداخت», «تأیید»). */
  steps: string[];
  /** The step the person is on, counting from 0. */
  current: number;
};

// Where the person is in a few steps: a bar for the eye, the same in words («مرحله ۲ از ۴»)
export function Stepper({ steps, current }: StepperProps) {
  const slots = stepper();
  return (
    <div className={slots.root()}>
      <div aria-hidden className={slots.bar()}>
        {steps.map((step, index) => (
          <span
            key={step}
            data-reached={index <= current}
            className={slots.segment()}
          />
        ))}
      </div>
      <p className={slots.label()}>
        {t.stepper.position(
          formatNumber(current + 1),
          formatNumber(steps.length),
          steps[current] ?? '',
        )}
      </p>
    </div>
  );
}
