# Why not an existing tool

[← back to the README](../README.md)

| | tiles a PDF | drawing-scale control | alignment marks |
|---|---|---|---|
| Acrobat "Poster" print | yes | % zoom only, no `1:50 → 1:1` | overlap + faint marks |
| [pdfposter](https://pdfposter.readthedocs.io) | yes | box sizes, not scales | none |
| [PosteRazor](https://posterazor.sourceforge.io) | raster only | no | overlap guides |
| Inkscape / QGIS atlas | manual | manual | manual |

They all tile. None lets you say *"this drawing is 1:50, print it 1:1"*, none
finds the drawing's bounding box for you, and none puts registration crosshairs
on **identical real-world coordinates** on both sides of a joint — which is the
thing that makes a four-metre assembly come out right.

If you just want a quick poster split, `pdfposter` is a one-liner and does the
job. If the print has to be *correct to the millimetre*, use this.
