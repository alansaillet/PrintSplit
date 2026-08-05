#!/usr/bin/env python
"""Build docs/hero.png -- the picture at the top of the README.

Everything in it is real output: the sample drawing on the left, the sheets
PrintSplit actually produced on the right, and three crops taken straight from
one of those sheets along the bottom. Nothing is mocked up, so the picture
cannot drift away from what the tool does.

    python examples/make_hero_image.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pymupdf as fitz

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "src"))

import printsplit  # noqa: E402

OUT = REPO / "docs" / "hero.png"
PT_PER_MM = 72.0 / 25.4

W, H = 1600, 1150  # canvas, points == pixels at 72 dpi
MARGIN = 44
TOP_Y = 152  # where the two top panels start
TOP_H = 430  # how tall the sheet grid is allowed to be
BAND_Y = 672  # the rule above the detail crops
CROP_W, CROP_H = 240.0, 157.0  # clip taken from a real sheet, in points
INK = (0.141, 0.161, 0.184)  # #24292f
MUTED = (0.341, 0.376, 0.416)  # #57606a
ACCENT = (0.122, 0.435, 0.922)  # #1f6feb
EDGE = (0.816, 0.843, 0.867)  # #d0d7de
PAPER = (1, 1, 1)


def text(page, x, y, s, size=13, color=INK, bold=False, anchor="start"):
    font = "hebo" if bold else "helv"
    if anchor != "start":
        length = fitz.get_text_length(s, fontname=font, fontsize=size)
        x -= length / 2 if anchor == "middle" else length
    page.insert_text(fitz.Point(x, y), s, fontname=font, fontsize=size, color=color)


def sheet(page, rect, shadow=6):
    """A page-shaped card: soft shadow, white fill, hairline edge."""
    page.draw_rect(
        fitz.Rect(rect.x0 + shadow, rect.y0 + shadow, rect.x1 + shadow, rect.y1 + shadow),
        color=None, fill=(0.55, 0.58, 0.62), fill_opacity=0.22, width=0,
    )
    page.draw_rect(rect, color=EDGE, fill=PAPER, width=0.8)


def fit(box: fitz.Rect, aspect: float) -> fitz.Rect:
    """Largest rect of the given w/h ratio, centred in ``box``."""
    w, h = box.width, box.height
    if w / h > aspect:
        w = h * aspect
    else:
        h = w / aspect
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    return fitz.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def arrow(page, x0, x1, y, label):
    page.draw_line(fitz.Point(x0, y), fitz.Point(x1 - 13, y), color=ACCENT, width=2.4)
    page.draw_polyline(
        [fitz.Point(x1, y), fitz.Point(x1 - 14, y - 8), fitz.Point(x1 - 14, y + 8)],
        color=ACCENT, fill=ACCENT, width=1,
    )
    text(page, (x0 + x1) / 2, y - 16, label, 17, ACCENT, bold=True, anchor="middle")


def crosshair_point(job, tile) -> fitz.Point:
    """Page position of a registration crosshair on this tile's left joint."""
    import math

    lay = job.layout
    top, _, _, left = lay.margins_mm
    spacing = job.cfg.marks.registration.spacing_mm
    jx = tile.window.x0 + lay.overlap_mm / 2
    first = math.ceil(tile.window.y0 / spacing - 1e-9)
    y = None
    for k in range(first, first + 8):
        candidate = k * spacing
        if candidate > tile.window.y1:
            break
        if candidate - tile.window.y0 > 120:  # clear of the top edge
            y = candidate
            break
    y = y if y is not None else (tile.window.y0 + tile.window.y1) / 2
    return fitz.Point(
        (left + jx - tile.window.x0) * PT_PER_MM,
        (top + y - tile.window.y0) * PT_PER_MM,
    )


def main() -> Path:
    if not (HERE / "sample_drawing.pdf").is_file():
        from make_sample_drawing import main as make_sample

        make_sample()

    work = Path(tempfile.mkdtemp(prefix="printsplit-hero-"))
    try:
        cfg = printsplit.load_config(REPO / "config" / "example.toml")
        cfg.project.output_dir = str(work)
        with printsplit.plan(cfg) as job:
            overview = printsplit.build_overview(job)
            printsplit.render(job, overview)
            overview.close()
            lay = job.layout
            tiles_pdf = job.tiles_pdf
            width_m = job.assembled_w_mm / 1000
            height_m = job.assembled_h_mm / 1000
            # a tile with a neighbour above and to the left, so it shows joints
            detail_tile = next(
                (t for t in lay.tiles if t.row > 0 and t.col > 0 and not t.blank),
                lay.tiles[-1],
            )
            cross = crosshair_point(job, detail_tile)

        src = fitz.open(HERE / "sample_drawing.pdf")
        tiles = fitz.open(tiles_pdf)
        detail_page = tiles[detail_tile.index]

        doc = fitz.open()
        page = doc.new_page(width=W, height=H)
        page.draw_rect(page.rect, color=None, fill=PAPER, width=0)

        # ---- top: the drawing, an arrow, the sheets ------------------------ #
        # Size the sheet grid to the space available, then give the drawing the rest.
        cols, rows = lay.cols, lay.rows
        gap = 11
        tile_aspect = lay.sheet_w_mm / lay.sheet_h_mm
        th = (TOP_H - gap * (rows - 1)) / rows
        tw = th * tile_aspect
        grid_w = tw * cols + gap * (cols - 1)
        grid_h = th * rows + gap * (rows - 1)
        grid_x0 = W - MARGIN - grid_w
        grid_y0 = TOP_Y

        src_aspect = src[0].rect.width / src[0].rect.height
        src_rect = fit(
            fitz.Rect(MARGIN, TOP_Y, grid_x0 - 120, TOP_Y + TOP_H), src_aspect
        )
        sheet(page, src_rect)
        page.show_pdf_page(src_rect + (8, 8, -8, -8), src, 0, keep_proportion=True)

        text(page, MARGIN, TOP_Y - 48, "ONE A4 DRAWING", 12, MUTED, bold=True)
        text(page, MARGIN, TOP_Y - 22, "drawn 1:20", 19, INK, bold=True)
        text(page, MARGIN, src_rect.y1 + 30,
             "297 x 210 mm  -  too small to build from", 12, MUTED)

        arrow(page, src_rect.x1 + 32, grid_x0 - 30,
              (src_rect.y0 + src_rect.y1) / 2, f"x{int(job.magnification)}")

        for tile in lay.tiles:
            if tile.blank:
                continue
            x0 = grid_x0 + tile.col * (tw + gap)
            y0 = grid_y0 + tile.row * (th + gap)
            rect = fitz.Rect(x0, y0, x0 + tw, y0 + th)
            sheet(page, rect, shadow=5)
            page.show_pdf_page(rect + (1, 1, -1, -1), tiles, tile.index,
                               keep_proportion=True)

        text(page, grid_x0, TOP_Y - 48, "PRINTED AT 1:1", 12, ACCENT, bold=True)
        text(page, grid_x0, TOP_Y - 22,
             f"{lay.sheet_count} x {cfg.sheet.size} {lay.orientation}", 19, INK, bold=True)
        text(page, grid_x0, grid_y0 + grid_h + 30,
             f"{width_m:.2f} x {height_m:.2f} m assembled  -  "
             f"{lay.overlap_mm:g} mm overlap, aligned to the millimetre", 12, MUTED)

        # ---- bottom: three crops, all at the same zoom, from one real sheet -- #
        page.draw_line(fitz.Point(MARGIN, BAND_Y), fitz.Point(W - MARGIN, BAND_Y),
                       color=EDGE, width=1)
        text(page, MARGIN, BAND_Y + 32, "ON EVERY SHEET", 12, MUTED, bold=True)

        def window(cx: float, cy: float, width: float) -> fitz.Rect:
            """A crop centred on a feature, always the card's aspect ratio.

            Widths differ per feature on purpose -- a 45 pt crosshair and a
            500 mm ruler do not read at the same zoom.
            """
            height = width * CROP_H / CROP_W
            return fitz.Rect(cx - width / 2, cy - height / 2,
                             cx + width / 2, cy + height / 2)

        note = detail_page.search_for("PRINT AT 100%")
        panel_clip = (window(note[0].x0 + 175, note[0].y0 - 42, 640)
                      if note else window(400, detail_page.rect.height - 300, 640))
        crops = [
            (fitz.Rect(0, 0, CROP_W, CROP_H),
             "Cut line and overlap",
             "cut the red dashes, butt-join the neighbour"),
            (window(cross.x + 26, cross.y, 210),
             "Registration crosshairs",
             "the same real-world point on both sheets"),
            (panel_clip,
             "Sheet identity",
             "which sheet it is, where it goes, how to print it"),
        ]

        cw = (W - 2 * MARGIN - 2 * 34) / 3
        ch = cw * CROP_H / CROP_W
        cy0 = BAND_Y + 56
        for i, (clip, title, sub) in enumerate(crops):
            x0 = MARGIN + i * (cw + 34)
            box = fitz.Rect(x0, cy0, x0 + cw, cy0 + ch)
            sheet(page, box, shadow=4)
            page.show_pdf_page(box + (1, 1, -1, -1), tiles, detail_tile.index,
                               clip=clip, keep_proportion=True)
            text(page, box.x0, box.y1 + 28, title, 14.5, INK, bold=True)
            text(page, box.x0, box.y1 + 48, sub, 11.5, MUTED)

        text(page, W - MARGIN, H - 24,
             "PrintSplit  -  github.com/alansaillet/PrintSplit", 11, MUTED, anchor="end")

        OUT.parent.mkdir(parents=True, exist_ok=True)
        doc[0].get_pixmap(dpi=96).save(OUT)
        for d in (doc, src, tiles):
            d.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} kB)")
    return OUT


if __name__ == "__main__":
    main()
