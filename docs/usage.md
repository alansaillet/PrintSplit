# Usage

[← back to the README](../README.md)

## A new drawing, in one command

```bash
python printsplit.py --new projects/bridge/deck.pdf
```

Writes `projects/bridge/deck.toml` next to the drawing, tiles it, and runs the
[checks](checks.md). Edit the config and re-run to adjust anything.

## Everything else

```bash
python printsplit.py projects/bridge/deck.toml     # one job
python printsplit.py "projects/*/*.toml"           # several - wildcards are
                                                   # expanded by the tool, so
                                                   # they work on Windows too
python printsplit.py --all                         # every job it can find
python printsplit.py <config> --dry-run            # numbers + checks, no PDFs
python printsplit.py <config> --out DIR            # override the output folder
python printsplit.py <config> --no-check           # skip the checks
python printsplit.py <config> -q                   # print only the file paths
```

`--dry-run` gives the sheet count, the assembled size and which tile covers
which part of the drawing without producing anything. Use it to try sheet sizes,
overlaps and scales before committing a roll of paper.

## What each run writes

| file | what |
|---|---|
| `<basename>.pdf` | one page per sheet, all the same size, ready for the plotter |
| `<basename>_assembly_map.pdf` | the whole drawing with the sheet grid on top |
| `<basename>_report.txt` | every number behind the job, including the checks |

## Where things live

Your drawings are yours; keep them out of the tool. Each job is a folder holding
the drawing, its `.toml` and its `out/` — self-contained, so it can be moved,
archived or backed up whole.

```
PrintSplit/              the tool (this repo)
└── config/              shipped defaults and the example
PrintSplit-Projects/     your jobs - a sibling folder, nothing to do with the repo
├── bridge/
│   ├── deck.pdf
│   ├── deck.toml
│   └── out/
└── foundation/
```

Point the tool at them once:

```bash
setx PRINTSPLIT_PROJECTS "C:\path\to\PrintSplit-Projects"   # Windows
export PRINTSPLIT_PROJECTS=~/PrintSplit-Projects            # macOS / Linux
```

after which `--all` finds them. Or say so per run with `--projects DIR`
(repeatable), or just name the config directly. A `projects/` folder beside the
tool also works and is git-ignored, if you would rather keep everything in one
place.
