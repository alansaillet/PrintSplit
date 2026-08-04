"""Assemble the tiled output PDF.

The source artwork is placed with ``show_pdf_page``, which keeps it as vectors:
no rasterising, so a 60x magnification stays razor sharp and the file stays
small.  Each tile shows exactly the slice of the source that belongs to it, and
the marks are painted around and on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pymupdf as fitz

from . import __version__, strokes
from .config import Config
from .errors import PrintSplitError, SourceError
from .geometry import ContentBox, content_box
from .layout import BoxMM, Layout, build, mark_blank_tiles
from .marks import MarkPainter, SheetInfo
from .units import MM_PER_PT, PT_PER_MM, mm_to_pt, pt_to_mm


@dataclass
class Job:
    """One tiling job: the plan, the numbers, and (after render) the files.

    Returned by :func:`plan`. Holds an open PyMuPDF document, so use it as a
    context manager or call :meth:`close`::

        with printsplit.plan(cfg) as job:
            print(job.layout.sheet_count)
            printsplit.render(job)
    """

    cfg: Config
    layout: Layout
    content: ContentBox
    magnification: float
    assembled_w_mm: float
    assembled_h_mm: float
    source_path: Path
    tiles_pdf: Path | None = None
    overview_pdf: Path | None = None
    report_txt: Path | None = None
    per_tile_pdfs: list[Path] = field(default_factory=list)
    source_rotation: int = 0
    generated: str = ""
    #: every artwork bbox, in assembled millimetres
    content_boxes_mm: list[BoxMM] = field(default_factory=list)
    #: the source document, with line widths already re-weighted (never saved)
    doc: fitz.Document | None = None
    strokes_reweighted: int = 0
    strokes_seen: int = 0
    #: automatic sanity checks, see audit.py
    findings: list = field(default_factory=list)

    def close(self) -> None:
        if self.doc is not None:
            self.doc.close()
            self.doc = None

    def __enter__(self) -> "Job":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def outputs(self) -> list[Path]:
        """Every file this job wrote, in the order they were produced."""
        found = [self.tiles_pdf, self.overview_pdf, self.report_txt]
        return [p for p in (*found, *self.per_tile_pdfs) if p is not None]


#: Backwards-compatible alias for the pre-1.0 name.
Result = Job


def _assembled_box(rect: fitz.Rect, content: ContentBox, mag: float) -> BoxMM:
    """Source-page rect (pt) -> assembled millimetres."""
    return BoxMM(
        (rect.x0 - content.rect.x0) * MM_PER_PT * mag,
        (rect.y0 - content.rect.y0) * MM_PER_PT * mag,
        (rect.x1 - content.rect.x0) * MM_PER_PT * mag,
        (rect.y1 - content.rect.y0) * MM_PER_PT * mag,
    )


def _source_rect(box: BoxMM, content: ContentBox, mag: float) -> fitz.Rect:
    """Assembled millimetres -> source-page rect (pt)."""
    scale = PT_PER_MM / mag
    return fitz.Rect(
        content.rect.x0 + box.x0 * scale,
        content.rect.y0 + box.y0 * scale,
        content.rect.x0 + box.x1 * scale,
        content.rect.y0 + box.y1 * scale,
    )


def plan(cfg: Config) -> Job:
    """Work out the layout without writing anything.

    Returns an open :class:`Job`; close it (or use ``with``) when done.
    """
    source_path = cfg.resolve(cfg.project.input)
    if not source_path.is_file():
        raise SourceError(f"source PDF not found: {source_path}")

    try:
        doc = fitz.open(source_path)
    except Exception as exc:  # pragma: no cover - depends on the file
        raise SourceError(f"cannot open {source_path}: {exc}") from None
    if not 1 <= cfg.project.page <= doc.page_count:
        doc.close()
        raise SourceError(
            f"project.page = {cfg.project.page} but {source_path.name} has "
            f"{doc.page_count} page(s)"
        )
    mag = cfg.scale.magnification
    # Re-weight the strokes before measuring, so the stroke-aware bounding box
    # reflects the widths that will actually be printed.
    reweighted, strokes_seen = strokes.apply(doc, cfg.project.page - 1, cfg, mag)
    page = doc[cfg.project.page - 1]
    if reweighted:
        doc.reload_page(page)
        page = doc[cfg.project.page - 1]
    content = content_box(page, cfg)

    assembled_w = content.width_mm * mag
    assembled_h = content.height_mm * mag

    layout = build(cfg, assembled_w, assembled_h)
    boxes = [_assembled_box(r, content, mag) for r in content.items]
    mark_blank_tiles(layout, boxes)
    if not cfg.tiling.skip_blank_tiles:
        for tile in layout.tiles:
            tile.blank = False

    # Renumber so "sheet n of m" counts only the sheets that will be printed.
    index = 0
    for tile in layout.tiles:
        if not tile.blank:
            tile.index = index
            index += 1

    result = Result(
        cfg=cfg,
        layout=layout,
        content=content,
        magnification=mag,
        assembled_w_mm=assembled_w,
        assembled_h_mm=assembled_h,
        source_path=source_path,
        source_rotation=page.rotation,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        content_boxes_mm=boxes,
        doc=doc,
        strokes_reweighted=reweighted,
        strokes_seen=strokes_seen,
    )
    return result


def _sheet_info(result: Result) -> SheetInfo:
    cfg = result.cfg
    lay = result.layout
    scale = cfg.scale
    if abs(scale.target_scale - 1.0) < 1e-9:
        scale_text = f"Printed 1:1 (full size) - source drawn 1:{scale.source_scale:g}"
    else:
        scale_text = (
            f"Printed 1:{scale.target_scale:g} - source drawn 1:{scale.source_scale:g}"
        )
    return SheetInfo(
        project=cfg.project.name,
        scale_text=scale_text,
        sheet_text=(
            f"{cfg.sheet.size} {lay.orientation} {lay.sheet_w_mm:g} x "
            f"{lay.sheet_h_mm:g} mm, printable margin "
            f"{'/'.join(f'{m:g}' for m in lay.margins_mm)} mm"
        ),
        assembled_text=(
            f"Assembled drawing {result.assembled_w_mm / 1000:.3f} x "
            f"{result.assembled_h_mm / 1000:.3f} m on {lay.cols} x {lay.rows} sheets"
        ),
        generated=f"PrintSplit {__version__} - {result.generated} - "
        f"{result.source_path.name}",
    )


def _render_tile(
    out_page: fitz.Page,
    tile,
    result: Result,
    src_doc: fitz.Document,
) -> None:
    cfg = result.cfg
    painter = MarkPainter(
        out_page,
        tile,
        result.layout,
        cfg,
        _sheet_info(result),
        content_boxes=result.content_boxes_mm,
    )
    painter.draw_background()

    clip = (
        _source_rect(tile.window, result.content, result.magnification)
        & result.content.rect
        & result.content.page_rect
    )
    if not clip.is_empty:
        box = _assembled_box(clip, result.content, result.magnification)
        target = fitz.Rect(
            painter.px(box.x0), painter.py(box.y0), painter.px(box.x1), painter.py(box.y1)
        )
        out_page.show_pdf_page(
            target,
            src_doc,
            cfg.project.page - 1,
            clip=clip,
            keep_proportion=False,
        )
    painter.draw_foreground()


def render(
    result: Job,
    overview_doc: fitz.Document | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> Job:
    """Produce the tile PDF (and optionally one file per tile).

    ``progress(done, total, label)`` is called as each sheet is composed, so a
    GUI can drive a progress bar on a job that runs to dozens of sheets.
    """
    cfg = result.cfg
    lay = result.layout
    out_dir = cfg.resolve(cfg.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    src_doc = result.doc
    if src_doc is None:
        raise PrintSplitError(
            "this job has been closed; call plan() again before render()"
        )
    out = fitz.open()
    sheet_w_pt = mm_to_pt(lay.sheet_w_mm)
    sheet_h_pt = mm_to_pt(lay.sheet_h_mm)

    printing = [t for t in lay.tiles if not t.blank]
    for done, tile in enumerate(printing, start=1):
        page = out.new_page(width=sheet_w_pt, height=sheet_h_pt)
        _render_tile(page, tile, result, src_doc)
        if progress is not None:
            progress(done, len(printing), tile.label)

    tile_page_offset = 0
    if overview_doc is not None:
        if cfg.overview.separate_file:
            path = out_dir / f"{cfg.project.output_basename}_assembly_map.pdf"
            _guard_overwrite(path, cfg)
            overview_doc.save(path, deflate=True, garbage=3)
            result.overview_pdf = path
        else:
            out.insert_pdf(overview_doc, start_at=0)
            tile_page_offset = overview_doc.page_count

    out.set_metadata(
        {
            "title": f"{cfg.project.name} - {lay.sheet_count} x {cfg.sheet.size} "
            f"{lay.orientation}",
            "subject": f"Tiled at 1:{cfg.scale.target_scale:g} from a "
            f"1:{cfg.scale.source_scale:g} drawing",
            "creator": f"PrintSplit {__version__}",
            "producer": f"PrintSplit {__version__}",
            "keywords": f"printsplit;{cfg.sheet.size};overlap {lay.overlap_mm:g}mm",
        }
    )

    if cfg.output.single_pdf:
        target = out_dir / f"{cfg.project.output_basename}.pdf"
        _guard_overwrite(target, cfg)
        out.save(target, deflate=True, garbage=3)
        result.tiles_pdf = target

    if cfg.output.per_tile_pdfs:
        printed = [t for t in lay.tiles if not t.blank]
        for n, tile in enumerate(printed):
            page_no = n + tile_page_offset
            single = fitz.open()
            single.insert_pdf(out, from_page=page_no, to_page=page_no)
            path = out_dir / f"{cfg.project.output_basename}_{tile.label}.pdf"
            _guard_overwrite(path, cfg)
            single.save(path, deflate=True, garbage=3)
            single.close()
            result.per_tile_pdfs.append(path)

    out.close()
    return result


def _guard_overwrite(path: Path, cfg: Config) -> None:
    if path.exists() and not cfg.output.overwrite:
        raise PrintSplitError(
            f"{path} already exists and output.overwrite is false"
        )
