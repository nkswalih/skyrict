# Skyrict Design System

**Version:** 1.0 · **Theme:** Sky (current) · **Last updated:** 2026-10-22

Skyrict is an AI Business Operating System. The interface has to make dense
operational data feel calm, current, and trustworthy — and it has to make the
next action obvious. This document is the canonical reference for colour,
type, spacing, components, motion, and theming across the marketing site,
workspace, ERP, agents, and intelligence surfaces.

- **Source of truth:** [`apps/web/src/styles/globals.css`](../../apps/web/src/styles/globals.css)
- **Living reference:** run `pnpm --filter @skyrict/web dev` and open
  [`/design-system`](http://localhost:3000/design-system) (development only).
- **Stack:** Next.js App Router, React 19, Tailwind CSS v4, shadcn primitives,
  Radix UI, `class-variance-authority`, lucide icons.

> If this document and `globals.css` disagree, the CSS wins. Update both in the
> same pull request.

---

## 1. Principles

1. **Signals over noise.** One primary action per surface. Decoration must earn
   its place by clarifying state or hierarchy.
2. **Calm density.** Enterprise tables are unavoidable; neutrals, generous line
   height, and a single accent keep them readable. Use borders and spacing
   before shadows and colour.
3. **Sky is the signature.** The brand accent is a light, optimistic sky blue.
   It marks what is interactive or newly important — never large body areas.
4. **Every module is the same product.** Module "worlds" change hue, never
   structure, spacing, or typography. Users should feel a change of context,
   not a change of application.
5. **Accessible by default.** Keyboard focus, contrast, reduced motion, and
   text labels are part of the component, not an afterthought.
6. **Tokens, not hex.** Product code consumes semantic tokens. Raw values are
   allowed only inside `globals.css` and brand assets.

---

## 2. Brand

> The full brand strategy, voice, messaging, logo rules, and application
> guidance live in [`docs/brand/README.md`](../brand/README.md). This section
> covers only what component and token work needs.

| Attribute   | Guidance                                                                                                     |
| ----------- | ------------------------------------------------------------------------------------------------------------ |
| Name        | **Skyrict** — always capitalised, one word.                                                                  |
| Tagline     | **AI Business Operating System**                                                                             |
| Personality | Clear, composed, forward-looking, commercially literate.                                                     |
| Voice       | Short sentences. Active verbs. Numbers with units and periods. No hype.                                      |
| Signature   | Sky-blue accent, crisp 1px borders, restrained radii, mono overlines.                                        |
| Logo mark   | Rounded 32×32 gradient tile with an ascending bar chart, a 2×2 ERP grid, or an AI orbit, depending on world. |

Logo tones (`apps/web/src/components/brand/logo.tsx`):

| Tone  | Gradient            | Use                           |
| ----- | ------------------- | ----------------------------- |
| `sky` | `#aedef1 → #4cb6e1` | Workspace, marketing, default |
| `erp` | `#6ee7b7 → #34d399` | ERP shell and ERP navigation  |
| `ai`  | `#c7d2fe → #6366f1` | Agents and AI surfaces        |

Wordmark uses **Bricolage Grotesque**, semibold, `tracking-tight`, `text-lg`.
Never re-colour the wordmark independently of the mark.

---

## 3. Colour

### 3.1 Core tokens

All product UI uses semantic tokens. Values below are the current **Sky** theme.

| Token                    | Light     | Dark      | Use                                |
| ------------------------ | --------- | --------- | ---------------------------------- |
| `--background`           | `#f4fafd` | `#0b1119` | App canvas                         |
| `--foreground`           | `#0a2f3e` | `#e6edf5` | Primary text                       |
| `--card`                 | `#ffffff` | `#111a24` | Cards, panels, sticky chrome       |
| `--card-foreground`      | `#0a2f3e` | `#e6edf5` | Text on cards                      |
| `--popover`              | `#ffffff` | `#15202c` | Menus, dialogs, portalled surfaces |
| `--popover-foreground`   | `#0a2f3e` | `#e6edf5` | Text on popovers                   |
| `--primary`              | `#87ceeb` | `#6ec2e8` | Brand accent, primary action       |
| `--primary-foreground`   | `#061f29` | `#06121c` | Text/icons on primary              |
| `--secondary`            | `#e6f5fa` | `#1a2836` | Secondary action, quiet fill       |
| `--secondary-foreground` | `#0d3f53` | `#d9e8f2` | Text on secondary                  |
| `--muted`                | `#edf7fc` | `#151f2b` | Subtle fills, hover, skeletons     |
| `--muted-foreground`     | `#176a8b` | `#8fa3b8` | Secondary text, icons, hints       |
| `--accent`               | `#e6f5fa` | `#182636` | Hover/selected surfaces            |
| `--accent-foreground`    | `#0d3f53` | `#d9e8f2` | Text on accent                     |
| `--destructive`          | `#dc2626` | `#f87171` | Errors, destructive actions        |
| `--success`              | `#047857` | `#34d399` | Completed, healthy, positive delta |
| `--warning`              | `#b45309` | `#fbbf24` | Attention, degraded, pending       |
| `--info`                 | `#0369a1` | `#38bdf8` | Neutral notices, tips              |
| `--border`               | `#cae9f6` | `#1f2c3d` | Default 1px borders                |
| `--input`                | `#cae9f6` | `#223043` | Input/select/textarea borders      |
| `--ring`                 | `#87ceeb` | `#4db8e8` | Focus ring                         |

**Semantic foregrounds** for solid status fills: `--success-foreground`,
`--warning-foreground`, `--info-foreground` (white in light, deep tint in dark).

#### Status usage

Use the soft pattern for inline state, and the solid pattern only for
high-emphasis confirmation:

```tsx
// Soft (default) — status text stays readable in both themes
<span className="rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
  Paid
</span>

// Solid (rare) — single decisive badge or toast
<span className="bg-success text-success-foreground">Approved</span>
```

> **Note:** `--destructive` was corrected from near-black `#020a0d` to
> `#dc2626` so light-mode error panels are recognisably red. Status tokens were
> added in v1.0; older hard-coded `emerald`/`amber`/`rose` utilities should
> migrate to `success`/`warning`/`destructive` as files are touched.

#### Chart tokens

| Token       | Light     | Dark      | Use                            |
| ----------- | --------- | --------- | ------------------------------ |
| `--chart-1` | `#87ceeb` | `#6ec2e8` | Primary series                 |
| `--chart-2` | `#4cb6e1` | `#4cb6e1` | Secondary series               |
| `--chart-3` | `#2199ca` | `#38bdf8` | Tertiary series                |
| `--chart-4` | `#114f68` | `#8fa3b8` | Reference/benchmark            |
| `--chart-5` | `#aedef1` | `#255a7a` | Fills, forecasts, muted series |

Charts must never rely on colour alone: pair series with labels, patterns, or
direct annotations. Order series 1→5; do not invent ad-hoc colours.

### 3.2 Surface ladder

Light mode: `background (#f4fafd) → muted (#edf7fc) → card (#ffffff) →
popover (#ffffff)`. Dark mode: `background (#0b1119) → card (#111a24) →
popover (#15202c)`. Elevation is communicated by **border + one step of
surface**, not by heavy shadows.

### 3.3 Module worlds

Each module re-tints the token set via a class on its shell. The base Sky
tokens remain the default for marketing, docs, auth, onboarding, and the
workspace home.

| World        | Class                 | Light primary | Dark primary | Applied in                 |
| ------------ | --------------------- | ------------- | ------------ | -------------------------- |
| Sky (base)   | —                     | `#87ceeb`     | `#6ec2e8`    | Marketing, workspace, auth |
| Agents       | `.theme-agents`       | `#a5b4fc`     | `#8b93f8`    | Agents shell               |
| ERP          | `.theme-erp`          | `#86efac`     | `#55cf96`    | ERP shell                  |
| Intelligence | `.theme-intelligence` | `#38bdf8`     | `#55c2ee`    | Intelligence surfaces      |

Module worlds are **dark-mode aware**: each has a matching `.dark .theme-*`
block. When adding a world, define the full token set (surfaces, text, borders,
charts, sidebar) in both modes — do not override only `--primary`.

**Portals:** Radix portals escape the themed wrapper. Always mount floating
surfaces inside the active theme scope using
`getThemeContainer()` (`src/lib/theme-world.ts`) or
`useThemeScopeContainer()` (`src/lib/theme-scope.ts`). Shells set
`data-theme-world` / `data-theme-scope` for this purpose.

---

## 4. Typography

| Role                           | Family                  | Token            | Typical style                         |
| ------------------------------ | ----------------------- | ---------------- | ------------------------------------- |
| Body / UI                      | **Inter**               | `--font-sans`    | 14–16px, 400–500, 1.5 line height     |
| Display / headings             | **Bricolage Grotesque** | `--font-display` | 600, `tracking-tight`, 1.15–1.25      |
| Code / overlines / data labels | **JetBrains Mono**      | `--font-mono`    | 10–12px, 500, uppercase for overlines |

### Type scale

| Level      | Size / line height         | Weight                                        | Usage                           |
| ---------- | -------------------------- | --------------------------------------------- | ------------------------------- |
| Display XL | 36px / 1.15 → 48px at `sm` | 600                                           | Marketing hero `h1`             |
| Display L  | 30px / 1.2 → 36px at `sm`  | 600                                           | Section `h2`                    |
| Display M  | 24px / 1.3                 | 600                                           | Page titles, dialog titles      |
| Heading    | 18px / 1.4                 | 600                                           | Card and panel titles           |
| Body L     | 16–18px / 1.6              | 400                                           | Marketing lead paragraphs       |
| Body       | 15px / 1.75                | 400                                           | Docs and long-form reading      |
| UI         | 14px / 1.4                 | 400–500                                       | Controls, tables, default text  |
| Small      | 12px / 1.4                 | 400–500                                       | Helper text, metadata           |
| Overline   | 11–12px / 1.4              | 500, mono, `tracking-[0.15–0.2em]`, uppercase | Section eyebrows, table headers |

Rules:

- Use `font-display` for headings only; never for body copy or controls.
- Use `tabular-nums` for financial figures, metrics, and aligned table numbers.
- Do not go below 12px for interactive text; 10–11px mono is reserved for
  decorative data labels.
- Headings use `text-foreground`; supporting copy uses `text-muted-foreground`.
- Avoid all-caps sans text. All-caps belongs to mono overlines.

---

## 5. Space, layout, radius

### Spacing

The scale is Tailwind's 4px base. Use these steps; avoid arbitrary values.

| Token   | px    | Typical use                       |
| ------- | ----- | --------------------------------- |
| `1`     | 4     | Icon/text gap, tight chips        |
| `2`     | 8     | Control inner gap                 |
| `3`     | 12    | Button padding, form rows         |
| `4`     | 16    | Card padding (compact), stack gap |
| `6`     | 24    | Card padding, page gutter         |
| `8`     | 32    | Section inner spacing             |
| `12`    | 48    | Block separation                  |
| `16`    | 64    | Marketing section padding         |
| `20–24` | 80–96 | Hero / major section rhythm       |

### Layout

- Content max width: `max-w-6xl` (1152px) for marketing, docs, and dashboards.
- Marketing gutters: `px-6`; vertical section rhythm `py-16`–`py-24`.
- Dashboard gutters: `px-4 py-6` mobile, `lg:px-6 lg:py-8`.
- Reading width: `max-w-2xl` for hero copy, `max-w-xl` for lead paragraphs.
- Sidebar + topbar shell uses `h-dvh` with the main column as the only scroll
  container (`overflow-y-auto`). Never introduce a second nested page scroll.
- Prefer CSS grid for dashboards and `flex` for toolbars. Tables scroll
  horizontally inside their own `overflow-x-auto` wrapper.

### Radius

Base radius is `--radius: 0.625rem` (10px). Derived scale:

| Utility       | Computed | Use                               |
| ------------- | -------- | --------------------------------- |
| `rounded-sm`  | 6px      | Tiny chips, inner markers         |
| `rounded-md`  | 8px      | Compact controls, nav items       |
| `rounded-lg`  | 10px     | Buttons, inputs, default surfaces |
| `rounded-xl`  | 14px     | Cards, panels, dialogs            |
| `rounded-2xl` | 18px     | Feature tiles, hero panels        |
| `rounded-4xl` | 26px     | Badges and pills                  |

### Elevation

| Level                   | Treatment                                                                      |
| ----------------------- | ------------------------------------------------------------------------------ |
| 0 — canvas              | `bg-background`, no border                                                     |
| 1 — surface             | `bg-card border border-border`, no shadow                                      |
| 2 — floating            | `bg-popover border border-border shadow-lg`                                    |
| 3 — hero/product visual | Single long soft shadow, e.g. `shadow-[0_24px_60px_-24px_rgba(10,47,62,0.35)]` |

Do not stack multiple shadows. Do not use shadow as a substitute for a border in
dense tables.

---

## 6. Iconography & logo

- **Library:** lucide-react. Do not mix icon families.
- **Sizes:** 16px default (`size-4`), 14px in compact controls (`size-3.5`),
  12px inline (`size-3`), 20px in empty states.
- **Stroke:** library default (2). Do not override per-icon unless optically
  correcting a custom glyph.
- **Colour:** icons inherit `currentColor`; muted icons use
  `text-muted-foreground`.
- **Meaning:** pair unfamiliar icons with a text label or `aria-label`. Purely
  decorative icons are `aria-hidden="true"`.
- **Custom brand glyphs** (`LogoMark`, `AiGlyph`) come from
  `src/components/brand/logo.tsx`; do not redraw them inline.

---

## 7. Components

Primitives live in `apps/web/src/components/ui`. Product code should compose
these rather than restyling raw HTML.

### Button

| Property | Values                                                                      |
| -------- | --------------------------------------------------------------------------- |
| Variants | `default` (primary), `outline`, `secondary`, `ghost`, `destructive`, `link` |
| Sizes    | `xs` 24px, `sm` 28px, `default` 32px, `lg` 36px, `icon*` square             |
| Radius   | `rounded-lg` (compact sizes use ~8px)                                       |
| Text     | 14px medium (`sm` 12.8px, `xs` 12px)                                        |
| Focus    | 3px `ring-ring/50` + `border-ring`                                          |
| Disabled | `opacity-50`, pointer-events off                                            |
| Press    | 1px translate on non-popup buttons                                          |

- One `default` button per view. Secondary actions use `outline`/`ghost`.
- Destructive variant is tinted, not solid red, to keep error surfaces calm.
- Icons: 16px, gap `1.5`; use `data-icon="inline-start|inline-end"` so padding
  adapts.
- Do not put a button inside a link. Use `asChild` for navigation CTAs.

### Badge

- Height 20px, pill radius, 12px medium text, optional 12px icon.
- Variants mirror buttons. Use `outline` for neutral metadata, `secondary` for
  categories, status colours for state.
- Never use a badge as the only indicator of destructive/irreversible state.

### Input, Select, Textarea

- Height 32px (`sm` select 28px), radius 10px, 1px `--input` border.
- 14px text on desktop, 16px on mobile to prevent iOS zoom.
- Placeholder `text-muted-foreground`; helper text 12px.
- Focus: `border-ring` + 3px `ring-ring/50`.
- Error: `aria-invalid` + `border-destructive` + destructive ring. Always pair
  with a text message — never colour alone.
- Labels are always visible. Placeholders are examples, not labels.

### ErrorPanel

- Use for failed loads. `role="alert"`, 1px `destructive/30` border,
  `destructive/5` fill, 14px title + message.
- `onRetry` is allowed **only** for idempotent reads. Mutation failures use a
  message-only toast; never offer retry on a POST.

### Feedback & loading

- **Spinner:** shared `Spinner` component (8 segments, 0.7s). Never hand-roll
  `Loader2 + animate-spin`. Do not pass `animate-spin` yourself.
- **Skeleton:** `.skeleton` shimmer, 1.6s, 9% foreground sheen; respects
  reduced motion. Use block skeletons that match final dimensions to avoid
  layout shift.
- **Toasts:** sonner, bottom-right, one line, action optional. Do not toast
  success for every keystroke or background refresh.

### Dialogs, menus, tooltips

- Built on Radix; mount inside the theme scope (see §3.3).
- Dialog: `bg-popover`, 1px border, `rounded-xl`, `shadow-lg`, 24px padding.
- Menus: 14px items, 8px radius, `bg-popover`, `shadow-lg`.
- Tooltips: short noun phrases only; never put required information there.

### Data display

- Tables: sticky header optional, `text-sm`, row borders `border-border/60`,
  numeric columns right-aligned with `tabular-nums`, hover `bg-muted/40`.
- Empty states: one sentence of context + one primary action.
- Charts: use chart tokens, direct labels, and a text summary for screen
  readers.

---

## 8. Motion

Motion should explain a change, not perform. Durations:

| Token    | Value    | Use                                  |
| -------- | -------- | ------------------------------------ |
| Fast     | 150ms    | Hover, press, small toggles          |
| Base     | 200ms    | Colour/background transitions        |
| Enter    | 380ms    | Popovers, pop-in, reveal             |
| Standard | 700ms    | Staged hero/product choreography     |
| Ambient  | 1.6–2.8s | Shimmer, scan, pulse, thinking sheen |

Easing: `cubic-bezier(0.22, 1, 0.36, 1)` for entrances; `ease`/`ease-in-out`
for colour and ambient loops. Available named utilities in `globals.css`:
`.sky-anim`, `.sky-enter-fade`, `.sky-pop-in`, `.sky-recommendation`,
`.sky-highlight`, `.sky-blink`, `.skeleton`, `.chat-thinking`,
`.chart-scan/.chart-draw/.chart-pulse`.

Rules:

- Every animation must be disabled or reduced under
  `@media (prefers-reduced-motion: reduce)`.
- Never animate layout properties (`width`, `height`, `top`, `left`) when
  `transform`/`opacity` will do.
- No infinite motion in dense data views except a single loading indicator.
- Do not animate focus rings or delay interactive feedback.

---

## 9. Accessibility

- **Target:** WCAG 2.2 AA. Body text ≥ 4.5:1; large text ≥ 3:1; UI borders and
  focus indicators ≥ 3:1.
- **Focus:** every interactive element uses `focus-visible` with a visible
  ring. Never `outline: none` without a replacement.
- **Keyboard:** dialogs trap focus; menus and tabs follow Radix patterns;
  Escape closes floating surfaces.
- **Labels:** icon-only controls need `aria-label`; decorative icons need
  `aria-hidden="true"`.
- **State:** pair colour with text or icon. Status badges include words.
- **Errors:** `role="alert"` on load failures; field errors use
  `aria-invalid` + `aria-describedby`.
- **Targets:** aim for 44×44px on touch surfaces; compact 24–32px controls are
  desktop-only.
- **Motion:** honour `prefers-reduced-motion`; avoid autoplay video.
- **Zoom:** layouts must survive 200% zoom and 320px width without horizontal
  page scroll.

---

## 10. Content guidelines

- Sentence case for headings, buttons, labels, and menu items.
- Buttons are verbs: “Create invoice”, “Invite member”, “Retry”.
- Numbers: thousands separators, currency symbols, units (`12 days`,
  `₹4,20,000`, `98.4%`). Use tabular figures in tables.
- Dates: locale-aware; relative dates only when the exact date is available on
  hover/focus.
- Empty: explain the value, not the absence. “No invoices yet — create your
  first one to start tracking cash.”
- Errors: say what happened, what was preserved, and the next safe action. No
  stack traces, no blame.
- Avoid “AI magic”, “revolutionary”, and exclamation marks.

---

## 11. Contribution checklist

Before shipping a UI change:

- [ ] Colours come from tokens (`bg-primary`, `text-muted-foreground`,
      `border-border`), not raw hex or `hsl(var(--…))`.
- [ ] Status uses `success` / `warning` / `info` / `destructive`, paired with
      text.
- [ ] Light and dark mode both checked — including portals and module worlds.
- [ ] Keyboard-only pass: Tab, Shift+Tab, Enter/Space, Escape.
- [ ] Focus ring visible on every control.
- [ ] Text meets AA against its actual surface.
- [ ] Motion respects `prefers-reduced-motion`.
- [ ] No second page-level scroll container; tables own their overflow.
- [ ] Numbers use `tabular-nums`; destructive actions are confirmed.
- [ ] New primitives are added to `components/ui` and documented here.
- [ ] `globals.css` and this document are updated together.

---

## 12. Known gaps & roadmap

| Gap                                                                              | Next step                                                                        |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Status colours still hard-coded in several features (`emerald`, `amber`, `rose`) | Migrate per-file to `success`/`warning`/`destructive` tokens.                    |
| Raw brand hex (`#87ceeb`) in some auth and marketing CTAs                        | Migrate to `bg-primary text-primary-foreground`.                                 |
| Motion values are not tokenised                                                  | Add `--duration-*` / `--ease-*` variables and refactor named animations.         |
| No shared `Card` primitive                                                       | Several surfaces compose `div` + border; extract when the third duplicate lands. |
| No component test/story harness                                                  | Add a Playwright screenshot pass for `/design-system` once stable.               |
| Module worlds duplicate the full token set                                       | Consider generating world blocks from a single palette source.                   |

---

## 13. Changelog

| Date       | Change                                                                                                                                                                                                                                                                                         |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-10-22 | v1.0 — codified Sky theme tokens, type/space/radius scales, component specs, module worlds, motion, accessibility, and contribution checklist. Corrected light-mode `--destructive` to `#dc2626`; added `success`/`warning`/`info` tokens; fixed invalid `hsl(var(--…))` chat-markdown styles. |
