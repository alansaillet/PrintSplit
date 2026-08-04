"""Alignment markings drawn on every tile.

What ends up on a sheet, and why:

* **frame**        - the printable area of the sheet (thin grey).
* **crop marks**   - corner ticks so you can find that frame after cutting.
* **overlap band** - lightly shaded, with a dashed line at its far edge: this
  strip is duplicated on the neighbouring sheet.
* **cut line**     - solid-dashed red on the left/top edges that have a
  neighbour. Cut here and butt-join onto the previous sheet.
* **registration** - crosshairs sitting on round assembled coordinates. Both
  sheets sharing a band draw them at the *same real-world position*, so
  overlaying two sheets until the crosses coincide is exact alignment.
* **ticks**        - a 100 mm scale along the top/left frame, labelled with the
  assembled coordinate, so you can check any point with a tape measure.
* **ruler**        - a printed 500 mm bar: measure it. If it is not 500 mm the
  plotter rescaled the job and the whole print is wrong.
* **info panel**   - which sheet this is, where it goes, and the print settings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pymupdf as fitz

from .config import Config, dash_pattern, parse_color
from .layout import BoxMM, Layout, Tile
from .units import format_length, mm_to_pt, pt_to_mm

ARROWS = {"left": "<-", "right": "->", "top": "^", "bottom": "v"}


@dataclass
class SheetInfo:
    """Free-text facts shown in the info panel."""

    project: str
    scale_text: str
    sheet_text: str
    assembled_text: str
    generated: str = ""


class MarkPainter:
    """Draws the marks for one tile onto one PDF page."""

    #: preference order when a corner is chosen automatically
    CORNERS = ("bottom_left", "bottom_right", "top_left", "top_right")

    def __init__(
        self,
        page: fitz.Page,
        tile: Tile,
        layout: Layout,
        cfg: Config,
        info: SheetInfo,
        content_boxes: list | None = None,
    ) -> None:
        self.page = page
        self.tile = tile
        self.layout = layout
        self.cfg = cfg
        self.marks = cfg.marks
        self.info = info
        self.content_boxes = content_boxes or []
        self._taken_corners: set[str] = set()
        top, right, bottom, left = layout.margins_mm
        self.margin = {"top": top, "right": right, "bottom": bottom, "left": left}
        self.printable = fitz.Rect(
            mm_to_pt(left),
            mm_to_pt(top),
            mm_to_pt(layout.sheet_w_mm - right),
            mm_to_pt(layout.sheet_h_mm - bottom),
        )

    # -- coordinate mapping -------------------------------------------------- #

    def px(self, assembled_x_mm: float) -> float:
        """Assembled x (mm) -> page x (pt)."""
        return mm_to_pt(self.margin["left"] + assembled_x_mm - self.tile.window.x0)

    def py(self, assembled_y_mm: float) -> float:
        """Assembled y (mm) -> page y (pt)."""
        return mm_to_pt(self.margin["top"] + assembled_y_mm - self.tile.window.y0)

    def rect_of(self, box) -> fitz.Rect:
        return fitz.Rect(self.px(box.x0), self.py(box.y0), self.px(box.x1), self.py(box.y1))

    # -- primitives ---------------------------------------------------------- #

    def _line(self, p0, p1, color: str, width_mm: float, dash: str = "") -> None:
        self.page.draw_line(
            fitz.Point(*p0),
            fitz.Point(*p1),
            color=parse_color(color),
            width=mm_to_pt(width_mm),
            dashes=dash_pattern(dash),
        )

    def _text(
        self,
        x: float,
        y: float,
        text: str,
        size: float,
        color: str,
        rotate: int = 0,
        anchor: str = "start",
        font: str | None = None,
    ) -> None:
        font = font or self.marks.font
        if anchor != "start":
            length = fitz.get_text_length(text, fontname=font, fontsize=size)
            shift = length / 2.0 if anchor == "middle" else length
            if rotate == 0:
                x -= shift
            elif rotate == 90:
                y += shift
            elif rotate == 270:
                y -= shift
            else:
                x += shift
        self.page.insert_text(
            fitz.Point(x, y),
            text,
            fontname=font,
            fontsize=size,
            color=parse_color(color),
            rotate=rotate,
        )

    # -- background (drawn before the artwork) -------------------------------- #

    def draw_background(self) -> None:
        if not self.marks.enabled:
            return
        cfg = self.marks.overlap
        if not (cfg.enabled and cfg.shade):
            return
        for side, band in self._overlap_bands().items():
            self.page.draw_rect(
                band, color=None, fill=parse_color(cfg.shade_color), width=0
            )

    def _overlap_bands(self) -> dict[str, fitz.Rect]:
        """Page rects of the strips shared with a neighbour, per side."""
        overlap = self.layout.overlap_mm
        if overlap <= 0:
            return {}
        w = self.tile.window
        bands: dict[str, fitz.Rect] = {}
        has = self.tile.has
        if has["left"]:
            bands["left"] = fitz.Rect(
                self.px(w.x0), self.py(w.y0), self.px(w.x0 + overlap), self.py(w.y1)
            )
        if has["right"]:
            bands["right"] = fitz.Rect(
                self.px(w.x1 - overlap), self.py(w.y0), self.px(w.x1), self.py(w.y1)
            )
        if has["top"]:
            bands["top"] = fitz.Rect(
                self.px(w.x0), self.py(w.y0), self.px(w.x1), self.py(w.y0 + overlap)
            )
        if has["bottom"]:
            bands["bottom"] = fitz.Rect(
                self.px(w.x0), self.py(w.y1 - overlap), self.px(w.x1), self.py(w.y1)
            )
        return bands

    # -- foreground (drawn on top of the artwork) ----------------------------- #

    def draw_foreground(self) -> None:
        if not self.marks.enabled:
            return
        self._draw_frame()
        self._draw_crop_marks()
        self._draw_overlap_edges()
        self._draw_cut_lines()
        self._draw_registration()
        self._draw_ticks()
        self._draw_arrows()
        self._draw_ruler()
        self._draw_info_panel()

    def _draw_frame(self) -> None:
        cfg = self.marks.frame
        if not cfg.enabled:
            return
        self.page.draw_rect(
            self.printable,
            color=parse_color(cfg.color),
            width=mm_to_pt(cfg.line_width_mm),
        )

    def _draw_crop_marks(self) -> None:
        cfg = self.marks.crop
        if not cfg.enabled:
            return
        r = self.printable
        length = mm_to_pt(cfg.length_mm)
        corners = [
            ((r.x0, r.y0), (1, 0), (0, 1)),
            ((r.x1, r.y0), (-1, 0), (0, 1)),
            ((r.x0, r.y1), (1, 0), (0, -1)),
            ((r.x1, r.y1), (-1, 0), (0, -1)),
        ]
        for (cx, cy), dx, dy in corners:
            for vec in (dx, dy):
                self._line(
                    (cx, cy),
                    (cx + vec[0] * length, cy + vec[1] * length),
                    cfg.color,
                    cfg.line_width_mm,
                )

    def _draw_overlap_edges(self) -> None:
        """Dashed line at the far edge of each shared band (informational)."""
        cfg = self.marks.overlap
        if not cfg.enabled or self.layout.overlap_mm <= 0:
            return
        w = self.tile.window
        overlap = self.layout.overlap_mm
        has = self.tile.has
        if has["right"]:
            x = self.px(w.x1 - overlap)
            self._line((x, self.py(w.y0)), (x, self.py(w.y1)), cfg.color,
                       cfg.line_width_mm, cfg.dash)
        if has["bottom"]:
            y = self.py(w.y1 - overlap)
            self._line((self.px(w.x0), y), (self.px(w.x1), y), cfg.color,
                       cfg.line_width_mm, cfg.dash)

    def _draw_cut_lines(self) -> None:
        """Red dashed 'cut here' on the left/top edges that have a neighbour."""
        cfg = self.marks.cut
        if not cfg.enabled or self.layout.overlap_mm <= 0:
            return
        t = self.tile
        trim = t.trim
        if t.has["left"]:
            x = self.px(trim.x0)
            self._line((x, self.py(t.window.y0)), (x, self.py(t.window.y1)),
                       cfg.color, cfg.line_width_mm, cfg.dash)
            if cfg.label:
                self._text(
                    x - mm_to_pt(2.5),
                    self.py((t.window.y0 + t.window.y1) / 2),
                    f"CUT  |  overlaps {t.neighbours['left']}",
                    cfg.font_size_pt,
                    cfg.color,
                    rotate=90,
                    anchor="middle",
                )
        if t.has["top"]:
            y = self.py(trim.y0)
            self._line((self.px(t.window.x0), y), (self.px(t.window.x1), y),
                       cfg.color, cfg.line_width_mm, cfg.dash)
            if cfg.label:
                self._text(
                    self.px((t.window.x0 + t.window.x1) / 2),
                    y - mm_to_pt(2.5),
                    f"CUT  |  overlaps {t.neighbours['top']}",
                    cfg.font_size_pt,
                    cfg.color,
                    anchor="middle",
                )

    # -- registration --------------------------------------------------------- #

    def _join_lines(self) -> tuple[list[float], list[float]]:
        """Assembled coordinates of the centre lines of the shared bands."""
        w = self.tile.window
        half = self.layout.overlap_mm / 2.0
        has = self.tile.has
        xs = []
        ys = []
        if has["left"]:
            xs.append(w.x0 + half)
        if has["right"]:
            xs.append(w.x1 - half)
        if has["top"]:
            ys.append(w.y0 + half)
        if has["bottom"]:
            ys.append(w.y1 - half)
        return xs, ys

    def _cross(self, x_mm: float, y_mm: float, cfg, target: bool = False) -> None:
        x, y = self.px(x_mm), self.py(y_mm)
        half = mm_to_pt(cfg.size_mm) / 2.0
        self._line((x - half, y), (x + half, y), cfg.color, cfg.line_width_mm)
        self._line((x, y - half), (x, y + half), cfg.color, cfg.line_width_mm)
        if cfg.circle:
            radius = mm_to_pt(cfg.circle_radius_mm) * (1.6 if target else 1.0)
            self.page.draw_circle(
                fitz.Point(x, y),
                radius,
                color=parse_color(cfg.color),
                width=mm_to_pt(cfg.line_width_mm),
            )
        if target:
            self.page.draw_circle(
                fitz.Point(x, y),
                mm_to_pt(cfg.line_width_mm) * 1.6,
                color=None,
                fill=parse_color(cfg.color),
                width=0,
            )

    def _draw_registration(self) -> None:
        cfg = self.marks.registration
        if not cfg.enabled:
            return
        w = self.tile.window
        spacing = cfg.spacing_mm
        xs, ys = self._join_lines()
        inset = mm_to_pt(cfg.size_mm)

        def ladder(lo: float, hi: float) -> list[float]:
            """Assembled coordinates that are multiples of the spacing."""
            start = math.ceil(lo / spacing - 1e-9)
            stop = math.floor(hi / spacing + 1e-9)
            return [i * spacing for i in range(start, stop + 1)]

        for jx in xs:
            for y in ladder(w.y0, w.y1):
                if self.py(y) - self.printable.y0 < inset or self.printable.y1 - self.py(y) < inset:
                    continue
                self._cross(jx, y, cfg)
                if cfg.label:
                    self._text(
                        self.px(jx) + mm_to_pt(cfg.size_mm) * 0.6,
                        self.py(y) - mm_to_pt(1.0),
                        f"y {format_length(y, 'm')}",
                        cfg.font_size_pt,
                        cfg.color,
                    )
        for jy in ys:
            for x in ladder(w.x0, w.x1):
                if self.px(x) - self.printable.x0 < inset or self.printable.x1 - self.px(x) < inset:
                    continue
                self._cross(x, jy, cfg)
                if cfg.label:
                    self._text(
                        self.px(x) + mm_to_pt(1.5),
                        self.py(jy) - mm_to_pt(cfg.size_mm) * 0.6,
                        f"x {format_length(x, 'm')}",
                        cfg.font_size_pt,
                        cfg.color,
                    )
        if cfg.corner_targets:
            for jx in xs:
                for jy in ys:
                    self._cross(jx, jy, cfg, target=True)

    # -- measuring aids -------------------------------------------------------- #

    def _draw_ticks(self) -> None:
        cfg = self.marks.ticks
        if not cfg.enabled or cfg.step_mm <= 0:
            return
        w = self.tile.window
        length = mm_to_pt(cfg.length_mm)

        start = math.ceil(w.x0 / cfg.step_mm - 1e-9)
        stop = math.floor(w.x1 / cfg.step_mm + 1e-9)
        for i in range(start, stop + 1):
            value = i * cfg.step_mm
            major = i % cfg.long_every == 0
            x = self.px(value)
            self._line((x, self.printable.y0), (x, self.printable.y0 + length * (2 if major else 1)),
                       cfg.color, cfg.line_width_mm)
            if major:
                self._text(x + mm_to_pt(1.0), self.printable.y0 + length * 2 + mm_to_pt(2.5),
                           format_length(value, cfg.units), cfg.font_size_pt, cfg.color)

        start = math.ceil(w.y0 / cfg.step_mm - 1e-9)
        stop = math.floor(w.y1 / cfg.step_mm + 1e-9)
        for i in range(start, stop + 1):
            value = i * cfg.step_mm
            major = i % cfg.long_every == 0
            y = self.py(value)
            self._line((self.printable.x0, y), (self.printable.x0 + length * (2 if major else 1), y),
                       cfg.color, cfg.line_width_mm)
            if major:
                self._text(self.printable.x0 + length * 2 + mm_to_pt(1.5), y - mm_to_pt(1.0),
                           format_length(value, cfg.units), cfg.font_size_pt, cfg.color)

    @property
    def exclusive(self) -> BoxMM:
        """The part of the sheet no neighbour shares.

        Blocks placed here survive both assembly styles: they are not on a strip
        that gets cut off, and not under a sheet laid on top.
        """
        w = self.tile.window
        o = self.layout.overlap_mm
        has = self.tile.has
        return BoxMM(
            w.x0 + (o if has["left"] else 0.0),
            w.y0 + (o if has["top"] else 0.0),
            w.x1 - (o if has["right"] else 0.0),
            w.y1 - (o if has["bottom"] else 0.0),
        )

    def _corner_box_mm(self, corner: str, w_mm: float, h_mm: float, offset_mm: float):
        """Where a block of this size would sit, in assembled mm."""
        trim = self.exclusive
        if corner.endswith("left"):
            x0 = trim.x0 + offset_mm
            x1 = x0 + w_mm
        else:
            x1 = trim.x1 - offset_mm
            x0 = x1 - w_mm
        if corner.startswith("top"):
            y0 = trim.y0 + offset_mm
            y1 = y0 + h_mm
        else:
            y1 = trim.y1 - offset_mm
            y0 = y1 - h_mm
        return BoxMM(x0, y0, x1, y1)

    def _artwork_in(self, box: BoxMM) -> float:
        """Total artwork area (mm2) falling inside ``box`` -- used to keep the
        info panel and the ruler off the drawing."""
        total = 0.0
        for item in self.content_boxes:
            w = min(box.x1, item.x1) - max(box.x0, item.x0)
            h = min(box.y1, item.y1) - max(box.y0, item.y0)
            if w > 0 and h > 0:
                total += w * h
        return total

    def _pick_corner(self, corner: str, w_mm: float, h_mm: float, offset_mm: float) -> str:
        """Honour an explicit corner, or find the emptiest free one."""
        if corner != "auto":
            self._taken_corners.add(corner)
            return corner
        free = [c for c in self.CORNERS if c not in self._taken_corners] or list(self.CORNERS)
        best = min(free, key=lambda c: self._artwork_in(self._corner_box_mm(c, w_mm, h_mm, offset_mm)))
        self._taken_corners.add(best)
        return best

    def _corner_anchor(self, corner: str, offset_mm: float) -> tuple[float, float, int, int]:
        """Page point inside the sheet's exclusive area, plus x/y signs."""
        trim = self.rect_of(self.exclusive)
        offset = mm_to_pt(offset_mm)
        sx = 1 if corner.endswith("left") else -1
        sy = 1 if corner.startswith("top") else -1
        x = trim.x0 + offset if sx > 0 else trim.x1 - offset
        y = trim.y0 + offset if sy > 0 else trim.y1 - offset
        return x, y, sx, sy

    def _draw_ruler(self) -> None:
        cfg = self.marks.ruler
        if not cfg.enabled:
            return
        footprint = cfg.length_mm + cfg.height_mm
        corner = self._pick_corner(
            cfg.corner,
            footprint,
            footprint if cfg.both_axes else cfg.height_mm * 2,
            cfg.offset_mm,
        )
        x, y, sx, sy = self._corner_anchor(corner, cfg.offset_mm)
        length = mm_to_pt(cfg.length_mm)
        height = mm_to_pt(cfg.height_mm)
        color = parse_color(cfg.color)
        width = mm_to_pt(cfg.line_width_mm)
        divisions = max(1, int(round(cfg.length_mm / cfg.division_mm)))

        def bar(horizontal: bool) -> None:
            if horizontal:
                x0, x1 = (x, x + sx * length) if sx > 0 else (x - length, x)
                y0, y1 = (y, y + sy * height) if sy > 0 else (y - height, y)
            else:
                x0, x1 = (x, x + height) if sx > 0 else (x - height, x)
                y0, y1 = (y, y + length) if sy > 0 else (y - length, y)
            rect = fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            self.page.draw_rect(rect, color=color, width=width)
            for i in range(divisions):
                if i % 2 == 0:
                    continue
                if horizontal:
                    seg = fitz.Rect(
                        rect.x0 + rect.width * i / divisions, rect.y0,
                        rect.x0 + rect.width * (i + 1) / divisions, rect.y1,
                    )
                else:
                    seg = fitz.Rect(
                        rect.x0, rect.y0 + rect.height * i / divisions,
                        rect.x1, rect.y0 + rect.height * (i + 1) / divisions,
                    )
                self.page.draw_rect(seg, color=None, fill=color, width=0)
            return rect

        hrect = bar(True)
        caption = f"{cfg.length_mm:g} mm - measure me"
        self._text(
            hrect.x0,
            hrect.y0 - mm_to_pt(2.0) if sy < 0 else hrect.y1 + mm_to_pt(4.0),
            caption,
            cfg.font_size_pt,
            cfg.color,
        )
        if cfg.both_axes:
            bar(False)

    # -- annotations ------------------------------------------------------------ #

    def _draw_arrows(self) -> None:
        cfg = self.marks.arrows
        if not cfg.enabled:
            return
        t = self.tile
        w = t.window
        pad = mm_to_pt(6.0)
        mid_x = self.px((w.x0 + w.x1) / 2)
        mid_y = self.py((w.y0 + w.y1) / 2)
        if t.neighbours.get("right"):
            self._text(self.px(w.x1) - pad, mid_y, f"{t.neighbours['right']} ->",
                       cfg.font_size_pt, cfg.color, rotate=90, anchor="end")
        if t.neighbours.get("left"):
            self._text(self.px(w.x0) + pad + mm_to_pt(3), mid_y, f"<- {t.neighbours['left']}",
                       cfg.font_size_pt, cfg.color, rotate=90, anchor="start")
        if t.neighbours.get("top"):
            self._text(mid_x, self.py(w.y0) + pad + mm_to_pt(3), f"^ {t.neighbours['top']}",
                       cfg.font_size_pt, cfg.color, anchor="middle")
        if t.neighbours.get("bottom"):
            self._text(mid_x, self.py(w.y1) - pad, f"v {t.neighbours['bottom']}",
                       cfg.font_size_pt, cfg.color, anchor="middle")

    def _panel_lines(self) -> list[str]:
        t = self.tile
        lay = self.layout
        joins = "  ".join(
            f"{ARROWS[side]} {t.neighbours[side]}"
            for side in ("left", "right", "top", "bottom")
            if t.neighbours.get(side)
        )
        lines = [
            self.info.project,
            f"Sheet {t.index + 1} of {lay.sheet_count}   row {t.row + 1}/{lay.rows}"
            f"   column {t.col + 1}/{lay.cols}",
            self.info.scale_text,
            self.info.sheet_text,
            self.info.assembled_text,
            f"This sheet covers x {format_length(t.window.x0, 'm')} .. "
            f"{format_length(t.window.x1, 'm')} m,  y {format_length(t.window.y0, 'm')} .. "
            f"{format_length(t.window.y1, 'm')} m",
            f"Overlap {lay.overlap_mm:g} mm - cut the red dashed edges, butt-join,"
            f" or overlay on the crosshairs",
        ]
        if self.marks.label.show_neighbours and joins:
            lines.append(f"Neighbours: {joins}")
        if self.info.generated:
            lines.append(self.info.generated)
        return lines

    def _draw_info_panel(self) -> None:
        cfg = self.marks.label
        if not cfg.enabled:
            return
        lines = self._panel_lines()
        note = cfg.notes
        font = self.marks.font
        pad = mm_to_pt(4.0)
        leading = cfg.font_size_pt * 1.45
        title_h = cfg.title_font_size_pt * 1.0

        widths = [fitz.get_text_length(t, fontname=font, fontsize=cfg.font_size_pt) for t in lines]
        widths.append(fitz.get_text_length(note, fontname=font, fontsize=cfg.font_size_pt * 1.1))
        title_w = fitz.get_text_length(self.tile.label, fontname=font,
                                       fontsize=cfg.title_font_size_pt)
        body_w = max(widths) if widths else 0.0
        panel_w = max(body_w, 0.0) + title_w + pad * 3
        panel_h = max(title_h, len(lines) * leading + cfg.font_size_pt * 1.6) + pad * 2

        corner = self._pick_corner(
            cfg.corner, pt_to_mm(panel_w), pt_to_mm(panel_h), cfg.offset_mm
        )
        x, y, sx, sy = self._corner_anchor(corner, cfg.offset_mm)
        x0 = x if sx > 0 else x - panel_w
        y0 = y if sy > 0 else y - panel_h
        panel = fitz.Rect(x0, y0, x0 + panel_w, y0 + panel_h)

        if cfg.background:
            self.page.draw_rect(panel, color=None, fill=parse_color(cfg.background_color), width=0)
        if cfg.border:
            self.page.draw_rect(panel, color=parse_color(cfg.border_color), width=mm_to_pt(0.25))

        self._text(panel.x0 + pad, panel.y0 + pad + cfg.title_font_size_pt * 0.85,
                   self.tile.label, cfg.title_font_size_pt, cfg.color)

        text_x = panel.x0 + pad * 2 + title_w
        cursor = panel.y0 + pad + cfg.font_size_pt
        for line in lines:
            self._text(text_x, cursor, line, cfg.font_size_pt, cfg.color)
            cursor += leading
        self._text(text_x, cursor + cfg.font_size_pt * 0.3, note,
                   cfg.font_size_pt * 1.1, self.marks.cut.color)
