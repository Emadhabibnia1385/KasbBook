'use client';

import { type ReactNode, useLayoutEffect, useRef, useState } from 'react';

type ScrollRegionProps = {
  /** What scrolls («جدول تعرفه»): it names the region once there is something to scroll. */
  label: string;
  className?: string;
  children: ReactNode;
};

// Content wider than the screen scrolls sideways, and only then is it a stop a keyboard can reach
export function ScrollRegion({
  label,
  className,
  children,
}: ScrollRegionProps) {
  const box = useRef<HTMLElement>(null);
  const [scrolls, setScrolls] = useState(false);
  useLayoutEffect(() => {
    const element = box.current;
    if (!element) return;
    const measure = () =>
      setScrolls(element.scrollWidth > element.clientWidth + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    for (const child of element.children) observer.observe(child);
    return () => observer.disconnect();
  }, []);
  // A keyboard can scroll only what it can focus, so the stop and the name come with the scrolling
  const stop = scrolls ? { tabIndex: 0, 'aria-label': label } : {};
  return (
    <section
      ref={box}
      {...stop}
      className={`overflow-x-auto ${className ?? ''}`}
    >
      {children}
    </section>
  );
}
