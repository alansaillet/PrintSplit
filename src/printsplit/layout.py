"""Tiling arithmetic.

This module is deliberately free of PDF concepts: it works purely in
"assembled millimetres" -- the coordinate system of the finished, taped-together
drawing, origin at its top-left corner, x right, y down.  That makes the
geometry unit-testable without touching a PDF.

Convention for the overlap
--------------------------
Neighbouring sheets share a band of ``overlap_mm``.  Every sheet is cut along
its *left* and *top* edge (where a neighbour exists), then butt-joined onto the
sheet to its left / above::

    sheet A1 covers  [a, a+usable]
    sheet B1 covers  [a+step, a+step+usable]   with step = usable - overlap

    cutting B1 at its own x0+overlap makes it start exactly where A1 ends.

The same marks also support the tape-and-overlay workflow: keep the strip and
line up the registration crosses instead, since those sit on identical assembled
coordinates on both sheets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import Config, margins_mm
from .errors import LayoutError
from .units import paper_size_mm

EPS = 1e-6


@dataclass(frozen=True)
class BoxMM:
    """An axis-aligned rectangle in assembled millimetres (y down)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def intersects(self, other: "BoxMM") -> bool:
        """Overlap test, inclusive of touching edges.

        Inclusive on purpose: this decides whether a sheet is blank, and the
        safe error is to print a sheet that turns out to be nearly empty rather
        than to skip one that had a line right on its edge.
        """
        return (
            self.x0 <= other.x1 + EPS
            and other.x0 <= self.x1 + EPS
            and self.y0 <= other.y1 + EPS
            and other.y0 <= self.y1 + EPS
        )


@dataclass
class Tile:
    """One printed sheet."""

    row: int  # 0-based, top to bottom
    col: int  # 0-based, left to right
    label: str
    window: BoxMM  # what this sheet shows, in assembled mm (= its printable area)
    trim: BoxMM  # cut here, then butt-join
    neighbours: dict[str, str | None] = field(default_factory=dict)
    blank: bool = False
    index: int = 0  # page order

    @property
    def has(self) -> dict[str, bool]:
        return {side: self.neighbours.get(side) is not None for side in
                ("left", "right", "top", "bottom")}


@dataclass
class Layout:
    rows: int
    cols: int
    orientation: str
    sheet_w_mm: float
    sheet_h_mm: float
    margins_mm: tuple[float, float, float, float]  # top, right, bottom, left
    usable_w_mm: float
    usable_h_mm: float
    overlap_mm: float
    step_w_mm: float
    step_h_mm: float
    assembled_w_mm: float
    assembled_h_mm: float
    origin_mm: tuple[float, float]  # assembled coords of the grid's top-left corner
    tiles: list[Tile] = field(default_factory=list)

    @property
    def sheet_count(self) -> int:
        return sum(1 for t in self.tiles if not t.blank)

    @property
    def total_cells(self) -> int:
        return self.rows * self.cols

    @property
    def paper_area_m2(self) -> float:
        return self.sheet_count * self.sheet_w_mm * self.sheet_h_mm / 1e6


def column_label(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    label = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        label = chr(ord("A") + rem) + label
    return label


def tile_label(row: int, col: int, style: str, cols: int) -> str:
    if style == "R1C1":
        return f"R{row + 1}C{col + 1}"
    if style == "index":
        return str(row * cols + col + 1)
    return f"{column_label(col)}{row + 1}"


def _tiles_needed(total: float, usable: float, overlap: float) -> int:
    """How many sheets to cover ``total`` mm with ``usable`` mm sheets."""
    if usable <= 0:
        raise LayoutError("sheet margins leave no printable area")
    if total <= usable + EPS:
        return 1
    step = usable - overlap
    if step <= EPS:
        raise LayoutError(
            f"tiling.overlap_mm ({overlap:g} mm) is not smaller than the printable "
            f"sheet size ({usable:g} mm) -- the tiles would never advance"
        )
    return int(math.ceil((total - overlap) / step - EPS))


def _grid_for(
    assembled_w: float,
    assembled_h: float,
    sheet_w: float,
    sheet_h: float,
    margins: tuple[float, float, float, float],
    overlap: float,
) -> tuple[int, int, float, float]:
    top, right, bottom, left = margins
    usable_w = sheet_w - left - right
    usable_h = sheet_h - top - bottom
    cols = _tiles_needed(assembled_w, usable_w, overlap)
    rows = _tiles_needed(assembled_h, usable_h, overlap)
    return rows, cols, usable_w, usable_h


def build(cfg: Config, assembled_w_mm: float, assembled_h_mm: float) -> Layout:
    """Work out the sheet grid for a drawing of the given assembled size."""
    margins = margins_mm(cfg.sheet)
    overlap = cfg.tiling.overlap_mm

    if cfg.sheet.size.lower() == "custom":
        base_w, base_h = cfg.sheet.custom_size_mm
    else:
        base_w, base_h = paper_size_mm(cfg.sheet.size, "portrait")

    candidates: list[tuple[str, float, float]] = []
    if cfg.sheet.orientation in ("auto", "portrait"):
        candidates.append(("portrait", base_w, base_h))
    if cfg.sheet.orientation in ("auto", "landscape"):
        candidates.append(("landscape", base_h, base_w))

    best = None
    for orientation, sheet_w, sheet_h in candidates:
        rows, cols, usable_w, usable_h = _grid_for(
            assembled_w_mm, assembled_h_mm, sheet_w, sheet_h, margins, overlap
        )
        waste = rows * cols * sheet_w * sheet_h - assembled_w_mm * assembled_h_mm
        # Fewest sheets wins; then least wasted paper; then the orientation whose
        # shape matches the drawing, which is what a human would have picked.
        mismatch = int((sheet_w >= sheet_h) != (assembled_w_mm >= assembled_h_mm))
        key = (rows * cols, waste, mismatch)
        if best is None or key < best[0]:
            best = (key, orientation, sheet_w, sheet_h, rows, cols, usable_w, usable_h)

    assert best is not None
    _, orientation, sheet_w, sheet_h, rows, cols, usable_w, usable_h = best

    if rows * cols > cfg.tiling.max_sheets:
        raise LayoutError(
            f"this job needs {rows * cols} sheets, over tiling.max_sheets="
            f"{cfg.tiling.max_sheets}. Check scale.source_scale / sheet.size, or "
            f"raise the limit."
        )

    step_w = usable_w - overlap if cols > 1 else usable_w
    step_h = usable_h - overlap if rows > 1 else usable_h
    covered_w = usable_w + (cols - 1) * step_w
    covered_h = usable_h + (rows - 1) * step_h

    if cfg.tiling.center_content:
        ox = -(covered_w - assembled_w_mm) / 2.0
        oy = -(covered_h - assembled_h_mm) / 2.0
    else:
        ox = oy = 0.0

    layout = Layout(
        rows=rows,
        cols=cols,
        orientation=orientation,
        sheet_w_mm=sheet_w,
        sheet_h_mm=sheet_h,
        margins_mm=margins,
        usable_w_mm=usable_w,
        usable_h_mm=usable_h,
        overlap_mm=overlap,
        step_w_mm=step_w,
        step_h_mm=step_h,
        assembled_w_mm=assembled_w_mm,
        assembled_h_mm=assembled_h_mm,
        origin_mm=(ox, oy),
    )

    style = cfg.tiling.label_style
    grid: list[list[Tile]] = []
    for row in range(rows):
        line: list[Tile] = []
        for col in range(cols):
            x0 = ox + col * step_w
            y0 = oy + row * step_h
            window = BoxMM(x0, y0, x0 + usable_w, y0 + usable_h)
            trim = BoxMM(
                x0 + (overlap if col > 0 else 0.0),
                y0 + (overlap if row > 0 else 0.0),
                window.x1,
                window.y1,
            )
            line.append(
                Tile(row=row, col=col, label=tile_label(row, col, style, cols),
                     window=window, trim=trim)
            )
        grid.append(line)

    for row in range(rows):
        for col in range(cols):
            tile = grid[row][col]
            tile.neighbours = {
                "left": grid[row][col - 1].label if col > 0 else None,
                "right": grid[row][col + 1].label if col < cols - 1 else None,
                "top": grid[row - 1][col].label if row > 0 else None,
                "bottom": grid[row + 1][col].label if row < rows - 1 else None,
            }

    if cfg.tiling.page_order == "column_major":
        ordered = [grid[r][c] for c in range(cols) for r in range(rows)]
    else:
        ordered = [grid[r][c] for r in range(rows) for c in range(cols)]
    for i, tile in enumerate(ordered):
        tile.index = i
    layout.tiles = ordered
    return layout


def mark_blank_tiles(layout: Layout, content_boxes: list[BoxMM]) -> None:
    """Flag tiles whose window contains no artwork at all."""
    for tile in layout.tiles:
        tile.blank = not any(tile.window.intersects(box) for box in content_boxes)
