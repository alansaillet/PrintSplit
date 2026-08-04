"""Configuration schema, TOML loading and validation.

Every knob PrintSplit has lives in a TOML file -- nothing is hard-coded in the
CLI.  A config may ``extends`` another one (typically ``config/default.toml``),
which is deep-merged underneath it, so a project file only states what differs.

Unknown keys are a hard error: a typo in a config is far more likely to be a
mistake than an intention, and silently ignoring it would print 12 wrong A0s.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints

from .errors import ConfigError

__all__ = ["Config", "ConfigError", "load", "from_dict", "to_dict", "dump", "validate"]


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


@dataclass
class ProjectCfg:
    """What is being printed, and where the result goes."""

    name: str = "Untitled"
    input: str = ""  # path to the source PDF, relative to the repo root
    page: int = 1  # 1-based page number of the source PDF
    output_dir: str = "out"
    output_basename: str = "tiled"
    root: str = ""  # override for relative-path resolution (default: repo root)


@dataclass
class ScaleCfg:
    """Drawing scale in, drawing scale out.

    ``source_scale = 60`` means the PDF is drawn at 1:60.  ``target_scale = 1``
    means print it full size.  The magnification applied to the PDF is therefore
    ``source_scale / target_scale``.
    """

    source_scale: float = 1.0
    target_scale: float = 1.0

    @property
    def magnification(self) -> float:
        return self.source_scale / self.target_scale


@dataclass
class SourceCfg:
    """How to find the drawing inside the source page."""

    bbox_mode: str = "auto"  # auto | page | manual
    include_drawings: bool = True
    include_text: bool = True
    include_images: bool = True
    stroke_aware: bool = True  # grow vector bboxes by half the stroke width
    drop_page_frame: bool = False  # ignore items that span (nearly) the whole page
    page_frame_tolerance_mm: float = 3.0
    manual_bbox_mm: list[float] = field(default_factory=list)  # x0,y0,x1,y1 on the page
    padding_mm: float = 0.0  # padding around the drawing, in OUTPUT mm
    round_up_to_mm: float = 0.0  # round the assembled size up to a multiple of this


@dataclass
class LinesCfg:
    """How thick the drawing's own strokes come out.

    Magnification magnifies line weights too: at x60 a 0.72 pt line prints
    15 mm wide, which is an imprecise thing to mark a floor from.  All widths
    here are in *printed* millimetres, i.e. what a ruler on the paper measures.
    """

    mode: str = "keep"  # keep | scale | fixed
    scale: float = 1.0  # mode = "scale": multiply the printed width
    width_mm: float = 0.5  # mode = "fixed": every stroke this wide
    min_width_mm: float = 0.0  # clamp, any mode. 0 = no floor
    max_width_mm: float = 0.0  # clamp, any mode. 0 = no ceiling
    keep_hairlines: bool = True  # leave zero-width (device hairline) strokes alone


@dataclass
class SheetCfg:
    """The paper actually going through the plotter."""

    size: str = "A0"
    orientation: str = "auto"  # auto | portrait | landscape
    custom_size_mm: list[float] = field(default_factory=list)  # [w, h] if size = "custom"
    # Non-printable border. Either a single number or [top, right, bottom, left].
    margin_mm: Any = 10.0


@dataclass
class TilingCfg:
    """How the assembled drawing is cut into sheets."""

    overlap_mm: float = 20.0  # shared band between neighbouring sheets
    center_content: bool = True  # spread the leftover paper evenly
    skip_blank_tiles: bool = True  # do not emit sheets with no artwork on them
    label_style: str = "A1"  # A1 | R1C1 | index
    page_order: str = "row_major"  # row_major | column_major
    max_sheets: int = 200  # guard against a mis-typed scale eating a paper roll


@dataclass
class FrameMarks:
    enabled: bool = True
    color: str = "#9aa4ae"
    line_width_mm: float = 0.2


@dataclass
class CropMarks:
    enabled: bool = True
    length_mm: float = 15.0
    color: str = "#000000"
    line_width_mm: float = 0.3


@dataclass
class CutMarks:
    """The dashed 'cut here' line on the edges that overlap a neighbour."""

    enabled: bool = True
    color: str = "#d1242f"
    line_width_mm: float = 0.35
    dash: str = "6 4"
    label: bool = True
    font_size_pt: float = 9.0


@dataclass
class OverlapMarks:
    """The far edge of the shared band -- shown, but not cut."""

    enabled: bool = True
    color: str = "#9aa4ae"
    line_width_mm: float = 0.25
    dash: str = "2 4"
    shade: bool = True
    shade_color: str = "#eef3f8"


@dataclass
class RegistrationMarks:
    """Crosshairs that land on identical real-world coordinates on both sheets."""

    enabled: bool = True
    spacing_mm: float = 200.0
    size_mm: float = 16.0
    line_width_mm: float = 0.3
    color: str = "#1f6feb"
    circle: bool = True
    circle_radius_mm: float = 5.0
    corner_targets: bool = True
    label: bool = True
    font_size_pt: float = 6.0


@dataclass
class TickMarks:
    """Ruler ticks along the sheet frame, labelled in assembled coordinates."""

    enabled: bool = True
    step_mm: float = 100.0
    length_mm: float = 4.0
    long_every: int = 5  # every n-th tick is drawn double length and labelled
    units: str = "m"  # m | cm | mm
    font_size_pt: float = 7.0
    color: str = "#5a6672"
    line_width_mm: float = 0.2


@dataclass
class RulerMarks:
    """A printed ruler so you can verify the plotter did not rescale anything."""

    enabled: bool = True
    corner: str = "auto"  # auto = the emptiest corner of this sheet
    offset_mm: float = 16.0
    length_mm: float = 500.0
    division_mm: float = 100.0
    height_mm: float = 7.0
    font_size_pt: float = 9.0
    color: str = "#000000"
    line_width_mm: float = 0.3
    both_axes: bool = True


@dataclass
class LabelBlock:
    """The identification block: which sheet this is and how to print it."""

    enabled: bool = True
    corner: str = "auto"  # auto | top_left | top_right | bottom_left | bottom_right
    offset_mm: float = 14.0
    font_size_pt: float = 11.0
    title_font_size_pt: float = 40.0
    color: str = "#000000"
    background: bool = True
    background_color: str = "#ffffff"
    border: bool = True
    border_color: str = "#9aa4ae"
    show_neighbours: bool = True
    notes: str = "PRINT AT 100% - DO NOT USE FIT TO PAGE"


@dataclass
class ArrowMarks:
    """'-> B2' hints in the margin telling you which sheet joins where."""

    enabled: bool = True
    font_size_pt: float = 13.0
    color: str = "#1f6feb"


@dataclass
class MarksCfg:
    enabled: bool = True
    font: str = "helv"
    frame: FrameMarks = field(default_factory=FrameMarks)
    crop: CropMarks = field(default_factory=CropMarks)
    cut: CutMarks = field(default_factory=CutMarks)
    overlap: OverlapMarks = field(default_factory=OverlapMarks)
    registration: RegistrationMarks = field(default_factory=RegistrationMarks)
    ticks: TickMarks = field(default_factory=TickMarks)
    ruler: RulerMarks = field(default_factory=RulerMarks)
    label: LabelBlock = field(default_factory=LabelBlock)
    arrows: ArrowMarks = field(default_factory=ArrowMarks)


@dataclass
class OverviewCfg:
    """The assembly map: one small page showing how the tiles fit together."""

    enabled: bool = True
    separate_file: bool = True  # keep the tile PDF homogeneous for the plotter
    size: str = "A3"
    orientation: str = "auto"
    margin_mm: float = 14.0
    font_size_pt: float = 9.0
    grid_color: str = "#1f6feb"
    blank_color: str = "#c9d1d9"
    drawing_color: str = "#24292f"


@dataclass
class OutputCfg:
    single_pdf: bool = True
    per_tile_pdfs: bool = False
    report: bool = True
    overwrite: bool = True


@dataclass
class Config:
    project: ProjectCfg = field(default_factory=ProjectCfg)
    scale: ScaleCfg = field(default_factory=ScaleCfg)
    source: SourceCfg = field(default_factory=SourceCfg)
    lines: LinesCfg = field(default_factory=LinesCfg)
    sheet: SheetCfg = field(default_factory=SheetCfg)
    tiling: TilingCfg = field(default_factory=TilingCfg)
    marks: MarksCfg = field(default_factory=MarksCfg)
    overview: OverviewCfg = field(default_factory=OverviewCfg)
    output: OutputCfg = field(default_factory=OutputCfg)

    # Filled in by load(); not settable from TOML.
    config_path: Path = field(default_factory=Path)
    root: Path = field(default_factory=Path)

    def resolve(self, relative: str) -> Path:
        """Resolve a config-supplied path against the project root."""
        p = Path(relative.replace("\\", "/"))
        return p if p.is_absolute() else (self.root / p)


_INTERNAL_FIELDS = {"config_path", "root"}


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` on top of ``base`` (neither is mutated)."""
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _coerce(value: Any, annotation: Any, path: str) -> Any:
    if annotation is Any:
        return value
    if annotation is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{path}: expected true/false, got {value!r}")
        return value
    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{path}: expected an integer, got {value!r}")
        return value
    if annotation is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{path}: expected a number, got {value!r}")
        return float(value)
    if annotation is str:
        if not isinstance(value, str):
            raise ConfigError(f"{path}: expected a string, got {value!r}")
        return value
    if annotation in (list[float], "list[float]"):
        if not isinstance(value, list) or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
        ):
            raise ConfigError(f"{path}: expected a list of numbers, got {value!r}")
        return [float(v) for v in value]
    return value


def _build(cls: type, data: dict, path: str = "") -> Any:
    hints = get_type_hints(cls)
    known = {f.name for f in fields(cls)}
    if cls is Config:  # these are filled in by load(), not by the user
        known -= _INTERNAL_FIELDS
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            close = ", ".join(sorted(known))
            raise ConfigError(f"unknown setting '{path}{key}'. Valid keys here: {close}")
        annotation = hints[key]
        if is_dataclass(annotation):
            if not isinstance(value, dict):
                raise ConfigError(f"{path}{key}: expected a [table], got {value!r}")
            kwargs[key] = _build(annotation, value, f"{path}{key}.")
        else:
            kwargs[key] = _coerce(value, annotation, f"{path}{key}")
    return cls(**kwargs)


def _read_toml(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    # Notepad and PowerShell's Out-File write UTF-8 with a BOM, which tomllib
    # refuses. Config files are meant to be edited, so accept it.
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ConfigError(f"{path}: config files must be UTF-8") from None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML - {exc}") from None


def _find_root(config_path: Path) -> Path:
    """Repo root = nearest ancestor holding pyproject.toml, else the config's parent."""
    for parent in config_path.resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return config_path.resolve().parent


def load(config_path: str | Path, _seen: set[Path] | None = None) -> Config:
    """Load a config file, following ``extends`` chains."""
    path = Path(config_path).resolve()
    seen = _seen or set()
    if path in seen:
        raise ConfigError(f"circular 'extends' chain at {path}")
    seen.add(path)

    data = _read_toml(path)
    parent_name = data.pop("extends", None)
    if parent_name is not None:
        if not isinstance(parent_name, str):
            raise ConfigError(f"{path}: 'extends' must be a string")
        parent_path = (path.parent / parent_name).resolve()
        parent_data = _load_raw(parent_path, seen)
        data = _deep_merge(parent_data, data)

    cfg = _build(Config, data)
    cfg.config_path = path
    cfg.root = (
        Path(cfg.project.root).resolve() if cfg.project.root else _find_root(path)
    )
    validate(cfg)
    return cfg


def from_dict(data: dict) -> Config:
    """Build a validated :class:`Config` from plain nested dicts.

    The counterpart of :func:`to_dict`, and the way a GUI should hand settings
    over: unknown keys and bad values raise :class:`ConfigError` here rather
    than surfacing as a broken print later.
    """
    cfg = _build(Config, data)
    cfg.root = Path(cfg.project.root).resolve() if cfg.project.root else Path.cwd()
    validate(cfg)
    return cfg


def to_dict(cfg: Config) -> dict:
    """Plain nested dicts, ready for JSON or TOML. Round-trips with ``from_dict``."""
    out = asdict(cfg)
    for key in _INTERNAL_FIELDS:
        out.pop(key, None)
    return out


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    raise ConfigError(f"cannot serialise {value!r} to TOML")


def dump(cfg: Config, path: str | Path | None = None) -> str:
    """Serialise a config back to TOML. Writes it too, if ``path`` is given."""
    data = to_dict(cfg)
    lines: list[str] = []

    def emit(table: dict, prefix: str) -> None:
        scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
        if scalars or not table:
            lines.append(f"[{prefix}]")
            for key, value in scalars.items():
                lines.append(f"{key} = {_toml_scalar(value)}")
            lines.append("")
        for key, value in table.items():
            if isinstance(value, dict):
                emit(value, f"{prefix}.{key}")

    for name, value in data.items():
        if isinstance(value, dict):
            emit(value, name)
    text = "\n".join(lines).rstrip() + "\n"
    if path is not None:
        Path(path).write_text(text, encoding="utf-8")
    return text


def _load_raw(path: Path, seen: set[Path]) -> dict:
    if path in seen:
        raise ConfigError(f"circular 'extends' chain at {path}")
    seen.add(path)
    data = _read_toml(path)
    parent_name = data.pop("extends", None)
    if parent_name:
        parent_path = (path.parent / parent_name).resolve()
        return _deep_merge(_load_raw(parent_path, seen), data)
    return data


# --------------------------------------------------------------------------- #
# Validation & helpers
# --------------------------------------------------------------------------- #


def validate(cfg: Config) -> None:
    if not cfg.project.input:
        raise ConfigError("project.input is required (path to the source PDF)")
    if cfg.project.page < 1:
        raise ConfigError("project.page is 1-based and must be >= 1")
    if cfg.scale.source_scale <= 0 or cfg.scale.target_scale <= 0:
        raise ConfigError("scale.source_scale and scale.target_scale must be > 0")
    if cfg.source.bbox_mode not in ("auto", "page", "manual"):
        raise ConfigError("source.bbox_mode must be one of: auto, page, manual")
    if cfg.source.bbox_mode == "manual" and len(cfg.source.manual_bbox_mm) != 4:
        raise ConfigError("source.manual_bbox_mm must be [x0, y0, x1, y1] in page mm")
    if cfg.lines.mode not in ("keep", "scale", "fixed"):
        raise ConfigError("lines.mode must be one of: keep, scale, fixed")
    if cfg.lines.mode == "fixed" and cfg.lines.width_mm <= 0:
        raise ConfigError('lines.width_mm must be > 0 when lines.mode = "fixed"')
    if cfg.lines.mode == "scale" and cfg.lines.scale <= 0:
        raise ConfigError('lines.scale must be > 0 when lines.mode = "scale"')
    if (
        cfg.lines.min_width_mm > 0
        and cfg.lines.max_width_mm > 0
        and cfg.lines.min_width_mm > cfg.lines.max_width_mm
    ):
        raise ConfigError("lines.min_width_mm is greater than lines.max_width_mm")
    if cfg.sheet.orientation not in ("auto", "portrait", "landscape"):
        raise ConfigError("sheet.orientation must be one of: auto, portrait, landscape")
    if cfg.sheet.size.lower() == "custom" and len(cfg.sheet.custom_size_mm) != 2:
        raise ConfigError('sheet.custom_size_mm must be [width, height] when size = "custom"')
    if cfg.tiling.overlap_mm < 0:
        raise ConfigError("tiling.overlap_mm must be >= 0")
    if cfg.tiling.label_style not in ("A1", "R1C1", "index"):
        raise ConfigError("tiling.label_style must be one of: A1, R1C1, index")
    if cfg.tiling.page_order not in ("row_major", "column_major"):
        raise ConfigError("tiling.page_order must be row_major or column_major")
    corners = ("auto", "top_left", "top_right", "bottom_left", "bottom_right")
    if cfg.marks.label.corner not in corners:
        raise ConfigError(f"marks.label.corner must be one of: {', '.join(corners)}")
    if cfg.marks.ruler.corner not in corners:
        raise ConfigError(f"marks.ruler.corner must be one of: {', '.join(corners)}")
    if cfg.marks.ticks.units not in ("m", "cm", "mm"):
        raise ConfigError("marks.ticks.units must be m, cm or mm")


def margins_mm(cfg: SheetCfg) -> tuple[float, float, float, float]:
    """Normalise ``sheet.margin_mm`` to (top, right, bottom, left)."""
    value = cfg.margin_mm
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        return v, v, v, v
    if isinstance(value, list) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
    ):
        vals = [float(v) for v in value]
        if len(vals) == 1:
            return vals[0], vals[0], vals[0], vals[0]
        if len(vals) == 2:
            return vals[0], vals[1], vals[0], vals[1]
        if len(vals) == 4:
            return vals[0], vals[1], vals[2], vals[3]
    raise ConfigError(
        "sheet.margin_mm must be a number, [vertical, horizontal] or [top, right, bottom, left]"
    )


def parse_color(value: str) -> tuple[float, float, float]:
    """``"#1f6feb"`` or ``"31,111,235"`` or ``"0.1,0.4,0.9"`` -> RGB floats 0..1."""
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
        if len(text) == 3:
            text = "".join(c * 2 for c in text)
        if len(text) != 6:
            raise ConfigError(f"bad colour {value!r}: expected #rgb or #rrggbb")
        try:
            return tuple(int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            raise ConfigError(f"bad colour {value!r}") from None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise ConfigError(f"bad colour {value!r}: expected #rrggbb or 'r,g,b'")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ConfigError(f"bad colour {value!r}") from None
    if any(n > 1.0 for n in nums):
        nums = [n / 255.0 for n in nums]
    return nums[0], nums[1], nums[2]


def dash_pattern(value: str) -> str | None:
    """``"6 4"`` -> the PDF dash array string PyMuPDF expects."""
    text = value.strip()
    if not text:
        return None
    return f"[{text}] 0"
