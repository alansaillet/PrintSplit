# Line widths

[← back to the README](../README.md)

Magnification magnifies line weights too. At ×50 an ordinary 0.6 pt CAD line
prints **30 mm wide** — not just ugly, but imprecise: a 30 mm line is a 30 mm
wide answer to "where exactly does this edge go?".

```toml
[lines]
mode = "fixed"      # keep | fixed | scale
width_mm = 0.5
```

| `mode` | effect |
|---|---|
| `keep` | leave the weights alone; they scale with the drawing (the default) |
| `fixed` | every stroke prints `width_mm` wide |
| `scale` | keep the drawing's *relative* weights, multiplied by `scale` |

`min_width_mm` / `max_width_mm` clamp the result in any mode — `keep` plus
`max_width_mm = 1.0` keeps the drawing's line hierarchy but caps the fat ones.
All values are in **printed** millimetres: what a ruler on the paper reads.

## Two things worth knowing

**Nothing moves.** A stroke's centreline is unaffected by its width, so
re-weighting changes ink only — every position stays exactly where it was. (The
*bounding box* shifts by half a stroke width, since it is stroke-aware, which
nudges the assembled coordinate origin by a fraction of a millimetre.)

**Round-capped dots shrink.** Some CAD exports draw bolt holes as a zero-length
stroke with a round cap, where the *line width is the hole diameter*. Thinning
the lines turns those into markers: their centres stay exact, which is what you
mark from, but the hole size is no longer to scale. Use `mode = "keep"` if you
need it.

## Why this is not a search-and-replace

In PDF the line width set by `w` is in user space, and it is the matrix in
effect **when the path is stroked** that scales it — not the matrix when `w`
ran. CAD exports routinely write:

```
6 w  0 -0.12 .12 0 0 595 cm  ...  S      -> a 0.72 pt line, not a 6 pt one
```

Rewriting the `6` naively would be 60× wrong. PrintSplit tokenises the content
stream — handling strings, hex strings, comments and inline images so a `w`
inside them is never mistaken for an operator — tracks `q`/`Q`/`cm`/`gs`, and
injects a corrected width immediately before each stroking operator, where the
matrix is finally known.

The source file on disk is never modified; the rewrite happens in memory, and
before the bounding box is measured, so the box reflects what actually prints.
