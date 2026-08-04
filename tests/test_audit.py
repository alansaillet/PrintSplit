"""The automatic sanity checks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pymupdf as fitz  # noqa: E402

from printsplit.audit import (  # noqa: E402
    _off_page,
    _rotated_text,
    containment,
)


def test_containment_identical():
    a = {(0, 0), (10, 10), (20, 20)}
    assert containment(a, a) == 1.0


def test_containment_disjoint():
    assert containment({(0, 0)}, {(500, 500)}) == 0.0


def test_containment_is_directional():
    """A big drawing containing a small one is not symmetric."""
    small = {(0, 0), (1, 1)}
    big = {(0, 0), (1, 1), (50, 50), (60, 60)}
    assert containment(small, big) == 1.0
    assert containment(big, small) == 0.5


def test_containment_tolerance():
    # 1 mm of slack, so a point 1 mm away still counts
    assert containment({(0, 0)}, {(1, 0)}) == 1.0
    assert containment({(0, 0)}, {(3, 0)}) == 0.0


def _page_with_text():
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((50, 100), "upright", fontsize=10)
    page.insert_text((50, 150), "vertical", fontsize=10, rotate=90)
    page.insert_text((50, 200), "flipped", fontsize=10, rotate=180)
    return doc, page


def test_rotated_text_separates_sideways_from_upside_down():
    doc, page = _page_with_text()
    upside_down, sideways = _rotated_text(page)
    doc.close()
    assert len(upside_down) == 1, upside_down
    assert "flipped" in upside_down[0]
    assert len(sideways) == 1, sideways
    assert "vertical" in sideways[0]


def test_upright_text_is_not_flagged():
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((50, 100), "all fine", fontsize=10)
    upside_down, sideways = _rotated_text(page)
    doc.close()
    assert upside_down == [] and sideways == []


def test_off_page_detects_content_past_the_media_box():
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_line(fitz.Point(10, 10), fitz.Point(100, 100))
    count, worst = _off_page(page)
    assert count == 0 and worst == 0.0

    # a line running off the bottom edge
    page.draw_line(fitz.Point(50, 250), fitz.Point(50, 340))
    count, worst = _off_page(page)
    doc.close()
    assert count == 1
    assert abs(worst - 40.0) < 1.0, worst


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
