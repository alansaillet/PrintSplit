#!/usr/bin/env python
"""Generate examples/sample_drawing.pdf -- a synthetic 1:20 foundation plan.

A stand-in for the real thing: an A4 sheet carrying a 2400 x 1200 mm base
plate with six anchor pads, drawn at 1:20, so `config/example.toml` has
something to tile without shipping anyone's actual drawings.

Deterministic: running it twice produces the same geometry.

    python examples/make_sample_drawing.py
"""

from pathlib import Path

import pymupdf as fitz

SCALE = 20.0  # the drawing is 1:20
PT_PER_MM = 72.0 / 25.4
LINE_PT = 0.6  # a normal CAD line weight
THIN_PT = 0.35

PLATE_W, PLATE_H = 2400.0, 1200.0  # real millimetres
PAD_W, PAD_H = 200.0, 140.0
PITCH = 800.0  # anchor pad spacing, centre to centre

OUT = Path(__file__).resolve().parent / "sample_drawing.pdf"


def main() -> Path:
    page_w, page_h = 297.0 * PT_PER_MM, 210.0 * PT_PER_MM  # A4 landscape
    doc = fitz.open()
    page = doc.new_page(width=page_w, height=page_h)

    # real millimetres -> page points, centred on the sheet
    span_w, span_h = PLATE_W / SCALE * PT_PER_MM, PLATE_H / SCALE * PT_PER_MM
    ox, oy = (page_w - span_w) / 2, (page_h - span_h) / 2

    def X(mm: float) -> float:
        return ox + mm / SCALE * PT_PER_MM

    def Y(mm: float) -> float:
        return oy + mm / SCALE * PT_PER_MM

    black = (0, 0, 0)

    # base plate outline
    page.draw_rect(
        fitz.Rect(X(0), Y(0), X(PLATE_W), Y(PLATE_H)), color=black, width=LINE_PT
    )

    # six anchor pads: two rows of three, on a PITCH grid
    for row in range(2):
        for col in range(3):
            cx = 400.0 + col * PITCH
            cy = 300.0 + row * 600.0
            rect = fitz.Rect(
                X(cx - PAD_W / 2), Y(cy - PAD_H / 2),
                X(cx + PAD_W / 2), Y(cy + PAD_H / 2),
            )
            page.draw_rect(rect, color=black, width=LINE_PT)
            # hatching
            step = rect.width / 5
            for i in range(1, 9):
                x0 = rect.x0 + i * step - rect.height
                page.draw_line(
                    fitz.Point(max(x0, rect.x0), rect.y1 - max(0.0, rect.x0 - x0)),
                    fitz.Point(min(x0 + rect.height, rect.x1),
                               rect.y1 - min(rect.height, rect.x1 - x0)),
                    color=black, width=THIN_PT,
                )
            # bolt hole at the centre
            page.draw_circle(
                fitz.Point(X(cx), Y(cy)), 20.0 / SCALE * PT_PER_MM,
                color=black, width=THIN_PT,
            )

    # dimension chain along the top: 3 x 800
    dim_y = Y(-140.0)
    for col in range(3):
        x0, x1 = X(400.0 + col * PITCH - PITCH / 2), X(400.0 + col * PITCH + PITCH / 2)
        page.draw_line(fitz.Point(x0, dim_y), fitz.Point(x1, dim_y),
                       color=black, width=THIN_PT)
        for x in (x0, x1):
            page.draw_line(fitz.Point(x, dim_y - 4), fitz.Point(x, dim_y + 4),
                           color=black, width=THIN_PT)
        label = f"{PITCH:.0f}"
        width = fitz.get_text_length(label, fontname="helv", fontsize=5)
        page.insert_text(fitz.Point((x0 + x1) / 2 - width / 2, dim_y - 3),
                         label, fontname="helv", fontsize=5, color=black)

    # overall dimension down the left
    dim_x = X(-160.0)
    page.draw_line(fitz.Point(dim_x, Y(0)), fitz.Point(dim_x, Y(PLATE_H)),
                   color=black, width=THIN_PT)
    page.insert_text(fitz.Point(dim_x - 3, (Y(0) + Y(PLATE_H)) / 2),
                     f"{PLATE_H:.0f}", fontname="helv", fontsize=5,
                     color=black, rotate=90)

    page.insert_text(fitz.Point(X(0), Y(PLATE_H) + 22),
                     "SAMPLE BASE PLATE  -  scale 1:20  -  all dimensions in mm",
                     fontname="helv", fontsize=6, color=black)

    doc.set_metadata({"title": "PrintSplit sample drawing (1:20)",
                      "creator": "examples/make_sample_drawing.py"})
    doc.save(OUT, deflate=True, garbage=3)
    doc.close()
    print(f"wrote {OUT}  ({PLATE_W:.0f} x {PLATE_H:.0f} mm at 1:{SCALE:.0f})")
    return OUT


if __name__ == "__main__":
    main()
