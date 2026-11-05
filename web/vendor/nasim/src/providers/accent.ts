// One brand colour, one accent per scheme: keep hue and chroma, move lightness as little as needed.
import {
  blendOver,
  contrastOf,
  contrastRatio,
  luminance,
  mixOklab,
  oklchToRgb,
  parseHex,
  type Rgb,
  rgbToOklch,
  toHex,
  type Triple,
} from './color';

export type SchemeName = 'light' | 'dark';

/** What an accent works with in one scheme; mirrors tokens.css (tokens.test.ts catches drift). */
export type SchemeSpec = {
  background: Triple;
  surface: Triple;
  secondary: Triple;
  /** `--default`, the fill of the secondary button, whose text is the soft accent text. */
  fill: Triple;
  /** The page text colour, mixed into the accent for text on a soft tint. */
  foreground: Triple;
  /** Opacity of `--accent-soft` over a surface. */
  softShare: number;
  /** The accent's part (0..1) in `--accent-soft-foreground`; the rest is page text. */
  softText: number;
};

export const SCHEMES: Record<SchemeName, SchemeSpec> = {
  light: {
    background: [0.975, 0.005, 245],
    surface: [1, 0, 0],
    secondary: [0.96, 0.006, 245],
    fill: [0.94, 0.008, 250],
    foreground: [0.21, 0.02, 255],
    softShare: 0.15,
    softText: 0.7,
  },
  dark: {
    background: [0.15, 0.014, 255],
    surface: [0.2, 0.016, 255],
    secondary: [0.24, 0.017, 255],
    fill: [0.29, 0.018, 255],
    foreground: [0.975, 0.004, 250],
    softShare: 0.12,
    softText: 0.45,
  },
};

const SNOW: Triple = [0.9911, 0, 0]; // HeroUI --snow, as OKLCH
const ECLIPSE: Triple = [0.2103, 0.0059, 285.89]; // HeroUI --eclipse
const HOVER = 0.9; // --accent-hover keeps 90% accent, 10% foreground
const MARGIN = 0.05;

export const MIN_UI = 3; // WCAG 1.4.11: the edge of a control against what it sits on
export const MIN_TEXT = 4.5;

export type AccentRatios = {
  /** The accent against the page, the surface and the secondary surface: the weakest ratio. */
  ui: number;
  /** The text on the accent, also on its hover shade. */
  text: number;
  /** `--accent-soft-foreground` on the soft tint over each surface and the secondary fill. */
  soft: number;
};

// What a scheme contributes to every candidate, worked out once: the fit tries hundreds of them.
type Ground = {
  grounds: Rgb[];
  luminances: number[];
  text: Rgb;
  fillLuminance: number;
  fillHoverLuminance: number;
};

const grounds = new WeakMap<SchemeSpec, Ground>();

function groundOf(spec: SchemeSpec): Ground {
  let ground = grounds.get(spec);
  if (!ground) {
    const rgbs = [spec.background, spec.surface, spec.secondary].map(
      oklchToRgb,
    );
    const text = oklchToRgb(spec.foreground);
    const fill = oklchToRgb(spec.fill);
    ground = {
      grounds: rgbs,
      luminances: rgbs.map(luminance),
      text,
      fillLuminance: luminance(fill),
      fillHoverLuminance: luminance(mixOklab(fill, 0.96, text)),
    };
    grounds.set(spec, ground);
  }
  return ground;
}

const uiRatio = (accent: Rgb, { luminances }: Ground) => {
  const own = luminance(accent);
  return Math.min(...luminances.map((ground) => contrastOf(own, ground)));
};

const textRatio = (accent: Rgb, foreground: Rgb) =>
  Math.min(
    contrastRatio(accent, foreground),
    contrastRatio(mixOklab(accent, HOVER, foreground), foreground),
  );

const softRatio = (accent: Rgb, spec: SchemeSpec, ground: Ground) => {
  const own = luminance(mixOklab(accent, spec.softText, ground.text));
  return Math.min(
    ...ground.grounds.map((rgb) =>
      contrastOf(own, luminance(blendOver(accent, spec.softShare, rgb))),
    ),
    contrastOf(own, ground.fillLuminance),
    contrastOf(own, ground.fillHoverLuminance),
  );
};

/** Every contrast an accent must keep, measured the way the CSS computes them. */
export function accentRatios(
  accent: Rgb,
  foreground: Rgb,
  spec: SchemeSpec,
): AccentRatios {
  const ground = groundOf(spec);
  return {
    ui: uiRatio(accent, ground),
    text: textRatio(accent, foreground),
    soft: softRatio(accent, spec, ground),
  };
}

export const meetsAccentRules = (
  { ui, text, soft }: AccentRatios,
  margin = 0,
) =>
  ui >= MIN_UI + margin &&
  text >= MIN_TEXT + margin &&
  soft >= MIN_TEXT + margin;

const css = ([L, C, h]: Triple) =>
  `oklch(${L.toFixed(4)} ${C.toFixed(4)} ${h.toFixed(2)})`;

export type SchemeAccent = {
  accent: string;
  foreground: string;
  accentHex: string;
  foregroundHex: string;
};

const FOREGROUNDS = [SNOW, ECLIPSE].map((triple) => ({
  triple,
  rgb: oklchToRgb(triple),
}));

/** The nearest lightness to the brand's where every rule holds, with the text colour that fits. */
export function fitAccent(base: Triple, spec: SchemeSpec): SchemeAccent | null {
  const ground = groundOf(spec);
  const step = 0.005;
  for (let i = 0; i <= 190; i++) {
    for (const direction of i === 0 ? [1] : [-1, 1]) {
      const lightness = base[0] + direction * i * step;
      if (lightness < 0.02 || lightness > 1) continue;
      const lch: Triple = [lightness, base[1], base[2]];
      const accent = oklchToRgb(lch);
      // The rules that do not depend on the text colour go first: most candidates fail one.
      if (uiRatio(accent, ground) < MIN_UI + MARGIN) continue;
      if (softRatio(accent, spec, ground) < MIN_TEXT + MARGIN) continue;
      const best = FOREGROUNDS.map((foreground) => ({
        foreground,
        text: textRatio(accent, foreground.rgb),
      }))
        .filter((option) => option.text >= MIN_TEXT + MARGIN)
        .sort((a, b) => b.text - a.text)[0];
      if (best) {
        // Written from the gamut-mapped colour: a clipped oklch() would differ from what was measured.
        return {
          accent: css(rgbToOklch(accent)),
          foreground: css(best.foreground.triple),
          accentHex: toHex(accent),
          foregroundHex: toHex(best.foreground.rgb),
        };
      }
    }
  }
  return null;
}

/**
 * One accent per scheme from the reseller's `#rgb` or `#rrggbb`; null when it is not a colour.
 * `schemes` are the surfaces to fit against: Nasim's own unless the app has a palette
 * (`paletteSchemes`).
 */
export function readableAccents(
  value: string,
  schemes: Record<SchemeName, SchemeSpec> = SCHEMES,
): Record<SchemeName, SchemeAccent> | null {
  const rgb = parseHex(value);
  if (!rgb) return null;
  const base = rgbToOklch(rgb);
  const light = fitAccent(base, schemes.light);
  const dark = fitAccent(base, schemes.dark);
  return light && dark ? { light, dark } : null;
}

// Sets the tenant colours on <html> (HeroUI derives hover and soft tones from them); returns undo.
export function applyAccent(
  value: string,
  root: HTMLElement = document.documentElement,
  schemes: Record<SchemeName, SchemeSpec> = SCHEMES,
) {
  const pair = readableAccents(value, schemes);
  if (!pair) return () => {};
  const before = new Map<string, string>();
  for (const scheme of ['light', 'dark'] as const) {
    const set = (name: string, text: string) => {
      before.set(name, root.style.getPropertyValue(name));
      root.style.setProperty(name, text);
    };
    set(`--nasim-accent-${scheme}`, pair[scheme].accent);
    set(`--nasim-accent-foreground-${scheme}`, pair[scheme].foreground);
  }
  return () => {
    for (const [name, previous] of before) {
      if (previous) root.style.setProperty(name, previous);
      else root.style.removeProperty(name);
    }
  };
}
