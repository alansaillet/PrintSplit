"""Automatic sanity checks, run on every job.

These are the checks that would otherwise be done by hand every time a new
drawing arrives. They are the difference between "the tool produced 36 sheets"
and "the tool produced 36 correct sheets", and none of them needs a human:

* Is the source page's content actually inside the page? (a stray path outside
  the media box is invisible in the PDF but would otherwise inflate the print)
* Is any text rotated? (a CAD export can emit upside-down dimension labels)
* How wide will the strokes really print?
* Does this drawing agree with its siblings' coordinate system? -- the check
  that catches a revision which silently moved geometry, and that confirms an
  undocumented drawing is at the same scale as a documented one.
* Did the finished PDF really get placed at an exact scale, with tile offsets
  matching the advance?

Findings are advisory. Nothing here stops a print; it just tells you what you
are about to spend paper on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

from .units import MM_PER_PT, PT_PER_MM, pt_to_mm

OK, NOTE, WARN = "ok", "note", "warn"
LEVEL_MARK = {OK: "  ok  ", NOTE: " note ", WARN: " WARN "}


@dataclass
class Finding:
    level: str
    check: str
    message: str

    def __str__(self) -> str:
        return f"[{LEVEL_MARK[self.level]}] {self.check:<18} {self.message}"


# --------------------------------------------------------------------------- #
# Source checks
# --------------------------------------------------------------------------- #


def _off_page(page: fitz.Page) -> tuple[int, float]:
    """Paths lying (partly) outside the media box, and the worst overshoot."""
    worst = 0.0
    count = 0
    for path in page.get_drawings():
        r = path["rect"]
        over = max(
            page.rect.x0 - r.x0, page.rect.y0 - r.y0,
            r.x1 - page.rect.x1, r.y1 - page.rect.y1,
        )
        if over > 0.01:
            count += 1
            worst = max(worst, over)
    return count, worst


def _rotated_text(page: fitz.Page) -> tuple[list[str], list[str]]:
    """Text that is not upright, split into (upside_down, sideways).

    Sideways text is normal -- that is how every CAD package labels a vertical
    dimension. Upside-down text is not, and is worth shouting about, because at
    1:1 on a floor it is simply unreadable.
    """
    upside_down: list[str] = []
    sideways: list[str] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type", 0) != 0:
            continue
        for line in block["lines"]:
            dx, dy = line["dir"]
            if abs(dx - 1.0) < 1e-6 and abs(dy) < 1e-6:
                continue
            angle = round(math.degrees(math.atan2(dy, dx)))
            text = "".join(s["text"] for s in line["spans"]).strip()
            entry = f"{text!r} at {angle}deg"
            if abs(abs(angle) - 180) < 15:
                upside_down.append(entry)
            else:
                sideways.append(entry)
    return upside_down, sideways


def geometry_points(doc: fitz.Document, page_no: int, magnification: float) -> set:
    """Path vertices in real-world millimetres, rounded to 1 mm."""
    scale = MM_PER_PT * magnification
    pts = set()
    for path in doc[page_no].get_drawings():
        for item in path["items"]:
            for obj in item[1:]:
                if isinstance(obj, fitz.Point):
                    pts.add((round(obj.x * scale), round(obj.y * scale)))
                elif isinstance(obj, fitz.Rect):
                    pts.add((round(obj.x0 * scale), round(obj.y0 * scale)))
                    pts.add((round(obj.x1 * scale), round(obj.y1 * scale)))
    return pts


def containment(a: set, b: set, tolerance: int = 1) -> float:
    """Fraction of ``a`` present in ``b`` at zero offset."""
    if not a:
        return 0.0
    offsets = [
        (dx, dy)
        for dx in range(-tolerance, tolerance + 1)
        for dy in range(-tolerance, tolerance + 1)
    ]
    hit = sum(
        1 for x, y in a if any((x + dx, y + dy) in b for dx, dy in offsets)
    )
    return hit / len(a)


def _siblings(source: Path) -> list[Path]:
    """Other PDFs sitting next to the source, newest last."""
    return sorted(
        p for p in source.parent.glob("*.pdf")
        if p.resolve() != source.resolve()
    )


def source_findings(result, compare: bool = True) -> list[Finding]:
    cfg = result.cfg
    doc = result.doc
    page_no = cfg.project.page - 1
    page = doc[page_no]
    out: list[Finding] = []

    if doc.page_count > 1:
        out.append(Finding(NOTE, "pages",
                           f"source has {doc.page_count} pages; tiling page "
                           f"{cfg.project.page}"))

    count, worst = _off_page(page)
    if count:
        out.append(Finding(
            NOTE, "off-page",
            f"{count} path(s) outside the page, up to {pt_to_mm(worst):.2f} mm "
            f"({pt_to_mm(worst) * result.magnification:.0f} mm printed). They are "
            f"invisible in the source too, and are excluded."))
    else:
        out.append(Finding(OK, "off-page", "all content is inside the page"))

    upside_down, sideways = _rotated_text(page)
    if upside_down:
        shown = "; ".join(upside_down[:3]) + (" ..." if len(upside_down) > 3 else "")
        out.append(Finding(
            WARN, "text rotation",
            f"{len(upside_down)} text line(s) are UPSIDE DOWN: {shown}. This is in "
            f"the source, not the tiling; it will print that way."))
    elif sideways:
        out.append(Finding(
            OK, "text rotation",
            f"{len(sideways)} sideways label(s) (normal for vertical dimensions), "
            f"none upside down"))
    else:
        out.append(Finding(OK, "text rotation", "all text is upright"))

    widths = {
        round((p.get("width") or 0.0) * result.magnification * MM_PER_PT, 2)
        for p in page.get_drawings()
        if p["type"] in ("s", "fs")
    }
    widths.discard(0.0)
    if widths:
        lo, hi = min(widths), max(widths)
        level = WARN if hi > 5.0 else OK
        note = "  <- set [lines] to thin these" if level == WARN else ""
        out.append(Finding(level, "stroke width",
                           f"printed {lo:g} .. {hi:g} mm{note}"))

    lay = result.layout
    blanks = lay.total_cells - sum(1 for t in lay.tiles if not t.blank)
    if blanks and not cfg.tiling.skip_blank_tiles:
        labels = ", ".join(t.label for t in lay.tiles if t.blank)
        out.append(Finding(NOTE, "blank sheets",
                           f"{blanks} sheet(s) have no artwork ({labels}); printed "
                           f"anyway as spacers. skip_blank_tiles=true drops them."))

    if lay.sheet_count >= 20:
        out.append(Finding(NOTE, "size",
                           f"{lay.sheet_count} sheets = {lay.paper_area_m2:.0f} m2 of "
                           f"paper. target_scale = 2.0 would quarter that."))

    if compare:
        out += _compare_with_siblings(result)
    return out


def _compare_with_siblings(result) -> list[Finding]:
    """Does this drawing share its siblings' coordinate system?"""
    out: list[Finding] = []
    others = _siblings(result.source_path)
    if not others:
        return out
    mine = geometry_points(result.doc, result.cfg.project.page - 1, result.magnification)
    if not mine:
        return out
    best = []
    for path in others:
        try:
            doc = fitz.open(path)
        except Exception:
            continue
        theirs = geometry_points(doc, 0, result.magnification)
        doc.close()
        if not theirs:
            continue
        best.append((containment(mine, theirs), containment(theirs, mine), path.name))
    if not best:
        return out
    # Agreement is symmetric: a big drawing containing a small one agrees with
    # it just as much as the small one agrees with the big one.
    best.sort(key=lambda t: max(t[0], t[1]), reverse=True)
    for into, back, name in best[:4]:
        if into >= 0.98:
            level, verdict = OK, f"is fully contained in {name}"
        elif back >= 0.98:
            level, verdict = OK, f"fully contains {name}"
        elif max(into, back) >= 0.5:
            level, verdict = OK, f"shares the coordinate system of {name}"
        else:
            level, verdict = NOTE, f"has little in common with {name}"
        out.append(Finding(
            level, "vs sibling",
            f"this drawing {verdict} at zero offset "
            f"({into*100:.1f}% of mine in theirs, {back*100:.1f}% of theirs in mine)"))
    if max(max(into, back) for into, back, _ in best) < 0.5:
        out.append(Finding(
            WARN, "vs sibling",
            "no sibling shares this drawing's coordinates. If it should be the "
            "same machine at the same scale, check scale.source_scale."))
    return out


# --------------------------------------------------------------------------- #
# Output checks
# --------------------------------------------------------------------------- #


def output_findings(pdf_path: Path, result) -> list[Finding]:
    """Re-open the finished PDF and prove it came out right."""
    out: list[Finding] = []
    mag = result.magnification
    lay = result.layout
    doc = fitz.open(pdf_path)
    matrices: dict[int, tuple] = {}
    bad_scale = []
    for n in range(doc.page_count):
        for xref, name, *_ in ((x[0], x[1]) for x in doc[n].get_xobjects()):
            if not str(name).startswith("fzFrm"):
                continue
            kind, value = doc.xref_get_key(xref, "Matrix")
            if kind != "array":
                continue
            a, b, c, d, e, f = (float(v) for v in value.strip("[]").split())
            matrices[n] = (a, b, c, d, e, f)
            if (abs(a - mag) > 1e-6 or abs(d - mag) > 1e-6
                    or abs(b) > 1e-9 or abs(c) > 1e-9):
                bad_scale.append(n + 1)
    doc.close()

    if not matrices:
        out.append(Finding(NOTE, "placement", "no artwork placed (all sheets blank?)"))
        return out
    if bad_scale:
        out.append(Finding(WARN, "placement",
                           f"pages {bad_scale} are not placed at exactly x{mag:g}"))
    else:
        out.append(Finding(OK, "placement",
                           f"all {len(matrices)} page(s) placed at exactly "
                           f"[{mag:g} 0 0 {mag:g}] - no distortion, no rasterising"))

    # Tile-to-tile offsets must equal the advance.
    printed = [t for t in lay.tiles if not t.blank]
    by_cell = {(t.row, t.col): t.index for t in printed}
    worst = 0.0
    checked = 0
    for (row, col), index in by_cell.items():
        for drow, dcol, step_mm, axis in (
            (0, 1, lay.step_w_mm, 4), (1, 0, lay.step_h_mm, 5)
        ):
            other = by_cell.get((row + drow, col + dcol))
            if other is None or index not in matrices or other not in matrices:
                continue
            delta = matrices[other][axis] - matrices[index][axis]
            # x advances negatively on the page, y positively (PDF y is up)
            expected = -step_mm * PT_PER_MM if axis == 4 else step_mm * PT_PER_MM
            worst = max(worst, abs(delta - expected) * MM_PER_PT)
            checked += 1
    if checked:
        level = OK if worst < 0.01 else WARN
        out.append(Finding(level, "tile offsets",
                           f"{checked} neighbour pair(s) match the advance to "
                           f"{worst:.5f} mm"))
    return out


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "  (no checks run)"
    return "\n".join("  " + str(f) for f in findings)


def worst_level(findings: list[Finding]) -> str:
    for level in (WARN, NOTE, OK):
        if any(f.level == level for f in findings):
            return level
    return OK
