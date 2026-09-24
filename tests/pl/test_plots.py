"""Plotting smoke tests (matplotlib Agg; PyVista off-screen)."""
import numpy as np
import pandas as pd
import pytest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


@pytest.fixture(autouse=True)
def _close():
    yield
    plt.close("all")


def _mat(n=8):
    i = np.arange(n)
    return np.abs(i[:, None] - i[None, :]).astype(float)


def test_plot_distance_matrix_and_contact_map():
    from uchrom.pl import plot_contact_map, plot_distance_matrix

    bins = [(k * 1000, (k + 1) * 1000) for k in range(8)]
    for fn in (plot_distance_matrix, plot_contact_map):
        fig, ax = plt.subplots()
        out = fn(_mat(), bin_ids=bins, title="t", ax=ax)
        assert out is not None
        assert ax.get_title() == "t"
        assert len(ax.images) == 1


def test_plot_rg_histogram():
    from uchrom.pl import plot_rg_histogram

    fig, ax = plt.subplots()
    plot_rg_histogram(pd.Series(np.random.default_rng(0).gamma(2, size=100)),
                      bins=10, ax=ax)
    assert len(ax.patches) == 10


def test_plot_structure_3d_offscreen(tmp_path):
    pv = pytest.importorskip("pyvista")
    from uchrom import ChromData
    from uchrom.pl import plot_structure_3d

    old, pv.OFF_SCREEN = pv.OFF_SCREEN, True
    n = 30
    t = np.linspace(0, 4 * np.pi, n)
    spots = pd.DataFrame({"chrom": "chr1", "start": np.arange(n) * 1000,
                          "end": np.arange(1, n + 1) * 1000, "trace_id": 0})
    cd = ChromData(np.c_[np.cos(t), np.sin(t), t / 4], spots)
    png = tmp_path / "s.png"
    try:
        plotter = plot_structure_3d(cd, show=False, save_png=str(png),
                                    window_size=(200, 150), notebook=False)
    except Exception as e:  # no GL context on this runner
        if "render" in str(e).lower() or "opengl" in str(e).lower():
            pytest.skip(f"no off-screen GL: {e}")
        raise
    finally:
        pv.OFF_SCREEN = old
    assert plotter is not None
    assert png.exists() and png.stat().st_size > 0
