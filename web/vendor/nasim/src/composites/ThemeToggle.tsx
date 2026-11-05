'use client';

import { useSyncExternalStore } from 'react';
import { MoonIcon, SunIcon } from '../icons';
import { Button } from '../primitives';
import { useTheme } from '../providers/ThemeProvider';

const never = () => () => {};

type ThemeToggleProps = {
  /** Names the press that switches to the light theme («حالت روشن»). */
  lightLabel: string;
  /** Names the press that switches to the dark theme («حالت تیره»). */
  darkLabel: string;
  className?: string;
};

// Shows the other theme's icon. A press stores that choice, except when it is what the host (the
// device, or Telegram) shows anyway: then the choice is handed back to the host.
export function ThemeToggle({
  lightLabel,
  darkLabel,
  className,
}: ThemeToggleProps) {
  const { scheme, setMode, automatic, automaticScheme } = useTheme();
  // The scheme is the device's, unknown to the server: the icon waits for hydration.
  const ready = useSyncExternalStore(
    never,
    () => true,
    () => false,
  );
  const next = scheme === 'dark' ? 'light' : 'dark';
  const label = next === 'light' ? lightLabel : darkLabel;
  return (
    <Button
      isIconOnly
      size="sm"
      variant="outline"
      className={`size-11 min-h-11 min-w-11 rounded-full${className ? ` ${className}` : ''}`}
      aria-label={label}
      isDisabled={!ready}
      onPress={() => setMode(next === automaticScheme ? automatic : next)}
    >
      {ready ? next === 'light' ? <SunIcon /> : <MoonIcon /> : null}
    </Button>
  );
}
