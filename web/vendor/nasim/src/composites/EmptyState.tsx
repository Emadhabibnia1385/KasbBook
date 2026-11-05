import {
  isValidElement,
  type ReactElement,
  type ReactNode,
  type Ref,
} from 'react';
import { tv } from 'tailwind-variants';
import { EmptyIcon } from '../icons';
import { Button, LinkButton } from '../primitives';

const emptyState = tv({
  slots: {
    root: 'mx-auto flex max-w-sm flex-col items-center gap-3 px-4 py-10 text-center',
    icon: 'grid size-14 place-items-center rounded-full bg-default text-muted [&>svg]:size-7',
    title: 'text-lg font-semibold text-foreground',
    description: 'text-sm text-muted text-pretty',
  },
});

type EmptyStateProps = {
  title: string;
  /** What this list is for, or what the person can do about it being empty. */
  description?: ReactNode;
  icon?: ReactNode;
  /** Heading level: "h1" when the state is the whole page, "h2" (default) inside one. */
  as?: 'h1' | 'h2';
  /** A ref to the title, which takes focus when a screen swaps this state in. */
  titleRef?: Ref<HTMLHeadingElement>;
  /** The next step: a link into the app, a handler, or your own element when it needs more than a button. */
  action?:
    | ReactElement
    | ({ label: string } & ({ href: string } | { onPress: () => void }));
};

export function EmptyState({
  title,
  description,
  icon,
  action,
  as: Heading = 'h2',
  titleRef,
}: EmptyStateProps) {
  const slots = emptyState();
  return (
    <div className={slots.root()}>
      <span aria-hidden className={slots.icon()}>
        {icon ?? <EmptyIcon />}
      </span>
      <Heading
        ref={titleRef}
        tabIndex={titleRef ? -1 : undefined}
        className={slots.title()}
      >
        {title}
      </Heading>
      {description ? (
        <p className={slots.description()}>{description}</p>
      ) : null}
      {isValidElement(action) ? action : null}
      {action && !isValidElement(action) && 'href' in action ? (
        <LinkButton href={action.href} size="lg">
          {action.label}
        </LinkButton>
      ) : null}
      {action && !isValidElement(action) && 'onPress' in action ? (
        <Button size="lg" onPress={action.onPress}>
          {action.label}
        </Button>
      ) : null}
    </div>
  );
}
