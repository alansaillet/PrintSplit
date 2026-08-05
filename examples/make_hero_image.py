#!/usr/bin/env python
"""Build docs/hero.png -- the picture at the top of the README.

Everything in it is real output: the sample drawing on the left, the sheets
PrintSplit actually produced butt-joined on the right, and two crops taken
straight from one of those sheets. Nothing is mocked up, so the picture cannot
drift away from what the tool does.

Sized for GitHub, which renders a README image into a column about 900 px wide.
The canvas is exactly twice that, and one point here is one pixel, so every
type size below is simply double what it measures on screen -- which is why
they look large in the source and read correctly in the browser.

    python examples/make_hero_image.py
"""

from __future__ import annotations

import math
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

W, H = 1800, 1330  # canvas; 1 pt == 1 px, shown at ~900 px on GitHub
MARGIN = 56
TOP_Y = 196
PANEL_H = 470
PANEL_W = 1010  # the assembled-result panel
BAND_Y = 768

# Type sizes are doubled on purpose: halve them to get the on-screen size.
T_LABEL, T_HEAD, T_CAPTION = 23, 44, 25
T_CROP_TITLE, T_CROP_SUB, T_ARROW, T_SHEET = 31, 24, 40, 26

INK = (0.141, 0.161, 0.184)
MUTED = (0.341, 0.376, 0.416)
ACCENT = (0.122, 0.435, 0.922)
EDGE = (0.816, 0.843, 0.867)
PAPER = (1, 1, 1)


def text(page, x, y, s, size=T_CAPTION, color=INK, bold=False, anchor="start"):
    font = "hebo" if bold else "helv"
    if anchor != "start":
        length = fitz.get_text_length(s, fontname=font, fontsize=size)
        x -= length / 2 if anchor == "middle" else length
    page.insert_text(fitz.Point(x, y), s, fontname=font, fontsize=size, color=color)


def card(page, rect, shadow=8):
    """A page-shaped card: soft shadow, white fill, hairline edge."""
    page.draw_rect(
        fitz.Rect(rect.x0 + shadow, rect.y0 + shadow, rect.x1 + shadow, rect.y1 + shadow),
        color=None, fill=(0.55, 0.58, 0.62), fill_opacity=0.22, width=0,
    )
    page.draw_rect(rect, color=EDGE, fill=PAPER, width=1)


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
    page.draw_line(fitz.Point(x0, y), fitz.Point(x1 - 17, y), color=ACCENT, width=4)
    page.draw_polyline(
        [fitz.Point(x1, y), fitz.Point(x1 - 19, y - 11), fitz.Point(x1 - 19, y + 11)],
        color=ACCENT, fill=ACCENT, width=1,
    )
    text(page, (x0 + x1) / 2, y - 22, label, T_ARROW, ACCENT, bold=True, anchor="middle")


def crosshair_point(job, tile) -> fitz.Point:
    """Page position of a registration crosshair on this tile's left joint."""
    lay = job.layout
    top, _, _, left = lay.margins_mm
    spacing = job.cfg.marks.registration.spacing_mm
    jx = tile.window.x0 + lay.overlap_mm / 2
    first = math.ceil(tile.window.y0 / spacing - 1e-9)
    y = next(
        (k * spacing for k in range(first, first + 8)
         if k * spacing <= tile.window.y1 and k * spacing - tile.window.y0 > 120),
        (tile.window.y0 + tile.window.y1) / 2,
    )
    return fitz.Point((left + jx - tile.window.x0) * PT_PER_MM,
                      (top + y - tile.window.y0) * PT_PER_MM)


def draw_assembled(page, box, tiles, job):
    """The sheets butt-joined, exactly as they go together on the floor.

    Each sheet contributes its trim rectangle -- what is left after cutting the
    overlap away -- so the pieces meet edge to edge and rebuild the drawing.
    Showing it assembled rather than as a row of thumbnails is the only way the
    drawing itself stays legible once GitHub halves the image.
    """
    lay = job.layout
    top, _, _, left = lay.margins_mm
    trims = [t.trim for t in lay.tiles]
    x0, y0 = min(t.x0 for t in trims), min(t.y0 for t in trims)
    x1, y1 = max(t.x1 for t in trims), max(t.y1 for t in trims)

    target = fit(box, (x1 - x0) / (y1 - y0))
    scale = target.width / (x1 - x0)
    card(page, target)

    def to_canvas(mx, my):
        return target.x0 + (mx - x0) * scale, target.y0 + (my - y0) * scale

    for tile in lay.tiles:
        if tile.blank:
            continue
        trim = tile.trim
        clip = fitz.Rect(
            (left + trim.x0 - tile.window.x0) * PT_PER_MM,
            (top + trim.y0 - tile.window.y0) * PT_PER_MM,
            (left + trim.x1 - tile.window.x0) * PT_PER_MM,
            (top + trim.y1 - tile.window.y0) * PT_PER_MM,
        )
        cx0, cy0 = to_canvas(trim.x0, trim.y0)
        cx1, cy1 = to_canvas(trim.x1, trim.y1)
        page.show_pdf_page(fitz.Rect(cx0, cy0, cx1, cy1), tiles, tile.index,
                           clip=clip, keep_proportion=False)

    for tile in lay.tiles:  # the joins, and a name on every sheet
        cx0, cy0 = to_canvas(tile.trim.x0, tile.trim.y0)
        cx1, cy1 = to_canvas(tile.trim.x1, tile.trim.y1)
        page.draw_rect(fitz.Rect(cx0, cy0, cx1, cy1), color=ACCENT, width=1.6,
                       dashes="[7 5] 0")
        text(page, cx0 + 13, cy0 + 34, tile.label, T_SHEET, ACCENT, bold=True)
    page.draw_rect(target, color=EDGE, width=1)
    return target


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
            width_m, height_m = job.assembled_w_mm / 1000, job.assembled_h_mm / 1000
            magnification = job.magnification
            detail_tile = next(
                (t for t in lay.tiles if t.row > 0 and t.col > 0 and not t.blank),
                lay.tiles[-1],
            )
            cross = crosshair_point(job, detail_tile)

            src = fitz.open(HERE / "sample_drawing.pdf")
            tiles = fitz.open(job.tiles_pdf)
            detail_page = tiles[detail_tile.index]

            doc = fitz.open()
            page = doc.new_page(width=W, height=H)
            page.draw_rect(page.rect, color=None, fill=PAPER, width=0)

            # ---- the assembled result ---------------------------------- #
            panel_x0 = W - MARGIN - PANEL_W
            panel = draw_assembled(
                page, fitz.Rect(panel_x0, TOP_Y, W - MARGIN, TOP_Y + PANEL_H),
                tiles, job,
            )

            # ---- the drawing it came from ------------------------------ #
            src_aspect = src[0].rect.width / src[0].rect.height
            src_rect = fit(
                fitz.Rect(MARGIN, TOP_Y, panel_x0 - 150, TOP_Y + PANEL_H), src_aspect
            )
            card(page, src_rect)
            page.show_pdf_page(src_rect + (10, 10, -10, -10), src, 0,
                               keep_proportion=True)

            text(page, MARGIN, TOP_Y - 62, "ONE A4 DRAWING", T_LABEL, MUTED, bold=True)
            text(page, MARGIN, TOP_Y - 22, "drawn 1:20", T_HEAD, INK, bold=True)
            text(page, MARGIN, src_rect.y1 + 44,
                 "297 x 210 mm  -  too small to build from", T_CAPTION, MUTED)

            arrow(page, src_rect.x1 + 40, panel_x0 - 38,
                  (src_rect.y0 + src_rect.y1) / 2, f"x{int(magnification)}")

            text(page, panel_x0, TOP_Y - 62, "PRINTED AT 1:1", T_LABEL, ACCENT, bold=True)
            text(page, panel_x0, TOP_Y - 22,
                 f"{lay.sheet_count} x {cfg.sheet.size}, assembled", T_HEAD, INK,
                 bold=True)
            text(page, panel_x0, panel.y1 + 44,
                 f"{width_m:.2f} x {height_m:.2f} m  -  cut the dashed joins, butt "
                 f"them together, and it is exact", T_CAPTION, MUTED)

            # ---- two crops from one real sheet -------------------------- #
            page.draw_line(fitz.Point(MARGIN, BAND_Y), fitz.Point(W - MARGIN, BAND_Y),
                           color=EDGE, width=1)
            text(page, MARGIN, BAND_Y + 46, "ON EVERY SHEET", T_LABEL, MUTED, bold=True)

            cw = (W - 2 * MARGIN - 56) / 2
            ch = cw * 0.40
            cy0 = BAND_Y + 78

            def window(cx, cy, width):
                height = width * ch / cw
                return fitz.Rect(cx - width / 2, cy - height / 2,
                                 cx + width / 2, cy + height / 2)

            note = detail_page.search_for("PRINT AT 100%")
            crops = [
                (window(cross.x + 34, cross.y, 340),
                 "Cut line, overlap, crosshairs",
                 "the crosshair lands on the same real-world point on both sheets"),
                (window(note[0].x0 + 165, note[0].y0 - 40, 720) if note
                 else window(500, detail_page.rect.height - 400, 720),
                 "Sheet identity",
                 "which sheet it is, where it goes, how to print it"),
            ]
            for i, (clip, title, sub) in enumerate(crops):
                bx = MARGIN + i * (cw + 56)
                box = fitz.Rect(bx, cy0, bx + cw, cy0 + ch)
                card(page, box, shadow=6)
                page.show_pdf_page(box + (1, 1, -1, -1), tiles, detail_tile.index,
                                   clip=clip, keep_proportion=False)
                text(page, box.x0, box.y1 + 46, title, T_CROP_TITLE, INK, bold=True)
                text(page, box.x0, box.y1 + 78, sub, T_CROP_SUB, MUTED)

            text(page, W - MARGIN, H - 30,
                 "PrintSplit  -  github.com/alansaillet/PrintSplit", T_CROP_SUB,
                 MUTED, anchor="end")

            OUT.parent.mkdir(parents=True, exist_ok=True)
            doc[0].get_pixmap(dpi=72).save(OUT)
            for d in (doc, src, tiles):
                d.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} kB, {W}x{H} px)")
    return OUT


if __name__ == "__main__":
    main()
