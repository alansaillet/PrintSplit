"""Human-readable report of what was produced.

Printed to the console and, when ``output.report`` is on, saved next to the
PDFs so the numbers behind a print job survive the print job.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .config import Config
from .units import pt_to_mm

RULE = "-" * 78


def build(result) -> str:
    cfg: Config = result.cfg
    lay = result.layout
    content = result.content
    out: list[str] = []
    add = out.append

    add(RULE)
    add(f"PrintSplit {__version__}   {result.generated}")
    add(f"Project        : {cfg.project.name}")
    add(f"Config         : {cfg.config_path}")
    add(RULE)

    add("SOURCE")
    add(f"  file         : {result.source_path}")
    add(f"  page         : {cfg.project.page}  (rotation {result.source_rotation} deg)")
    add(
        f"  page size    : {pt_to_mm(content.page_rect.width):.1f} x "
        f"{pt_to_mm(content.page_rect.height):.1f} mm"
    )
    add(
        f"  content bbox : mode '{content.mode}'  "
        f"x {pt_to_mm(content.detected.x0):.2f} .. {pt_to_mm(content.detected.x1):.2f} mm, "
        f"y {pt_to_mm(content.detected.y0):.2f} .. {pt_to_mm(content.detected.y1):.2f} mm"
    )
    add(
        f"                 {pt_to_mm(content.detected.width):.2f} x "
        f"{pt_to_mm(content.detected.height):.2f} mm on paper"
    )
    add(
        f"  items used   : {content.counts.get('items_used', 0)} "
        f"({content.counts.get('drawings', 0)} vector paths, "
        f"{content.counts.get('text_blocks', 0)} text blocks, "
        f"{content.counts.get('images', 0)} images)"
    )
    if cfg.source.padding_mm:
        add(
            f"  padding      : {cfg.source.padding_mm:g} mm of printed paper on every side"
        )
    add(
        f"  tiled region : {content.width_mm:.2f} x {content.height_mm:.2f} mm of the "
        f"source page"
    )
    add("")

    add("SCALE")
    add(f"  drawing is   : 1:{cfg.scale.source_scale:g}")
    add(f"  printed at   : 1:{cfg.scale.target_scale:g}")
    add(f"  magnification: x{result.magnification:g}")
    add(
        f"  real size    : {result.assembled_w_mm / 1000:.3f} x "
        f"{result.assembled_h_mm / 1000:.3f} m "
        f"({result.assembled_w_mm:.1f} x {result.assembled_h_mm:.1f} mm)"
    )
    add("")

    add("LINE WIDTHS")
    lines = cfg.lines
    if lines.mode == "keep":
        add("  mode         : keep - the drawing's own weights, magnified with it")
    elif lines.mode == "fixed":
        add(f"  mode         : fixed - every stroke printed {lines.width_mm:g} mm wide")
    else:
        add(f"  mode         : scale - printed weights multiplied by {lines.scale:g}")
    if lines.min_width_mm or lines.max_width_mm:
        add(
            f"  clamped to   : {lines.min_width_mm:g} .. "
            f"{lines.max_width_mm or float('inf'):g} mm"
        )
    add(
        f"  applied to   : {result.strokes_seen} stroke operations "
        f"({result.strokes_reweighted} width change(s) injected; one covers every "
        f"following stroke in the same state)"
    )
    if lines.mode == "keep" and not (lines.min_width_mm or lines.max_width_mm):
        add(
            f"  note         : at x{result.magnification:g} a 0.25 mm line prints "
            f"{0.25 * result.magnification:.0f} mm wide"
        )
    add("")

    add("SHEETS")
    add(
        f"  paper        : {cfg.sheet.size} {lay.orientation}  "
        f"{lay.sheet_w_mm:g} x {lay.sheet_h_mm:g} mm"
    )
    add(
        f"  margins      : top {lay.margins_mm[0]:g}, right {lay.margins_mm[1]:g}, "
        f"bottom {lay.margins_mm[2]:g}, left {lay.margins_mm[3]:g} mm"
    )
    add(f"  printable    : {lay.usable_w_mm:g} x {lay.usable_h_mm:g} mm")
    add(f"  overlap      : {lay.overlap_mm:g} mm")
    add(f"  advance      : {lay.step_w_mm:g} x {lay.step_h_mm:g} mm per sheet")
    add(f"  grid         : {lay.cols} columns x {lay.rows} rows")
    skipped = lay.total_cells - lay.sheet_count
    add(
        f"  sheets       : {lay.sheet_count} to print"
        + (f"  ({skipped} blank cell(s) skipped)" if skipped else "")
    )
    add(f"  paper area   : {lay.paper_area_m2:.2f} m2")
    add("")

    add("TILES  (coverage of the assembled drawing, metres)")
    add(f"  {'sheet':<8}{'page':>5}  {'x from':>8}{'x to':>9}  {'y from':>8}{'y to':>9}")
    for tile in lay.tiles:
        page_no = "-" if tile.blank else str(tile.index + 1)
        add(
            f"  {tile.label:<8}{page_no:>5}  "
            f"{tile.window.x0 / 1000:>8.3f}{tile.window.x1 / 1000:>9.3f}  "
            f"{tile.window.y0 / 1000:>8.3f}{tile.window.y1 / 1000:>9.3f}"
            + ("   (blank, not printed)" if tile.blank else "")
        )
    add("")

    add("OUTPUT")
    for label, path in (
        ("tiles", result.tiles_pdf),
        ("assembly map", result.overview_pdf),
        ("report", result.report_txt),
    ):
        if path:
            add(f"  {label:<13}: {path}")
    for path in result.per_tile_pdfs:
        add(f"  {'tile':<13}: {path}")
    add("")

    if result.findings:
        from .audit import format_findings
        add("CHECKS")
        add(format_findings(result.findings))
        add("")

    add("HOW TO PRINT")
    add("  1. Print at 100% / actual size. Turn OFF 'fit to page' and 'shrink to")
    add("     printable area' in the printer dialog.")
    add(f"  2. Measure the {cfg.marks.ruler.length_mm:g} mm ruler on the first sheet.")
    add("     If it is off, the printer rescaled the job - fix that before printing")
    add("     the rest.")
    add("  3. Cut each sheet along the red dashed lines (its left and top edges),")
    add("     then butt-join it to the sheet named on that edge.")
    add("     Or: keep the overlap, lay the sheets on top of each other so the blue")
    add("     crosshairs coincide, and tape.")
    add("  4. The assembly map shows which sheet goes where.")
    add(RULE)
    return "\n".join(out)


def write(result) -> Path:
    cfg: Config = result.cfg
    out_dir = cfg.resolve(cfg.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cfg.project.output_basename}_report.txt"
    result.report_txt = path
    path.write_text(build(result), encoding="utf-8")
    return path
