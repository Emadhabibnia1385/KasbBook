// A product's own palette for Nasim: surfaces, text, accent and statuses, in light and dark.
// Pure and server-safe: the CSS can be rendered on the server (no flash) and the contrast rules
// can run in a test, from the same object.
import {
  blendOver,
  contrastRatio,
  mixOklab,
  parseHex,
  type Rgb,
  rgbToOklch,
} from './providers/color';
import type { SchemeName, SchemeSpec } from './providers/accent';

/** One colour role (the accent or a status): its fill, the text on it, and its soft pair. */
export type PaletteColor = {
  /** The solid colour: a button fill, a switch track, a status mark. `#rrggbb`. */
  fill: string;
  /** Text on the fill, at least 4.5:1 (also on the hover shade, 10% towards it). */
  onFill: string;
  /**
   * The soft background of a chip or alert. Leave it out to get the fill at 15% (12% in dark)
   * over whatever surface it sits on, which follows a tenant accent too.
   */
  tint?: string;
  /** Text on the tint, at least 4.5:1. Leave it out to get the fill mixed with the page text. */
  text?: string;
};

/** Everything one theme (light or dark) paints with. Every colour is `#rrggbb`. */
export type SchemePalette = {
  background: string;
  foreground: string;
  surface: string;
  surfaceSecondary: string;
  /** Also HeroUI's `--default`: hovered rows, the secondary button, a neutral chip. */
  surfaceTertiary: string;
  /** Menus, popovers and dialogs. */
  overlay: string;
  /** Secondary text, at least 4.5:1 on every surface above. */
  muted: string;
  /** Dividers and card edges; not a control's boundary. */
  border: string;
  /** A control's boundary (field, off switch, checkbox), at least 3:1 on every surface. */
  fieldBorder: string;
  accent: PaletteColor;
  success: PaletteColor;
  warning: PaletteColor;
  danger: PaletteColor;
  info: PaletteColor;
  /** The focus ring, at least 3:1 on every surface. Default: the accent mixed into the page text. */
  focus?: string;
  /** Default: the surface. */
  fieldBackground?: string;
  /** Default: `border`. */
  separator?: string;
  /** A CSS `box-shadow` for cards, or `none`. Default: the theme's. */
  shadow?: string;
  /** A CSS `box-shadow` for dialogs and menus. Default: the theme's. */
  overlayShadow?: string;
  /** The scrim behind a dialog, `#rrggbb` with an optional alpha (`#rrggbbaa`). */
  backdrop?: string;
};

export type Palette = {
  light: SchemePalette;
  dark: SchemePalette;
  /** Card and control corner radius, e.g. `0.625rem`. */
  radius?: string;
  /** Corner radius of fields, e.g. `0.625rem`. */
  fieldRadius?: string;
};

export type PaletteIssue = {
  scheme: SchemeName;
  /** What was measured, e.g. `muted on surface`. */
  pair: string;
  ratio: number;
  min: number;
};

const COLORS = ['accent', 'success', 'warning', 'danger', 'info'] as const;
type ColorName = (typeof COLORS)[number];
const SCHEME_NAMES: SchemeName[] = ['light', 'dark'];
const HEX = /^#[\da-f]{6}$/i;
const HEX_ALPHA = /^#[\da-f]{6}([\da-f]{2})?$/i;
// A shadow is written into a stylesheet: only what a box-shadow needs gets through.
const SHADOW = /^[\w\s#.,()%/-]*$/;
const LENGTH = /^[\d.]+(rem|px|em)$/;

// What the soft tint and its text are made of when a palette gives neither (written into the CSS
// and measured by checkPalette from the same numbers).
export const DERIVED = {
  light: { tint: 0.15, text: 0.5 },
  dark: { tint: 0.12, text: 0.45 },
} as const;

type Resolved = {
  grounds: [string, Rgb][];
  foreground: Rgb;
  scheme: SchemePalette;
};

function rgb(value: string, where: string): Rgb {
  const parsed = HEX.test(value) ? parseHex(value) : null;
  if (!parsed) throw new Error(`${where} is not a #rrggbb colour: ${value}`);
  return parsed;
}

/** Throws a plain-language error for anything that is not a colour, so CSS never gets junk. */
export function assertPalette(palette: Palette): void {
  for (const name of SCHEME_NAMES) {
    const scheme = palette[name];
    for (const key of [
      'background',
      'foreground',
      'surface',
      'surfaceSecondary',
      'surfaceTertiary',
      'overlay',
      'muted',
      'border',
      'fieldBorder',
    ] as const)
      rgb(scheme[key], `palette.${name}.${key}`);
    for (const key of ['focus', 'fieldBackground', 'separator'] as const) {
      const value = scheme[key];
      if (value !== undefined) rgb(value, `palette.${name}.${key}`);
    }
    for (const color of COLORS)
      for (const key of ['fill', 'onFill', 'tint', 'text'] as const) {
        const value = scheme[color][key];
        if (value !== undefined) rgb(value, `palette.${name}.${color}.${key}`);
      }
    if (scheme.backdrop !== undefined && !HEX_ALPHA.test(scheme.backdrop))
      throw new Error(`palette.${name}.backdrop is not a colour`);
    for (const key of ['shadow', 'overlayShadow'] as const) {
      const value = scheme[key];
      if (value !== undefined && !SHADOW.test(value))
        throw new Error(`palette.${name}.${key} is not a box-shadow`);
    }
  }
  for (const key of ['radius', 'fieldRadius'] as const) {
    const value = palette[key];
    if (value !== undefined && !LENGTH.test(value))
      throw new Error(`palette.${key} is not a length: ${value}`);
  }
}

const lowerHex = (value: string) =>
  value.replace(/#[\da-f]{6}(?:[\da-f]{2})?\b/gi, (hex) => hex.toLowerCase());

// The colour a palette gives a role on one scheme, with the soft pair worked out where it is left out.
function declarations(name: SchemeName, scheme: SchemePalette): string[] {
  const derived = DERIVED[name];
  const percent = (share: number) => `${Math.round(share * 100)}%`;
  const out: [string, string][] = [
    ['color-scheme', name],
    ['--background', scheme.background],
    ['--foreground', scheme.foreground],
    ['--surface', scheme.surface],
    ['--surface-secondary', scheme.surfaceSecondary],
    ['--surface-tertiary', scheme.surfaceTertiary],
    ['--overlay', scheme.overlay],
    ['--muted', scheme.muted],
    ['--default', 'var(--surface-tertiary)'],
    ['--default-foreground', 'var(--foreground)'],
    ['--segment', 'var(--surface)'],
    ['--segment-foreground', 'var(--foreground)'],
    ['--border', scheme.border],
    ['--separator', scheme.separator ?? 'var(--border)'],
    ['--field-background', scheme.fieldBackground ?? 'var(--surface)'],
    ['--field-foreground', 'var(--foreground)'],
    ['--field-placeholder', 'var(--muted)'],
    ['--field-border', scheme.fieldBorder],
    [
      '--field-border-hover',
      'color-mix(in oklab, var(--field-border) 80%, var(--foreground))',
    ],
    ['--field-border-focus', 'var(--focus)'],
    [
      '--focus',
      scheme.focus ??
        'color-mix(in oklab, var(--accent) 62%, var(--foreground))',
    ],
    ['--accent', `var(--nasim-accent-${name}, ${scheme.accent.fill})`],
    [
      '--accent-foreground',
      `var(--nasim-accent-foreground-${name}, ${scheme.accent.onFill})`,
    ],
  ];
  for (const color of COLORS) {
    const role = scheme[color];
    if (color !== 'accent') {
      out.push([`--${color}`, role.fill]);
      out.push([`--${color}-foreground`, role.onFill]);
    }
    out.push([
      `--${color}-soft`,
      role.tint
        ? role.tint
        : `color-mix(in oklab, var(--${color}) ${percent(derived.tint)}, transparent)`,
    ]);
    out.push([
      `--${color}-soft-foreground`,
      role.text
        ? role.text
        : `color-mix(in oklab, var(--${color}) ${percent(derived.text)}, var(--foreground))`,
    ]);
  }
  if (scheme.backdrop) out.push(['--backdrop', scheme.backdrop]);
  if (scheme.shadow) out.push(['--surface-shadow', scheme.shadow]);
  if (scheme.overlayShadow)
    out.push(['--overlay-shadow', scheme.overlayShadow]);
  return out.map(([property, value]) => `${property}:${lowerHex(value)}`);
}

/**
 * The stylesheet of a palette. `html`-qualified selectors beat tokens.css without depending on
 * which stylesheet loads last, and a device in dark mode with no saved choice gets the dark colours
 * from the first byte (the `@media` rule), before the theme controller has run.
 */
export function paletteCss(palette: Palette): string {
  assertPalette(palette);
  const light = declarations('light', palette.light).join(';');
  const dark = declarations('dark', palette.dark).join(';');
  const geometry = [
    palette.radius ? `--radius:${palette.radius}` : null,
    palette.fieldRadius ? `--field-radius:${palette.fieldRadius}` : null,
  ].filter(Boolean);
  return [
    `html:root,html.light,html[data-theme='light']{${[...geometry, light].join(';')}}`,
    `html.dark,html[data-theme='dark']{${dark}}`,
    `@media (prefers-color-scheme:dark){html:root:not(.light):not([data-theme='light']){${dark}}}`,
  ].join('\n');
}

function resolve(scheme: SchemePalette, name: SchemeName): Resolved {
  const grounds = (
    [
      'background',
      'surface',
      'surfaceSecondary',
      'surfaceTertiary',
      'overlay',
    ] as const
  ).map((key): [string, Rgb] => [key, rgb(scheme[key], `${name}.${key}`)]);
  return { grounds, foreground: rgb(scheme.foreground, name), scheme };
}

// The tint of a role over one ground, as the browser paints it.
function tintOver(
  role: PaletteColor,
  name: SchemeName,
  ground: Rgb,
  fill: Rgb,
): Rgb {
  if (role.tint) return rgb(role.tint, 'tint');
  return blendOver(fill, DERIVED[name].tint, ground);
}

/** Every contrast the palette must keep, measured; an empty list means the palette is sound. */
export function checkPalette(palette: Palette): PaletteIssue[] {
  assertPalette(palette);
  const issues: PaletteIssue[] = [];
  for (const name of SCHEME_NAMES) {
    const { grounds, foreground, scheme } = resolve(palette[name], name);
    const measure = (pair: string, a: Rgb, b: Rgb, min: number) => {
      const ratio = contrastRatio(a, b);
      if (ratio < min) issues.push({ scheme: name, pair, ratio, min });
    };
    const muted = rgb(scheme.muted, 'muted');
    const fieldBorder = rgb(scheme.fieldBorder, 'fieldBorder');
    const fieldBackground = rgb(
      scheme.fieldBackground ?? scheme.surface,
      'fieldBackground',
    );
    for (const [ground, value] of grounds) {
      measure(`foreground on ${ground}`, foreground, value, 4.5);
      measure(`muted on ${ground}`, muted, value, 4.5);
      if (ground !== 'surfaceTertiary')
        measure(`fieldBorder on ${ground}`, fieldBorder, value, 3);
    }
    measure('fieldBorder on fieldBackground', fieldBorder, fieldBackground, 3);
    measure('muted on fieldBackground', muted, fieldBackground, 4.5);

    const accent = rgb(scheme.accent.fill, 'accent');
    const focus = scheme.focus
      ? rgb(scheme.focus, 'focus')
      : mixOklab(accent, 0.62, foreground);
    for (const [ground, value] of grounds) {
      measure(`accent on ${ground}`, accent, value, 3);
      measure(`focus on ${ground}`, focus, value, 3);
    }

    // Error text is danger itself, on the page and every surface.
    const danger = rgb(scheme.danger.fill, 'danger');
    for (const [ground, value] of grounds)
      measure(`danger on ${ground}`, danger, value, 4.5);

    for (const color of COLORS satisfies readonly ColorName[]) {
      const role = scheme[color];
      const fill = rgb(role.fill, `${color}.fill`);
      const onFill = rgb(role.onFill, `${color}.onFill`);
      measure(`${color} text on ${color}`, onFill, fill, 4.5);
      measure(
        `${color} text on hovered ${color}`,
        onFill,
        mixOklab(fill, 0.9, onFill),
        4.5,
      );
      const text = role.text
        ? rgb(role.text, `${color}.text`)
        : mixOklab(fill, DERIVED[name].text, foreground);
      for (const [ground, value] of grounds)
        measure(
          `${color} soft text on its tint over ${ground}`,
          text,
          tintOver(role, name, value, fill),
          4.5,
        );
    }
  }
  return issues;
}

/**
 * What a tenant accent is fitted against under this palette (see `readableAccents`): the accent
 * keeps the same contrast on these surfaces as the palette's own accent does.
 */
export function paletteSchemes(
  palette: Palette,
): Record<SchemeName, SchemeSpec> {
  const spec = (name: SchemeName): SchemeSpec => {
    const scheme = palette[name];
    const triple = (value: string) => rgbToOklch(rgb(value, name));
    return {
      background: triple(scheme.background),
      surface: triple(scheme.surface),
      secondary: triple(scheme.surfaceSecondary),
      fill: triple(scheme.surfaceTertiary),
      foreground: triple(scheme.foreground),
      softShare: DERIVED[name].tint,
      softText: DERIVED[name].text,
    };
  };
  return { light: spec('light'), dark: spec('dark') };
}

// The colour maths, for a server module or a test that has no use for the components.
export { contrastRatio, luminance, parseHex } from './providers/color';
