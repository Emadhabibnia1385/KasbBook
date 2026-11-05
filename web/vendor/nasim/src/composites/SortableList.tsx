'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Button as HandleButton,
  DropIndicator,
  GridList,
  GridListItem,
  Text,
  useDragAndDrop,
  type Key,
} from 'react-aria-components';
import { tv } from 'tailwind-variants';
import { ChevronDownIcon, GripIcon } from '../icons';
import { Button } from '../primitives';
import { formatNumber, t } from '../strings';

const sortableList = tv({
  slots: {
    list: 'flex flex-col gap-2 outline-none',
    row: [
      'flex min-h-14 items-center gap-2 rounded-2xl border border-border bg-surface px-2 py-1.5 text-start outline-none',
      'transition-colors motion-reduce:transition-none',
      'data-[dragging=true]:opacity-60 data-[drop-target=true]:border-accent',
      'data-[focus-visible=true]:outline-2 data-[focus-visible=true]:outline-solid data-[focus-visible=true]:outline-offset-2 data-[focus-visible=true]:outline-focus',
    ],
    handle: [
      'grid size-11 shrink-0 cursor-grab place-items-center rounded-xl text-muted outline-none',
      'data-[disabled=true]:cursor-default data-[disabled=true]:opacity-50',
      'data-[focus-visible=true]:outline-2 data-[focus-visible=true]:outline-solid data-[focus-visible=true]:outline-offset-2 data-[focus-visible=true]:outline-focus',
    ],
    text: 'flex min-w-0 flex-1 flex-col gap-0.5',
    label: 'font-medium text-foreground',
    description: 'text-sm text-muted text-pretty',
    moves: 'flex shrink-0 items-center gap-1',
    indicator:
      'h-0.5 -my-1 rounded-full bg-transparent data-[drop-target=true]:bg-accent',
  },
  variants: {
    isDisabled: { true: { list: 'opacity-60' } },
  },
});

type SortableItem = { id: string; label: string; description?: string };

type SortableListProps = {
  /** The rows in the order to show; the list keeps no order of its own. */
  items: readonly SortableItem[];
  /** Called with every id in its new order, after a drop or a press of «بالا» or «پایین». */
  onReorder: (ids: string[]) => void;
  /** What is being ordered («ترتیب درگاه‌های پرداخت»): it names the list. */
  label: string;
  isDisabled?: boolean;
};

const DRAG_TYPE = 'application/x-nasim-sortable';

// The ids with `moved` taken out and put back before or after `target`; the same array when nothing moves.
function placed(
  ids: readonly string[],
  moved: ReadonlySet<Key>,
  target: Key,
  position: 'before' | 'after',
): readonly string[] {
  const dragged = ids.filter((id) => moved.has(id));
  const rest = ids.filter((id) => !moved.has(id));
  const at = rest.indexOf(String(target));
  if (at < 0 || dragged.length === 0) return ids;
  rest.splice(position === 'after' ? at + 1 : at, 0, ...dragged);
  return rest.every((id, index) => id === ids[index]) ? ids : rest;
}

// A short list ordered by dragging (mouse, touch, or the keyboard through React Aria's drag handle), with
// «بالا» / «پایین» on every row for a person who cannot drag (WCAG 2.2, 2.5.7).
export function SortableList({
  items,
  onReorder,
  label,
  isDisabled = false,
}: SortableListProps) {
  const slots = sortableList({ isDisabled });
  const ids = items.map((item) => item.id);
  const listRef = useRef<HTMLDivElement>(null);
  const [said, setSaid] = useState('');
  // The browser drops focus from a row that React moves. The list inside React Aria builds its rows a pass
  // after this component renders, so focus goes back on the next frame, to the other button at an edge.
  const refocus = useRef<{ id: string; dir: 'up' | 'down'; order: string }>(
    null,
  );

  useEffect(() => {
    const pending = refocus.current;
    // An owner that saves first and renders later gets its focus back when the new order arrives.
    if (!pending || pending.order !== ids.join('\n')) return;
    refocus.current = null;
    requestAnimationFrame(() => {
      const at = ids.indexOf(pending.id);
      const edge = pending.dir === 'up' ? at === 0 : at === ids.length - 1;
      const dir = edge ? (pending.dir === 'up' ? 'down' : 'up') : pending.dir;
      listRef.current
        ?.querySelectorAll<HTMLButtonElement>('[data-sortable-move]')
        .forEach((button) => {
          if (
            button.dataset.sortableId === pending.id &&
            button.dataset.sortableMove === dir
          )
            button.focus();
        });
    });
  });

  function move(id: string, dir: 'up' | 'down') {
    const from = ids.indexOf(id);
    const to = dir === 'up' ? from - 1 : from + 1;
    if (from < 0 || to < 0 || to >= ids.length) return;
    const next = ids.slice();
    next.splice(from, 1);
    next.splice(to, 0, id);
    refocus.current = { id, dir, order: next.join('\n') };
    const name = items[from]?.label ?? '';
    setSaid(
      t.sortableList.moved(
        name,
        formatNumber(to + 1),
        formatNumber(ids.length),
      ),
    );
    onReorder(next);
  }

  const { dragAndDropHooks } = useDragAndDrop({
    isDisabled,
    acceptedDragTypes: [DRAG_TYPE],
    getItems: (keys) => [...keys].map((key) => ({ [DRAG_TYPE]: String(key) })),
    onReorder(event) {
      const { key, dropPosition } = event.target;
      if (dropPosition === 'on') return;
      const next = placed(ids, event.keys, key, dropPosition);
      if (next !== ids) onReorder([...next]);
    },
    renderDropIndicator: (target) => (
      <DropIndicator target={target} className={slots.indicator()} />
    ),
  });

  return (
    <>
      <GridList
        ref={listRef}
        aria-label={label}
        dragAndDropHooks={dragAndDropHooks}
        className={slots.list()}
      >
        {items.map((item, index) => (
          <GridListItem
            key={item.id}
            id={item.id}
            textValue={item.label}
            className={slots.row()}
          >
            <HandleButton slot="drag" className={slots.handle()}>
              <GripIcon />
            </HandleButton>
            <div className={slots.text()}>
              <Text className={slots.label()}>{item.label}</Text>
              {item.description ? (
                <Text slot="description" className={slots.description()}>
                  {item.description}
                </Text>
              ) : null}
            </div>
            <div className={slots.moves()}>
              <Button
                isIconOnly
                variant="ghost"
                className="size-11"
                aria-label={t.sortableList.moveUp(item.label)}
                isDisabled={isDisabled || index === 0}
                onPress={() => move(item.id, 'up')}
                data-sortable-move="up"
                data-sortable-id={item.id}
              >
                <ChevronDownIcon className="rotate-180" />
              </Button>
              <Button
                isIconOnly
                variant="ghost"
                className="size-11"
                aria-label={t.sortableList.moveDown(item.label)}
                isDisabled={isDisabled || index === items.length - 1}
                onPress={() => move(item.id, 'down')}
                data-sortable-move="down"
                data-sortable-id={item.id}
              >
                <ChevronDownIcon />
              </Button>
            </div>
          </GridListItem>
        ))}
      </GridList>
      <span role="status" className="sr-only">
        {said}
      </span>
    </>
  );
}
