// Colour maths for the accent and for the token contrast test: OKLCH, linear sRGB, WCAG contrast.
export type Rgb = [number, number, number]; // linear sRGB, 0..1
export type Triple = [number, number, number];

const toLinear = (c: number) =>
  c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
const toGamma = (c: number) =>
  c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
const clamp = (x: number) => Math.min(1, Math.max(0, x));

function oklabToRgb([L, a, b]: Triple): Rgb {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

export function rgbToOklab([r, g, b]: Rgb): Triple {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

export function rgbToOklch(rgb: Rgb): Triple {
  const [L, a, b] = rgbToOklab(rgb);
  return [
    L,
    Math.hypot(a, b),
    ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360,
  ];
}

const oklchToOklab = ([L, C, h]: Triple): Triple => [
  L,
  C * Math.cos((h * Math.PI) / 180),
  C * Math.sin((h * Math.PI) / 180),
];

const inGamut = (rgb: Rgb) => rgb.every((c) => c >= -1e-4 && c <= 1 + 1e-4);

/** OKLCH to linear sRGB; when the colour is out of gamut the chroma is reduced until it fits. */
export function oklchToRgb([L, C, h]: Triple): Rgb {
  const exact = oklabToRgb(oklchToOklab([L, C, h]));
  if (inGamut(exact)) return exact;
  let low = 0;
  let high = C;
  for (let i = 0; i < 20; i++) {
    const mid = (low + high) / 2;
    if (inGamut(oklabToRgb(oklchToOklab([L, mid, h])))) low = mid;
    else high = mid;
  }
  return oklabToRgb(oklchToOklab([L, low, h])).map(clamp) as Rgb;
}

/** color-mix(in oklab, a <share>%, b): `share` is a's part, 0..1. */
export function mixOklab(a: Rgb, share: number, b: Rgb): Rgb {
  const [x, y] = [rgbToOklab(a), rgbToOklab(b)];
  return oklabToRgb(
    x.map((v, i) => v * share + (y[i] as number) * (1 - share)) as Triple,
  );
}

/** `top` painted at `opacity` over `base`, blended like a browser does: in gamma-encoded sRGB. */
export function blendOver(top: Rgb, opacity: number, base: Rgb): Rgb {
  return top.map((c, i) =>
    toLinear(
      toGamma(clamp(c)) * opacity +
        toGamma(clamp(base[i] as number)) * (1 - opacity),
    ),
  ) as Rgb;
}

/** WCAG relative luminance of a linear sRGB colour. */
export function luminance([r, g, b]: Rgb) {
  return 0.2126 * clamp(r) + 0.7152 * clamp(g) + 0.0722 * clamp(b);
}

/** The contrast ratio of two luminances, 1 to 21. */
export function contrastOf(a: number, b: number): number {
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** WCAG 2 contrast ratio, 1 to 21. */
export function contrastRatio(a: Rgb, b: Rgb): number {
  return contrastOf(luminance(a), luminance(b));
}

export function parseHex(value: string): Rgb | null {
  const match = /^#?([\da-f]{3}|[\da-f]{6})$/i.exec(value.trim());
  if (!match?.[1]) return null;
  const digits =
    match[1].length === 3 ? [...match[1]].map((d) => d + d).join('') : match[1];
  return [0, 2, 4].map((i) =>
    toLinear(Number.parseInt(digits.slice(i, i + 2), 16) / 255),
  ) as Rgb;
}

export const toHex = (rgb: Rgb) =>
  `#${rgb
    .map((c) =>
      Math.round(clamp(toGamma(clamp(c))) * 255)
        .toString(16)
        .padStart(2, '0'),
    )
    .join('')}`;
