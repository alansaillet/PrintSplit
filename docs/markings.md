# Markings and assembly

[← back to the README](../README.md)

## What ends up on a sheet

```
  crop mark                        ^ B1   (the sheet above)
  ---+                  ,--- CUT (red dashed): cut here, butt-join onto B1
     |  . . . . . . . . | . . . . . . . . . . . . . . . .   <- shaded overlap band
     |  +---------------+--------------------------------+
  C  |  |    (+)              (+)              (+)       |   <- registration
  U  |  |                                                |      crosshairs on round
  T  |  |                                                |      real-world coordinates
     |  |            the drawing, at 1:1                 |
     |  |                                                |
     |  |  +----+                                        |
     |  |  | A1 |  which sheet this is, what it covers   |
     |  |  +----+  |=========|  500 mm — measure it      |
     |  +-------------------------------------------+----+
```

* **Cut line** — red dashed, on the left and top edges that have a neighbour.
  Cut there and the sheet butt-joins its neighbour exactly.
* **Registration crosshairs** — placed on round assembled coordinates, so the
  same cross lands on the same real-world point on *both* sheets sharing a
  joint.
* **Coordinate ticks** — every 100 mm along the top and left frame, labelled in
  metres from the drawing's corner, so any point can be checked with a tape.
* **Calibration ruler** — 500 mm, horizontal and vertical. If it does not
  measure 500 mm, the printer rescaled the job and nothing else can be trusted.
* **Info panel** — sheet id, the metre range it covers, its neighbours, and the
  print settings.
* **Assembly map** — a separate small page showing how the sheets fit together.

The info panel and the ruler are placed automatically in the emptiest corner of
each sheet, inside the area no neighbour overlaps, so they never cover the
drawing and never get cut off.

## Printing

1. Print at **100% / actual size**. Turn off "fit to page" and "shrink to
   printable area" in the printer dialog.
2. **Measure the 500 mm ruler on the first sheet** before printing the rest. If
   it is off, the printer rescaled the job — fix that first.
3. Then either:
   * **Butt-join** — cut each sheet along its red dashed edges and lay the cut
     edge against the neighbour named on that edge; or
   * **Overlay** — keep the overlap, lay the sheets on top of each other until
     the blue crosshairs coincide, and tape.
4. The assembly map shows which sheet goes where.

Both workflows are supported by the same marks, so you can decide at the table.

## Why the crosshairs work

Every crosshair sits at a round coordinate in the *assembled* drawing — not at
some position on the sheet. Two sheets sharing a joint therefore draw their
crosshairs at the same real-world point, and lining them up is exact by
construction rather than by eye. The same is true of the corner targets where
four sheets meet.
