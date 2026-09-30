"""The web backend on a backed ``.chromdata.zarr`` store: every view must
match the same data loaded in memory (summaries come from ``index/``,
geometry from row ranges)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.browser.web.data import DatasetStore, GeometryFilter, decode_geometry

_FOV0 = Path(__file__).resolve().parents[2] / "example-data" / "takei2025_fov0"
# built by example-data/build_takei2025_fov0.py
TAKEI = _FOV0 / "takei2025_fov0.chromdata.zarr"


def _synthetic():
    rng = np.random.default_rng(1)
    rows, coords = [], []
    for cell in ["c10", "c2", "c1"]:
        for t, chrom in enumerate(["chr2", "chr10", "chr1", "chrX"]):
            for b in rng.permutation(12)[:9]:
                rows.append({"chrom": chrom, "start": 5000 * b, "end": 5000 * (b + 1),
                             "trace_id": f"{cell}_{t}", "cell_id": cell})
                coords.append(rng.normal(size=3))
    coords = np.array(coords)
    coords[[4, 30]] = np.nan
    spots = pd.DataFrame(rows)
    # one trace spanning two chromosomes, as some tracing designs do
    spots.loc[spots.index[:3], "trace_id"] = "c10_1"
    cells = pd.DataFrame({"cell_type": ["A", "B", "A"]}, index=pd.Index(["c1", "c2", "c10"], name="cell_id"))
    cd = ChromData(coords, spots, cells=cells, uns={"xyz_unit": "um"},
                   spot_tracks=pd.DataFrame({"IF": rng.normal(size=len(spots)),
                                             "tag": rng.choice(["p", "q"], len(spots))}))
    cd.bin_tracks = pd.DataFrame({"atac": np.arange(cd.n_bins, dtype=float)})
    return cd


def _pair(tmp_path, cd):
    path = tmp_path / "d.chromdata.zarr"
    cd.write(path, row_group_rows=20)
    backed = DatasetStore().load(path)
    assert backed.backed and backed.cd.backed and backed.name == "d"
    mem = DatasetStore().add(ChromData.read(path), name="d", path=str(path))
    return mem, backed


def _same_geometry(mem, backed, flt):
    a, b = decode_geometry(mem.geometry(flt)), decode_geometry(backed.geometry(flt))
    assert a["header"] == b["header"]
    np.testing.assert_array_equal(a["positions"], b["positions"])
    np.testing.assert_array_equal(a["starts"], b["starts"])
    np.testing.assert_array_equal(a["offsets"], b["offsets"])


def _check(mem, backed, cells, traces, chroms):
    assert backed.summary() == mem.summary()
    assert backed.traces(limit=10_000) == mem.traces(limit=10_000)
    assert backed.traces(chrom=chroms[0]) == mem.traces(chrom=chroms[0])
    assert backed.cells(limit=10_000) == mem.cells(limit=10_000)
    assert backed.known_cells() == mem.known_cells()
    for flt in ([GeometryFilter(cell_ids=[c]) for c in cells]
                + [GeometryFilter(cell_ids=cells[:2] + ["missing"])]
                + [GeometryFilter(trace_ids=[t]) for t in traces]
                + [GeometryFilter(chroms=[c]) for c in chroms]
                + [GeometryFilter(chroms=chroms[:2], cell_ids=cells[:1]),
                   GeometryFilter(region={"chrom": chroms[0], "start": 0, "end": 30_000}),
                   GeometryFilter(cell_ids=cells[:1], max_points=5), GeometryFilter()]):
        _same_geometry(mem, backed, flt)
    kw = dict(chrom=chroms[0])
    assert backed.tracks([t["name"] for t in mem.track_names()], **kw) == \
        mem.tracks([t["name"] for t in mem.track_names()], **kw)
    assert backed.stats_rg(chrom=chroms[0]) == mem.stats_rg(chrom=chroms[0])
    assert backed.distance(**kw) == mem.distance(**kw)


def test_backed_views_match_memory(tmp_path):
    mem, backed = _pair(tmp_path, _synthetic())
    assert [t["name"] for t in backed.track_names()] == ["atac", "IF"]
    _check(mem, backed, ["c1", "c10"], ["c10_1", "c2_3"], ["chr1", "chr2", "chr10"])


def test_backed_views_match_memory_on_real_data(tmp_path):
    if not TAKEI.exists():
        pytest.skip("example-data/takei2025_fov0 not built")
    cd = ChromData.read(TAKEI)
    cells = list(cd.spots["cell_id"].cat.categories[:3])
    cd = cd[cd.spots["cell_id"].isin(cells).to_numpy()]
    mem, backed = _pair(tmp_path, cd)
    traces = list(mem.cd.spots["trace_id"].cat.categories[:2])
    _check(mem, backed, cells[:2], traces, ["chr1", "chr19"])
