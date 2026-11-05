import { tv } from 'tailwind-variants';
import { t } from '../strings';
import { Spinner } from '../primitives';

const loadingState = tv({
  base: 'flex items-center justify-center gap-3 text-muted',
  variants: {
    size: {
      page: 'min-h-[40dvh] flex-col py-10',
      inline: 'py-4',
    },
  },
  defaultVariants: { size: 'page' },
});

type LoadingStateProps = {
  /** Defaults to «در حال بارگذاری». */
  label?: string;
  size?: 'page' | 'inline';
};

export function LoadingState({
  label = t.common.loading,
  size,
}: LoadingStateProps) {
  return (
    <output className={loadingState({ size })}>
      <Spinner aria-hidden size={size === 'inline' ? 'sm' : 'lg'} />
      <span className="text-sm">{label}</span>
    </output>
  );
}
