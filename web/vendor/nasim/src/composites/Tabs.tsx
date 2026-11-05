'use client';

import { Tabs as HeroTabs } from '@heroui/react';
import { type ReactNode, useLayoutEffect, useRef } from 'react';
import { t } from '../strings';

type TabItem = {
  id: string;
  label: ReactNode;
  /** The panel of this tab; leave it out when the page shows what the tab selects (route tabs). */
  content?: ReactNode;
  isDisabled?: boolean;
};

type TabsProps = {
  /** Names the tab list. */
  label: string;
  items: TabItem[];
  /** Controlled: the id of the selected tab. */
  selectedKey?: string;
  defaultSelectedKey?: string;
  onSelectionChange?: (id: string) => void;
  className?: string;
};

// HeroUI words the buttons that scroll a long tab list in English; they are set here in Persian.
const SCROLL_LABELS: Record<string, string> = {
  'Scroll tabs left': t.tabs.scrollStart,
  'Scroll tabs right': t.tabs.scrollEnd,
  'Scroll tabs up': t.tabs.scrollUp,
  'Scroll tabs down': t.tabs.scrollDown,
};

// Tabs on React Aria: arrow keys follow the reading direction (right to left in Persian).
export function Tabs({
  label,
  items,
  selectedKey,
  defaultSelectedKey,
  onSelectionChange,
  className,
}: TabsProps) {
  const root = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    for (const button of root.current?.querySelectorAll<HTMLElement>(
      'button[aria-label^="Scroll tabs"]',
    ) ?? []) {
      const persian = SCROLL_LABELS[button.getAttribute('aria-label') ?? ''];
      if (persian) button.setAttribute('aria-label', persian);
    }
  });
  return (
    <HeroTabs
      ref={root}
      className={className}
      selectedKey={selectedKey}
      defaultSelectedKey={defaultSelectedKey}
      onSelectionChange={
        onSelectionChange ? (key) => onSelectionChange(String(key)) : undefined
      }
    >
      <HeroTabs.ListContainer>
        <HeroTabs.List aria-label={label}>
          {items.map((item) => (
            <HeroTabs.Tab
              key={item.id}
              id={item.id}
              isDisabled={item.isDisabled}
            >
              {item.label}
              <HeroTabs.Indicator />
            </HeroTabs.Tab>
          ))}
        </HeroTabs.List>
      </HeroTabs.ListContainer>
      {items.map((item) =>
        item.content === undefined ? null : (
          <HeroTabs.Panel key={item.id} id={item.id} className="pt-4">
            {item.content}
          </HeroTabs.Panel>
        ),
      )}
    </HeroTabs>
  );
}
