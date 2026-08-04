"""The assembly map: one small page showing how the tiles fit together.

Print this on A3/A4 and keep it next to you while taping. It shows the whole
drawing, the sheet grid drawn on top of it, which sheet is which, and the
numbers you need (assembled size, overlap, sheet count).
"""

from __future__ import annotations

import pymupdf as fitz

from . import __version__
from .config import Config, parse_color
from .units import mm_to_pt, paper_size_mm


def _fit(inner_w: float, inner_h: float, box: fitz.Rect) -> tuple[float, fitz.Rect]:
    """Scale factor and centred target rect for content of the given size."""
    scale = min(box.width / inner_w, box.height / inner_h)
    w, h = inner_w * scale, inner_h * scale
    x0 = box.x0 + (box.width - w) / 2
    y0 = box.y0 + (box.height - h) / 2
    return scale, fitz.Rect(x0, y0, x0 + w, y0 + h)


def build(result) -> fitz.Document:
    """Render the assembly map into a fresh one-page document."""
    cfg: Config = result.cfg
    ov = cfg.overview
    lay = result.layout

    grid_w = lay.usable_w_mm + (lay.cols - 1) * lay.step_w_mm
    grid_h = lay.usable_h_mm + (lay.rows - 1) * lay.step_h_mm
    ox, oy = lay.origin_mm

    orientation = ov.orientation
    if orientation == "auto":
        orientation = "landscape" if grid_w >= grid_h else "portrait"
    page_w_mm, page_h_mm = paper_size_mm(ov.size, orientation)

    doc = fitz.open()
    page = doc.new_page(width=mm_to_pt(page_w_mm), height=mm_to_pt(page_h_mm))
    margin = mm_to_pt(ov.margin_mm)

    lines = _legend_lines(result)
    legend_h = (len(lines) + 1) * ov.font_size_pt * 1.5
    title_h = mm_to_pt(12.0)

    frame = fitz.Rect(
        margin,
        margin + title_h,
        page.rect.width - margin,
        page.rect.height - margin - legend_h,
    )
    scale, target = _fit(grid_w, grid_h, frame)

    def gx(x_mm: float) -> float:
        return target.x0 + (x_mm - ox) * scale

    def gy(y_mm: float) -> float:
        return target.y0 + (y_mm - oy) * scale

    # Title
    page.insert_text(
        fitz.Point(margin, margin + mm_to_pt(6.0)),
        f"{cfg.project.name} - assembly map",
        fontname="hebo",
        fontsize=ov.font_size_pt * 1.9,
        color=parse_color(ov.drawing_color),
    )

    # The drawing itself, scaled into the same frame as the grid.
    src = result.doc
    content_rect = fitz.Rect(
        gx(0.0),
        gy(0.0),
        gx(result.assembled_w_mm),
        gy(result.assembled_h_mm),
    )
    clip = result.content.rect & result.content.page_rect
    if not clip.is_empty:
        page.show_pdf_page(
            content_rect, src, cfg.project.page - 1, clip=clip, keep_proportion=False
        )

    # Content bounding box (dashed) so the padding is visible.
    page.draw_rect(
        content_rect,
        color=parse_color(ov.drawing_color),
        width=0.5,
        dashes="[2 2] 0",
    )

    # Sheet grid: the butt-join footprint of every tile.
    grid_color = parse_color(ov.grid_color)
    blank_color = parse_color(ov.blank_color)
    for tile in lay.tiles:
        rect = fitz.Rect(
            gx(tile.trim.x0), gy(tile.trim.y0), gx(tile.trim.x1), gy(tile.trim.y1)
        )
        color = blank_color if tile.blank else grid_color
        if tile.blank:
            page.draw_rect(rect, color=color, width=0.6, dashes="[3 3] 0")
        else:
            page.draw_rect(rect, color=color, width=1.0)
        # Labels go in the cell's top-left corner, not its centre, so they never
        # sit on top of the drawing.
        size = ov.font_size_pt * 1.8
        page.insert_text(
            fitz.Point(rect.x0 + 4, rect.y0 + size),
            tile.label,
            fontname="hebo",
            fontsize=size,
            color=color,
        )
        caption = f"page {tile.index + 1}" if not tile.blank else "not printed"
        page.insert_text(
            fitz.Point(rect.x0 + 4, rect.y0 + size + ov.font_size_pt * 1.2),
            caption,
            fontname="helv",
            fontsize=ov.font_size_pt * 0.85,
            color=color,
        )

    # Legend
    y = page.rect.height - margin - legend_h + ov.font_size_pt * 1.5
    for line in lines:
        page.insert_text(
            fitz.Point(margin, y),
            line,
            fontname="helv",
            fontsize=ov.font_size_pt,
            color=parse_color(ov.drawing_color),
        )
        y += ov.font_size_pt * 1.5

    doc.set_metadata(
        {
            "title": f"{cfg.project.name} - assembly map",
            "creator": f"PrintSplit {__version__}",
            "producer": f"PrintSplit {__version__}",
        }
    )
    return doc


def _legend_lines(result) -> list[str]:
    cfg: Config = result.cfg
    lay = result.layout
    skipped = lay.total_cells - lay.sheet_count
    lines = [
        f"Source: {result.source_path.name}  page {cfg.project.page}   |   "
        f"drawn 1:{cfg.scale.source_scale:g}, printed 1:{cfg.scale.target_scale:g} "
        f"(x{result.magnification:g})",
        f"Assembled size: {result.assembled_w_mm / 1000:.3f} x "
        f"{result.assembled_h_mm / 1000:.3f} m   |   "
        f"{lay.cols} columns x {lay.rows} rows = {lay.sheet_count} sheets of "
        f"{cfg.sheet.size} {lay.orientation}"
        + (f" ({skipped} blank sheet(s) skipped)" if skipped else ""),
        f"Overlap {lay.overlap_mm:g} mm   |   printable margin "
        f"{'/'.join(f'{m:g}' for m in lay.margins_mm)} mm   |   paper used "
        f"{lay.paper_area_m2:.1f} m2",
        "Assembly: print at 100% (no scaling)  ->  check the 500 mm ruler on each "
        "sheet  ->  cut every red dashed edge  ->  butt-join, or overlay on the "
        "crosshairs and tape.",
        f"PrintSplit {__version__} - {result.generated}",
    ]
    return lines
