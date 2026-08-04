"""Tiling arithmetic tests -- no PDF involved."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from printsplit.config import Config  # noqa: E402
from printsplit.errors import LayoutError  # noqa: E402
from printsplit.layout import _tiles_needed, build, column_label, tile_label  # noqa: E402

EPS = 1e-6


def make_cfg(**tiling):
    cfg = Config()
    cfg.sheet.size = "A0"
    cfg.sheet.orientation = "landscape"
    cfg.sheet.margin_mm = 10.0
    for key, value in tiling.items():
        setattr(cfg.tiling, key, value)
    return cfg


def test_column_labels():
    assert column_label(0) == "A"
    assert column_label(25) == "Z"
    assert column_label(26) == "AA"
    assert tile_label(2, 1, "A1", 3) == "B3"
    assert tile_label(2, 1, "R1C1", 3) == "R3C2"
    assert tile_label(2, 1, "index", 3) == "8"


def test_tiles_needed():
    assert _tiles_needed(100.0, 200.0, 20.0) == 1
    assert _tiles_needed(200.0, 200.0, 20.0) == 1
    assert _tiles_needed(201.0, 200.0, 20.0) == 2
    # exact fit of two sheets: 200 + (200 - 20) = 380
    assert _tiles_needed(380.0, 200.0, 20.0) == 2
    assert _tiles_needed(380.1, 200.0, 20.0) == 3


def test_grid_covers_the_drawing():
    cfg = make_cfg(overlap_mm=30.0, center_content=True)
    lay = build(cfg, 3157.0, 2530.0)
    xs = [t.window.x0 for t in lay.tiles]
    ys = [t.window.y0 for t in lay.tiles]
    assert min(xs) <= 0.0 + EPS
    assert min(ys) <= 0.0 + EPS
    assert max(t.window.x1 for t in lay.tiles) >= 3157.0 - EPS
    assert max(t.window.y1 for t in lay.tiles) >= 2530.0 - EPS


def test_trim_rects_butt_join_exactly():
    cfg = make_cfg(overlap_mm=30.0)
    lay = build(cfg, 3157.0, 2530.0)
    grid = {(t.row, t.col): t for t in lay.tiles}
    for (row, col), tile in grid.items():
        right = grid.get((row, col + 1))
        if right is not None:
            assert abs(tile.trim.x1 - right.trim.x0) < EPS
        below = grid.get((row + 1, col))
        if below is not None:
            assert abs(tile.trim.y1 - below.trim.y0) < EPS


def test_trim_rects_tile_the_whole_area():
    cfg = make_cfg(overlap_mm=30.0)
    lay = build(cfg, 3157.0, 2530.0)
    area = sum(t.trim.width * t.trim.height for t in lay.tiles)
    grid_w = lay.usable_w_mm + (lay.cols - 1) * lay.step_w_mm
    grid_h = lay.usable_h_mm + (lay.rows - 1) * lay.step_h_mm
    assert abs(area - grid_w * grid_h) < 1e-3


def test_shared_join_lines_coincide():
    """The centre of the overlap band is the same assembled coordinate on both
    sheets -- that is what makes the registration crosses line up."""
    cfg = make_cfg(overlap_mm=30.0)
    lay = build(cfg, 3157.0, 2530.0)
    grid = {(t.row, t.col): t for t in lay.tiles}
    half = lay.overlap_mm / 2.0
    for (row, col), tile in grid.items():
        right = grid.get((row, col + 1))
        if right is not None:
            assert abs((tile.window.x1 - half) - (right.window.x0 + half)) < EPS
            assert abs(tile.window.y0 - right.window.y0) < EPS  # same ladder
        below = grid.get((row + 1, col))
        if below is not None:
            assert abs((tile.window.y1 - half) - (below.window.y0 + half)) < EPS
            assert abs(tile.window.x0 - below.window.x0) < EPS


def test_orientation_auto_picks_fewest_sheets():
    cfg = make_cfg(overlap_mm=20.0)
    cfg.sheet.orientation = "auto"
    # A tall, narrow drawing should end up on portrait sheets.
    lay = build(cfg, 600.0, 3000.0)
    assert lay.orientation == "portrait"
    assert lay.cols == 1


def test_single_sheet_when_it_fits():
    cfg = make_cfg(overlap_mm=20.0)
    lay = build(cfg, 500.0, 400.0)
    assert (lay.rows, lay.cols) == (1, 1)
    assert lay.tiles[0].trim.x0 == lay.tiles[0].window.x0
    assert all(v is None for v in lay.tiles[0].neighbours.values())


def test_max_sheets_guard():
    cfg = make_cfg(overlap_mm=20.0, max_sheets=4)
    try:
        build(cfg, 10000.0, 10000.0)
    except LayoutError as exc:
        assert "max_sheets" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected the max_sheets guard to fire")


def test_overlap_wider_than_the_sheet_is_rejected():
    cfg = make_cfg(overlap_mm=5000.0)
    try:
        build(cfg, 10000.0, 10000.0)
    except LayoutError as exc:
        assert "overlap" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected the overlap guard to fire")


def test_hedelius_case():
    """The real job: a 1:60 drawing of ~52.6 x 42.2 mm printed 1:1."""
    cfg = make_cfg(overlap_mm=30.0)
    cfg.sheet.orientation = "auto"
    lay = build(cfg, 3157.2, 2530.4)
    assert lay.sheet_w_mm == 1189.0 and lay.sheet_h_mm == 841.0
    assert (lay.cols, lay.rows) == (3, 4)


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
