"""Command line entry point.

    printsplit config/hedelius_03.toml       one job
    printsplit "config/hedelius*.toml"       several (globs are expanded here)
    printsplit --all                         every job config in config/
    printsplit --new projects/X/plan.pdf     write a config for a new PDF, run it
    printsplit <config> --dry-run            the numbers and the checks, no PDFs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import load
from .errors import ConfigError, PrintSplitError

CONFIG_DIR = "config"  # shipped defaults and the example
PROJECTS_DIR = "projects"  # your drawings and their configs (git-ignored)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="printsplit",
        description="Tile a scaled PDF drawing across A0 (or any) sheets, with "
        "alignment marks.",
        epilog="Every run also prints a CHECKS section: content outside the page, "
        "rotated text, how wide the strokes really print, whether the drawing "
        "agrees with its siblings' coordinate system, and proof that the finished "
        "PDF was placed at an exact scale.",
    )
    parser.add_argument(
        "config",
        nargs="*",
        help="project TOML config(s); wildcards allowed",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"run every job config in {CONFIG_DIR}/ and {PROJECTS_DIR}/*/ "
        f"(bases without a project.input are skipped)",
    )
    parser.add_argument(
        "--new",
        metavar="PDF",
        help="write a config beside a source PDF that does not have one yet, then run it",
    )
    parser.add_argument(
        "--extends",
        metavar="TOML",
        help="base config for --new (default: a *_common.toml beside the drawing, "
        "else the shipped config/default.toml)",
    )
    parser.add_argument(
        "--force", action="store_true", help="let --new overwrite an existing config"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report the layout and checks, write nothing"
    )
    parser.add_argument("--no-check", action="store_true", help="skip the sanity checks")
    parser.add_argument("--out", metavar="DIR", help="override project.output_dir")
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="print only the output paths"
    )
    parser.add_argument("--version", action="version", version=f"PrintSplit {__version__}")
    return parser


# --------------------------------------------------------------------------- #
# Locating configs
# --------------------------------------------------------------------------- #


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def _is_job(path: Path) -> bool:
    """A job config names a source PDF; a base config is only meant to be extended."""
    import tomllib

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return True  # let the real loader produce the error message
    while "extends" in raw and not raw.get("project", {}).get("input"):
        parent = (path.parent / raw["extends"]).resolve()
        if not parent.is_file():
            break
        path = parent
        try:
            raw = tomllib.loads(parent.read_text(encoding="utf-8-sig"))
        except Exception:
            break
    return bool(raw.get("project", {}).get("input"))


def discover_configs(root: Path | None = None) -> list[Path]:
    """Every runnable job config: the shipped ones, plus everything in projects/."""
    root = root or _repo_root()
    found = sorted((root / CONFIG_DIR).glob("*.toml"))
    found += sorted((root / PROJECTS_DIR).glob("*/*.toml"))
    return [p for p in found if _is_job(p)]


def resolve_configs(args) -> list[Path]:
    paths: list[Path] = []
    if args.all:
        paths += discover_configs()
    for pattern in args.config:
        if any(ch in pattern for ch in "*?["):
            matched = sorted(Path().glob(pattern))
            if not matched:
                raise ConfigError(f"no config matched {pattern!r}")
            paths += matched
        else:
            paths.append(Path(pattern))
    # de-duplicate, keep order
    seen, unique = set(), []
    for p in paths:
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


# --------------------------------------------------------------------------- #
# Scaffolding a config for a new drawing
# --------------------------------------------------------------------------- #

TEMPLATE = '''\
# Written by `printsplit --new`. Adjust and re-run.
extends = "{base}"

[project]
name = "{name}"
input = "{input}"
page = 1
output_dir = "{output_dir}"
output_basename = "{basename}"
'''


def scaffold(pdf: str, extends: str | None, force: bool) -> Path:
    """Write a config for a source PDF, next to the drawing itself.

    Keeping the config beside its drawing means a project folder is
    self-contained -- drawing, settings and output travel together, and the
    repo itself stays free of anyone's job data.
    """
    import os

    root = _repo_root()
    source = Path(pdf).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"no such PDF: {source}")

    stem = source.stem
    target = source.parent / f"{stem}.toml"
    if target.exists() and not force:
        raise FileExistsError(
            f"{target} already exists; edit it, or pass --force to overwrite"
        )

    if extends:
        base = extends
    else:
        # a shared base beside the drawing wins, else the shipped default
        commons = sorted(source.parent.glob("*_common.toml"))
        if len(commons) == 1:
            base = commons[0].name
        else:
            base = Path(
                os.path.relpath(root / CONFIG_DIR / "default.toml", source.parent)
            ).as_posix()

    try:
        rel = source.relative_to(root).as_posix()
        out_dir = (source.parent.relative_to(root) / "out").as_posix()
    except ValueError:  # the PDF lives outside the repo
        rel = source.as_posix()
        out_dir = (source.parent / "out").as_posix()
    target.write_text(
        TEMPLATE.format(
            base=base,
            name=stem.replace("_", " "),
            input=rel,
            output_dir=out_dir,
            basename=f"{stem}_A0_1to1",
        ),
        encoding="utf-8",
    )
    print(f"wrote {target}  (extends {base})")
    return target


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #


def run_one(path: Path, args) -> int:
    from . import audit, overview, report, tiler

    cfg = load(path)
    if args.out:
        cfg.project.output_dir = args.out

    result = tiler.plan(cfg)
    try:
        if not args.no_check:
            result.findings = audit.source_findings(result)

        if args.dry_run:
            print(report.build(result))
            return 0

        overview_doc = overview.build(result) if cfg.overview.enabled else None
        tiler.render(result, overview_doc)
        if overview_doc is not None:
            overview_doc.close()

        if not args.no_check and result.tiles_pdf:
            result.findings += audit.output_findings(result.tiles_pdf, result)
        if cfg.output.report:
            report.write(result)

        if args.quiet:
            for p in filter(None, [result.tiles_pdf, result.overview_pdf,
                                   result.report_txt, *result.per_tile_pdfs]):
                print(p)
        else:
            print(report.build(result))
        return 0
    finally:
        result.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        configs = resolve_configs(args)
        if args.new:
            configs.insert(0, scaffold(args.new, args.extends, args.force))
        if not configs:
            build_parser().print_usage(sys.stderr)
            print("printsplit: give a config, or --all, or --new PDF", file=sys.stderr)
            return 2

        failed = 0
        for n, path in enumerate(configs):
            if len(configs) > 1 and not args.quiet:
                print(f"\n===== [{n + 1}/{len(configs)}] {path}")
            try:
                failed |= run_one(path, args)
            except (PrintSplitError, OSError) as exc:
                print(f"printsplit: {path}: {exc}", file=sys.stderr)
                failed = 1
        return failed

    except ConfigError as exc:
        print(f"printsplit: config error: {exc}", file=sys.stderr)
        return 2
    except (PrintSplitError, OSError) as exc:
        print(f"printsplit: {exc}", file=sys.stderr)
        return 1


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    run()
