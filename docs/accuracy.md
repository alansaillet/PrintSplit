# Accuracy

[← back to the README](../README.md)

The artwork is placed as a PDF form XObject whose matrix is an exact integer
scale — `[50 0 0 50 tx ty]` — so nothing is rasterised, nothing is rotated, and
a ×50 magnification stays razor sharp while the file stays small.

Tile offsets match the advance distance to within about 2 × 10⁻⁴ mm, which is
PDF number formatting: four orders of magnitude below what any plotter can hold.
The only real error left is the printer's own, which is what the 500 mm ruler on
every sheet is for.

Both of those are re-measured from the finished PDF on every run — see the
`placement` and `tile offsets` [checks](checks.md).

## The tiling arithmetic

`layout.py` is deliberately free of PDF concepts: it works purely in "assembled
millimetres", the coordinate system of the finished, taped-together drawing.
That makes it unit-testable without touching a PDF, and it is tested on its
properties rather than on examples:

* the grid covers the whole drawing
* trim rectangles butt-join with no gap and no double-up, and tile the plane
* the centre of a shared band is the same assembled coordinate on both sheets —
  which is what makes the registration crosshairs line up
* margins and overlaps that cannot work are rejected rather than silently fudged

## The overlap convention

Neighbouring sheets share a band of `overlap_mm`. Every sheet is cut along its
*left* and *top* edge where a neighbour exists, then butt-joined onto the sheet
to its left or above:

```
sheet A1 covers  [a, a+usable]
sheet B1 covers  [a+step, a+step+usable]   with step = usable - overlap

cutting B1 at its own x0+overlap makes it start exactly where A1 ends.
```

The same marks also support the tape-and-overlay workflow: keep the strip and
line up the crosshairs instead, since those sit on identical assembled
coordinates on both sheets.
