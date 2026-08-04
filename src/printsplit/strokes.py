"""Re-weighting the drawing's line widths.

Magnifying a drawing magnifies its strokes with it: a 0.72 pt line on a 1:60
drawing becomes 43 pt -- 15 mm -- when printed 1:1.  That is both ugly and
imprecise, because a 15 mm wide line is a 15 mm wide answer to "where exactly
does this plate edge go?".

This module rewrites the page's content stream so the strokes come out at a
width you choose, in printed millimetres.

Why it is not a search-and-replace on ``w``
-------------------------------------------
In PDF, the line width set by ``w`` is in *user space*, and it is the CTM in
effect **when the path is stroked** that scales it -- not the CTM when ``w`` was
executed.  CAD exports routinely do::

    6 w  0 -0.12 .12 0 0 595 cm  ...  S      -> a 0.72 pt line, not a 6 pt one

So we tokenise the stream, track the graphics state (``q``/``Q``/``cm``/``gs``),
and inject a corrected ``w`` immediately before every stroking operator, where
the CTM is finally known.
"""

from __future__ import annotations

import math
import re
from typing import Callable, Iterator

import pymupdf as fitz

from .units import MM_PER_PT, PT_PER_MM

WHITESPACE = b"\x00\t\n\x0c\r "
DELIMITERS = b"()<>[]{}/%"
NUMBER_RE = re.compile(rb"^[+-]?(?:\d+\.?\d*|\.\d+)$")
STROKE_OPS = {b"S", b"s", b"B", b"B*", b"b", b"b*"}
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
WHITESPACE_SET = {WHITESPACE[k : k + 1] for k in range(len(WHITESPACE))}
DELIM_SET = {DELIMITERS[k : k + 1] for k in range(len(DELIMITERS))}
_BREAK = WHITESPACE_SET | DELIM_SET


# --------------------------------------------------------------------------- #
# Minimal content-stream tokeniser
# --------------------------------------------------------------------------- #


def tokenize(data: bytes) -> Iterator[tuple[str, bytes, int, int]]:
    """Yield ``(kind, text, start, end)`` for a PDF content stream.

    ``kind`` is one of: number, name, string, array, dict, operator.
    Enough of the syntax is handled that a ``w`` or ``S`` inside a string or an
    inline image is never mistaken for an operator.
    """
    i, n = 0, len(data)
    while i < n:
        c = data[i : i + 1]
        if c in WHITESPACE_SET:
            i += 1
            continue
        start = i
        if c == b"%":  # comment
            while i < n and data[i : i + 1] not in (b"\r", b"\n"):
                i += 1
            continue
        if c == b"(":  # literal string, may nest
            depth, i = 1, i + 1
            while i < n and depth:
                ch = data[i : i + 1]
                if ch == b"\\":
                    i += 2
                    continue
                if ch == b"(":
                    depth += 1
                elif ch == b")":
                    depth -= 1
                i += 1
            yield "string", data[start:i], start, i
            continue
        if c == b"<":
            if data[i : i + 2] == b"<<":
                i += 2
                yield "dict", b"<<", start, i
                continue
            while i < n and data[i : i + 1] != b">":
                i += 1
            i += 1
            yield "string", data[start:i], start, i
            continue
        if data[i : i + 2] == b">>":
            i += 2
            yield "dict", b">>", start, i
            continue
        if c in b"[]{}":
            i += 1
            yield "array", c, start, i
            continue
        if c == b"/":
            i += 1
            while i < n and data[i : i + 1] not in _BREAK:
                i += 1
            yield "name", data[start:i], start, i
            continue
        while i < n and data[i : i + 1] not in _BREAK:
            i += 1
        if i == start:  # a stray delimiter we do not understand; skip it
            i += 1
            continue
        text = data[start:i]
        kind = "number" if NUMBER_RE.match(text) else "operator"
        yield kind, text, start, i
        if kind == "operator" and text == b"BI":
            # Inline image: binary data runs from ID to the matching EI.
            marker = data.find(b"ID", i)
            if marker == -1:
                return
            end = data.find(b"EI", marker + 2)
            i = (end + 2) if end != -1 else n


# --------------------------------------------------------------------------- #
# Graphics state
# --------------------------------------------------------------------------- #


def _matmul(m: tuple, n: tuple) -> tuple:
    """PDF matrix product ``m x n`` (``cm`` premultiplies the CTM)."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (
        a * A + b * C,
        a * B + b * D,
        c * A + d * C,
        c * B + d * D,
        e * A + f * C + E,
        e * B + f * D + F,
    )


def _scale_of(ctm: tuple) -> float:
    """The uniform scale a matrix applies (exact for scale+rotation)."""
    a, b, c, d = ctm[0], ctm[1], ctm[2], ctm[3]
    return math.sqrt(abs(a * d - b * c))


def _format(value: float) -> bytes:
    return f"{value:.6f}".rstrip("0").rstrip(".").encode("ascii") or b"0"


def rewrite_stream(
    data: bytes,
    resolve: Callable[[float], float],
    extgstate_lw: dict[bytes, float] | None = None,
) -> tuple[bytes, int, int]:
    """Inject corrected line widths before every stroking operator.

    ``resolve`` maps the current stroke width (in page points) to the width it
    should have (also page points).  Returns ``(stream, changes, strokes)``.
    A single injected ``w`` covers every following stroke that shares the same
    graphics state, so ``changes`` is normally far smaller than ``strokes``.
    """
    extgstate_lw = extgstate_lw or {}
    out: list[bytes] = []
    cursor = 0
    changes = 0
    strokes_seen = 0

    ctm = IDENTITY
    ctm_stack: list[tuple] = []
    width = 1.0  # PDF default line width
    width_stack: list[float] = []
    operands: list[bytes] = []

    for kind, text, start, end in tokenize(data):
        if kind == "number":
            operands.append(text)
            continue
        if kind != "operator":
            operands.append(text)
            continue

        if text == b"q":
            ctm_stack.append(ctm)
            width_stack.append(width)
        elif text == b"Q":
            if ctm_stack:
                ctm = ctm_stack.pop()
            if width_stack:
                width = width_stack.pop()
        elif text == b"cm" and len(operands) >= 6:
            try:
                m = tuple(float(v) for v in operands[-6:])
            except ValueError:
                m = IDENTITY
            ctm = _matmul(m, ctm)
        elif text == b"w" and operands:
            try:
                width = float(operands[-1])
            except ValueError:
                pass
        elif text == b"gs" and operands:
            lw = extgstate_lw.get(operands[-1])
            if lw is not None:
                width = lw
        elif text in STROKE_OPS:
            strokes_seen += 1
            scale = _scale_of(ctm)
            if scale > 0:
                current_pt = width * scale
                wanted_pt = resolve(current_pt)
                if wanted_pt is not None and abs(wanted_pt - current_pt) > 1e-9:
                    out.append(data[cursor:start])
                    out.append(_format(wanted_pt / scale) + b" w ")
                    cursor = start
                    width = wanted_pt / scale
                    changes += 1

        operands = []

    out.append(data[cursor:])
    return b"".join(out), changes, strokes_seen


# --------------------------------------------------------------------------- #
# Page-level entry point
# --------------------------------------------------------------------------- #


def _extgstate_widths(doc: fitz.Document, page: fitz.Page) -> dict[bytes, float]:
    """``/Name -> line width`` for any ExtGState on the page that sets /LW."""
    widths: dict[bytes, float] = {}
    kind, value = doc.xref_get_key(page.xref, "Resources/ExtGState")
    if kind != "dict":
        return widths
    for name in re.findall(rb"/([^\s/<>\[\]()]+)", value.encode("latin-1")):
        sub = doc.xref_get_key(page.xref, f"Resources/ExtGState/{name.decode('latin-1')}/LW")
        if sub[0] in ("int", "float"):
            try:
                widths[b"/" + name] = float(sub[1])
            except ValueError:
                pass
    return widths


def make_resolver(cfg, magnification: float) -> Callable[[float], float] | None:
    """Build the page-points -> page-points width mapping from the config.

    Returns ``None`` when the config asks for no change at all.
    """
    lines = cfg.lines
    has_clamp = lines.min_width_mm > 0 or lines.max_width_mm > 0
    if lines.mode == "keep" and not has_clamp:
        return None

    def resolve(current_pt: float) -> float:
        # Everything is decided in printed millimetres.
        printed_mm = current_pt * magnification * MM_PER_PT
        if current_pt <= 0 and lines.keep_hairlines:
            return current_pt  # a device hairline: leave it alone
        if lines.mode == "fixed":
            printed_mm = lines.width_mm
        elif lines.mode == "scale":
            printed_mm *= lines.scale
        if lines.min_width_mm > 0:
            printed_mm = max(printed_mm, lines.min_width_mm)
        if lines.max_width_mm > 0:
            printed_mm = min(printed_mm, lines.max_width_mm)
        return printed_mm * PT_PER_MM / magnification

    return resolve


def apply(doc: fitz.Document, page_no: int, cfg, magnification: float) -> tuple[int, int]:
    """Re-weight the strokes of one page in an open document, in memory.

    The document is modified but never saved, so the source file on disk is
    untouched.  Returns ``(width_changes, strokes_seen)``.
    """
    resolve = make_resolver(cfg, magnification)
    if resolve is None:
        return 0, 0
    page = doc[page_no]
    # Multiple content streams are concatenated before interpretation, so the
    # graphics state carries across them. Consolidate first rather than parse
    # each one from a reset state.
    if len(page.get_contents()) > 1:
        page.clean_contents()
    extgstate = _extgstate_widths(doc, page)
    changes = strokes_seen = 0
    for xref in page.get_contents():
        data = doc.xref_stream(xref)
        new, count, seen = rewrite_stream(data, resolve, extgstate)
        strokes_seen += seen
        if count:
            doc.update_stream(xref, new)
            changes += count
    return changes, strokes_seen
