from pathlib import Path
from pipeline.render_nb import render_notebook


def test_render_real_notebook(tmp_path):
    nb = Path(__file__).resolve().parents[3] / "tutorials" / "takei2025_walkthrough.ipynb"
    if not nb.exists():
        import pytest
        pytest.skip("notebook fixture missing")
    out = tmp_path / "out.html"
    ok = render_notebook(str(nb), str(out))
    assert ok is True
    assert out.exists()
    assert out.stat().st_size > 1000
    assert "<html" in out.read_text(errors="ignore").lower()


def test_render_missing_notebook_returns_false(tmp_path):
    out = tmp_path / "out.html"
    ok = render_notebook(str(tmp_path / "nope.ipynb"), str(out))
    assert ok is False
    assert not out.exists()
