import { tableVariants } from '@heroui/styles';
import type { ReactNode } from 'react';

type StaticTableProps = {
  /** Names the table and the region that scrolls it; screen readers read it, nobody sees it. */
  caption: string;
  /** Column headings. The first heads the column of row headers. */
  columns: readonly ReactNode[];
  /** One cell per column; the first cell of a row is its header. */
  rows: readonly { id: string; cells: readonly ReactNode[] }[];
  /** Added to the `<table>`: a minimum width such as "min-w-[36rem]" keeps a wide table from squeezing. */
  className?: string;
};

// Read-only rows for a page that is text, not a tool (a comparison, a support list): plain markup in
// HeroUI's table skin, so a Server Component draws it with no client JavaScript. A list a person works
// through (sorting, paging, keyboard grid) is DataTable.
export function StaticTable({
  caption,
  columns,
  rows,
  className,
}: StaticTableProps) {
  const slots = tableVariants({ variant: 'primary' });
  return (
    <div className={slots.base()}>
      {/* A keyboard user can only scroll a wide table sideways if the region takes focus. */}
      <div
        className={slots.scrollContainer()}
        tabIndex={0}
        role="region"
        aria-label={caption}
      >
        <table className={slots.content({ className })}>
          <caption className="sr-only">{caption}</caption>
          <thead className={slots.header()}>
            <tr>
              {columns.map((column, index) => (
                <th key={index} scope="col" className={slots.column()}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className={slots.body()}>
            {rows.map((row) => (
              <tr key={row.id} className={slots.row()}>
                {row.cells.map((cell, index) =>
                  index === 0 ? (
                    <th
                      key={index}
                      scope="row"
                      className={slots.cell({
                        className: 'text-start font-medium',
                      })}
                    >
                      {cell}
                    </th>
                  ) : (
                    <td key={index} className={slots.cell()}>
                      {cell}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
