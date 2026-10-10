"""uchrom.pl.plot_spatial: one panel per section, numeric and categorical colours."""

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd

from uchrom.pl import plot_spatial

from ..spatial.test_spatial import _grid_cd


def test_plot_spatial_panels():
    cd = _grid_cd(regions=("s1", "s2"))
    axes = plot_spatial(cd, "gradient")
    assert [a.get_title() for a in axes] == ["s1", "s2"]
    assert len(axes[0].collections) == 1 and len(axes[0].collections[0].get_offsets()) == 120
    vals = pd.Series(np.where(np.arange(240) % 7 == 0, np.nan, 1.0), index=cd.cells["cell_id"])
    axes = plot_spatial(cd, vals, regions=["s2"], center=1.0, cmap="RdBu_r")
    assert len(axes) == 1 and len(axes[0].collections) == 2          # missing cells drawn grey first
    axes = plot_spatial(cd, "type")
    assert axes[-1].get_legend() is not None
