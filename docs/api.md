# Python API

[← back to the README](../README.md)

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

## The surface

| | |
|---|---|
| `load_config(path)` | read a `.toml`, following `extends` |
| `from_dict(d, validate_it=True)` | build one from plain dicts; pass `False` for a form the user has not finished filling in |
| `to_dict(cfg)` / `dump_config(cfg, path)` | back to dicts or TOML — round-trips both ways |
| `validate_config(cfg)` | run the "is this runnable" rules on demand |
| `plan(cfg) -> Job` | compute the layout, write nothing. A context manager |
| `render(job, overview=None, progress=...)` | produce the PDFs; `progress(done, total, label)` fires per sheet |
| `build_overview(job)` | the assembly map, as a PyMuPDF document |
| `build_report(job)` / `write_report(job)` | the text report |
| `source_findings(job)` / `output_findings(path, job)` | the [checks](checks.md), as `Finding(level, check, message)` |
| `PAPER_SIZES_MM` | the paper table, for populating a dropdown |
| `PrintSplitError` | base of `ConfigError`, `SourceError`, `LayoutError` |

## The Job object

`plan()` returns a `Job` holding an open document — use `with`, or call
`job.close()`.

| | |
|---|---|
| `job.layout.rows` / `.cols` / `.sheet_count` / `.paper_area_m2` | the grid |
| `job.layout.tiles[]` | each tile's `label`, `neighbours`, and the metre range it covers |
| `job.assembled_w_mm` / `.assembled_h_mm` | the finished size |
| `job.magnification` | `source_scale / target_scale` |
| `job.outputs` | every file written, after `render()` |

## Notes

* The top-level import stays light: PyMuPDF is loaded lazily on first use, so
  `import printsplit` is cheap enough for a CLI's `--help`.
* `plan()` is fast and writes nothing, so it is safe to call on every keystroke
  to keep a live sheet count in a UI.
* Do not share a `Job` between threads — it holds a PyMuPDF document, which is
  not thread-safe. Plan and render on the same thread; for a background render,
  plan again there.

A working consumer of all of this is
[PrintSplit GUI](https://github.com/alansaillet/PrintSplit-GUI).

## Where the code lives

```
printsplit.py               run from a checkout, no install needed
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
examples/
├── make_sample_drawing.py  generates the sample drawing
└── make_hero_image.py      builds docs/hero.png from real output
```
