"""The public API -- the surface another program (a GUI) builds on.

If something here breaks, a downstream caller breaks with it.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import printsplit  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "config" / "example.toml"


def test_exports_are_all_reachable():
    for name in printsplit.__all__:
        assert getattr(printsplit, name) is not None, name


def test_every_error_derives_from_one_base():
    for err in (printsplit.ConfigError, printsplit.SourceError, printsplit.LayoutError):
        assert issubclass(err, printsplit.PrintSplitError)


def test_paper_sizes_are_exposed():
    assert printsplit.PAPER_SIZES_MM["A0"] == (841.0, 1189.0)
    assert printsplit.PAPER_SIZES_MM["A4"] == (210.0, 297.0)


def test_plan_reports_the_layout_without_writing():
    cfg = printsplit.load_config(EXAMPLE)
    with printsplit.plan(cfg) as job:
        assert job.layout.sheet_count > 0
        assert job.layout.rows >= 1 and job.layout.cols >= 1
        assert job.magnification == 20.0
        assert job.assembled_w_mm > job.assembled_h_mm  # the sample is landscape
        assert job.outputs == []  # nothing written yet
        assert len(job.layout.tiles) == job.layout.rows * job.layout.cols


def test_job_closes_and_refuses_to_render_afterwards():
    cfg = printsplit.load_config(EXAMPLE)
    job = printsplit.plan(cfg)
    job.close()
    try:
        printsplit.render(job)
    except printsplit.PrintSplitError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected PrintSplitError after close()")


def test_render_writes_files_and_reports_progress():
    cfg = printsplit.load_config(EXAMPLE)
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg.project.output_dir = tmpdir
        seen = []
        with printsplit.plan(cfg) as job:
            printsplit.render(job, progress=lambda i, n, label: seen.append((i, n, label)))
            assert job.tiles_pdf and job.tiles_pdf.is_file()
            assert job.outputs and all(p.is_file() for p in job.outputs)
            expected = job.layout.sheet_count
        assert len(seen) == expected
        assert seen[-1][0] == seen[-1][1] == expected  # ends at n of n


def test_checks_run_on_a_planned_job():
    cfg = printsplit.load_config(EXAMPLE)
    with printsplit.plan(cfg) as job:
        findings = printsplit.source_findings(job, compare=False)
    assert findings
    assert {f.level for f in findings} <= {"ok", "note", "warn"}
    assert all(f.check and f.message for f in findings)


def test_missing_source_raises_source_error():
    cfg = printsplit.from_dict({"project": {"input": "does/not/exist.pdf"}})
    try:
        printsplit.plan(cfg)
    except printsplit.SourceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected SourceError")


def test_impossible_layout_raises_layout_error():
    cfg = printsplit.load_config(EXAMPLE)
    cfg.tiling.overlap_mm = 5000.0  # wider than any sheet
    try:
        with printsplit.plan(cfg):
            pass
    except printsplit.LayoutError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected LayoutError")


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
