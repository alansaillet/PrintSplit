#!/usr/bin/env python
"""Generate examples/sample_drawing.pdf -- a synthetic 1:20 foundation plan.

A stand-in for the real thing: an A4 sheet carrying a 2400 x 1200 mm machine
base with a rotary table, anchor pads, a cable channel and dimension chains,
drawn at 1:20 -- so `config/example.toml` has something realistic to tile
without shipping anyone's actual drawings.

Deterministic: running it twice produces the same geometry.

    python examples/make_sample_drawing.py
"""

from math import cos, pi, sin
from pathlib import Path

import pymupdf as fitz

SCALE = 20.0  # the drawing is 1:20
PT_PER_MM = 72.0 / 25.4
HEAVY, LINE, THIN = 0.8, 0.55, 0.3  # CAD line weights, in points

PLATE_W, PLATE_H = 2400.0, 1200.0  # real millimetres
PAD_W, PAD_H = 200.0, 140.0
PITCH = 600.0  # anchor pad spacing, centre to centre
TABLE_R = 380.0  # rotary table radius
BOLT_R = 300.0  # bolt circle radius
CHANNEL_H = 80.0  # cable channel depth

OUT = Path(__file__).resolve().parent / "sample_drawing.pdf"
BLACK = (0, 0, 0)


def main() -> Path:
    page_w, page_h = 297.0 * PT_PER_MM, 210.0 * PT_PER_MM  # A4 landscape
    doc = fitz.open()
    page = doc.new_page(width=page_w, height=page_h)

    span_w, span_h = PLATE_W / SCALE * PT_PER_MM, PLATE_H / SCALE * PT_PER_MM
    ox, oy = (page_w - span_w) / 2, (page_h - span_h) / 2 + 6

    def X(mm: float) -> float:
        return ox + mm / SCALE * PT_PER_MM

    def Y(mm: float) -> float:
        return oy + mm / SCALE * PT_PER_MM

    def line(x0, y0, x1, y1, width=LINE, dashes=None):
        page.draw_line(fitz.Point(X(x0), Y(y0)), fitz.Point(X(x1), Y(y1)),
                       color=BLACK, width=width, dashes=dashes)

    def rect(x0, y0, x1, y1, width=LINE, dashes=None):
        page.draw_rect(fitz.Rect(X(x0), Y(y0), X(x1), Y(y1)),
                       color=BLACK, width=width, dashes=dashes)

    def circle(cx, cy, r, width=THIN, dashes=None):
        page.draw_circle(fitz.Point(X(cx), Y(cy)), r / SCALE * PT_PER_MM,
                         color=BLACK, width=width, dashes=dashes)

    def label(x, y, s, size=5, rotate=0):
        page.insert_text(fitz.Point(x, y), s, fontname="helv", fontsize=size,
                         color=BLACK, rotate=rotate)

    # --- base plate outline, with its machined inset ----------------------- #
    rect(0, 0, PLATE_W, PLATE_H, HEAVY)
    rect(60, 60, PLATE_W - 60, PLATE_H - 60, THIN, "[3 3] 0")

    # --- rotary table: rim, bolt circle, centre lines ---------------------- #
    cx, cy = PLATE_W / 2, PLATE_H / 2
    circle(cx, cy, TABLE_R, LINE)
    circle(cx, cy, TABLE_R - 45, THIN)
    circle(cx, cy, BOLT_R, THIN, "[6 3 1 3] 0")
    for i in range(8):
        a = i * pi / 4
        circle(cx + BOLT_R * cos(a), cy + BOLT_R * sin(a), 22.0, THIN)
    line(cx - TABLE_R - 90, cy, cx + TABLE_R + 90, cy, THIN, "[8 3 1 3] 0")
    line(cx, cy - TABLE_R - 90, cx, cy + TABLE_R + 90, THIN, "[8 3 1 3] 0")

    # --- anchor pads: two rows of four, hatched ---------------------------- #
    for row in range(2):
        for col in range(4):
            px = 300.0 + col * PITCH
            py = 170.0 + row * (PLATE_H - 340.0)
            x0, y0 = px - PAD_W / 2, py - PAD_H / 2
            rect(x0, y0, x0 + PAD_W, y0 + PAD_H, LINE)
            # 45-degree hatching, entry and exit clipped to the pad edges
            step = 34.0
            off = step
            while off < PAD_W + PAD_H:
                sx, sy = ((x0 + off, y0) if off <= PAD_W
                          else (x0 + PAD_W, y0 + off - PAD_W))
                ex, ey = ((x0, y0 + off) if off <= PAD_H
                          else (x0 + off - PAD_H, y0 + PAD_H))
                line(sx, sy, ex, ey, THIN)
                off += step
            circle(px, py, 24.0, THIN)

    # --- cable channel along the bottom ------------------------------------ #
    rect(400, PLATE_H - CHANNEL_H - 20, PLATE_W - 400, PLATE_H - 20, LINE)
    for i in range(14):
        x = 400 + (i + 1) * (PLATE_W - 800) / 15
        line(x, PLATE_H - CHANNEL_H - 20, x, PLATE_H - 20, THIN)

    # --- dimension chains --------------------------------------------------- #
    def dim_h(x0: float, x1: float, y: float, text: str) -> None:
        line(x0, y, x1, y, THIN)
        for x in (x0, x1):
            line(x, y - 26, x, y + 26, THIN)
        width = fitz.get_text_length(text, fontname="helv", fontsize=5)
        label((X(x0) + X(x1)) / 2 - width / 2, Y(y) - 4, text)

    for col in range(4):
        dim_h(300.0 + col * PITCH - PITCH / 2, 300.0 + col * PITCH + PITCH / 2,
              -95.0, f"{PITCH:.0f}")
    dim_h(0, PLATE_W, -175.0, f"{PLATE_W:.0f}")

    line(-150, 0, -150, PLATE_H, THIN)
    for y in (0.0, PLATE_H):
        line(-176, y, -124, y, THIN)
    label(X(-150) - 4, (Y(0) + Y(PLATE_H)) / 2, f"{PLATE_H:.0f}", rotate=90)

    label(X(0), Y(PLATE_H) + 13,
          "SAMPLE MACHINE BASE  -  scale 1:20  -  dimensions in mm", size=6)

    doc.set_metadata({"title": "PrintSplit sample drawing (1:20)",
                      "creator": "examples/make_sample_drawing.py"})
    doc.save(OUT, deflate=True, garbage=3)
    doc.close()
    print(f"wrote {OUT}  ({PLATE_W:.0f} x {PLATE_H:.0f} mm at 1:{SCALE:.0f})")
    return OUT


if __name__ == "__main__":
    main()
