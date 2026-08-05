# Configuration

[← back to the README](../README.md)

A job is a TOML file. `printsplit --new` writes one for you; this is what it
looks like filled in:

```toml
extends = "../../config/default.toml"

[project]
name = "Bridge deck"
input = "projects/bridge/deck.pdf"
output_dir = "projects/bridge/out"
output_basename = "deck_A0_1to1"

[scale]
source_scale = 50.0   # the drawing is 1:50
target_scale = 1.0    # print it full size

[sheet]
size = "A0"           # A0..A5, 2A0, 4A0, B0..B2, Letter, Legal, ARCH_D/E, custom
margin_mm = 10.0      # your plotter's dead border

[tiling]
overlap_mm = 30.0
```

## The settings you actually touch

| setting | why |
|---|---|
| `scale.target_scale` | print at 1:2 or 1:5 instead of full size — the fastest way to cut the sheet count |
| `lines.mode` | how thick the drawing's strokes come out — see [Line widths](line-widths.md) |
| `source.bbox_mode` | `auto` finds the artwork; `manual` + `manual_bbox_mm` crops to one detail of a busy sheet |
| `source.padding_mm` | clear paper around the drawing, in printed mm |
| `sheet.margin_mm` | a number, `[vertical, horizontal]` or `[top, right, bottom, left]` |
| `tiling.overlap_mm` | wider = easier to align, more sheets |
| `tiling.skip_blank_tiles` | drop sheets with nothing on them — but see the warning below |
| `marks.*` | every mark can be turned off, recoloured, resized or repositioned |

[`config/default.toml`](../config/default.toml) lists **every** setting with a
comment explaining it. Anything you do not mention keeps its default from there.

## Inheritance

A config may `extends` another, chained as deep as you like:

```
deck.toml  ->  bridge_common.toml  ->  config/default.toml
```

So a set of drawings for the same job can share one base and cannot drift apart
in scale, overlap or line weight — which matters when the sheets have to lie
against each other on the same floor.

Unknown keys are rejected with the list of valid ones, so a typo cannot silently
ruin a print. Paths in `extends` are relative to the file that names them.

## A warning about blank sheets

`tiling.skip_blank_tiles = true` drops sheets with no artwork on them. That
saves paper, but an empty sheet in the *middle* of a drawing is the physical
spacer holding the two halves the correct distance apart. Skip it and you have
to measure that gap yourself. The default is `false` for that reason.

## Paper sizes

`A0`–`A5`, `2A0`, `4A0`, `B0`–`B2`, `LETTER`, `LEGAL`, `ARCH_D`, `ARCH_E`, or
`custom` with `custom_size_mm = [width, height]`. `orientation` may be
`portrait`, `landscape`, or `auto` — which picks whichever needs fewer sheets,
breaking ties toward the shape that matches the drawing.

Note that smaller paper means *more* sheets, not smaller ones: a 2.7 × 1.6 m
print is 6 × A0 but 12 × A1.
