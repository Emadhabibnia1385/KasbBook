'use client';

import { Table } from '@heroui/react';
import type { ReactNode } from 'react';
import { t } from '../strings';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { Pager } from './Pager';
import { TableSkeleton } from './Skeletons';
import { useIsNarrow } from './useIsNarrow';

export type DataColumn<T> = {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Figures and amounts line up at the end; a column can instead be centred under its heading. */
  align?: 'start' | 'end' | 'center';
  /** Exactly one column should name the row for a screen reader. */
  isRowHeader?: boolean;
  className?: string;
  /** The row's buttons. On a card they sit in the footer instead of being a label and value pair. */
  isActions?: boolean;
  /** Leave the column out of a card (it is still a column of the table). */
  hideOnCard?: boolean;
};

type DataTableProps<T> = {
  /** Names the table: its visible heading is a good choice. */
  ariaLabel: string;
  columns: readonly DataColumn<T>[];
  rows: readonly T[] | undefined;
  getRowId: (row: T) => string;
  /** loading shows skeleton rows, error the error state with a retry, ready the rows or the empty state. */
  status: 'loading' | 'error' | 'ready';
  onRetry?: () => void;
  /** Replaces the default error state, for a screen that words its own errors. */
  errorState?: ReactNode;
  /** The empty state's explanation. */
  empty?: ReactNode;
  /** A short heading above it («هنوز فاکتوری ندارید»). */
  emptyTitle?: string;
  emptyIcon?: ReactNode;
  /** The next step, as an element (a button or a link). */
  emptyAction?: ReactNode;
  pagination?: {
    page: number;
    pageCount: number;
    onPageChange: (page: number) => void;
  };
  /**
   * Below this breakpoint each row is a card (the row header as its title, the other columns as
   * labelled values, the `isActions` columns in its footer) so nothing scrolls sideways on a phone.
   */
  cards?: 'sm' | 'md';
  className?: string;
};

function EmptyView({
  empty,
  emptyTitle,
  emptyIcon,
  emptyAction,
}: Pick<
  DataTableProps<unknown>,
  'empty' | 'emptyTitle' | 'emptyIcon' | 'emptyAction'
>) {
  return (
    <div className="p-4">
      <EmptyState
        title={
          emptyTitle ?? (typeof empty === 'string' ? empty : t.state.emptyTable)
        }
        description={
          emptyTitle && typeof empty === 'string' ? empty : undefined
        }
        icon={emptyIcon}
      />
      {emptyAction ? (
        <div className="flex justify-center pb-4">{emptyAction}</div>
      ) : null}
    </div>
  );
}

// The footer of a card: a row with nothing to do (a revoked key) gets no empty bar with a rule above it.
function CardActions<T>({
  columns,
  row,
}: {
  columns: readonly DataColumn<T>[];
  row: T;
}) {
  const cells = columns
    .map((column) => ({ id: column.id, cell: column.cell(row) }))
    .filter(
      ({ cell }) => cell !== null && cell !== undefined && cell !== false,
    );
  if (!cells.length) return null;
  return (
    <div className="flex flex-wrap gap-2 border-t border-border pt-3">
      {cells.map(({ id, cell }) => (
        <span key={id} className="contents">
          {cell}
        </span>
      ))}
    </div>
  );
}

function Cards<T>({
  ariaLabel,
  columns,
  rows,
  getRowId,
}: Pick<DataTableProps<T>, 'ariaLabel' | 'columns' | 'getRowId'> & {
  rows: readonly T[];
}) {
  const title = columns.find((column) => column.isRowHeader) ?? columns[0];
  const actions = columns.filter((column) => column.isActions);
  const fields = columns.filter(
    (column) => column !== title && !column.isActions && !column.hideOnCard,
  );
  return (
    <ul
      aria-label={ariaLabel}
      className="flex flex-col gap-3"
      data-testid="data-cards"
    >
      {rows.map((row) => (
        <li
          key={getRowId(row)}
          className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4"
        >
          {title ? (
            <div className="min-w-0 break-words font-medium">
              {title.cell(row)}
            </div>
          ) : null}
          {fields.length ? (
            <dl className="grid grid-cols-1 gap-2 text-sm min-[420px]:grid-cols-2">
              {fields.map((column) => (
                <div key={column.id} className="flex min-w-0 flex-col gap-0.5">
                  <dt className="text-xs text-muted">{column.header}</dt>
                  <dd className="min-w-0 break-words">{column.cell(row)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          <CardActions columns={actions} row={row} />
        </li>
      ))}
    </ul>
  );
}

// A data table on React Aria's grid: keyboard navigation, RTL aware. A wide table scrolls sideways
// inside its own region, its cells never wrap digit by digit.
export function DataTable<T>({
  ariaLabel,
  columns,
  rows,
  getRowId,
  status,
  onRetry,
  errorState,
  empty,
  emptyTitle,
  emptyIcon,
  emptyAction,
  pagination,
  cards,
  className,
}: DataTableProps<T>) {
  const narrow = useIsNarrow(cards);
  if (status === 'error') return errorState ?? <ErrorState onRetry={onRetry} />;
  if (status === 'loading') return <TableSkeleton rows={5} />;
  const list = rows ?? [];
  const emptyView = (
    <EmptyView
      empty={empty}
      emptyTitle={emptyTitle}
      emptyIcon={emptyIcon}
      emptyAction={emptyAction}
    />
  );
  if (narrow) {
    return (
      <div className={className}>
        {list.length ? (
          <Cards
            ariaLabel={ariaLabel}
            columns={columns}
            rows={list}
            getRowId={getRowId}
          />
        ) : (
          emptyView
        )}
        {pagination && pagination.pageCount > 1 ? (
          <Pager
            page={pagination.page}
            pageCount={pagination.pageCount}
            onPrevious={() => pagination.onPageChange(pagination.page - 1)}
            onNext={() => pagination.onPageChange(pagination.page + 1)}
            onPage={pagination.onPageChange}
          />
        ) : null}
      </div>
    );
  }
  const items = list.map((row) => ({ key: getRowId(row), row }));
  return (
    <Table className={['w-full', className].filter(Boolean).join(' ')}>
      <Table.ScrollContainer>
        <Table.Content
          aria-label={ariaLabel}
          className="min-w-full [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap"
        >
          <Table.Header>
            {columns.map((column) => (
              <Table.Column
                key={column.id}
                id={column.id}
                isRowHeader={column.isRowHeader}
                className={[
                  column.align === 'end' && 'text-end',
                  column.align === 'center' && 'text-center',
                  column.className,
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                {column.header}
              </Table.Column>
            ))}
          </Table.Header>
          <Table.Body items={items} renderEmptyState={() => emptyView}>
            {(item) => (
              <Table.Row id={item.key}>
                {columns.map((column) => (
                  <Table.Cell
                    key={column.id}
                    className={[
                      column.align === 'end' && 'text-end',
                      column.align === 'center' && 'text-center',
                      column.className,
                    ]
                      .filter(Boolean)
                      .join(' ')}
                  >
                    {column.cell(item.row)}
                  </Table.Cell>
                ))}
              </Table.Row>
            )}
          </Table.Body>
        </Table.Content>
      </Table.ScrollContainer>
      {pagination && pagination.pageCount > 1 ? (
        <Table.Footer>
          <Pager
            page={pagination.page}
            pageCount={pagination.pageCount}
            onPrevious={() => pagination.onPageChange(pagination.page - 1)}
            onNext={() => pagination.onPageChange(pagination.page + 1)}
            onPage={pagination.onPageChange}
          />
        </Table.Footer>
      ) : null}
    </Table>
  );
}
