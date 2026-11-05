# Changelog

Versions follow the contract of the system: a breaking change to a prop, a token name or a
default is a new minor version while we are below 1.0.

## 0.7.0 - 2026-10-27

A new part: a list ordered by dragging, for the admin screens that order a few things (payment gateways,
start-menu buttons).

### Added

- `SortableList`: `items` (`{ id, label, description? }`), `onReorder(ids)`, `label` and `isDisabled`. It is
  controlled and keeps no order. A mouse or touch drags a row; the keyboard and screen readers use the drag
  handle React Aria gives a `GridList` row. Every row also has «بردن به بالا» and «بردن به پایین» buttons, the
  single-pointer alternative to dragging (WCAG 2.2, 2.5.7), with the first row's up and the last row's down
  disabled; focus follows the pressed button and a polite line says where the row went. Followed in React
  Aria Components 1.21.1: `GridList` + `useDragAndDrop` (`getItems`, `acceptedDragTypes`, `onReorder`,
  `renderDropIndicator`, `isDisabled`) and `<Button slot="drag">`, as the skill's dnd guide and
  `GridList.mjs` describe them. The README's `SortableList` section has the details.
- `t.reactAria['@react-aria/dnd']`: React Aria's drag-and-drop words in Persian (the handle's name, the
  instructions, the announcements). Before this, any drag in a Nasim part was announced in English.
  `reactAriaStrings.test.tsx` now lets the key names `Escape` and `Tab` stand in Persian text, as it
  already did `Enter`, `Alt` and `Delete`.

## 0.6.1 - 2026-10-27

Seamless moves onto `@nyxon/nasim`; its checkout needed one part Nasim lacked.

### Added

- `FormFields`: the fields of a form whose submit lives outside it (Telegram's MainButton, a sheet's
  footer). They bind by `name` as in `FormRoot`, with no `<form>` drawn, so Enter submits nothing and a
  small form of its own may sit inside. Since 0.6.0 a named field needs a form around it, and React Hook
  Form's own `FormProvider` no longer counts as one.

## 0.6.0 - 2026-10-23

What two reviews of the move onto Nasim found.

### Changed

- Choosing the `defaultMode` again (a person who flips the theme twice and lands on «follow my device») forgets
  the saved choice: the storage entry is removed and the cookie expires, instead of saving «system» for a
  year. Where the default is not `"system"` (Telegram), «system» is still a choice and is saved.
  `themeCookie.test.tsx` pins the cookie: `Path=/`, `SameSite=Lax`, one year, `Secure` on https, removal.
- Less on every page. React Hook Form is imported by `FormRoot` and its `boundField.tsx` only: a field given
  a `name` reaches the form through a context `FormRoot` provides, so a page whose fields are all controlled no
  longer ships it. A field with a `name` and no `FormRoot` throws a clear error (it used to fail inside React
  Hook Form). The tenant accent maths (`applyAccent`) is loaded with a dynamic import when `accent` is passed
  instead of with the theme provider. `bundle.test.tsx` guards both.

### Fixed

- A `DataTable` card whose `isActions` cells all render nothing (a revoked key has nothing to do) had an empty
  footer: a rule and a gap with no button. It has no footer now.
- `CopyButton` showed nothing when copying failed, and its screen-reader text said «متن انتخاب شد» though it
  selects nothing. A failed copy now puts a danger icon on the button and a line of words under it,
  «کپی نشد؛ مقدار را دستی انتخاب و کپی کنید.», which is also the live region; it stays until the next
  press. `CopyField`, which does select the text, keeps its own hint.
- A field's `description` that appeared after the field did was not tied to its control: React Aria links a
  control to its description when the field mounts, and again only when told that a description exists, so
  the hint of the option just chosen described nothing for a screen reader. `TextField`, `TextAreaField`,
  `NumberField`, `SelectField`, `RadioGroupField`, `CheckboxGroupField` and `DateTimeField` now tell it
  (`lateDescription.test.tsx` covers every field, mounted with the hint and given it later). The README says
  that help for a field is its `description`.
- `DateTimeField`'s year button was named by HeroUI in English («Mehr 1405 AP, year selector»). It now takes its
  name from its visible month and year plus “انتخاب سال” (`t.calendar.selectYear`), so the label is Persian and
  contains the text it shows. The README's «Not exported yet» list is corrected: it called the year picker
  impossible to override and still listed `Tabs`, which Nasim has had for a while.
- One copy of React Aria. `@heroui/react` reads its hooks from `react-aria` and Nasim's `I18nProvider` comes
  from `react-aria-components`; the workspace resolved two copies of `react-aria` (3.53.1 and 3.52.1) and of
  `react-stately`, each with its own locale context, so the date picker's month and year button and its year
  list ignored the provider and drew Latin digits, English months and an «AP» era on an English browser. The
  root `overrides` now pin `react-aria` 3.52.1, `react-stately` 3.50.0 and `react-aria-components` 1.21.1
  (Nasim's own pin), the same way `lucide-react` is pinned; the newest set (3.53.1, 3.51.0, 1.22.1) leaves a
  modal that a finished request closed on screen in the e2e suite. `calendarLocale.test.tsx` opens the
  calendar under `en-US` and fails when the copies drift apart.
- Two README claims that were false are corrected. Composites and form fields were «under about 80 lines» and
  several are not; the rule is one idea per file. «A dark device with the `system` mode paints the first
  frame light» was true of `tokens.css` alone and not of a product that hands over a `palette`, whose
  stylesheet carries a `prefers-color-scheme: dark` rule.

## 0.5.0 - 2026-10-23

PAYNYX's web app moves onto Nasim; what its screens needed and Nasim lacked is generic and lands here.

### Added

- `palette` on `NasimProvider`: a product supplies its whole palette (surfaces, text, the accent and
  four statuses, light and dark, `#rrggbb`) and Nasim renders it as a stylesheet, on the server too, with
  a `prefers-color-scheme: dark` rule so a dark device paints dark from the first byte. `checkPalette`
  measures the same contrast rules as `tokens.css` (text 4.5:1, controls 3:1, the soft pairs, hover shades)
  and names every pair that fails; `paletteCss` and `paletteSchemes` expose the stylesheet and the
  surfaces a tenant `accent` is fitted against (`readableAccents` and `applyAccent` take them).
- The `info` status: `--info`, `--info-foreground`, `--info-soft`, `--info-soft-foreground` and the
  Tailwind colours `bg-info`, `bg-info-soft`, `text-info-soft-foreground`, held to the same contrast rules.
- The theme choice is also saved in the cookie `THEME_COOKIE` (`nasim-theme`). A server layout reads it
  with `parseThemeMode` and passes `initialMode` to `NasimProvider`, so there is no flash on a
  non-default theme. `persist={false}` writes neither.
- `contrastRatio` is exported with the other colour helpers.
- Display parts a dashboard repeats on every screen: `StatusChip` (icon and words on a soft tint, five
  tones), `Notice` (an inline message with a tone, a title and a role), `StatCard`, `SectionCard` (a card
  named by its own heading), the skeletons `SkeletonRows`, `TableSkeleton` and `PageSkeleton`,
  `OfflineBanner` with `useOnline`, `CopyButton` (with the older copy command as a fallback for a WebView)
  and `Collapsible` (a native disclosure). The presentational ones render on the server.
- Every form field also works controlled, with `value`, `onChange` and `errorMessage` instead of `name`
  (a filter bar, a dialog, a flow that keeps its own state), and takes `className` and `data-testid`.
  `TextField` gains `minLength` and `spellCheck`, and its label may be a node.
- `RadioGroupField`, `CheckboxGroupField` and `CheckboxField`; `DateTimeField` (a date and time in the Persian
  calendar, value kept as the Gregorian local string); `HexColorPicker`.
- Structure for a dashboard: `AppShell` (sidebar, phone bar and drawer, `<main>`, safe areas), `DataTable`
  with `Pager` (loading, error, empty and paged states on React Aria's grid), `Modal` (a centred dialog that
  registers as a layer) and `Tabs` (HeroUI's English scroll-button names are set in Persian).
- `PageHeader` takes a node for its description, a `meta` line and `className`, and its actions wrap under the
  title on a narrow screen. `EmptyState` takes a node for its description and an element for its action.
- `ConfirmDialog` takes `isPending` when its caller owns the running action (a mutation), and a node or children
  as its body. `ErrorState` takes children as detail under the message. `LinkButton` adds
  `rel="noopener noreferrer"` to `target="_blank"`. `tokens.css` carries HeroUI's RTL fix for a drawer's
  placement.
- `ThemeToggle`, a round icon button that flips light and dark and hands the choice back to the host
  (`useTheme` gains `automatic` and `automaticScheme` for it).
- `DataTable` takes `cards="sm" | "md"`: below that breakpoint every row is a card (title, labelled values,
  footer actions), driven by the new column fields `isActions` and `hideOnCard`; `useIsNarrow` is the same
  media query as a hook.
- `ColumnChart` and `BarTable`: accessible charts in plain SVG and HTML (no chart library) where every
  exact value is text: a tooltip on each bar, a summary for the picture, a data table behind a disclosure
  (`ColumnChart`), and a table whose rows carry a bar (`BarTable`). Server-renderable.
- `NavTabs`: sibling pages under one menu entry as a tab-looking bar of links (`aria-current` on the page on
  screen), for what `Tabs` is not: a page of its own behind each tab.
- `KeyValueList` takes a node for a label, skips `false`, `null` and `undefined` entries, takes `className`,
  wraps a long value under its label in the `split` layout, and has a `grid` layout (two columns, label above
  value) for the details of one record.
- `StaticTable`, read-only rows in HeroUI's table skin that a Server Component renders (a comparison, a
  list of banks); the scroll region is named and takes focus.
- A controlled field's `errorMessage` may be `null` as well as `undefined`: a lookup that finds no error
  passes straight through.
- `AppShell`'s menu button and the drawer's close button show their name in a tooltip, as the other
  icon-only buttons of a dashboard do.

### Changed

- `SubmitButton` is disabled while it runs, with a decorative spinner, instead of React
  Aria's `isPending`: that announces the button by its own id, and a form that closes or is replaced on
  success left the announcement pointing at a removed element (axe `role-img-alt`).
- Zod's Persian fallback locale is set when `FormRoot` loads, from `zod/v4/locales/fa.js`, instead of in
  `NasimProvider` from the whole `z.locales` namespace: a page without a form no longer ships Zod (about
  15 KB gzip).
- `PageHeader`'s actions may shrink and wrap on a phone, and a `.card` never grows past its column, so a
  long row of buttons or a wide chart no longer widens the page.

## 0.4.0 - 2026-10-23

Nasim leaves the Seamless web app and becomes `@nyxon/nasim`, a workspace package of the NYXON
monorepo (`libs/nasim`) that any dashboard can use. Its first consumer is `apps/paynyx/web`.

### Changed

- The sources moved under `src/`; the package exports `.` (the components), `./tokens.css`, `./fonts.css`
  and `./demo` (`NasimDemo`) as TypeScript and CSS source. An app compiles it with
  `transpilePackages: ['@nyxon/nasim']` and tells Tailwind where to look with `@source`.
- `NasimProvider` no longer takes a TanStack `router`. It takes `navigate(href, options?)` and an optional
  `useHref`, handed to React Aria's `RouterProvider`; `routerOptions` on a `Link` carries
  `{ replace?, scroll? }` (`NasimNavigate`, `NasimNavigateOptions`). An address with a scheme or a
  `//host` still never reaches the router.
- Nasim's own words are in `src/strings/` (`common`, `state`, `stepper`, `toast`, `reactAria`) instead of
  the Seamless app's string tree. The Seamless-only keys (`theme`, `toman`) stay with the app; the demo
  carries its own copy.
- The six icons are inline SVG (Solar, linear set, CC BY 4.0) instead of `~icons/solar/*`, so no bundler
  plugin is needed.
- `fonts.css` only chooses the font: the `@font-face` rules are gone and the app loads the files. Each
  `[data-font]` rule reads `--font-<id>` (what `next/font` exposes) and falls back to the family name.
- React Aria's message functions in `t.reactAria` are typed per message instead of `any`.

### Added

- `'use client'` on every module that holds state, effects, context or an event handler. `KeyValueList`,
  `Stepper`, `Cover`, `LoadingState`, `EmptyState` and the colour helpers can be imported from a Server
  Component. Nothing reads `window`, `document` or `localStorage` during render: the React Aria
  dictionary is installed in the browser only, and the saved theme choice is read after hydration.
- `NumberField` names its steppers and its role from the Persian strings, so a server-rendered page does
  not say «Increase» and «Decrease» in English.

### Fixed

- `Select` and `SelectField` fall back to the Persian placeholder when `placeholder` is passed as
  `undefined` (it used to reach React Aria's English «Select an item» in a server render).

### Removed

- The Seamless build tooling: oxlint, the strings and comments checks, Biome and the React Compiler in the
  tests (a test that only asserted the compiler's output went with it). `bunx nx run-many -t typecheck test
-p @nyxon/nasim` and Prettier replace them.

## 0.3.9 - 2026-10-12

### Added

- `NasimProvider` takes `font`, the reseller's font: `data-font` on `<html>`, with `fonts.css` holding the
  faces of Vazirmatn (the default), Estedad, Mikhak, Sahel, Shabnam, Noto Sans Arabic FD and Parastoo and
  one `[data-font]` rule per font (family and digit feature). `data-font` with `font-sans` on any element
  previews a font.
- `OptionCards` takes `className` (a grid of cards) and a node as a card's `description`.

### Changed

- The Farsi-digits feature is no longer fixed to `ss01` on `html`: it follows the font (`--nasim-font-features`).

## 0.3.8 - 2026-10-12

### Added

- `ColorPicker`, `ColorArea`, `ColorSlider` and `ColorSwatch`, exported from HeroUI for a colour chosen
  by eye (a swatch that opens a popover with a saturation and brightness area and a hue slider), shown in
  the `/__nasim` demo. React Aria's colour labels and colour names are translated in `t.reactAria`.

## 0.3.7 - 2026-10-09

### Changed

- `CopyField` is one pressable field: the label above, the value left to right (cut in the middle with
  an ellipsis, its last characters kept) and a «کپی» mark that turns into «کپی شد». It takes children,
  shown under the field (a QR button, a pager). The value is no longer an input.

## 0.3.6 - 2026-10-08

### Added

- `MessageBar`, a chat's compact composer (attach, a text box that grows to five lines, send; Enter
  sends) that can show a note instead once the conversation is closed.
- `Cover`: a 16:9 picture box whose placeholder (accent-tinted gradient and the kind's icon) stands in
  for a missing or loading picture, so cards with and without a picture have the same shape.

## 0.3.5 - 2026-10-07

### Added

- `BottomSheet` takes `isDismissable` (`false` for a flow that moves money: the backdrop and a drag
  down close nothing; Escape, the close button and the host's Back still do) and `isBusy` (a request is
  running: the same presses are ignored until it ends).

### Fixed

- A quick second tap on a wizard's Continue could land on the backdrop and close the sheet: the next
  step is shorter, so the button had moved. A press on the backdrop is now ignored for half a second
  after the content changes height, and while the sheet opens.

## 0.3.4 - 2026-10-07

### Fixed

- The text of a soft success or warning chip read 4.3:1 on the tint a hovered list row gives it (a
  service's «active» on its card under a pointer) and on the tertiary surface, under the 4.5:1 text
  needs. Both soft texts now mix half and half with the page text in the light theme, and
  `tokens.test.ts` holds every soft text at 4.5:1 on every surface, `--default` and the overlay included.

## 0.3.3 - 2026-10-07

### Fixed

- A placeholder in a search, number or other field Tailwind's preflight styles was half the text
  colour (3.4:1 on white, under the 4.5:1 text needs). Every `input` and `textarea` placeholder now
  takes `--field-placeholder`, which `tokens.test.ts` holds at 4.5:1 on each surface in both themes.

## 0.3.2 - 2026-10-07

### Fixed

- An off `Switch`'s track was HeroUI's pale fill, 1.19:1 on a white surface, so the state could not be
  seen (WCAG 1.4.11). The track is now the field border (3:1 or more on every surface, in both themes),
  and a hovered track mixes towards the text instead of towards transparent, so it never gets paler.

## 0.3.1 - 2026-10-07

### Added

- `ScrollRegion`: content wider than the screen (a price table) scrolls sideways, and only then is it
  a named focus stop a keyboard can scroll.
- The accent maths is public: `readableAccents`, `accentRatios`, `SCHEMES`, `MIN_UI`, `MIN_TEXT`,
  `parseHex`, `toHex` and `oklchToRgb`, so a screen that lets an admin pick the brand colour can show
  what the shop will really use in each theme and how readable it is.

## 0.3.0 - 2026-10-07

### Added

- `SearchBox`, `FilterChips` and `OptionCards`: a list's search field, a one-of-few filter drawn as chips
  and a one-of-few choice drawn as cards (a package with its price, a payment method with its fee).
  The services, transactions, tickets, wallet and renewal screens need all three.
- `Stepper`: the position in a flow of a few steps, as a bar and as words. The renewal and transfer
  sheets use it.
- `TextAreaField`: the multi-line field for notes and messages, with the same RHF + Zod behaviour as
  `TextField`.
- `Switch` is exported for a setting that acts at once. A form still uses `SwitchField`.

### Changed

- `CopyField` takes `multiline` for a value of several lines, such as a WireGuard profile.
- `NumberField` takes `hideSteppers` for an identifier (a Telegram id), where − and + mean nothing.
- `BottomSheet`'s footer takes no room while it has nothing in it: a sheet whose action is Telegram's
  MainButton passes a footer that renders nothing, and used to keep an empty strip at the bottom.

### Fixed

- HeroUI labels the search field's clear button "Close"; `SearchBox` labels it in Persian.

## 0.2.4 - 2026-10-06

### Added

- `EmptyState` and `ErrorState` take `titleRef`: the title becomes focusable and a screen that swaps a
  state in can move focus to it, so a keyboard user is where the news is and a screen reader hears it.
- `ErrorState` takes `retryIn` (seconds): the retry button counts them down before it works, for a
  429's `Retry-After`.

## 0.2.3 - 2026-10-06

### Added

- `usePageHeading`: `PageHeader`'s h1 announces its title while it is on screen, so the host's top
  bar can leave out a name the page already shows.

## 0.2.2 - 2026-10-06

### Added

- `useBottomBar`: a host's bottom bar publishes its height as `--nasim-bottom-bar`, and toasts sit
  above it instead of over it.
- `px-safe`, `px-page` and `p-page` utilities for the safe-area insets. The left and right insets
  are physical; padding them with `ps-*`/`pe-*` put a notch's room on the wrong side of a
  right-to-left page. README rule 4 says so.

### Changed

- `BottomSheet`'s body is a named, focusable section only when its content scrolls. A short sheet
  no longer adds a stop to the keyboard path.

### Fixed

- `PageHeader` draws its back arrow 44px tall on every screen size and centres the title on it: the
  title sat 5px above the arrow's centre.
- The tenant accent is written as an `oklch()` inside sRGB. It used to keep the brand's chroma
  although the colour had been fitted after reducing it, so a browser clipped it and the contrast
  that was measured was not the one shown (text on a pure blue accent in the dark scheme was 4.16:1).
  A browser-level test now measures the painted colours of the edge cases.

## 0.2.1 - 2026-10-06

### Fixed

- A link with a scheme (`https://t.me/...`, `tel:`, `mailto:`) or a protocol-relative address lost
  its address when `NasimProvider` had a router: the bridge turned it into a path of the app
  (`/login/https:/t.me/...`). External addresses now reach the `href` untouched.

## 0.2.0 - 2026-10-06

### Added

- `useOverlayStack` and `useRegisterOverlay`: open dialogs and sheets form a stack that a host can
  close from outside (Telegram's BackButton). `BottomSheet` and `ConfirmDialog` register themselves.
- `NasimProvider nativeBack` and `useNativeBack`: `PageHeader` omits its back arrow when the host
  has a back button.
- `persist` on `NasimProvider`/`ThemeProvider`: `false` neither reads nor writes the saved theme, so
  Telegram's scheme is never overridden by the website's saved choice on the same origin.
- `--nasim-chrome-top` and `--nasim-chrome-bottom`: the colours a host app paints around the page.
- `readableAccents`, `--nasim-accent-light/-dark` and their `-foreground` partners.
- `EmptyState` and `ErrorState` take `as="h1"` for when they are the whole page.
- `initialScheme` on `NasimProvider`/`ThemeProvider`: the external scheme known at the first render,
  so a host that reads Telegram's launch theme synchronously never renders in the device's scheme.

### Changed

- The tenant accent is fitted to each colour scheme separately (accent 3:1 against the page and
  surfaces, text on it 4.5:1, soft text 4.5:1 on the soft tint and the secondary button fill); the
  default accent has its own dark value. The README separates text tokens from fills.
- `SubmitButton` reads the submitting state from a context that `FormRoot` publishes through
  `useFormState`, so it works when the React Compiler memoises the form element.
- Left-to-right values align the same way everywhere: start edge in fields and stacked
  `KeyValueList` rows, end edge in two-column rows.
- `BottomSheet`'s scrolling body is a named section that takes focus; toasts keep clear of the safe
  areas; `ErrorState` announces only its title and message; `KeyValueList` rows take an optional `id`.

- `applyAccent`'s undo puts back the colours that were there before instead of removing them.
- The `/__nasim` gallery runs under the app's own provider, so there is one theme controller and one
  toast region; its colour buttons only preview other brand colours on top.

### Fixed

- `LoadingState` kept a `<p>` inside `<output>`; `KeyValueList` collided on repeated labels.

### Removed

- `--nasim-duration-fast` and `--nasim-duration-base` (nothing used them).

## 0.1.0 - 2026-10-06

First release of «نسیم», built on HeroUI 3.2.6.

### Added

- `NasimProvider`: Persian locale and React Aria strings, in-app link navigation through the
  TanStack router, the theme controller, the tenant accent and the toast region.
- Theme controller with modes `system`, `light`, `dark` and `telegram`. `setScheme` lets the Mini App
  shell feed Telegram's colour scheme without this folder importing Telegram. The choice is
  remembered in `localStorage` and applied as `class` and `data-theme` on `<html>`.
- Tenant accent: a brand colour is nudged until text on it (and on its hover shade) passes WCAG AA.
- Tokens: light and dark palettes, bordered fields in both themes, invalid-field borders,
  Persian line heights, `--nasim-safe-*` safe-area tokens that combine the device insets with
  Telegram's, and a 44px touch target token.
- Composites: `PageHeader`, `SubmitButton`, `LoadingState`, `EmptyState`, `ErrorState`,
  `ConfirmDialog`, `KeyValueList`, `CopyField`, `BottomSheet`.
- Forms for React Hook Form and Zod: `FormRoot`, `TextField`, `NumberField`, `SelectField`,
  `SwitchField`.
- Primitives: Persian-labelled `Spinner`, `CloseButton` and `Select`, the router-aware
  `LinkButton`, and re-exports of the HeroUI components the app needs.
- Persian strings in `src/strings/fa.ts` and `bun run check:strings` (Latin JSX text, literal
  accessibility attributes and unused keys; existing screens are listed in a baseline that may
  only shrink).
- Tests: every composite in light and dark with axe, keyboard use of `ConfirmDialog` and
  `BottomSheet`, double-submit protection, Persian labels, token contrast and accent contrast.
- Demo route `/__nasim` (development only).

### Known gaps

- `Tabs`, the calendar year picker, `Pagination`, `Autocomplete` and `Tag` are not exported: they
  contain English labels that cannot be overridden from outside.
