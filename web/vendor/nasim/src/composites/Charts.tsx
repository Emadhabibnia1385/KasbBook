import { type ReactNode, useId } from 'react';
import { tv } from 'tailwind-variants';

/*
 * Small accessible charts in plain SVG and HTML, no chart library. A bar's height is only a picture:
 * every exact value is text (the bar's tooltip, a sentence, a data table), so nothing is lost to scaling.
 * The plot sits in a left-to-right box so time runs left to right whatever the page direction.
 */

const column = tv({
  slots: {
    figure: 'flex flex-col gap-2',
    caption: 'text-sm font-semibold text-foreground',
    empty:
      'rounded-md border border-dashed border-field-border p-4 text-center text-sm text-muted',
    plot: 'w-full rounded-md bg-surface-secondary',
    ends: 'flex justify-between text-xs text-muted',
    disclosure: 'rounded-md border border-border text-sm',
    summary: 'min-h-11 cursor-pointer px-3 py-2.5 font-medium',
  },
  variants: {
    size: {
      md: { plot: 'h-36' },
      lg: { plot: 'h-40' },
    },
  },
  defaultVariants: { size: 'md' },
});

// Written out, not built from the tone name: Tailwind only keeps class names it can read.
const BAR_FILL = {
  accent: 'fill-accent',
  success: 'fill-success',
  info: 'fill-info',
} as const;
const BAR_BACKGROUND = {
  accent: 'bg-accent',
  success: 'bg-success',
  info: 'bg-info',
} as const;

export type ChartTone = keyof typeof BAR_FILL;

export type ChartPoint = {
  key: string;
  /** Short label for the chart's two ends (a day of the month). */
  label: string;
  /** The bar's tooltip: its full label and exact value, as text. */
  tooltip: string;
  /** The height of the bar only; the exact value is in `tooltip` and in the table. */
  value: number;
};

type ChartTable = {
  /** Words of the disclosure that opens the table. */
  showLabel: string;
  /** Names the table and the region that scrolls it. */
  label: string;
  columns: readonly ReactNode[];
  /** One cell per column; the first cell of a row is its header. */
  rows: readonly { key: string; cells: readonly ReactNode[] }[];
};

type ColumnChartProps = {
  /** The chart's caption. */
  title: string;
  points: readonly ChartPoint[];
  /** What a screen reader hears for the picture: the range, how many have data, the peak. */
  summary: string;
  /** Shown instead of the picture when there is no value above zero. */
  empty: string;
  /** Draws `summary` as a line under the title too. */
  showSummary?: boolean;
  tone?: ChartTone;
  size?: 'md' | 'lg';
  /** A line under the chart: how the heights are scaled. */
  note?: ReactNode;
  /** The exact values as a table behind a disclosure. */
  table?: ChartTable;
  /** Also on `${data-testid}-summary` and `${data-testid}-table`. */
  'data-testid'?: string;
};

// One bar per point. Server-renderable.
export function ColumnChart({
  title,
  points,
  summary,
  empty,
  showSummary = false,
  tone = 'accent',
  size,
  note,
  table,
  'data-testid': testId,
}: ColumnChartProps) {
  const captionId = useId();
  const slots = column({ size });
  const max = Math.max(0, ...points.map((point) => point.value));
  const width = Math.max(1, points.length) * 10;
  const drawn = points.length > 0 && max > 0;
  return (
    <figure
      className={slots.figure()}
      aria-labelledby={captionId}
      data-testid={testId}
    >
      <figcaption id={captionId} className={slots.caption()}>
        {title}
      </figcaption>
      {showSummary ? (
        <p
          className="text-sm text-muted"
          data-testid={testId ? `${testId}-summary` : undefined}
        >
          {summary}
        </p>
      ) : null}
      {drawn ? (
        <div dir="ltr" className="flex flex-col gap-1">
          <svg
            role="img"
            aria-label={summary}
            viewBox={`0 0 ${width} 100`}
            preserveAspectRatio="none"
            className={slots.plot()}
          >
            <line
              x1="0"
              x2={width}
              y1="99.5"
              y2="99.5"
              className="stroke-field-border"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
            {points.map((point, index) => {
              const height =
                point.value > 0 ? Math.max(1.5, (point.value / max) * 96) : 0;
              return (
                <rect
                  key={point.key}
                  x={index * 10 + 1.5}
                  width={7}
                  y={100 - height}
                  height={height}
                  className={BAR_FILL[tone]}
                >
                  <title>{point.tooltip}</title>
                </rect>
              );
            })}
          </svg>
          <div className={slots.ends()} aria-hidden="true">
            <span>{points[0]?.label}</span>
            <span>{points[points.length - 1]?.label}</span>
          </div>
        </div>
      ) : (
        <p className={slots.empty()}>{empty}</p>
      )}
      {note ? <p className="text-xs text-muted">{note}</p> : null}
      {table && points.length > 0 ? (
        <details className={slots.disclosure()}>
          <summary className={slots.summary()}>{table.showLabel}</summary>
          <div
            className="max-h-80 overflow-auto"
            tabIndex={0}
            role="region"
            aria-label={table.label}
          >
            <table
              className="w-full text-sm"
              data-testid={testId ? `${testId}-table` : undefined}
            >
              <caption className="sr-only">{table.label}</caption>
              <thead>
                <tr className="border-b border-border text-muted">
                  {table.columns.map((header, index) => (
                    <th
                      key={index}
                      scope="col"
                      className={`px-3 py-2 font-medium ${index === 0 ? 'text-start' : 'text-end'}`}
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row) => (
                  <tr
                    key={row.key}
                    className="border-b border-border last:border-0"
                  >
                    {row.cells.map((cell, index) =>
                      index === 0 ? (
                        <th
                          key={index}
                          scope="row"
                          className="px-3 py-1.5 text-start font-normal"
                        >
                          {cell}
                        </th>
                      ) : (
                        <td key={index} className="px-3 py-1.5 text-end">
                          {cell}
                        </td>
                      ),
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </figure>
  );
}

export type BarRow = {
  key: string;
  label: ReactNode;
  /** The length of the bar only; the exact values are the cells. */
  value: number;
  /** The exact values, one per `valueHeaders`, as text. */
  cells: readonly ReactNode[];
};

type BarTableProps = {
  /** The caption, and the table's name. */
  title: string;
  labelHeader: string;
  valueHeaders: readonly string[];
  rows: readonly BarRow[];
  /** Shown instead of the table when there are no rows. */
  empty: string;
  tone?: ChartTone;
  /** The caption is only for screen readers (the page has the heading already). */
  hideTitle?: boolean;
  /** Names the scrolling region; defaults to the title. */
  regionLabel?: string;
  /** The bars are decoration: hide them on a phone to give the numbers the width. */
  barFrom?: 'always' | 'sm';
  'data-testid'?: string;
};

// Horizontal bars that are themselves a data table: the label, a bar in proportion to `value`, and the exact
// values in text cells. Screen readers read a table. Server-renderable.
export function BarTable({
  title,
  labelHeader,
  valueHeaders,
  rows,
  empty,
  tone = 'accent',
  hideTitle = false,
  regionLabel,
  barFrom = 'always',
  'data-testid': testId,
}: BarTableProps) {
  const captionId = useId();
  const max = Math.max(0, ...rows.map((row) => row.value));
  const barCell = barFrom === 'sm' ? 'hidden sm:table-cell' : '';
  return (
    <figure
      className="flex flex-col gap-2"
      aria-labelledby={captionId}
      data-testid={testId}
    >
      <figcaption
        id={captionId}
        className={hideTitle ? 'sr-only' : 'text-sm font-semibold'}
      >
        {title}
      </figcaption>
      {rows.length === 0 ? (
        <p className={column().empty()}>{empty}</p>
      ) : (
        // A named region that takes focus: a keyboard user can scroll a table wider than the screen.
        <div
          className="overflow-x-auto"
          tabIndex={0}
          role="region"
          aria-label={regionLabel ?? title}
        >
          <table className="w-full text-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-border text-muted">
                <th scope="col" className="px-2 py-2 text-start font-medium">
                  {labelHeader}
                </th>
                <th scope="col" className={`w-1/4 px-2 py-2 ${barCell}`}>
                  <span className="sr-only">{title}</span>
                </th>
                {valueHeaders.map((header) => (
                  <th
                    key={header}
                    scope="col"
                    className="px-2 py-2 text-end font-medium"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.key}
                  className="border-b border-border last:border-0"
                >
                  <th
                    scope="row"
                    className="max-w-48 truncate px-2 py-2 text-start font-normal"
                  >
                    {row.label}
                  </th>
                  <td className={`px-2 py-2 ${barCell}`}>
                    <div
                      className="h-2.5 w-full rounded-full bg-surface-tertiary"
                      aria-hidden="true"
                    >
                      <div
                        className={`h-2.5 rounded-full ${BAR_BACKGROUND[tone]}`}
                        style={{
                          width: `${max > 0 ? Math.max(2, (row.value / max) * 100) : 0}%`,
                        }}
                      />
                    </div>
                  </td>
                  {row.cells.map((cell, index) => (
                    <td
                      key={index}
                      className="whitespace-nowrap px-2 py-2 text-end"
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </figure>
  );
}
