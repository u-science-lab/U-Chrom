"""Plots of called structures: domains / loops on a matrix, compartment tracks (matplotlib Agg)."""
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


def _bins(n=10, chrom="chr1"):
    return pd.DataFrame({"chrom": chrom, "start": np.arange(n) * 1000, "end": np.arange(1, n + 1) * 1000})


def test_draw_domains_from_a_table_and_from_row_pairs():
    from uchrom.pl import draw_domains

    fig, ax = plt.subplots()
    ax.imshow(np.zeros((10, 10)))
    tads = pd.DataFrame({"chrom": ["chr1", "chr1", "chr1", "chr2"], "start": [0, 3000, 0, 0],
                         "end": [3000, 10000, 10000, 5000], "level": [1, 1, 2, 1]})
    patches = draw_domains(ax, tads, _bins(), level=1, edgecolor="cyan")
    assert [(p.get_x(), p.get_width()) for p in patches] == [(-0.5, 3), (2.5, 7)]     # chr2 left out
    assert patches[0].get_edgecolor()[:3] == matplotlib.colors.to_rgb("cyan")
    window = _bins().iloc[2:6]                                                       # rows 2..5 of a larger map
    clipped = draw_domains(ax, tads[tads.level == 1], window)
    assert [(p.get_x(), p.get_width()) for p in clipped] == [(0.5, 3)]               # [2,3) too short, [3,6) kept
    assert len(draw_domains(ax, [(0, 4), (4, 5), (5, 10)])) == 2                     # a 1-row domain left out
    with pytest.raises(TypeError, match="bins"):
        draw_domains(ax, tads)


def test_draw_loops_both_triangles_or_one():
    from uchrom.pl import draw_loops

    fig, ax = plt.subplots()
    ax.imshow(np.zeros((10, 10)))
    loops = pd.DataFrame({"chrom1": ["chr1", "chr2"], "start1": [1000, 1000], "start2": [7000, 7000]})
    (line,) = draw_loops(ax, loops, _bins())
    assert list(line.get_xdata()) == [7, 1] and list(line.get_ydata()) == [1, 7]
    two = draw_loops(ax, loops, _bins()["start"].to_numpy(), symmetric=False, mec="white")   # no chrom: both
    assert len(two) == 2
    one = two[0]
    assert list(one.get_xdata()) == [7] and list(one.get_ydata()) == [1]
    assert len(draw_loops(ax, loops, _bins())) == 1                                 # chr2 left out (chrom of bins)


def test_plot_compartments_tracks_and_bars():
    from uchrom import ChromData
    from uchrom.pl import plot_compartments

    b = _bins(8)
    spots = b.assign(trace_id=0)
    cd = ChromData(np.zeros((8, 3)), spots)
    lab = np.array(list("AABBBAAB"))
    cd.results.set("c1", b.assign(compartment=lab, pc2=np.where(lab == "A", 1.0, -1.0)), kind="table", function="t")
    cd.results.set("c2", b.assign(compartment=lab, pc1=np.linspace(-1, 1, 8)), kind="table", function="t")
    fig = plot_compartments(cd, ["c1", "c2"], names=["imaging", "Hi-C"])
    assert len(fig.axes) == 4
    assert fig.axes[0].get_ylabel() == "imaging" and fig.axes[2].get_ylabel() == "Hi-C"
    assert fig.axes[-1].get_xlabel() == "chr1 position (Mb)"
    assert np.array_equal(fig.axes[1].images[0].get_array()[0], (lab == "A").astype(float))
