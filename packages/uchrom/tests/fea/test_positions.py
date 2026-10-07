"""uchrom.fea.positions: spot centroids per cell / trace and the radial position of every spot."""
import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.fea import radial_position, spot_centroids


def _nuclei(seed=0):
    """Two cells, spots spread over spheres of radius 2 and 5 around (0, 0, 0) and (20, 0, 0)."""
    rng = np.random.default_rng(seed)
    rows, coords = [], []
    for cell, (centre, radius) in {"a": (0.0, 2.0), "b": (20.0, 5.0)}.items():
        for t in range(3):
            for k in range(40):
                v = rng.normal(size=3)
                coords.append(np.r_[centre, 0, 0] + radius * rng.uniform(0, 1) * v / np.linalg.norm(v))
                rows.append(("chr1", k * 1000, k * 1000 + 1000, f"{cell}_{t}", cell))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    return ChromData(np.array(coords), spots)


def test_spot_centroids():
    cd = _nuclei()
    xyz = pd.DataFrame(cd.coords, columns=list("xyz"))
    cell = cd.spots["cell_id"].astype(str).to_numpy()
    pd.testing.assert_frame_equal(spot_centroids(cd), xyz.groupby(cell).mean().rename_axis("cell_id"))
    med = spot_centroids(cd, by="trace", stat="median")
    assert med.index.name == "trace_id" and len(med) == 6
    assert np.allclose(med.loc["b_0"], [20, 0, 0], atol=2.5)
    with pytest.raises(ValueError, match="stat"):
        spot_centroids(cd, stat="max")
    with pytest.raises(ValueError, match="by"):
        spot_centroids(cd, by="chrom")


def test_radial_position_scaled_per_cell():
    cd = _nuclei()
    r = radial_position(cd)
    assert r.name == "radial_position" and len(r) == cd.n_spots
    assert np.array_equal(cd.spot_tracks["radial_position"].to_numpy(), r.to_numpy())
    assert cd.uns["feature_registry"][-1]["feature_group"] == "radial_position"
    cell = cd.spots["cell_id"].astype(str)
    # scaled: the 95th percentile of every cell is 1, whatever the nucleus size
    q = r.groupby(cell.to_numpy()).quantile(0.95)
    assert np.allclose(q, 1.0)
    # by hand: distance to the per-axis median of the cell's spots over its 95th percentile
    xyz = np.asarray(cd.coords)
    for c in ("a", "b"):
        m = (cell == c).to_numpy()
        d = np.linalg.norm(xyz[m] - np.median(xyz[m], axis=0), axis=1)
        assert np.allclose(r[m], d / np.quantile(d, 0.95))
    raw = radial_position(cd, scale=None, key_added=None)
    assert "radial_position" in cd.spot_tracks and raw.max() > 2       # unscaled: in coordinate units
    assert raw[(cell == "b").to_numpy()].median() > 2 * raw[(cell == "a").to_numpy()].median()


def test_radial_position_options(tmp_path):
    cd = _nuclei()
    new = radial_position(cd, by="trace", centre="mean", key_added="r_trace", copy=True)
    assert "r_trace" in new.spot_tracks and "r_trace" not in cd.spot_tracks
    with pytest.raises(ValueError, match="scale"):
        radial_position(cd, scale=1.5)
    with pytest.raises(ValueError, match="copy=True"):
        radial_position(cd, key_added=None, copy=True)
    path = tmp_path / "n.chromdata.zarr"
    cd.write(path)
    backed = ChromData.read(path, backed=True)
    with pytest.raises(ValueError, match="read-only"):
        radial_position(backed)
    r = radial_position(backed, key_added=None)
    assert len(r) == cd.n_spots and np.isfinite(r).all()
    nocell = ChromData(cd.coords, cd.spots.drop(columns="cell_id"))
    with pytest.raises(KeyError, match="cell_id"):
        radial_position(nocell)
