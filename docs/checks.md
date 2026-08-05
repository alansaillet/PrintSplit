# Checks

[← back to the README](../README.md)

Every run ends with a `CHECKS` section, so a new drawing does not need anyone to
eyeball it:

```
CHECKS
  [  ok  ] off-page           all content is inside the page
  [ WARN ] text rotation      3 text line(s) are UPSIDE DOWN: '981' at 180deg...
  [  ok  ] stroke width       printed 0.5 .. 0.5 mm
  [  ok  ] vs sibling         this drawing fully contains plan_02.pdf at zero offset
  [  ok  ] placement          all 6 page(s) placed at exactly [20 0 0 20]
  [  ok  ] tile offsets       7 neighbour pair(s) match the advance to 0.00049 mm
```

| check | catches |
|---|---|
| `off-page` | paths outside the media box — invisible in the source, but they would otherwise inflate the print |
| `text rotation` | upside-down labels in the export. Sideways is *not* flagged: that is how every CAD package draws a vertical dimension |
| `stroke width` | lines that would print absurdly wide once magnified |
| `vs sibling` | whether the drawing agrees with the other PDFs beside it, at zero offset |
| `size` | a job about to eat 20+ m² of paper |
| `placement` | the finished PDF really is at an exact integer scale, unrotated and unrasterised |
| `tile offsets` | every neighbouring pair is exactly one advance apart |

`placement` and `tile offsets` re-open the produced PDF and measure it, so they
check the actual output rather than the intent — they would catch a regression
in the tiler itself. `--no-check` skips everything here.

## The sibling check

This is the one that earns its keep. It compares the drawing's geometry against
the other PDFs sitting beside it, at zero offset, and reports containment both
ways:

```
[  ok  ] vs sibling   this drawing fully contains plan_02.pdf at zero offset
                      (17.6% of mine in theirs, 100.0% of theirs in mine)
```

Two things fall out of it:

* **An undocumented drawing's scale.** If a revision states no scale but places
  the same geometry at the same real-world coordinates as one that does, it is
  at that scale too.
* **A revision that silently moved something.** If a new version of a drawing
  suddenly shares far less with its predecessor, geometry moved — and you want
  to know that before printing forty sheets, not after.

Agreement is judged symmetrically: a large drawing that contains a small one
agrees with it just as much as the reverse.
