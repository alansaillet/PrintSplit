"""Line-width rewriting: tokeniser and CTM-aware width injection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from printsplit.config import Config  # noqa: E402
from printsplit.strokes import make_resolver, rewrite_stream, tokenize  # noqa: E402


def ops(data: bytes) -> list[bytes]:
    return [t for kind, t, _, _ in tokenize(data) if kind == "operator"]


def test_tokenizer_finds_operators():
    assert ops(b"6 w 0 0 m 10 10 l S") == [b"w", b"m", b"l", b"S"]


def test_tokenizer_ignores_operators_inside_strings():
    # "S" and "w" here are text, not operators
    assert ops(b"BT (S w 6 w) Tj ET") == [b"BT", b"Tj", b"ET"]
    assert ops(b"<48656C6C6F> Tj") == [b"Tj"]


def test_tokenizer_skips_comments_and_inline_images():
    assert ops(b"% 6 w S\n1 0 0 1 0 0 cm") == [b"cm"]
    assert ops(b"BI /W 2 ID \x00S w \xff EI Q") == [b"BI", b"Q"]


def test_width_is_scaled_by_the_ctm_at_stroke_time():
    """The classic CAD pattern: `w` first, then a scaling `cm`, then the stroke.

    A naive search-and-replace on `w` gets this wrong; 6 w under a 0.12 scale
    is a 0.72 pt line, not a 6 pt one.
    """
    data = b"6 w 0.12 0 0 0.12 0 0 cm 0 0 m 10 10 l S"
    seen = []

    def resolve(current_pt):
        seen.append(current_pt)
        return 0.024  # want 0.024 pt on the page

    out, changes, strokes = rewrite_stream(data, resolve)
    assert abs(seen[0] - 0.72) < 1e-9, seen  # 6 * 0.12
    assert changes == 1 and strokes == 1
    # injected operand must be 0.024 / 0.12 = 0.2
    assert b"0.2 w S" in out, out


def test_rotation_matrix_scale():
    """The Hedelius matrix is a rotation *and* a scale; only the scale counts."""
    data = b"6 w 0 -0.12 .12 0 0 595 cm 0 0 m 1 1 l S"
    seen = []
    rewrite_stream(data, lambda c: (seen.append(c), c)[1])
    assert abs(seen[0] - 0.72) < 1e-9, seen


def test_q_Q_restores_the_matrix():
    data = b"1 w q 0.5 0 0 0.5 0 0 cm 0 0 m 1 1 l S Q 0 0 m 1 1 l S"
    seen = []
    rewrite_stream(data, lambda c: (seen.append(c), c)[1])
    assert [round(v, 6) for v in seen] == [0.5, 1.0]


def test_default_width_is_one():
    seen = []
    rewrite_stream(b"0 0 m 1 1 l S", lambda c: (seen.append(c), c)[1])
    assert seen == [1.0]


def test_one_injection_covers_following_strokes():
    data = b"6 w 0.12 0 0 0.12 0 0 cm 0 0 m 1 1 l S 2 2 m 3 3 l S 4 4 m 5 5 l S"
    _, changes, strokes = rewrite_stream(data, lambda c: 0.024)
    assert strokes == 3
    assert changes == 1


def test_resolver_modes():
    cfg = Config()
    mag = 60.0

    cfg.lines.mode = "keep"
    assert make_resolver(cfg, mag) is None  # nothing to do

    cfg.lines.mode = "fixed"
    cfg.lines.width_mm = 0.5
    resolve = make_resolver(cfg, mag)
    # 0.5 mm printed, divided back through the x60 magnification
    assert abs(resolve(0.72) - 0.5 * (72 / 25.4) / 60) < 1e-12
    assert abs(resolve(0.48) - resolve(0.72)) < 1e-12  # every stroke the same

    cfg.lines.mode = "scale"
    cfg.lines.scale = 0.5
    resolve = make_resolver(cfg, mag)
    assert abs(resolve(0.72) - 0.36) < 1e-12  # relative weights preserved
    assert abs(resolve(0.48) - 0.24) < 1e-12


def test_resolver_clamps():
    cfg = Config()
    cfg.lines.mode = "keep"
    cfg.lines.max_width_mm = 1.0
    resolve = make_resolver(cfg, 60.0)
    assert resolve is not None  # a clamp alone is enough to act
    printed_mm = resolve(0.72) * 60 * 25.4 / 72
    assert abs(printed_mm - 1.0) < 1e-9

    cfg.lines.max_width_mm = 0.0
    cfg.lines.min_width_mm = 30.0
    resolve = make_resolver(cfg, 60.0)
    printed_mm = resolve(0.1) * 60 * 25.4 / 72
    assert abs(printed_mm - 30.0) < 1e-9


def test_hairlines_are_left_alone():
    cfg = Config()
    cfg.lines.mode = "fixed"
    cfg.lines.width_mm = 0.5
    cfg.lines.keep_hairlines = True
    assert make_resolver(cfg, 60.0)(0.0) == 0.0
    cfg.lines.keep_hairlines = False
    assert make_resolver(cfg, 60.0)(0.0) > 0.0


def test_stream_is_otherwise_untouched():
    """Only widths change -- every coordinate must survive byte for byte."""
    data = b"6 w 0.12 0 0 0.12 0 0 cm 4012 1087.92 m 4012 1008.92 l S"
    out, _, _ = rewrite_stream(data, lambda c: 0.024)
    for token in (b"4012 1087.92 m", b"4012 1008.92 l", b"0.12 0 0 0.12 0 0 cm"):
        assert token in out


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
