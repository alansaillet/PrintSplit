"""Config loading, merging and validation."""

import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from printsplit.config import (  # noqa: E402
    ConfigError,
    SheetCfg,
    dash_pattern,
    dump,
    from_dict,
    load,
    margins_mm,
    parse_color,
    to_dict,
)

REPO = Path(__file__).resolve().parents[1]


def _write(tmp: Path, name: str, text: str) -> Path:
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_load():
    cfg = load(REPO / "config" / "example.toml")
    assert cfg.scale.source_scale == 20.0
    assert cfg.scale.magnification == 20.0
    assert cfg.sheet.size == "A0"
    assert cfg.tiling.overlap_mm == 30.0
    # inherited from default.toml
    assert cfg.marks.crop.enabled is True
    assert cfg.output.single_pdf is True
    # relative paths resolve against the repo root
    assert cfg.resolve(cfg.project.input).is_file()


def test_extends_is_deep_merged():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        _write(tmp, "base.toml", '[project]\ninput = "a.pdf"\n[marks.crop]\nlength_mm = 9.0\n')
        child = _write(tmp, "child.toml", 'extends = "base.toml"\n[marks.crop]\ncolor = "#111111"\n')
        cfg = load(child)
        assert cfg.marks.crop.length_mm == 9.0  # kept from the base
        assert cfg.marks.crop.color == "#111111"  # overridden
        assert cfg.project.input == "a.pdf"


def test_dict_round_trip():
    cfg = load(REPO / "config" / "example.toml")
    data = to_dict(cfg)
    assert "config_path" not in data and "root" not in data  # internals stay out
    assert to_dict(from_dict(data)) == data


def test_dump_is_reloadable_toml():
    """A GUI must be able to save settings and read them back."""
    cfg = load(REPO / "config" / "example.toml")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "saved.toml"
        dump(cfg, path)
        again = load(path)
    assert to_dict(again) == to_dict(cfg)


def test_from_dict_rejects_bad_input():
    for bad in ({"project": {"input": "a.pdf"}, "nope": {}},
                {"project": {"input": "a.pdf"}, "scale": {"source_scale": -1.0}},
                {"project": {}}):
        try:
            from_dict(bad)
        except ConfigError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"expected ConfigError for {bad}")


def test_extends_chains_more_than_one_level():
    """leaf.toml -> middle.toml -> base.toml"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        _write(tmp, "a.toml", '[project]\ninput = "a.pdf"\n[tiling]\noverlap_mm = 5.0\n'
                              '[marks.crop]\nlength_mm = 9.0\n')
        _write(tmp, "b.toml", 'extends = "a.toml"\n[tiling]\noverlap_mm = 30.0\n'
                              '[scale]\nsource_scale = 60.0\n')
        c = _write(tmp, "c.toml", 'extends = "b.toml"\n[project]\nname = "leaf"\n')
        cfg = load(c)
        assert cfg.project.name == "leaf"  # from the leaf
        assert cfg.tiling.overlap_mm == 30.0  # from the middle, overriding the base
        assert cfg.scale.source_scale == 60.0  # from the middle
        assert cfg.marks.crop.length_mm == 9.0  # from the base
        assert cfg.project.input == "a.pdf"  # from the base


def test_circular_extends_is_caught():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        _write(tmp, "x.toml", 'extends = "y.toml"\n[project]\ninput = "a.pdf"\n')
        _write(tmp, "y.toml", 'extends = "x.toml"\n')
        try:
            load(tmp / "x.toml")
        except ConfigError as exc:
            assert "circular" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected a ConfigError")


def test_every_shipped_job_config_loads():
    """Every config that names a source PDF must load and point at a real file.

    Configs without a ``project.input`` (default.toml, hedelius_common.toml)
    are bases meant to be extended, not run.
    """
    checked = 0
    for path in sorted((REPO / "config").glob("*.toml")):
        raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        if not raw.get("project", {}).get("input"):
            continue
        cfg = load(path)
        assert cfg.resolve(cfg.project.input).is_file(), path.name
        assert cfg.scale.source_scale > 0
        checked += 1
    assert checked >= 1, "no runnable job configs found"


def test_unknown_key_is_rejected():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write(Path(tmpdir), "bad.toml", '[project]\ninput = "a.pdf"\noverlap = 3\n')
        try:
            load(path)
        except ConfigError as exc:
            assert "overlap" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected a ConfigError")


def test_validation_catches_bad_values():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write(
            Path(tmpdir),
            "bad.toml",
            '[project]\ninput = "a.pdf"\n[scale]\nsource_scale = 0.0\n',
        )
        try:
            load(path)
        except ConfigError as exc:
            assert "source_scale" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected a ConfigError")


def test_margins_forms():
    assert margins_mm(SheetCfg(margin_mm=10.0)) == (10.0, 10.0, 10.0, 10.0)
    assert margins_mm(SheetCfg(margin_mm=[5.0, 8.0])) == (5.0, 8.0, 5.0, 8.0)
    assert margins_mm(SheetCfg(margin_mm=[1.0, 2.0, 3.0, 4.0])) == (1.0, 2.0, 3.0, 4.0)


def test_colors_and_dashes():
    assert parse_color("#ffffff") == (1.0, 1.0, 1.0)
    assert parse_color("#000") == (0.0, 0.0, 0.0)
    r, g, b = parse_color("255,0,0")
    assert (round(r), round(g), round(b)) == (1, 0, 0)
    assert dash_pattern("6 4") == "[6 4] 0"
    assert dash_pattern("") is None


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
