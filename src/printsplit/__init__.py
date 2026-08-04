"""Tile a scaled drawing across large sheets, precisely.

Takes a PDF drawn at some scale (say 1:50), finds the bounding box of what is
actually on the page, magnifies it to the scale you want to print at (say 1:1)
and splits it across overlapping sheets -- with cut lines, registration
crosshairs, a coordinate grid and a printed ruler, so the pieces go back
together exactly.

Command line::

    printsplit --new drawings/plan.pdf     write a config for a PDF, then run it
    printsplit config/plan.toml            run a job
    printsplit --all                       run every job config

Library::

    import printsplit

    cfg = printsplit.load_config("config/plan.toml")
    cfg.scale.source_scale = 50.0          # or build one with from_dict()

    with printsplit.plan(cfg) as job:
        print(job.layout.sheet_count, "sheets")
        printsplit.render(job, progress=lambda i, n, label: print(i, "/", n))
        print(job.outputs)

Everything raises :class:`PrintSplitError` on purpose, so one ``except`` covers
the lot.
"""

from .errors import ConfigError, LayoutError, PrintSplitError, SourceError

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # errors
    "PrintSplitError",
    "ConfigError",
    "SourceError",
    "LayoutError",
    # configuration
    "Config",
    "load_config",
    "from_dict",
    "to_dict",
    "dump_config",
    "PAPER_SIZES_MM",
    # running a job
    "Job",
    "plan",
    "render",
    "build_overview",
    "build_report",
    "write_report",
    # checks
    "Finding",
    "source_findings",
    "output_findings",
]


def __getattr__(name: str):
    """Import the heavy parts (PyMuPDF) only when they are actually used."""
    if name in ("Config", "load_config", "from_dict", "to_dict", "dump_config"):
        from . import config as _config

        return {
            "Config": _config.Config,
            "load_config": _config.load,
            "from_dict": _config.from_dict,
            "to_dict": _config.to_dict,
            "dump_config": _config.dump,
        }[name]
    if name == "PAPER_SIZES_MM":
        from .units import PAPER_SIZES_MM

        return PAPER_SIZES_MM
    if name in ("Job", "plan", "render"):
        from . import tiler

        return {"Job": tiler.Job, "plan": tiler.plan, "render": tiler.render}[name]
    if name == "build_overview":
        from .overview import build

        return build
    if name in ("build_report", "write_report"):
        from . import report

        return {"build_report": report.build, "write_report": report.write}[name]
    if name in ("Finding", "source_findings", "output_findings"):
        from . import audit

        return {
            "Finding": audit.Finding,
            "source_findings": audit.source_findings,
            "output_findings": audit.output_findings,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
