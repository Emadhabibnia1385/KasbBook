import { tv } from 'tailwind-variants';
import { Skeleton } from '../primitives';
import { t } from '../strings';

const skeletons = tv({
  slots: {
    status: 'flex flex-col',
    bar: 'h-4 w-full rounded-md',
    row: 'flex items-center gap-3 rounded-xl border border-border bg-surface p-3',
    tile: 'flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4 sm:p-5',
  },
});

const slots = skeletons();

// Placeholders are decorative; the one visually hidden status tells a screen reader what is loading.
function Placeholder({ className }: { className?: string }) {
  return <Skeleton aria-hidden className={slots.bar({ className })} />;
}

function RowShape() {
  return (
    <div aria-hidden className={slots.row()}>
      <Placeholder className="size-9 shrink-0 rounded-full" />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <Placeholder className="h-3.5 w-2/5" />
        <Placeholder className="h-3 w-3/4" />
      </div>
    </div>
  );
}

type SkeletonProps = {
  /** Defaults to «در حال بارگذاری». */
  label?: string;
};

/** A list loading: card-shaped rows (a mark and two lines), or plain bars when `dense`. */
export function SkeletonRows({
  rows = 3,
  label = t.common.loading,
  dense = false,
}: SkeletonProps & { rows?: number; dense?: boolean }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3 py-2">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) =>
        dense ? (
          <Placeholder key={index} className="h-10" />
        ) : (
          <RowShape key={index} />
        ),
      )}
    </div>
  );
}

/** A table loading: a header bar and `rows` body rows. */
export function TableSkeleton({
  rows = 5,
  label = t.common.loading,
}: SkeletonProps & { rows?: number }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="overflow-hidden rounded-xl border border-border"
    >
      <span className="sr-only">{label}</span>
      <div aria-hidden className="flex flex-col">
        <div className="flex gap-4 bg-surface-secondary px-4 py-3">
          <Placeholder className="h-3 w-1/5" />
          <Placeholder className="h-3 w-1/4" />
          <Placeholder className="ms-auto h-3 w-1/6" />
        </div>
        {Array.from({ length: rows }, (_, index) => (
          <div
            key={index}
            className="flex gap-4 border-t border-border px-4 py-3.5"
          >
            <Placeholder className="h-3.5 w-1/5" />
            <Placeholder className="h-3.5 w-1/3" />
            <Placeholder className="ms-auto h-3.5 w-1/6" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** A whole screen loading: a header, optional key-figure tiles and list rows, so nothing jumps. */
export function PageSkeleton({
  stats = 0,
  rows = 4,
  header = true,
  label = t.common.loading,
}: SkeletonProps & { stats?: number; rows?: number; header?: boolean }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-6">
      <span className="sr-only">{label}</span>
      {header ? (
        <div aria-hidden className="flex flex-col gap-2">
          <Placeholder className="h-7 w-1/3" />
          <Placeholder className="h-4 w-3/5" />
        </div>
      ) : null}
      {stats > 0 ? (
        <div aria-hidden className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: stats }, (_, index) => (
            <div key={index} className={slots.tile()}>
              <Placeholder className="h-3 w-1/3" />
              <Placeholder className="h-7 w-2/3" />
              <Placeholder className="h-3 w-1/2" />
            </div>
          ))}
        </div>
      ) : null}
      <div aria-hidden className="flex flex-col gap-3">
        {Array.from({ length: rows }, (_, index) => (
          <RowShape key={index} />
        ))}
      </div>
    </div>
  );
}
