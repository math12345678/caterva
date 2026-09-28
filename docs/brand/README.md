# Brand

The mark is a C of eight dots: seven ink, one signal. *Caterva* is Latin
for a crowd, a band gathered together; the one dot in a different colour is
the reading that matters. Everything else follows from that ratio.

## Files

| file | use |
|---|---|
| [`../../Logo.png`](../../Logo.png) | mark and wordmark, ink on transparent (README, documents) |
| [`Logo-dark.png`](Logo-dark.png) | the same for dark backgrounds |
| [`caterva-mark.svg`](caterva-mark.svg) | the mark alone, vector, any size |
| [`caterva-mark-on-ink.svg`](caterva-mark-on-ink.svg) | the mark for ink or dark grounds |
| [`favicon.svg`](favicon.svg) | the mark on a paper tile, for browser tabs |
| [`social-preview.png`](social-preview.png) | 1280 x 640, for GitHub's social preview and link cards |

The site's copies (favicon, touch and PWA icons, social image) live in
`Science-Agent-Pipeline/artifacts/caterva-landing/public/`. The mark's
geometry was measured from the master artwork to a tenth of a pixel and is
also in `src/components/brand/Mark.tsx`; redraw nothing by eye.

## Colour

| role | hex | on ink |
|---|---|---|
| paper, the ground | `#FDF8EE` | text `#FDF8EE` |
| ink, text and solid shapes | `#2A2D35` | ground `#2A2D35` |
| signal, the one thing that matters in a view (verified, cited, live) | `#5D7F8D` | `#9DB8C4` |
| caution, read twice (a default, a flag, money) | `#946522` | `#D9AD6A` |
| failure | `#A63D35` | `#E08A80` |
| quiet ink, secondary marks | `#6A6E78` | `#A9ACB3` |

Signal is used sparingly, the way the mark uses it: one dot in eight. Text
is never lighter than about 66% ink on paper (4.5:1).

## Type

- **Spectral** (Light 300 and Regular 400) for the wordmark and headings.
  The wordmark is lowercase, tracked about 0.3 em.
- **Atkinson Hyperlegible Next** for body text.
- **DM Mono** for commands and output.

All three are SIL Open Font License, served from Google Fonts.

## Use

- Terminal windows and code are ink slabs on paper: the page's one solid
  shape, as the dots are. No glows, blurs or gradients.
- Keep clear space around the mark of at least one large dot's diameter.
- Do not recolour the signal dot, rotate the C, or set the wordmark in
  capitals.
