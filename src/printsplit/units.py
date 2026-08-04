"""Unit conversions and standard paper sizes.

Everything in PrintSplit is either in millimetres (human facing: config files and
"assembled sheet" coordinates) or in PDF points (1/72 inch, the native unit of
the PDF itself).  Conversions live here so no other module has to remember the
magic number 25.4.
"""

from __future__ import annotations

from .errors import ConfigError

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
PT_PER_MM = PT_PER_INCH / MM_PER_INCH  # 2.834645669...
MM_PER_PT = MM_PER_INCH / PT_PER_INCH  # 0.352777...


def mm_to_pt(value_mm: float) -> float:
    """Millimetres -> PDF points."""
    return value_mm * PT_PER_MM


def pt_to_mm(value_pt: float) -> float:
    """PDF points -> millimetres."""
    return value_pt * MM_PER_PT


# ISO 216 A/B series plus a few oversized formats, portrait (width, height) in mm.
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "4A0": (1682.0, 2378.0),
    "2A0": (1189.0, 1682.0),
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "B0": (1000.0, 1414.0),
    "B1": (707.0, 1000.0),
    "B2": (500.0, 707.0),
    "LETTER": (215.9, 279.4),
    "LEGAL": (215.9, 355.6),
    "ARCH_D": (609.6, 914.4),
    "ARCH_E": (914.4, 1219.2),
}


def paper_size_mm(name: str, orientation: str = "portrait") -> tuple[float, float]:
    """Return (width, height) in mm for a named paper size.

    ``orientation`` is ``"portrait"`` or ``"landscape"``.
    """
    key = name.strip().upper().replace("-", "_")
    if key not in PAPER_SIZES_MM:
        raise ConfigError(
            f"unknown paper size {name!r}; known sizes: {', '.join(sorted(PAPER_SIZES_MM))}"
        )
    width, height = PAPER_SIZES_MM[key]
    if orientation == "landscape":
        return height, width
    return width, height


def format_length(value_mm: float, units: str = "m") -> str:
    """Format a distance for on-sheet coordinate labels."""
    if units == "m":
        return f"{value_mm / 1000.0:.2f}"
    if units == "cm":
        return f"{value_mm / 10.0:.1f}"
    return f"{value_mm:.0f}"
