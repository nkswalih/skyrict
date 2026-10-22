# Skyrict brand assets

Exported, production-ready marks. The rules that govern their use live in
[`docs/brand/README.md`](../README.md). The digital logo is rendered from
[`apps/web/src/components/brand/logo.tsx`](../../../apps/web/src/components/brand/logo.tsx);
these files are for print, vendors, social profiles, and surfaces that cannot
use React.

| File                       | Colour                           | Use                                              |
| -------------------------- | -------------------------------- | ------------------------------------------------ |
| `skyrict-mark-mono.svg`    | Deep tile, transparent knockout  | One-colour print on Paper or light stock         |
| `skyrict-mark-reverse.svg` | Paper tile, transparent knockout | One-colour print on Deep or dark stock           |
| `skyrict-mark-glyph.svg`   | Deep bars and dot, no tile       | Inline marks, stamps, small spots without a tile |
| `skyrict-avatar-paper.svg` | Sky gradient mark on Paper       | Social avatars and 1:1 profile images            |

The primary digital mark remains
[`docs/assets/skyrict_logo.svg`](../../assets/skyrict_logo.svg).

## Rules

- Corporate signature is always the **Sky** tone. The ERP and AI tones are
  product wayfinding, not brand marks.
- Keep half the mark height clear on every side.
- Do not recolour, rotate, stretch, outline, or add effects.
- Do not add a tagline, URL, or trademark symbol inside the mark.
- For horizontal or stacked lockups, render the `Logo` component so the
  wordmark uses Bricolage Grotesque. If a vendor needs a static file, outline
  the wordmark before export and keep the editable source with the export.

## Naming

```
skyrict-[asset]-[variant]-[colour].[ext]
```

Lowercase, hyphens, no spaces.
