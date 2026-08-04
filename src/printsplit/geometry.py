"""Finding the drawing inside the source page.

A CAD export is usually a small drawing floating on a big sheet, often with a
title block or a page border.  Tiling the *page* would waste sheets, so we tile
the *content bounding box* instead: the union of every vector path, text block
and image on the page.

All rectangles here are in PyMuPDF page coordinates: PDF points, origin at the
top-left of the page, y increasing downwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf as fitz

from .config import Config
from .errors import SourceError
from .units import PT_PER_MM, pt_to_mm


@dataclass
class ContentBox:
    """The area of the source page that will be printed."""

    rect: fitz.Rect  # what gets tiled (detected box + padding)
    detected: fitz.Rect  # the raw detected box, before padding
    page_rect: fitz.Rect
    items: list[fitz.Rect] = field(default_factory=list)  # for blank-tile detection
    mode: str = "auto"
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def width_mm(self) -> float:
        return pt_to_mm(self.rect.width)

    @property
    def height_mm(self) -> float:
        return pt_to_mm(self.rect.height)


# A horizontal or vertical line has a zero-height / zero-width bounding box, and
# a CAD drawing is mostly such lines.  fitz treats those rects as "empty", so we
# must never filter on is_empty -- we give them a hair of thickness instead.
HAIR_PT = 0.01


def _grow(rect: fitz.Rect, amount: float) -> fitz.Rect:
    return fitz.Rect(
        rect.x0 - amount, rect.y0 - amount, rect.x1 + amount, rect.y1 + amount
    )


def _undegenerate(rect: fitz.Rect) -> fitz.Rect:
    """Give a zero-width/height rect enough extent to survive rect algebra."""
    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
    if x1 - x0 < HAIR_PT:
        mid = (x0 + x1) / 2.0
        x0, x1 = mid - HAIR_PT / 2, mid + HAIR_PT / 2
    if y1 - y0 < HAIR_PT:
        mid = (y0 + y1) / 2.0
        y0, y1 = mid - HAIR_PT / 2, mid + HAIR_PT / 2
    return fitz.Rect(x0, y0, x1, y1)


def _clamp(rect: fitz.Rect, bounds: fitz.Rect) -> fitz.Rect | None:
    """Clip to ``bounds`` without using rect algebra (which drops flat rects)."""
    x0 = max(rect.x0, bounds.x0)
    y0 = max(rect.y0, bounds.y0)
    x1 = min(rect.x1, bounds.x1)
    y1 = min(rect.y1, bounds.y1)
    if x1 < x0 or y1 < y0:
        return None
    return fitz.Rect(x0, y0, x1, y1)


def _is_page_frame(rect: fitz.Rect, page: fitz.Rect, tolerance_pt: float) -> bool:
    """True if the item is (nearly) the whole page: a border box, not artwork."""
    return (
        rect.width >= page.width - tolerance_pt
        and rect.height >= page.height - tolerance_pt
    )


def collect_items(page: fitz.Page, cfg: Config) -> list[fitz.Rect]:
    """Bounding boxes of everything drawn on the page, honouring the filters."""
    src = cfg.source
    tolerance_pt = src.page_frame_tolerance_mm * PT_PER_MM
    items: list[fitz.Rect] = []

    if src.include_drawings:
        for path in page.get_drawings():
            rect = fitz.Rect(path["rect"])
            if rect.is_infinite:
                continue
            if src.stroke_aware and path.get("type") in ("s", "fs"):
                # A stroke straddles the path, so half its width sticks out.
                rect = _grow(rect, (path.get("width") or 0.0) / 2.0)
            items.append(_undegenerate(rect))

    if src.include_text:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type", 0) != 0:  # 0 = text, 1 = image
                continue
            rect = fitz.Rect(block["bbox"])
            if not rect.is_infinite:
                items.append(_undegenerate(rect))

    if src.include_images:
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                rect = fitz.Rect(rect)
                if not rect.is_infinite:
                    items.append(_undegenerate(rect))

    if src.drop_page_frame:
        items = [r for r in items if not _is_page_frame(r, page.rect, tolerance_pt)]

    # Clip everything to the visible page; content outside it will not print.
    clipped = []
    for rect in items:
        inside = _clamp(rect, page.rect)
        if inside is not None:
            clipped.append(inside)
    return clipped


def content_box(page: fitz.Page, cfg: Config) -> ContentBox:
    """Determine the region of ``page`` to tile."""
    src = cfg.source
    items = collect_items(page, cfg)
    counts = {
        "drawings": len(page.get_drawings()) if src.include_drawings else 0,
        "text_blocks": sum(
            1 for b in page.get_text("dict")["blocks"] if b.get("type", 0) == 0
        )
        if src.include_text
        else 0,
        "images": len(page.get_images(full=True)) if src.include_images else 0,
        "items_used": len(items),
    }

    if src.bbox_mode == "page":
        detected = fitz.Rect(page.rect)
    elif src.bbox_mode == "manual":
        x0, y0, x1, y1 = src.manual_bbox_mm
        detected = fitz.Rect(
            x0 * PT_PER_MM, y0 * PT_PER_MM, x1 * PT_PER_MM, y1 * PT_PER_MM
        )
    else:
        if not items:
            raise SourceError(
                "no drawable content found on the page; use source.bbox_mode = "
                '"page" or "manual" to tile it anyway'
            )
        detected = fitz.Rect(items[0])
        for rect in items[1:]:
            detected |= rect

    if detected.width <= 0 or detected.height <= 0:
        raise SourceError("the detected content bounding box has no area")

    # Padding is specified in printed millimetres, so divide by the magnification
    # to get back to source-page points.
    mag = cfg.scale.magnification
    rect = _grow(detected, src.padding_mm * PT_PER_MM / mag)

    if src.round_up_to_mm > 0:
        step_pt = src.round_up_to_mm * PT_PER_MM / mag
        for axis in ("width", "height"):
            size = getattr(rect, axis)
            target = step_pt * (int(size / step_pt - 1e-9) + 1)
            extra = (target - size) / 2.0
            if axis == "width":
                rect = fitz.Rect(rect.x0 - extra, rect.y0, rect.x1 + extra, rect.y1)
            else:
                rect = fitz.Rect(rect.x0, rect.y0 - extra, rect.x1, rect.y1 + extra)

    return ContentBox(
        rect=rect,
        detected=detected,
        page_rect=fitz.Rect(page.rect),
        items=items,
        mode=src.bbox_mode,
        counts=counts,
    )
