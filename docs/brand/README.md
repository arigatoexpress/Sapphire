# Kadima brand assets

Primary mark: **B (Quadrilemniscate)** — two interlocking infinity curves rotated 90° from each other, forming a four-lobed rosette with four-fold rotational symmetry. Reads as both ∞ and fractal.

## Files

| File | Purpose |
|------|---------|
| `kadima-mark-a-recursive.svg` | Lemniscate with a smaller lemniscate nested at its crossover (rotated 90°). More literally reads as ∞. |
| `kadima-mark-b-quadrilemniscate.svg` | **Primary.** Two interlocking lemniscates, four-lobed rosette. |
| `kadima-mark-c-fractal-3level.svg` | Three-level recursive lemniscate — most explicit fractal, least legible at tiny sizes. |
| `*-64.png` | 64×64 favicon / app-icon rendering |
| `*-300.png` | 300×300 LinkedIn company-page logo size |
| `*-800.png` | 800×800 high-res header / marketing |
| `gemini-logo-prompts.md` | Three prompt variants for Gemini/Imagen if exploring alternates |

## Color

| Token | Hex | Use |
|-------|-----|-----|
| Sapphire (default) | `#0A2540` | Primary mark stroke |
| Ink | `#000000` | Fallback when single-color print is required |
| White | `#FFFFFF` | Knockout variant on dark backgrounds |

To re-color: open the `.svg`, change every `stroke="#0A2540"` to your new hex, re-run `cairosvg` to regenerate PNGs.

## Typography (recommendation)

- **Wordmark:** Inter, Medium weight, −2% letter-spacing for headline
- **Body:** Inter, Regular

Inter is free, open source, and mirrors the geometric precision of the mark. Pairs well with monospace (JetBrains Mono, IBM Plex Mono) for technical content.

## Sizing rules

- Favicon / app icon: use `*-64.png` (keep stroke simple — mark A or B scale best)
- LinkedIn company page / social avatar: `*-300.png`
- Header image: `*-800.png` or render to 2048×2048 for retina
- Print / pitch deck: use the SVG directly

## Re-rendering

```bash
python3 -m pip install cairosvg --user
cd docs/brand
for svg in *.svg; do
    name="${svg%.svg}"
    for size in 64 300 800; do
        python3 -c "import cairosvg; cairosvg.svg2png(url='$svg', write_to='$name-$size.png', output_width=$size, output_height=$size)"
    done
done
```
