# PrintSplit

**Tile a scaled drawing across large sheets, precisely.**

You have a PDF drawn at 1:50. You want it on the floor at 1:1, and it is four
metres wide. PrintSplit magnifies it exactly, splits it across overlapping A0
sheets, and prints the cut lines, registration crosshairs, coordinate grid and
calibration ruler you need to put the pieces back together to the millimetre.

Everything is driven by a config file. There is a CLI and a small Python API.

```bash
pip install -r requirements.txt
python examples/make_sample_drawing.py     # a synthetic 1:20 drawing
python printsplit.py config/example.toml   # -> 6 A0 sheets at 1:1
```

---

## Why not an existing tool?

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

---

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
  joint. Prefer tape to cutting? Overlay the sheets until the crosses coincide.
* **Coordinate ticks** — every 100 mm along the top and left frame, labelled in
  metres from the drawing's corner, so any point can be checked with a tape.
* **Calibration ruler** — 500 mm, horizontal and vertical. If it does not
  measure 500 mm, the printer rescaled the job and nothing else can be trusted.
* **Info panel** — sheet id, the metre range it covers, its neighbours, and the
  print settings. It and the ruler are placed automatically in the emptiest
  corner, inside the area no neighbour overlaps, so they never cover the drawing
  and never get cut off.
* **Assembly map** — a separate small page showing how the sheets fit together.

---

## Usage

A new drawing, in one command:

```bash
python printsplit.py --new projects/bridge/deck.pdf
```

That writes `projects/bridge/deck.toml` next to the drawing, tiles it, and runs
the checks. Edit the config and re-run to adjust.

```bash
python printsplit.py projects/bridge/deck.toml     # one job
python printsplit.py "projects/*/*.toml"           # several (wildcards expanded
                                                   # internally, so they work on
                                                   # Windows too)
python printsplit.py --all                         # every job it can find
python printsplit.py <config> --dry-run            # numbers + checks, no PDFs
python printsplit.py <config> --out DIR            # override the output folder
python printsplit.py <config> -q                   # print only the file paths
```

`--dry-run` gives the sheet count, the assembled size and which tile covers
which part of the drawing without producing anything — use it to try sheet
sizes, overlaps and scales before committing a roll of paper.

Each run writes `<basename>.pdf` (one page per sheet, all the same size, ready
for the plotter), `<basename>_assembly_map.pdf`, and `<basename>_report.txt`.

### Where things live

```
config/          shipped defaults and the example - part of the repo
projects/        your drawings, configs and output - git-ignored
```

Keep each job in its own folder: the drawing, its `.toml`, and `out/`. Nothing
of yours ends up in the repo, and a project folder can be moved or archived
whole.

---

## Configuring a job

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

[`config/default.toml`](config/default.toml) lists **every** setting with a
comment. The ones you are most likely to touch:

| setting | why |
|---|---|
| `scale.target_scale` | print at 1:2 or 1:5 instead of full size — the fastest way to cut the sheet count |
| `lines.mode` | how thick the drawing's strokes come out (see below) |
| `source.bbox_mode` | `auto` finds the artwork; `manual` + `manual_bbox_mm` crops to one detail of a busy sheet |
| `source.padding_mm` | clear paper around the drawing, in printed mm |
| `sheet.margin_mm` | a number, `[vertical, horizontal]` or `[top, right, bottom, left]` |
| `tiling.overlap_mm` | wider = easier to align, more sheets |
| `tiling.skip_blank_tiles` | drop sheets with nothing on them — but an empty sheet mid-drawing is the spacer holding the two halves apart |
| `marks.*` | every mark can be turned off, recoloured, resized or repositioned |

A config may `extends` another, chained as deep as you like, so a set of
drawings for the same job can share one base and cannot drift apart in scale or
overlap. Unknown keys are rejected with the list of valid ones — a typo cannot
silently ruin a print.

---

## Line widths

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
| `keep` | leave the weights alone; they scale with the drawing (default) |
| `fixed` | every stroke prints `width_mm` wide |
| `scale` | keep the drawing's *relative* weights, multiplied by `scale` |

`min_width_mm` / `max_width_mm` clamp the result in any mode — `keep` plus
`max_width_mm = 1.0` keeps the line hierarchy but caps the fat ones. All values
are in **printed** millimetres.

Two things worth knowing:

* **Nothing moves.** A stroke's centreline is unaffected by its width, so
  re-weighting changes ink only.
* **Round-capped dots shrink.** Some exports draw bolt holes as a zero-length
  stroke with a round cap, where the *line width is the hole diameter*. Thinning
  turns those into markers — centres exact, size no longer to scale. Use
  `mode = "keep"` if you need it.

This is not a search-and-replace on the `w` operator. In PDF the line width is
scaled by the matrix in effect **when the path is stroked**, not when `w` ran,
and CAD exports routinely write `6 w … 0.12 scale … S` — a 0.72 pt line, not a
6 pt one. PrintSplit tokenises the content stream, tracks `q`/`Q`/`cm`/`gs`, and
injects a corrected width where the matrix is finally known.

---

## The checks

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
| `text rotation` | upside-down labels in the export (sideways is fine — that is how vertical dimensions are drawn) |
| `stroke width` | lines that would print absurdly wide once magnified |
| `vs sibling` | whether the drawing agrees with the other PDFs beside it, at zero offset — confirms an undocumented drawing is at the same scale, and catches a revision that silently moved geometry |
| `size` | a job about to eat 20+ m² of paper |
| `placement` | the finished PDF really is at an exact integer scale, unrotated and unrasterised |
| `tile offsets` | every neighbouring pair is exactly one advance apart |

`placement` and `tile offsets` re-open the produced PDF, so they check the
actual output rather than the intent. `--no-check` skips them.

---

## Python API

Designed to be driven by another program — a GUI, a batch script, a service.
Everything raises `PrintSplitError`, so one `except` covers the lot.

```python
import printsplit

cfg = printsplit.load_config("projects/bridge/deck.toml")
cfg.scale.target_scale = 2.0                 # or build one with from_dict()

with printsplit.plan(cfg) as job:            # nothing written yet
    print(job.layout.sheet_count, "sheets")
    print(job.assembled_w_mm, "x", job.assembled_h_mm, "mm")
    for finding in printsplit.source_findings(job):
        print(finding)

    printsplit.render(job, progress=lambda i, n, label: print(f"{i}/{n} {label}"))
    print(job.outputs)                       # every file written
```

| | |
|---|---|
| `load_config(path)` / `from_dict(d)` / `to_dict(cfg)` / `dump_config(cfg, path)` | configs as files or plain dicts, round-tripping both ways |
| `plan(cfg) -> Job` | compute the layout, write nothing. A context manager |
| `render(job, progress=...)` | produce the PDFs; `progress(done, total, label)` per sheet |
| `job.layout` | `rows`, `cols`, `sheet_count`, `paper_area_m2`, `tiles[]` with each tile's label, neighbours and the metre range it covers |
| `source_findings(job)` / `output_findings(path, job)` | the checks, as `Finding(level, check, message)` |
| `PAPER_SIZES_MM` | the paper table, for populating a dropdown |
| `PrintSplitError` | base of `ConfigError`, `SourceError`, `LayoutError` |

`plan()` holds an open document — use `with`, or call `job.close()`.

---

## How the accuracy is achieved

The artwork is placed as a PDF form XObject whose matrix is an exact integer
scale — `[50 0 0 50 tx ty]` — so nothing is rasterised, nothing is rotated, and
a ×50 magnification stays razor sharp while the file stays small. Tile offsets
match the advance distance to within ~2 × 10⁻⁴ mm, which is PDF number
formatting, four orders of magnitude below what any plotter can hold. The only
real error left is the printer's own — which is what the 500 mm ruler is for.

The tiling arithmetic lives in `layout.py`, deliberately free of PDF concepts,
and is tested on its properties: the grid covers the whole drawing, trim
rectangles butt-join with no gap and no double-up, and the centre of a shared
band is the same assembled coordinate on both sheets.

---

## Repo layout

```
printsplit.py               run from a checkout, no install needed
config/
├── default.toml            every setting, documented
└── example.toml            the example job
examples/
├── make_sample_drawing.py  generates the sample
└── sample_drawing.pdf      a synthetic 1:20 drawing
src/printsplit/
├── cli.py                  argument parsing, scaffolding, batch runs
├── config.py               schema, extends-merging, validation, dict round-trip
├── errors.py               PrintSplitError and friends
├── units.py                mm <-> pt, paper sizes
├── geometry.py             find the drawing on the source page
├── strokes.py              re-weight the drawing's line widths
├── layout.py               tiling arithmetic (no PDF concepts)
├── marks.py                everything drawn on a sheet
├── tiler.py                assemble the output PDF
├── overview.py             the assembly map
├── report.py               the text report
└── audit.py                the automatic checks
tests/
projects/                   your jobs live here (git-ignored)
```

## Requirements

Python 3.11+ (uses the standard-library `tomllib`) and
[PyMuPDF](https://pymupdf.readthedocs.io). That is the only dependency.

## Tests

```bash
python -m pytest
```

Each test file also runs standalone (`python tests/test_layout.py`) if you would
rather not install pytest.

## License

MIT — see [LICENSE](LICENSE).
