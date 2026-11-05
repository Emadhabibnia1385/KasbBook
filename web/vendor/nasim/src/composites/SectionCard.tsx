import { cardVariants } from '@heroui/styles';
import { type ReactNode, useId } from 'react';
import { tv } from 'tailwind-variants';

const section = tv({
  slots: {
    head: 'flex flex-row flex-wrap items-start justify-between gap-3',
    text: 'min-w-0 flex-1',
    title: 'flex items-center gap-2 font-semibold text-foreground',
    description: 'mt-1 text-sm text-muted text-pretty',
    actions: 'flex flex-wrap gap-2',
  },
  variants: {
    level: {
      2: { title: 'text-lg' },
      3: { title: 'text-base' },
    },
  },
  defaultVariants: { level: 2 },
});

const card = cardVariants();

type SectionCardProps = {
  title: ReactNode;
  description?: ReactNode;
  /** Buttons at the far end of the header. */
  actions?: ReactNode;
  /** Decorative; the title carries the meaning. */
  icon?: ReactNode;
  /** Heading level of the title: 2 (default) or 3 inside another section. */
  level?: 2 | 3;
  /** Gives the heading an id (for a link or a test); the card is named by it either way. */
  id?: string;
  className?: string;
  children?: ReactNode;
};

// A card with a titled header and a body: a <section> named by its heading. Server-renderable.
export function SectionCard({
  title,
  description,
  actions,
  icon,
  level = 2,
  id,
  className,
  children,
}: SectionCardProps) {
  const generated = useId();
  const headingId = id ?? generated;
  const Heading = level === 2 ? 'h2' : 'h3';
  const slots = section({ level });
  return (
    <section
      aria-labelledby={headingId}
      className={card.base({
        className: ['min-w-0 border border-border', className]
          .filter(Boolean)
          .join(' '),
      })}
    >
      <div className={card.header({ className: slots.head() })}>
        <div className={slots.text()}>
          <Heading id={headingId} className={slots.title()}>
            {icon ? (
              <span aria-hidden className="text-muted">
                {icon}
              </span>
            ) : null}
            <span className="min-w-0">{title}</span>
          </Heading>
          {description ? (
            <p className={slots.description()}>{description}</p>
          ) : null}
        </div>
        {actions ? <div className={slots.actions()}>{actions}</div> : null}
      </div>
      {children ? <div className={card.content()}>{children}</div> : null}
    </section>
  );
}
