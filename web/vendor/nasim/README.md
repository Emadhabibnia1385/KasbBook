# «نسیم» (Nasim) design system

Version 0.7.0 (see [CHANGELOG.md](./CHANGELOG.md)).

`@nyxon/nasim` is one set of building blocks for every NYXON dashboard (PAYNYX's web dashboard and
Telegram Mini App first): Persian first, right to left, light and dark, with the Telegram safe areas
and a tenant accent. It is a thin layer over HeroUI 3.2.6 (React Aria Components + Tailwind v4),
written for the Next.js App Router. The demo page (see [Setup](#setup)) shows every piece in both
themes.

## Rules

1. Import from `@nyxon/nasim`. Only this package imports `@heroui/react` or `react-aria-components`
   (`tools/check.ts` enforces it); an app lists `@heroui/styles` for its stylesheet only (see Setup).
2. Nasim's own words (what a close button or a retry button says) live in `src/strings/`. Every
   screen passes its own copy to the components as props, from its own strings module. No Latin text
   in JSX and no literal `aria-label`, `placeholder`, `title` or `alt` in a screen.
3. Colours, radii and fonts come from tokens (`bg-surface`, `text-muted`, `border-border`,
   `bg-accent`, `rounded-field`). No hex values in feature code, and no `dark:` utilities: the
   tokens already switch with the theme.
4. Logical properties for layout (`ms-*`, `pe-*`, `text-start`, `inset-inline-*`). The exception is
   the safe-area insets, which are physical (a notch is on the left or the right of the screen, not
   at the start or the end): use `px-safe`, `px-page` or `pl-*`/`pr-*`, never `ps-*`/`pe-*`.
   Direction-bound icons get `rtl:rotate-180`. Technical values (ids, links, addresses) get
   `dir="ltr"` and `font-mono`.
5. One theme controller: the one in `NasimProvider`. Never call HeroUI's own `useTheme`.
6. Variants are written with `tv()` from `tailwind-variants`, never as long class strings in a
   screen.

## Setup

In a Next.js App Router app (webpack, like the other NYXON apps). The package exports TypeScript
source, so there is no build step, but the app compiles it:

```ts
// next.config.ts
const nextConfig: NextConfig = {
  transpilePackages: ['@nyxon/nasim'],
};
```

The app lists `@nyxon/nasim` (`workspace:*`), `@heroui/styles` (the same version as Nasim's, 3.2.6),
`tailwindcss` and `@tailwindcss/postcss` in its own `package.json`. `@heroui/styles` is there only
because a stylesheet `@import` is resolved from the app's own `node_modules`; the app never imports
`@heroui/react`.

The tree must hold one copy each of `react-aria`, `react-stately` and `react-aria-components`: HeroUI
reads its hooks from the first and Nasim's `I18nProvider` comes from the third, and every copy has its own
locale context, so with two the date picker's month and year button and its year list would ignore the
Persian locale. Bun installs a package once per peer set and lets the copies drift apart, so this
workspace pins them in the root `package.json` `overrides` to the set Nasim's own `react-aria-components`
pin brings (`react-aria` 3.52.1, `react-stately` 3.50.0, `react-aria-components` 1.21.1). The newest set
(3.53.1, 3.51.0, 1.22.1) is not used: with it, in the e2e suite, a modal closed by a finished request (the
card form of the onboarding journey, the role change of the team screen) stayed on screen and its backdrop
kept the next click from landing. Move all three together and run the e2e suite;
`calendarLocale.test.tsx` fails when they split.

The stylesheet loads the system in this order. Tailwind v4 skips `node_modules`, and the workspace
link to Nasim lives there, so `@source` points at the real folder (the path is relative to this
file; this one is `apps/paynyx/web/src/app/globals.css`):

```css
@import 'tailwindcss';
@import '@heroui/styles';
@import '@nyxon/nasim/tokens.css';
@import '@nyxon/nasim/fonts.css';
@source '../../../../../libs/nasim/src';
```

`<html>` is `lang="fa" dir="rtl"` and carries the font variable (see
[Digits and fonts](#digits-and-fonts)); it also needs `suppressHydrationWarning`, because the theme
controller sets its class and `data-theme` after hydration:

```tsx
// app/layout.tsx
<html lang="fa" dir="rtl" className={vazirmatn.variable} suppressHydrationWarning>
  <body>
    <Providers>{children}</Providers>
  </body>
</html>
```

Wrap the app once, in a client component, and hand the provider the router's `push` and `replace`.
The functions must be stable (`useCallback`): React Aria rebuilds every link when they change.

```tsx
// app/providers.tsx
'use client';

import { NasimProvider, type NasimNavigateOptions } from '@nyxon/nasim';
import { useRouter } from 'next/navigation';
import { type ReactNode, useCallback } from 'react';

export function Providers({ children }: { children: ReactNode }) {
  const router = useRouter();
  const navigate = useCallback((href: string, options?: NasimNavigateOptions) => (options?.replace ? router.replace(href, { scroll: options.scroll }) : router.push(href, { scroll: options?.scroll })), [router]);
  return (
    <NasimProvider navigate={navigate} defaultMode={inTelegram ? 'telegram' : 'system'} accent={tenant.accent}>
      {children}
    </NasimProvider>
  );
}
```

The demo page is two lines; keep it out of production:

```tsx
// app/nasim/page.tsx
import { NasimDemo } from '@nyxon/nasim/demo';
import { notFound } from 'next/navigation';

export default function Page() {
  if (process.env.NODE_ENV === 'production') notFound();
  return <NasimDemo />;
}
```

### In a Vite app: Seamless

Seamless (`Emadhabibnia1385/Seamless_bot`, a Vite SPA, a separate repository) keeps an unedited copy of
this package in `web_frontend/vendor/nasim`, a Bun workspace named `@nyxon/nasim`, taken from a commit of
this repository by its `bun run nasim:sync <nyxon checkout>` and proved by `bun run check:nasim` (the
tree hash and the pins in `vendor/nasim.lock.json`). So a change Seamless needs is made here, with its
test, README section and CHANGELOG entry, merged, then synced there; never in the copy. What a Vite app
does instead of the Next setup above: no `transpilePackages`, `@source` pointing at the vendored `src`,
its own `@font-face` rules, and `navigate`/`useHref` built from its router. `'use client'` is ignored.

### Server and client

Every module that holds state, effects, context or an event handler starts with `'use client'`, and
nothing reads `window`, `document` or `localStorage` while a component renders. A Server Component
may import from `@nyxon/nasim` and render the presentational parts with plain props: `KeyValueList`,
`Stepper`, `Cover`, `LoadingState`, `EmptyState` (with an `href` action), `StatusChip`, `StatCard`,
`SectionCard`, `Collapsible`, `StaticTable`, `ColumnChart`, `BarTable` and the skeletons, the colour helpers
(`readableAccents`, `accentRatios`, `parseHex`, `toHex`, `oklchToRgb`, `contrastRatio`, `SCHEMES`,
`MIN_UI`, `MIN_TEXT`), the palette helpers (`paletteCss`, `checkPalette`, `paletteSchemes`) and the
theme cookie helpers (`THEME_COOKIE`, `parseThemeMode`). Everything else is a client component: render it from a Server Component with props
that serialize (no functions), or inside a client component. A Server Component cannot dot into a
client module, so compound primitives (`Card.Header`, `Select.Trigger`) belong in client components.

On the server React Aria cannot reach the Persian dictionary described below (it reads it from
`window`), so the labels it words itself are English in the server HTML, and React does not patch an
attribute that differs on hydration. Nasim names the ones its own components own (the number field's
steppers, the search box's clear button, the select placeholder, spinners, close buttons and the toast
region) with its Persian strings, so they are Persian from the first byte. A primitive that has such a label of its own
(`ColorPicker`'s colour name) needs an explicit `aria-label`, or a client-only render.

The theme is applied to `<html>` after hydration, so with Nasim's own `tokens.css` alone a dark device
in the `"system"` mode paints the first frame light. A product that hands over a `palette` does not have
this: the stylesheet it renders carries a `prefers-color-scheme: dark` rule, and a saved light or dark
choice is on `<html>` from the server's first byte (see [A product's own palette](#a-products-own-palette)
and [The saved choice, for the server](#the-saved-choice-for-the-server)).

`NasimProvider` gives you, in one place:

- `I18nProvider locale="fa-IR"`: Persian numerals, Jalali calendars, RTL.
- React Aria's own strings in Persian ("Close", "Loading", "Dismiss" and the rest). React Aria has
  no override API, so the strings are installed through its global dictionary when this module
  loads (in the browser only), built from the complete en-US dictionary with the Persian keys laid
  over it. A test fails if the install breaks.
- `navigate`: with the host router's push, `LinkButton`, `Link` and menu items navigate without a
  page load. Without it they are plain links. An address with a scheme or a `//host` (Telegram, a
  phone number) is never handed to the router.
- The theme controller, the tenant accent and font, and the toast region.

Its props are typed as `NasimProviderProps`; `NasimNavigate` and `NasimNavigateOptions`
(`{ replace?: boolean; scroll?: boolean }`, what `routerOptions` on a `Link` or `LinkButton` carries) are
exported too:

| Prop            | Type                                          | Notes                                                                                                                                                         |
| --------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `palette`       | `Palette`                                     | The product's own colours and radius, rendered as a stylesheet on the server too (see [A product's own palette](#a-products-own-palette)).                    |
| `initialMode`   | `ThemeMode`                                   | The saved choice as the server read it from the cookie; `parseThemeMode` makes it (see [The saved choice, for the server](#the-saved-choice-for-the-server)). |
| `navigate`      | `NasimNavigate`                               | Optional. `(href, options?) => void`: the host router's push or replace. Enables in-app link navigation. Keep it stable.                                      |
| `useHref`       | `(href: string) => string`                    | Optional. The address a link shows, for a router with a base path; may be a hook. It is called for every link and ignored for an external address.            |
| `defaultMode`   | `"system" \| "light" \| "dark" \| "telegram"` | Used until the person picks one. Default `"system"`.                                                                                                          |
| `nativeBack`    | `boolean`                                     | The host app has its own back button (Telegram's BackButton): `PageHeader` then draws no back arrow. Default `false`.                                         |
| `persist`       | `boolean`                                     | Save the choice in `localStorage` (default `true`). `false` inside Telegram, where the website's saved choice must not win.                                   |
| `initialScheme` | `"light" \| "dark"`                           | The external scheme when it is known at the first render (Telegram's launch theme), so the first paint and the first colours sent to the host are right.      |
| `accent`        | `string` (`#rrggbb`)                          | The reseller's brand colour. Optional.                                                                                                                        |
| `font`          | `string`                                      | The reseller's font: an id with a rule in `fonts.css`. Optional; none (or `vazirmatn`) leaves the page in Vazirmatn.                                          |

### `useTheme`, `ThemeMode`, `ColorScheme`

```tsx
const { mode, setMode, scheme, setScheme } = useTheme();
```

| Field             | Meaning                                                                                                                                                                     |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mode`            | `ThemeMode`: `"system"`, `"light"`, `"dark"` or `"telegram"`.                                                                                                               |
| `setMode`         | Changes the mode and, unless `persist` is off, remembers it in `localStorage` and in the cookie `nasim-theme`; choosing the `defaultMode` forgets the saved choice instead. |
| `scheme`          | `ColorScheme` (`"light"` or `"dark"`): what is applied to `<html>` right now.                                                                                               |
| `setScheme`       | Feeds the external scheme that `"telegram"` mode follows. Ignored in other modes.                                                                                           |
| `automatic`       | The mode that follows the host: `"telegram"` where the app starts in it, else `"system"`.                                                                                   |
| `automaticScheme` | The scheme `automatic` shows right now: Telegram's fed scheme or the device's.                                                                                              |

The controller writes `class` and `data-theme` on `<html>` and nothing else. It does not import
Telegram: the app feeds `setScheme` from the one place that talks to the Mini Apps SDK. In
`"telegram"` mode with nothing fed yet it follows the device. The saved choice is read after
hydration, so the first client render agrees with the server's.

```tsx
import { useTelegramColorScheme } from '@/lib/telegram';

function TelegramTheme() {
  const { setScheme } = useTheme();
  const scheme = useTelegramColorScheme(); // follows Telegram's theme live, null outside it
  useLayoutEffect(() => {
    if (scheme) setScheme(scheme); // before the first paint, so there is no flash
  }, [scheme, setScheme]);
  return null;
}
```

Render `TelegramTheme` inside `NasimProvider` and start with `defaultMode="telegram"`,
`persist={false}` and `initialScheme` set to the same Telegram scheme (it is known synchronously at
launch), so the first render is already in it. A theme picker is three or four buttons calling `setMode` (see the demo).

### `useOverlayStack`, `useRegisterOverlay`

Open dialogs and sheets form a stack, so something outside them can close "the top layer" without
knowing which screen opened what: Telegram's BackButton closes the top sheet before it navigates
back. `BottomSheet` and `ConfirmDialog` register themselves while they are open (a dialog whose
action is still running ignores the request, as it does for Escape).

```tsx
const { count, closeTop } = useOverlayStack(); // count of open layers; closeTop() is false when none

useRegisterOverlay(isOpen, () => setOpen(false)); // for a layer of your own
```

### `usePageHeading`

The title of the page on screen, announced by its `PageHeader` (the h1 one) and `undefined` when
the page has none. A bar above the page uses it to avoid saying the same thing twice.

```tsx
const named = usePageHeading() === screenName; // the page already says it: leave the bar's title out
```

### `useNativeBack`

`true` when `NasimProvider` was given `nativeBack`: the host shows a back button, so a page draws
none. `PageHeader` reads it for you; use it only for a back control you draw yourself.

### `useBottomBar`

A bar your app draws at the bottom of the screen (a tab bar) would hide toasts, which sit just
above the safe area. Put the returned ref on the bar: its height, safe-area padding included, is
published as `--nasim-bottom-bar` and toasts rise above it.

```tsx
const bar = useBottomBar<HTMLElement>();
return (
  <nav ref={bar} className="px-safe pb-(--nasim-safe-bottom)">
    ...
  </nav>
);
```

### Tenant accent

`accent="#0b5cad"` sets the brand colour for both themes (its maths is a chunk of its own, downloaded only
when an `accent` is passed). One colour cannot serve both: a deep red
that reads on white vanishes on a dark surface, and a bright yellow does the opposite. So for each
theme the colour keeps its hue and chroma and moves in lightness only as far as it must, until

- the accent has at least 3:1 against that theme's page, surface and secondary surface, so
  buttons, switch tracks and spinners stay visible;
- text on the accent, and on its hover shade, has at least 4.5:1 (light or dark text is chosen);
- `--accent-soft-foreground` has at least 4.5:1 on the soft tint that chips and alerts use and on
  the secondary button's fill.

The two results are set on `<html>` as `--nasim-accent-light` and `--nasim-accent-dark`, each with
a `-foreground` partner, and `tokens.css` maps `--accent` to the one for the active theme. They
must be on `<html>`, not on a wrapper: HeroUI derives hover and soft tones there with
`color-mix()`. A value that is not a hex colour is ignored. The defaults in `tokens.css` obey the
same rules, and `tokens.test.ts` and `accent.test.ts` measure them for black, white, yellow, blue,
green and red and for every hue and lightness in between.

A screen that lets an admin pick the colour can show what the shop will really use. `readableAccents`
returns the accent and its text colour for each theme, or `null` for a value that is not a colour;
`accentRatios` measures them against the page of a theme in `SCHEMES`, with `MIN_UI` and `MIN_TEXT` as the
limits. `parseHex`, `toHex` and `oklchToRgb` turn a colour between hex and the maths, and `contrastRatio`
measures two of them (WCAG 2, 1 to 21).

### A product's own palette

`accent` fits one brand colour into Nasim's grey surfaces. A product that has its whole palette (PAYNYX:
green on navy) hands it over instead: surfaces, text, the accent and the four statuses, in light and
dark, as `#rrggbb`. Nasim writes it as a stylesheet, checks it against the same contrast rules as its
own tokens, and every component follows it. Nothing else in the app names a colour.

```tsx
// src/theme/palette.ts
import type { Palette } from '@nyxon/nasim';

export const palette: Palette = {
  radius: '0.625rem',
  light: {
    background: '#f5f8f7',
    foreground: '#121f30',
    surface: '#ffffff',
    surfaceSecondary: '#eaf2ee',
    surfaceTertiary: '#e1ece6',
    overlay: '#ffffff',
    muted: '#526477',
    border: '#d7e3dd',
    fieldBorder: '#6a7e8e',
    accent: { fill: '#07744a', onFill: '#ffffff' },
    success: { fill: '#08784d', onFill: '#ffffff', tint: '#e2f3ea', text: '#08784d' },
    warning: { fill: '#8a5700', onFill: '#ffffff' },
    danger: { fill: '#b42338', onFill: '#ffffff' },
    info: { fill: '#245baa', onFill: '#ffffff' },
  },
  dark: {
    // the same keys again
  },
};

// app/layout.tsx and providers.tsx
<NasimProvider palette={palette}>{children}</NasimProvider>;
```

What each key means, and the number it must hold (`checkPalette` measures all of them):

| Key                                                                   | Is                                                                            | Holds                                                |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------- |
| `background`, `surface`, `surfaceSecondary`                           | The page and the cards on it (`surfaceTertiary` is also HeroUI's `--default`) | `foreground` and `muted` at 4.5:1 on each            |
| `surfaceTertiary`, `overlay`                                          | Hovered rows and neutral chips; menus, popovers and dialogs                   | the same                                             |
| `fieldBorder`                                                         | The boundary of a field, a checkbox, an off switch                            | 3:1 on every surface                                 |
| `border`                                                              | Dividers and card edges (decoration only)                                     | nothing                                              |
| `accent.fill`, `accent.onFill`                                        | The brand: buttons, links, the active tab                                     | fill 3:1 on every surface; text on it 4.5:1, hovered |
| `success`, `warning`, `danger`, `info` (`fill/onFill`)                | The four statuses, solid                                                      | text on the fill 4.5:1, hovered too                  |
| `danger.fill`                                                         | Also error text                                                               | 4.5:1 on every surface                               |
| `<role>.tint`, `<role>.text`                                          | The soft pair of a chip or alert                                              | text 4.5:1 on the tint over every surface            |
| `focus`                                                               | The focus ring (default: the accent mixed into the text)                      | 3:1 on every surface                                 |
| `shadow`, `overlayShadow`, `backdrop`, `fieldBackground`, `separator` | Optional; the theme's own when left out                                       | `fieldBackground` carries the field rules            |

A role without `tint` and `text` gets its fill at 15% (12% in dark) as the tint and its fill mixed with
the page text as the text, so a tenant `accent` keeps working over a palette: it is fitted against
the palette's surfaces (`paletteSchemes`) instead of Nasim's. An explicit `tint` on the accent
switches that off for the accent's soft pair.

Test the palette where the product keeps it, so a change that breaks a rule fails the build:

```ts
import { checkPalette } from '@nyxon/nasim/palette';

it('keeps every contrast', () => expect(checkPalette(palette)).toEqual([]));
```

`@nyxon/nasim/palette` holds the types, `checkPalette`, `paletteCss` and `paletteSchemes` without any component,
and the colour maths (`parseHex`, `contrastRatio`, `luminance`), for a test or a server module.

`checkPalette` returns `{ scheme, pair, ratio, min }` for every pair that fails (an empty list when the
palette is sound) and throws on a value that is not `#rrggbb`: a colour is written into a stylesheet,
so nothing else gets through. `paletteCss` is the stylesheet itself. It is qualified with `html`, so
it wins over `tokens.css` whatever loads last, and it holds a `prefers-color-scheme: dark` rule for a
page with no saved choice, so with a palette a dark device paints dark from the first byte (without one,
see [Server and client](#server-and-client)). The `info` status
(`bg-info-soft text-info-soft-foreground`) exists in Nasim's own tokens too, for informational
messages that are neither good nor bad news.

### The saved choice, for the server

The theme controller keeps the choice in `localStorage` and in the cookie `THEME_COOKIE`
(`nasim-theme`). A server layout reads the cookie, renders the explicit choice on `<html>` and hands
it to the provider, so the first byte, the server render and the first client render agree and
nothing flashes:

```tsx
// app/layout.tsx (a Server Component)
const mode = parseThemeMode((await cookies()).get(THEME_COOKIE)?.value);
const explicit = mode === 'light' || mode === 'dark' ? mode : undefined;

<html lang="fa" dir="rtl" data-theme={explicit} suppressHydrationWarning>
  <body>
    <Providers initialMode={mode}>{children}</Providers>
  </body>
</html>;
```

`parseThemeMode` returns the mode a saved value stands for, or `undefined` for anything else, so a
stale or foreign cookie is ignored. `persist={false}` writes neither the storage nor the cookie. The cookie is
`nasim-theme=<mode>; Path=/; Max-Age=31536000; SameSite=Lax`, plus `; Secure` on https; going back to the
default mode removes it (`Max-Age=0`, same `Path` and `SameSite`).

## Tokens (`tokens.css`)

Semantic names over HeroUI's variables, defined once for light and dark.

| Group    | Tokens                                                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Surfaces | `background`, `foreground`, `surface`, `surface-secondary`, `surface-tertiary`, `overlay`                                       |
| Text     | `foreground`, `muted` and `danger` (4.5:1 or more on every surface), and each status's `*-soft-foreground` on its `*-soft` tint |
| Fills    | `accent` (3:1 or more on the page and surfaces), `success`, `warning`, `danger`, `info`, with `*-foreground` for text on them   |
| Lines    | `border`, `separator`                                                                                                           |
| Fields   | `--field-background`, `--field-border`, `--field-border-hover`, `--field-border-focus`, `--field-border-width` (1px)            |
| Focus    | `--focus`                                                                                                                       |
| Geometry | `--radius`, `--field-radius`, `--nasim-page-gutter`, `--nasim-tap-target` (44px)                                                |

Do not write text in `accent`, `success` or `warning`. As plain colours they are fills and edges:
`success` and `warning` measure about 2:1 on a light surface, and a tenant's accent is only
guaranteed 3:1. Coloured text uses the soft pair: `text-accent-soft-foreground` on `bg-accent-soft`
(chips and alerts already do; the secondary button puts it on `default`, which the accent rules
cover too), 4.5:1 or more in both themes.

Fields are bordered in both themes (in dark mode a field and its card share a fill) and an invalid
field shows it in the border. `tokens.test.ts` asserts the contrast of every text, fill and border
pair, and of every soft pair on the page and both surfaces, in both themes. An off switch's track is
the field border (hovered, it mixes towards the text), so it holds the same 3:1.

### Safe areas

`--nasim-safe-top`, `--nasim-safe-right`, `--nasim-safe-bottom`, `--nasim-safe-left` hold the room
a screen must leave for the device and for Telegram. Each is the larger of the device's
`env(safe-area-inset-*)` and Telegram's safe-area plus content-safe-area insets, read from
`--tg-safe-area-inset-*` and `--tg-content-safe-area-inset-*` (the names Telegram's own script
uses; the app binds them from the SDK's state and keeps them current on `safe_area_changed`) or,
failing those, the SDK's longer `--tg-viewport-*` names. Outside Telegram they are the device
insets. To force a value, set the variable on `<html>`. The Mini App shell also reads
`--tg-viewport-stable-height` for its own height.

`PageHeader placement="top"` and `BottomSheet` respect them. Your own fixed bars should too. The
left and right insets are physical, so they have their own utilities: `px-safe` pads by the insets
alone, `px-page` by the page gutter or the inset, whichever is larger, and `p-page` does that on
all four sides.

```tsx
<nav className="fixed inset-x-0 bottom-0 px-safe pb-(--nasim-safe-bottom)">...</nav>
```

### Touch targets

Primary actions on a phone are at least 44px: use `size="lg"` (44px on phones, 40px on desktop)
for the main button of a screen. `SubmitButton`, `EmptyState`, `ErrorState`, `ConfirmDialog` and
the `PageHeader` back button already do. Under `(pointer: coarse)` icon-only buttons, close
buttons and the number-field steppers keep their look but get a 44px hit area. Text fields,
selects and switch rows are at least 44px tall.

### Left-to-right values

Technical values (ids, links, codes, phone numbers) keep `dir="ltr"` so Latin text and digits read
correctly, and they sit on the RTL start edge, the right: `TextField dir="ltr"` and `CopyField`
right-align their text, and so does a `ltr` value in a `stacked` `KeyValueList`. In a two-column
`KeyValueList` row the value cell is at the row's end, so a `ltr` value aligns left there.

### Digits and fonts

Nasim chooses the font; the app loads it. `fonts.css` holds one `[data-font="<id>"]` rule per font
(its family and its digit feature) and the default rule for `:root`; it has no `@font-face`. A rule
takes the family from `--font-<id>` when the app exposes one (`next/font` with `variable:
'--font-vazirmatn'`, which brings its own fallback list) and otherwise names the family, which the
app then declares with its own `@font-face`. A font the app does not load is a font the page cannot
use, so a tenant's `font` id must be one the app ships. The default is Vazirmatn, `--font-vazirmatn`,
and it must be the cut that has Latin letters and digits (the `vazirmatn` package's
`Vazirmatn[wght].woff2`); the non-Latin cut in `@nyxon/ui` needs a Latin face in front of it, or Latin
silently falls back to Tahoma. `font="estedad"` on `NasimProvider` puts `data-font` on `<html>`, so the
whole page follows; on any element `data-font` with `font-sans` previews that font. `html` takes its
`font-feature-settings` from the font: `"ss01"` in Vazirmatn and `"ss20"` in Estedad draw ASCII digits as
Persian digits while the text stays ASCII (copied numbers still scan); the other builds have Persian digits
built in. `font-mono` ignores the feature, so technical values keep Latin digits. Use `tabular-nums` only
where numbers must line up (balances, prices, countdowns). To add a font: the app loads it and its
license, and `fonts.css` gets a rule with its id and digit feature.

## Composites

Each is one idea in one file (a part splits when it stops being one idea, not at a line count), takes
copy as props and uses Nasim's strings for its own words. The
examples read their copy from `t`, the app's own strings module, as screens must: `t.services.title`
and the like stand for keys you add there.

### `PageHeader`

A page or section heading with an optional back link and actions.

```tsx
<PageHeader title={t.services.title} description={t.services.subtitle} backHref="/" actions={<Button size="sm">{t.shop.buy}</Button>} />
```

`as` (`"h1"` default, `"h2"`, `"h3"`), `size` (`"page"`, `"section"`), `placement` (`"content"`
default; `"top"` when the header is the first thing on screen and must clear the safe areas).
`description` may be a node, `meta` is a small line under it (a status chip, the last update) and the
actions wrap under the title on a narrow screen.

### `SubmitButton`

The form's submit button: `type="submit"`, large, full width. Inside `FormRoot` it shows the
spinner while the form submits. While it runs the button is disabled, so clicks and Enter cannot
submit twice; it is deliberately not React Aria's `isPending`, whose announcement points at the
button's own id and dangles (axe `role-img-alt`) when a form closes or is replaced on success.
Outside a form, pass `isPending` yourself.

```tsx
<SubmitButton>{t.common.confirm}</SubmitButton>
```

### `ThemeToggle`

A round icon button that flips light and dark. It shows the other theme's icon and is named for the press
(`lightLabel`, `darkLabel`: the app's words). It stores the other theme, except when that is what the host
already shows (the device, or Telegram): then it hands the choice back (`automatic`), so a person who
flips twice is on «follow my device» again. Disabled until hydration, because the server does not know
the device's scheme.

```tsx
<ThemeToggle lightLabel={t.theme.light} darkLabel={t.theme.dark} />
```

### `LoadingState`

```tsx
<LoadingState />
<LoadingState size="inline" label={t.orders.checkingPayment} />
```

The default fills a page (centred, tall); `size="inline"` fits inside a card or list. It is an
`<output>` (a polite live region), so the label is announced.

### `EmptyState`

```tsx
<EmptyState title={t.services.emptyTitle} description={t.services.emptyHint} action={{ label: t.shop.browse, href: '/shop' }} />
```

`action` is `{ label, href }` or `{ label, onPress }`, or your own element when the next step needs
more than a button (two buttons, a button that is only there for some people). `description` may be a
node. An empty screen should always offer the next step. `icon` replaces the default. The title is an `h2`; pass `as="h1"` when the state is the
whole page. When a screen swaps a state in (a request failed, a wait ended), pass `titleRef` and
focus it: the title becomes focusable, so the keyboard is where the news is and a screen reader
hears it.

### `ErrorState`

```tsx
<ErrorState onRetry={refetch} supportHref={supportUrl} requestId={error.requestId} />
```

Defaults to a generic title and a connection hint; pass `title` and `message` for specific cases.
`requestId` is shown as a tracking code in a left-to-right monospace span. The title is an `h2`;
pass `as="h1"` when the state is the whole page, and `titleRef` to move focus to it like `EmptyState`.
`retryIn` (seconds) keeps the retry button disabled, counting down, for a server that said when to come back.
Children are detail under the message, announced with it (the fields a server refused).

### `ConfirmDialog`

An alert dialog for destructive or money-moving actions. `tone="danger"` for irreversible ones.

```tsx
<ConfirmDialog isOpen={open} onOpenChange={setOpen} tone="danger" title={t.services.deleteTitle} description={t.services.deleteWarning} confirmLabel={t.services.delete} onConfirm={() => removeService.mutateAsync(id)} />
```

`onConfirm` may return a promise: the button shows the spinner, Escape and the backdrop are
disabled meanwhile, and the dialog closes when it resolves. If it rejects the dialog stays open;
report the error yourself (toast, mutation `onError`). Escape and the cancel button close it.

When the caller already knows that the action is running (a mutation's `isPending`), pass `isPending`:
the dialog then only shows it, calls `onConfirm` without waiting and does not close itself; close it
when the action succeeds. `description` may be a node, or put a body of several paragraphs in the children.

### `BottomSheet`

A sheet from the bottom edge for choices and short forms.

```tsx
<BottomSheet
  isOpen={open}
  onOpenChange={setOpen}
  title={t.checkout.paymentMethod}
  footer={
    <Button size="lg" onPress={pay}>
      {t.checkout.pay}
    </Button>
  }
>
  {methods}
</BottomSheet>
```

Closes with Escape, a backdrop tap, a drag down or the close button. A press on the backdrop is
ignored for half a second after the content changes height (the button the tap was meant for has
moved, and the tap would land beside the sheet) and while `isBusy` is set, which a flow passes while
its request runs. A sheet that moves money passes `isDismissable={false}`: the backdrop and a drag
down close nothing, and only its own buttons, Escape and the host's Back close it. It keeps clear of
the safe areas, and inside Telegram its height follows `--tg-viewport-stable-height`. Footer buttons
fill the width on phones.

### `KeyValueList`

```tsx
<KeyValueList
  items={[
    { label: t.wallet.balance, value: formatToman(balance), numeric: true },
    { label: t.services.id, value: serviceId, ltr: true },
  ]}
  layout="split"
/>
```

`layout` is `"split"` (label at the start, value at the end; a long value wraps under its label),
`"stacked"` (value under label, for long values) or `"grid"` (pairs in two columns from `sm` up, label
above value: the details of one record). `label` may be a node. `ltr` marks technical values; `numeric`
aligns digits. A row that exists only sometimes is `cond && { label, value }`: `false`, `null` and
`undefined` are skipped. `className` lands on the `<dl>`. Server-renderable.

### `Cover`

A 16:9 picture box that keeps its shape with or without the picture: no `src` (none yet, or none at
all) shows an accent-tinted placeholder with the `icon` of the kind of thing it stands for, so every
card in a grid is the same height.

```tsx
<Cover src={category.image_url} icon={<CategoryIcon />} />
```

### `CopyField`

A read-only value in a field that copies when pressed anywhere; always left to right. A long value is
cut in the middle, so its last eight characters stay visible and nothing overflows.

```tsx
<CopyField label={t.services.subscriptionLink} value={subscriptionUrl} />
```

On success it shows a toast and «کپی شد»; if the clipboard is blocked it selects the text and tells
the person to copy it by hand. `children` sit under the field (a QR button, a pager of several values).

`multiline` shows a value of several lines (a WireGuard profile) whole, in a box of its own, and
copies it whole.

### `MessageBar`

A chat's compact composer: one rounded row with an attach button (`leading`), a text box that grows up
to five lines and a round send button. Enter sends, Shift+Enter breaks the line. The text is yours
(`value`, `onValueChange`); `attachment` and `notice` sit above the row.

```tsx
<MessageBar
	label={t.tickets.composer.message}
	sendLabel={t.tickets.composer.send}
	value={text}
	onValueChange={setText}
	onSubmit={send}
	canSend={text.trim() !== ""}
	leading={attachButton}
/>
<MessageBar closedNote={t.tickets.thread.closedNotice} />
```

`closedNote` replaces the whole bar with that note when the conversation is over. Put it at the bottom
of a screen that fills the window.

### `SearchBox`

A search field for filtering a list (outside a form). The label names it for a screen reader; there is
no visible one. It reports every keystroke, so wait before searching on each of them yourself.

```tsx
<SearchBox label={t.services.search} value={query} onChange={setQuery} />
```

The clear button and Escape empty it. HeroUI labels its clear button "Close"; ours says
«پاک کردن جست‌وجو».

### `FilterChips`

One of a few filters, always one chosen: a radio group drawn as chips that wrap on a narrow screen.
Arrow keys move between the chips and Space chooses.

```tsx
<FilterChips label={t.services.statusFilter} value={status} onChange={setStatus} options={[{ value: 'all', label: t.services.filters.all }]} />
```

### `OptionCards`

One of a few choices that need more than a word each (a package with its price, a payment method with
its fee): a radio group whose radios are tappable cards. `meta` is said at the end of the card.

```tsx
<OptionCards label={t.payments.method} value={method} onChange={setMethod} options={[{ value: 'wallet', title: t.payments.wallet, description: t.payments.walletHint, meta: price }]} />
```

`hideLabel` names the group for a screen reader only, when the screen has a heading for it; `isInvalid`
and a per-option `icon` and `isDisabled` exist too. A `description` may be a node (a sample drawn in a
font), and `className` lays the cards out some other way (`grid grid-cols-2`).

### `SortableList`

A short list (2 to 30 rows: the shop's payment gateways, the start-menu buttons) that a person puts in order
by dragging. It is controlled: it draws `items` in the order given and calls `onReorder` with every id in
the new order; it keeps no order of its own, so the owner saves the order and passes it back.

```tsx
<SortableList label={t.gateways.order} items={gateways} onReorder={saveOrder} />
```

`items` is `{ id, label, description? }[]`, `label` names the list for a screen reader, and `isDisabled`
(while saving) turns off dragging and the buttons. Four props, no more.

- **Drag.** A mouse or a finger drags a row by anywhere on it; the grip at its start is the drag handle for a
  keyboard and a screen reader (Enter to pick up, arrow keys or Tab to a place, Enter to drop, Escape to
  cancel). A line in the accent colour shows where the row will land.
- **Without dragging.** Every row has «بردن به بالا» and «بردن به پایین» buttons (WCAG 2.2, 2.5.7 Dragging
  Movements): the first row's up and the last row's down are disabled. Each button is named with its row
  («بردن زرین‌پال به بالا»), a polite line says where the row went, and focus stays on the pressed button
  (on the other one when the row reached the top or the bottom).
- **Targets and direction.** Every control is 44px (`size-11`); the layout is logical, so the grip sits at
  the start (the right) in Persian. The colours are tokens, and the focus ring is Nasim's.

What it follows in React Aria (`react-aria-components` 1.21.1, read from `dist/private/`, and the skill's
`references/guides/dnd.md` «Reordering items» and `components/GridList.md` «Drag and drop»):

- `GridList` takes `dragAndDropHooks` from `useDragAndDrop`; the row is `GridListItem` with a `textValue`.
  `GridList.mjs` warns when a draggable item has no `<Button slot="drag">` and gives that button the
  keyboard and screen-reader drag (it sets `pointer-events: none` on it, so the row itself is the mouse and
  touch source). The list has no selection, so a press on a row never fights a drag.
- `useDragAndDrop` options used: `getItems` (what is dragged; a private type, so a drop in a text box or from
  another page does nothing), `acceptedDragTypes`, `onReorder` (React Aria's «between items only» drop:
  `e.keys` and `e.target.key` with `dropPosition` `before` or `after`), `renderDropIndicator` with
  `DropIndicator`, and `isDisabled`, which empties the row's drag props and disables the handle.
- React Aria's drag-and-drop announcements and the handle's name («کشیدن زرین‌پال») are English in
  `@react-aria/dnd`; the Persian ones are in `t.reactAria['@react-aria/dnd']`.

### `ScrollRegion`

Wraps content that can be wider than the screen, such as a table. It scrolls sideways, and only while
it does it becomes a focus stop with a name, because a keyboard can scroll only what it can focus.

```tsx
<ScrollRegion label={t.content.tariff.table(name)}>
  <table>…</table>
</ScrollRegion>
```

### `Stepper`

Where the person is in a flow of a few steps (a renewal: options, method, confirm): a bar for the eye
and the same in words, «مرحله ۲ از ۴: روش پرداخت». The bar is decoration; the words are what a screen
reader gets. Move focus to the new step's heading yourself when the step changes.

```tsx
<Stepper steps={[t.renew.options, t.renew.method, t.renew.confirm]} current={1} />
```

### `StatusChip`

A status as an icon and words on a soft tint: `tone` is `"success"`, `"warning"`, `"danger"`, `"info"` or
`"neutral"`, `label` is the status in words (the chip is never colour alone), `size` is `"sm"`, `"md"` or
`"lg"`. `icon` replaces the tone's icon (a clock for «waiting», an hourglass for «expired»). Plain markup, so
a Server Component can render it.

```tsx
<StatusChip tone="success" label={t.invoice.paid} />
<StatusChip tone="neutral" label={t.invoice.expired} icon={<HourglassIcon />} size="sm" />
```

### `Notice`

An inline message (HeroUI's alert with its icon): `tone` is `"info"` (default), `"success"`, `"warning"`,
`"danger"` or `"neutral"`, with an optional `title`. Pass `role="alert"` for a failure that appears in answer
to an action and `role="status"` for good news.

```tsx
<Notice tone="warning" title={t.limits.title} role="status">
  {t.limits.body}
</Notice>
```

### `SectionCard`

A card with a titled header and a body: a `<section>` named by its own heading (`level` 2 by default, 3
inside another section), with `description`, `actions` at the far end of the header and a decorative
`icon`. A card with no header is `Card`. Server-renderable.

```tsx
<SectionCard title={t.destinations.title} description={t.destinations.hint} actions={<Button size="sm">{t.destinations.add}</Button>}>
  {rows}
</SectionCard>
```

### `StatCard`

A key figure: `label`, a tabular `value` (a number or an amount with its unit), a `hint` for its scope and a
`footer` (a comparison with the last period). `as="h2"` makes the label a heading when the tile titles a
section. Server-renderable.

```tsx
<StatCard label={t.sales.title} value={formatToman(total)} hint={t.sales.period} />
```

### `SkeletonRows`, `TableSkeleton`, `PageSkeleton`

Loading shapes that keep the layout still while data arrives: list rows (`dense` for plain bars), a table
with a header and `rows` body rows, and a whole screen (`header`, `stats` tiles, `rows`). Each is one
`role="status"` with a visually hidden `label` (default «در حال بارگذاری»); the shapes are decoration.

```tsx
<PageSkeleton stats={3} rows={4} label={t.dashboard.loading} />
```

### `OfflineBanner`, `useOnline`

A polite strip (`role="status"`) above the page while the connection is down and nothing while it is up;
its words are Nasim's, or pass your own as the child. `useOnline()` is the same fact as a boolean (the
server says `true`).

```tsx
<OfflineBanner />
```

### `CopyButton`

A button that copies `value` (its canonical form: Latin digits, no separators) and says so: its label
turns into `doneLabel` («کپی شد») for a moment and a polite live region announces it. Where the clipboard
API is refused (a Telegram WebView) it falls back to the older copy command. If that fails too, the button
shows a danger icon and a line under it, in words and as the live region, says «کپی نشد؛ مقدار را دستی
انتخاب و کپی کنید.»: the button selects nothing, so the value must be on the page beside it, and the failure
stays until the next press. `CopyField` is the field that shows the value and selects it for you when the
clipboard is refused; this is the button beside a value you show yourself (a card number grouped in fours,
a one-time secret).

```tsx
<CopyButton value={card} label={t.checkout.copyCard} />
```

### `Collapsible`

Advanced or rarely used options in a native `<details>`: the `title` says what is inside before it opens,
`description` is one line under it, `defaultOpen` starts it open. Keyboard and screen readers work with no
client JavaScript. Server-renderable.

```tsx
<Collapsible title={t.limits.advanced} description={t.limits.advancedHint}>
  {fields}
</Collapsible>
```

### `AppShell`

The frame of a dashboard: a sidebar from `lg` up, a bar with a menu button that opens the same navigation
in a drawer below it, `banner` above the page and the page itself in `<main id="main">`. The app knows the
route, so each nav item carries its own `isCurrent` (Nasim imports no router); links navigate through
`NasimProvider`. The bar and the page clear the safe areas, so the same shell serves the Telegram Mini App.

```tsx
<AppShell brand={<Logo />} navLabel={t.nav.label} nav={items.map((item) => ({ href: item.href, label: item.label, icon: <item.Icon />, isCurrent: item.href === current }))} topbar={<ThemeToggle lightLabel={t.theme.light} darkLabel={t.theme.dark} />} sidebarFooter={<Attribution />} banner={<OfflineBanner />}>
  {children}
</AppShell>
```

### `StaticTable`

Read-only rows for a page that is text, not a tool (a bank list, a comparison of methods): plain markup in
HeroUI's table skin, so a Server Component draws it with no client JavaScript. `caption` names the table and
the region that scrolls it (the region takes focus, so a keyboard user can scroll a wide table), `columns`
are the headings, and each of `rows` is `{ id, cells }` with one cell per column; the first cell of a row is
its header. `className` lands on the `<table>` (a `min-w-[36rem]` keeps a wide table from squeezing). A list a
person works through is `DataTable`.

```tsx
<StaticTable caption={t.banks.caption} columns={[t.banks.bank, t.banks.status]} rows={banks.map((bank) => ({ id: bank.code, cells: [bank.name, <StatusChip tone="info" label={bank.status} />] }))} className="min-w-[22rem]" />
```

### `ColumnChart`, `BarTable`

Charts in plain SVG and HTML, no chart library, written so that no number is only a picture. `ColumnChart`
draws one bar per `points` entry (`{ key, label, value, tooltip }`): `value` is only the bar's height, the
exact figure is `tooltip` (SVG `<title>`) and a data table behind a disclosure (`table`: `showLabel`, `label`,
`columns`, `rows` whose first cell is the row header). `summary` is what a screen reader hears for the
picture (the range, the busy days, the peak); `showSummary` writes it under the title, `note` explains the
scaling, `tone` is `"accent"`, `"success"` or `"info"`, and `empty` replaces the plot when no value is above
zero. The plot is left to right whatever the page direction, with the first and last label at its ends.
`BarTable` is a table that is also a chart: each row of `rows` (`{ key, label, value, cells }`) has its label,
a bar in proportion to `value` and its exact `cells`; `hideTitle` keeps the title for screen readers only,
`barFrom="sm"` drops the bars on a phone, `regionLabel` names the scrolling region. Both are
server-renderable and take `data-testid` (the chart's table and summary add `-table` and `-summary`).

```tsx
<ColumnChart data-testid="daily" title={t.sales.daily} summary={summaryText} points={days.map((day) => ({ key: day.id, label: day.short, value: day.count, tooltip: `${day.full}: ${day.count}` }))} empty={t.sales.noData} table={{ showLabel: t.sales.showTable, label: t.sales.tableLabel, columns: [t.sales.day, t.sales.count], rows: days.map((day) => ({ key: day.id, cells: [day.full, day.count] })) }} />
<BarTable title={t.sales.byCard} labelHeader={t.sales.card} valueHeaders={[t.sales.count, t.sales.amount]} rows={cards.map((card) => ({ key: card.id, label: card.name, value: card.rial, cells: [card.count, card.amount] }))} empty={t.sales.noData} />
```

### `DataTable`, `Pager`

A table on React Aria's grid (keyboard navigation, right to left), written for a list a person pages through.
`columns` are `{ id, header, cell, align?, isRowHeader?, className? }` (`align: "end"` for amounts; exactly one
column is the `isRowHeader`), `rows` and `getRowId` give the rows, and `status` is `"loading"` (skeleton rows),
`"error"` (the error state with `onRetry`, or your own `errorState`) or `"ready"` (the rows, or the empty state
made from `emptyTitle`, `empty`, `emptyIcon` and `emptyAction`). `ariaLabel` names it. A wide table scrolls
sideways in its own region. `pagination` (`{ page, pageCount, onPageChange }`) adds a `Pager` under it when
there is more than one page.

On a phone a table is hard to read, so `cards="sm"` or `cards="md"` turns every row into a card below that
breakpoint: the `isRowHeader` column is the title, the other columns are labelled values (leave one out with
`hideOnCard: true`), and the columns marked `isActions: true` are the buttons in the footer (a card whose action cells all render
nothing has no footer at all, not an empty bar). Only one layout is
in the DOM at a time (the server and the first client render draw the table), so text and roles are never
duplicated; the cards are a list named by `ariaLabel` with `data-testid="data-cards"`. `useIsNarrow` takes
`"sm"` or `"md"` and is the same media query as a hook, for a screen that swaps its own layout (a filter bar
that collapses); the server and the first client render say no.

`Pager` is the previous and next buttons with the page in words, «صفحه ۲ از ۵»: pass `pageCount`, or
`hasNext` for a cursor-paged list that does not know its end, and `isFetching` to say it is refreshing.

```tsx
<DataTable ariaLabel={t.invoices.title} columns={columns} rows={rows} getRowId={(row) => row.id} status={status} onRetry={refetch} emptyTitle={t.invoices.emptyTitle} empty={t.invoices.empty} />
<Pager page={page} hasNext={Boolean(nextCursor)} onPrevious={back} onNext={forward} />
```

### `Modal`

A centred dialog for a form or a detail; `BottomSheet` is the phone's. `title`, `children`, `footer` (the
cancel first, the main action last), `size` (`"xs"` to `"lg"`). `isDismissable={false}` for a form with
unsaved input: the backdrop and Escape close nothing; `isBusy` does the same while a request runs. It
registers as a layer, so Telegram's Back button closes it.

```tsx
<Modal isOpen={open} onOpenChange={setOpen} title={t.team.invite} footer={<Button onPress={send}>{t.team.send}</Button>}>
  {fields}
</Modal>
```

### `Tabs`

Tabs on React Aria: `label` names the list, `items` are `{ id, label, content?, isDisabled? }`, and the
selection is controlled with `selectedKey` and `onSelectionChange(id)` or left to `defaultSelectedKey`.
Leave `content` out when the page shows what the tab selects (route tabs). HeroUI's buttons that scroll a
long list are named in Persian here, not in its English.

```tsx
<Tabs label={t.settings.sections} items={sections} selectedKey={section} onSelectionChange={setSection} />
```

### `NavTabs`

Sibling pages that share one menu entry (invoices, payment links and the sales report under «فروش»),
switched with a tab-looking bar. Each tab is a link to a page of its own inside a `<nav>` named by
`label`, and `isCurrent` (the app knows the route) marks the page on screen with `aria-current`; `Tabs` is
for panels on one page. Links navigate through `NasimProvider`.

```tsx
<NavTabs label={t.sales.sections} items={sections.map((tab) => ({ href: tab.href, label: tab.label, isCurrent: tab.href === pathname }))} />
```

## Forms

React Hook Form + Zod. Fields read the form from context, validate with `validationBehavior="aria"`
(the resolver owns the rules) and show the resolver's message under the field. Loading `FormRoot` also
sets Zod's Persian locale as a fallback (a page without a form does not ship Zod); a schema should still
pass its own messages.

React Hook Form belongs to `FormRoot` alone. A field given a `name` reads its value through the form, and
a field given `value` and `onChange` does not, so a page whose fields are all controlled never downloads
React Hook Form. A field with a `name` and no `FormRoot` around it throws an error that says so.

Every field works in one of two ways, told by its props:

- **In a form**: pass `name`, the key in the form values. The field reads and writes the value itself.
- **Controlled**: pass `value` and `onChange` (and `errorMessage` for the text under the field). For a
  filter bar, a dialog, a flow that keeps its own state, where a form library would only be in the
  way. The field draws the same, validates nothing itself, and is invalid exactly while
  `errorMessage` is set.

```tsx
<TextField label={t.filters.search} value={query} onChange={setQuery} />
<SelectField label={t.filters.status} value={status} onChange={setStatus} options={statuses} />
```

Every field also takes `className` and `data-testid` for its root element.

Help for a field is its `description`, never a paragraph beside it and never an `aria-describedby` passed
to the field (a field takes neither: it would be dropped). The description is tied to the control for a
screen reader, also when it appears after the field did (the hint of the option just chosen is
`description={hints[choice]}`).

### `FormRoot`

```tsx
const form = useForm<Values>({ resolver: zodResolver(schema) });

<FormRoot form={form} onSubmit={(values) => mutate(values)} className="flex flex-col gap-4">
  <TextField name="email" type="email" dir="ltr" label={t.account.email} isRequired />
  <SubmitButton>{t.common.confirm}</SubmitButton>
</FormRoot>;
```

`onSubmit` receives validated values. A submit while one is still running is ignored (this also
covers a single-field form, where Enter submits implicitly). Handle failures inside `onSubmit`
(call `mutate`, not `mutateAsync`).

### `FormFields`

The fields of a form whose submit is not a button inside it: Telegram's MainButton, a sheet's footer.
Fields bind by `name` exactly as in `FormRoot`, but no `<form>` is drawn, so Enter in a field submits
nothing, and a small form of its own (a discount code with its own apply button) may sit inside. The
owner submits with `form.handleSubmit(...)` and guards a second press itself.

```tsx
<BottomSheet footer={<Button onPress={() => void submit()}>{t.checkout.pay}</Button>}>
  <FormFields form={form}>
    <CodeField />
    <SwitchField name="useWallet" label={t.checkout.useWallet} />
  </FormFields>
</BottomSheet>
```

### `TextField`

`label`, `description`, `isRequired`, `isDisabled`, plus `type`, `placeholder`, `autoComplete`,
`inputMode`, `maxLength`, `minLength`, `autoFocus`, `spellCheck`. `dir="ltr"` for emails, usernames and
phone numbers (Latin text types and aligns correctly). The label may be a node (a visually hidden one,
when the screen already names the field).

### `NumberField`

```tsx
<NumberField name="seats" label={t.plan.seats} minValue={1} maxValue={10} />
```

The value is a `number`, or `undefined` while the box is empty. Also `step` and `formatOptions`.
`hideSteppers` drops the − and + buttons for a number that is an identifier, not a quantity.

### `SelectField`

```tsx
<SelectField name="plan" label={t.plan.label} options={[{ value: '30', label: t.plan.days30 }]} />
```

In a form the value is the chosen option's `value` string, or `undefined`; controlled, it is that string
or `null`. An option may be `isDisabled`. `placeholder` defaults to the Persian one.

### `TextAreaField`

A multi-line `TextField` for notes and messages: `name`, `label`, `description`, `isRequired`,
`isDisabled`, `rows` (4), `placeholder`, `maxLength`, `autoFocus`. The value is the text as typed,
line breaks included.

```tsx
<TextAreaField name="note" label={t.services.note} rows={3} />
```

### `SwitchField`

```tsx
<SwitchField name="renew" label={t.plan.autoRenew} description={t.plan.autoRenewHint} />
```

### `RadioGroupField`, `CheckboxGroupField`, `CheckboxField`

One of a few choices, any of a few, and one yes or no. Options are `{ value, label, description?,
isDisabled? }`: the label names the option and the description is read with it. The radio value is the
chosen `value`, the checkbox group's is the list of chosen values, and `CheckboxField`'s is a boolean; its
label is its children. A few words each: a choice that needs a price or a long line is `OptionCards`.

```tsx
<RadioGroupField name="mode" label={t.link.mode} options={[{ value: 'live', label: t.link.live }]} />
<CheckboxGroupField name="scopes" label={t.team.scopes} options={scopes} />
<CheckboxField name="agree">{t.terms.agree}</CheckboxField>
```

### `DateTimeField`

A date and a 24-hour time in the Persian calendar with Persian digits (HeroUI's date picker under
`fa-IR-u-ca-persian`). The value stays the Gregorian local `YYYY-MM-DDTHH:mm` a form validates and
converts, or an empty string for no date; a clear button empties it. The three names are the app's words:
`calendarLabel` (the popover), `timeLabel` (the time box in it) and `clearLabel`.

```tsx
<DateTimeField name="expiresAt" label={t.link.expiry} calendarLabel={t.link.calendar} timeLabel={t.link.time} clearLabel={t.link.clear} />
```

### `HexColorPicker`

A swatch button that opens a colour area, a hue slider and a row of ready-made colours, and reports an
upper-case `#RRGGBB`. Controlled only: `value`, `onChange`, `presets`, `fallback` (what it opens on when
`value` is not a colour) and the three names `label`, `hueLabel` and `presetsLabel`.

```tsx
<HexColorPicker value={brand} onChange={setBrand} label={t.brand.pick} hueLabel={t.brand.hue} presetsLabel={t.brand.presets} presets={PRESETS} fallback="#0b905d" />
```

## Primitives

Straight re-exports from HeroUI unless marked. Use them with HeroUI's compound anatomy; the
HeroUI docs for 3.2.6 apply, except where a note says otherwise.

Wrapped, with Persian defaults or fixes:

| Export        | What the wrapper adds                                                                                                                     |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `Spinner`     | `aria-label` in Persian. Inside a button: `<Spinner color="current" size="sm" />`.                                                        |
| `CloseButton` | `aria-label` in Persian.                                                                                                                  |
| `Select`      | Persian placeholder. Parts: `Select.Trigger`, `.Value`, `.Indicator`, `.ClearButton`, `.Popover`.                                         |
| `LinkButton`  | A router-aware link styled as a button: `variant`, `size`, `fullWidth`, `isIconOnly`; `target="_blank"` adds `rel="noopener noreferrer"`. |

Re-exported:

| Export                                                                | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Button`                                                              | `variant`, `size`, `isPending` (pass a render function child to show a `Spinner`)                                                                                                                                                                                                                                                                                                                                                                                                    |
| `ButtonGroup`                                                         | Joins buttons.                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `Alert`                                                               | `Alert.Indicator`, `.Content`, `.Title`, `.Description`. No close part.                                                                                                                                                                                                                                                                                                                                                                                                              |
| `Avatar`, `Badge`                                                     | `Badge.Anchor` places a badge on an avatar.                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `Card`                                                                | `Card.Header`, `.Title`, `.Description`, `.Content`, `.Footer`.                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `Chip`                                                                | `color`, `variant="soft"`.                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `Checkbox`, `Input`, `TextArea`, `Label`, `Description`, `FieldError` | Field parts; use `TextField` and friends for forms.                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `ColorPicker`, `ColorArea`, `ColorSlider`, `ColorSwatch`              | A colour chosen by eye: `ColorPicker` (`value` as `#rrggbb` or a `Color`, `onChange(color)`) holds `.Trigger` (a `ColorSwatch` of its colour) and `.Popover` with a `ColorArea` (`colorSpace="hsb"`, `xChannel="saturation"`, `yChannel="brightness"`, `.Thumb`) and a hue `ColorSlider` (`.Track`, `.Thumb`). Name the trigger, the area and the slider with `aria-label`. `color.toString("hex")` is upper case. React Aria's colour names and labels are Persian (`t.reactAria`). |
| `Disclosure`, `DisclosureGroup`                                       | Expandable sections.                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `Dropdown`, `ListBox`, `Popover`                                      | Menus and lists; `ListBox.Item` takes `id` and `textValue`.                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `Link`                                                                | Text link; navigates in-app through `NasimProvider`'s `navigate`.                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `Meter`, `ProgressBar`                                                | Usage and progress bars.                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `Separator`, `Skeleton`, `Surface`                                    | Layout and loading shapes.                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `Switch`                                                              | An on/off setting that acts at once (auto-renew). In a form use `SwitchField`.                                                                                                                                                                                                                                                                                                                                                                                                       |
| `Tooltip`                                                             | Put the trigger directly inside: `<Tooltip><Button>…</Button><Tooltip.Content>…</Tooltip.Content></Tooltip>`.                                                                                                                                                                                                                                                                                                                                                                        |
| `toast`                                                               | `toast("…")`, `toast.success`, `toast.danger`. An action button does not close its toast: call `toast.close(id)` in `onPress`.                                                                                                                                                                                                                                                                                                                                                       |
| `useMediaQuery`, `useOverlayState`                                    | Hooks. Types `ButtonProps` and `Key` are exported too.                                                                                                                                                                                                                                                                                                                                                                                                                               |

### Not exported yet

HeroUI words some labels itself, in English. Two of those are named in Persian inside a Nasim part, and
HeroUI's own components stay behind it: `Tabs` (its scroll buttons; use Nasim's `Tabs`) and the calendar
(its year button, named from Nasim's strings; use `DateTimeField`), so HeroUI's `Tabs`, `Calendar`,
`DatePicker` and `TimeField` are not exported. These still wait for a Persian wrapper before first use:
`Pagination` (`Pager` is Nasim's paging control), `Autocomplete` and `Tag` (the remove button needs an
`aria-label`). When you add one, check it with the language switched to Persian and with axe.

## Strings

`src/strings/` holds only the words Nasim itself shows: `t.common` (close, cancel, retry, copy and the
like), `t.state` (the error state), `t.stepper`, `t.sortableList`, `t.toast`, and `t.reactAria` (React Aria's dictionary).
A screen's own copy is the app's: it reaches a component as a prop, and the screen reads it from its own
strings module. A theme picker, for one, says «روشن» and «تیره» in the app's words.

Keep Persian copy short, friendly and actionable (what happened, what to do next), and keep
zero-width non-joiners where the script needs them («می‌شود», «پیش‌فرض»).

## Adding a component

1. Read HeroUI's page and demos for it. Wrap it in `primitives/` only to add a Persian default or
   a fix; otherwise re-export it from `primitives/index.ts`.
2. A composite goes in `composites/`, a form field in `forms/`: one idea per file (split it when it
   stops being one, not at a line count), variants with `tv`, copy from `t`.
3. Export it from `index.ts`, document it here, add its strings, and note it in `CHANGELOG.md`.
4. Test it in `__tests__/`: render in light and dark with `renderNasim` and check
   `expectNoViolations`; add keyboard and Persian-label assertions where they apply.
5. `bunx nx run-many -t typecheck test -p @nyxon/nasim` and `bunx prettier --check libs/nasim`. A comment
   is one line of at most 100 characters that says why.
6. A module that holds state, effects, context or an event handler starts with `'use client'`; one that
   only draws from its props does not, so a Server Component can render it (see Setup).
