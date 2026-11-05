'use client';

import { type ReactNode, useLayoutEffect, useState } from 'react';
import { Button, PageHeader, useTheme } from '..';
import { applyAccent } from '../providers/accent';
import { CompositesDemo } from './CompositesDemo';
import { DashboardDemo } from './DashboardDemo';
import { FormsDemo } from './FormsDemo';
import { PrimitivesDemo } from './PrimitivesDemo';

// A gallery for development, rendered under the app's NasimProvider; its copy lives here.
const THEME_COPY = {
  label: 'ظاهر برنامه',
  light: 'روشن',
  dark: 'تیره',
  system: 'مطابق دستگاه',
  telegram: 'مطابق تلگرام',
};

const ACCENTS = [
  { name: 'فروشگاه', value: undefined },
  { name: 'قرمز', value: '#e11d48' },
  { name: 'زرد', value: '#facc15' },
  { name: 'سبز', value: '#16a34a' },
  { name: 'مشکی', value: '#111111' },
  { name: 'سفید', value: '#ffffff' },
];

export function NasimDemo() {
  const [accent, setAccent] = useState<string | undefined>();
  useLayoutEffect(() => (accent ? applyAccent(accent) : undefined), [accent]);
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-10 px-(--nasim-page-gutter) py-6">
      <PageHeader
        title="نسیم"
        description="سیستم طراحی فروشگاه: قطعه‌ها، فرم‌ها و رنگ‌ها در حالت روشن و تیره."
      />
      <Controls accent={accent} onAccent={setAccent} />
      <PrimitivesDemo />
      <CompositesDemo />
      <DashboardDemo />
      <FormsDemo />
    </main>
  );
}

function Controls({
  accent,
  onAccent,
}: {
  accent: string | undefined;
  onAccent: (value: string | undefined) => void;
}) {
  const { mode, setMode, scheme, setScheme } = useTheme();
  const modes = [
    { value: 'light', label: THEME_COPY.light },
    { value: 'dark', label: THEME_COPY.dark },
    { value: 'system', label: THEME_COPY.system },
    { value: 'telegram', label: THEME_COPY.telegram },
  ] as const;
  return (
    <div className="flex flex-col gap-4 rounded-3xl bg-surface p-4 shadow-surface">
      <Group label={THEME_COPY.label}>
        {modes.map((item) => (
          <Button
            key={item.value}
            size="sm"
            variant={mode === item.value ? 'primary' : 'secondary'}
            aria-pressed={mode === item.value}
            onPress={() => setMode(item.value)}
          >
            {item.label}
          </Button>
        ))}
      </Group>
      {mode === 'telegram' ? (
        <Group label="رنگ‌بندی تلگرام (شبیه‌سازی)">
          {(['light', 'dark'] as const).map((next) => (
            <Button
              key={next}
              size="sm"
              variant={scheme === next ? 'primary' : 'secondary'}
              aria-pressed={scheme === next}
              onPress={() => setScheme(next)}
            >
              {next === 'light' ? THEME_COPY.light : THEME_COPY.dark}
            </Button>
          ))}
        </Group>
      ) : null}
      <Group label="رنگ برند فروشگاه">
        {ACCENTS.map((item) => (
          <Button
            key={item.name}
            size="sm"
            variant={accent === item.value ? 'primary' : 'secondary'}
            aria-pressed={accent === item.value}
            onPress={() => onAccent(item.value)}
          >
            {item.name}
          </Button>
        ))}
      </Group>
    </div>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      role="group"
      aria-label={label}
      className="flex flex-wrap items-center gap-2"
    >
      <span className="me-2 text-sm text-muted">{label}</span>
      {children}
    </div>
  );
}
