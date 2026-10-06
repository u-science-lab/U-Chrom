"""
Tests for imputation on data with MISSING ROWS (absent loci), not just NaN rows.

These encode the desired behavior after the densification + ordering fix:
- Real FISH/tracing data represents a missing locus as an ABSENT row.
- Imputation must densify onto the per-chrom locus panel, fill, and return
  a ChromData whose spots are the full grid (NaN where unfillable).
- Non-missing coordinates must never be scrambled, regardless of input row order.
"""

import numpy as np
import pandas as pd
import pytest


PANEL_STARTS = np.arange(0, 800, 100)  # 8 loci on one chrom
N_LOCI = len(PANEL_STARTS)
N_TRACES = 5


def _make_panel_chromdata(seed=0, drop_frac=0.3, as_absent_rows=True):
    """Build a FISH-like ChromData: N_TRACES traces sharing one locus panel.

    A smooth 3D curve per trace (so interpolation/snapfish have signal), then
    `drop_frac` of (trace, locus) entries are removed.  If as_absent_rows is
    True the dropped entries become ABSENT rows; otherwise they stay as NaN rows.
    Each trace is guaranteed to keep >= 2 present loci.
    """
    from chromdata import ChromData

    rng = np.random.RandomState(seed)
    rows = []
    coords = []
    for t in range(N_TRACES):
        # smooth curve along the panel, trace-specific phase
        phase = t * 0.7
        for i, s in enumerate(PANEL_STARTS):
            x = np.sin(0.4 * i + phase) * 300 + rng.randn() * 5
            y = np.cos(0.4 * i + phase) * 300 + rng.randn() * 5
            z = i * 40 + rng.randn() * 5
            rows.append(dict(chrom="chr1", start=int(s), end=int(s + 100),
                             trace_id=f"t{t}"))
            coords.append([x, y, z])
    spots = pd.DataFrame(rows)
    coords = np.asarray(coords, dtype=float)

    # choose entries to drop, keeping >=2 per trace
    drop_mask = np.zeros(len(spots), dtype=bool)
    for t in range(N_TRACES):
        idx = np.where(spots["trace_id"].values == f"t{t}")[0]
        n_drop = min(int(len(idx) * drop_frac), len(idx) - 2)
        if n_drop > 0:
            drop_mask[rng.choice(idx, n_drop, replace=False)] = True

    if as_absent_rows:
        keep = ~drop_mask
        cd = ChromData(coords=coords[keep],
                       spots=spots[keep].reset_index(drop=True))
    else:
        coords[drop_mask] = np.nan
        cd = ChromData(coords=coords, spots=spots)
    return cd


def _present_keys(cd):
    """Map (chrom, start, trace_id) -> coord for non-NaN spots."""
    out = {}
    for i in range(len(cd.spots)):
        if not np.isnan(cd.coords[i, 0]):
            k = (cd.spots["chrom"].iloc[i], int(cd.spots["start"].iloc[i]),
                 cd.spots["trace_id"].iloc[i])
            out[k] = cd.coords[i]
    return out


def test_linear_fills_absent_rows():
    """Linear imputation must add rows for absent loci and fill them."""
    from uchrom.im.impute import impute_linear

    cd = _make_panel_chromdata(as_absent_rows=True)
    assert len(cd.spots) < N_TRACES * N_LOCI  # some rows really are absent

    out = impute_linear(cd)

    # output is the full dense grid
    assert len(out.spots) == N_TRACES * N_LOCI
    # all interpolable loci filled (each trace kept >=2 points, extrapolate=True)
    assert np.isnan(out.coords).sum() == 0


def test_snapfish_handles_absent_rows():
    """SnapFISH must not crash on absent rows and must reduce missingness."""
    pytest.importorskip("skimage")
    from uchrom.im.impute import impute_snapfish

    cd = _make_panel_chromdata(as_absent_rows=True)
    out = impute_snapfish(cd, max_iter=20, verbose=False)

    assert len(out.spots) == N_TRACES * N_LOCI
    grid_cells = N_TRACES * N_LOCI * 3
    present = sum(1 for k in _present_keys(cd)) * 3
    missing_before = grid_cells - present
    missing_after = int(np.isnan(out.coords).sum())
    assert missing_after < missing_before


def test_snapfish_preserves_nonmissing_under_shuffle():
    """Non-missing coords must stay correct regardless of input row order."""
    pytest.importorskip("skimage")
    from chromdata import ChromData
    from uchrom.im.impute import impute_snapfish

    cd = _make_panel_chromdata(as_absent_rows=True)
    rng = np.random.RandomState(1)
    perm = rng.permutation(len(cd.spots))
    cd_shuf = ChromData(coords=cd.coords[perm],
                        spots=cd.spots.iloc[perm].reset_index(drop=True))

    out = impute_snapfish(cd_shuf, max_iter=20, verbose=False)

    in_keys = _present_keys(cd_shuf)
    out_keys = {}
    for i in range(len(out.spots)):
        k = (out.spots["chrom"].iloc[i], int(out.spots["start"].iloc[i]),
             out.spots["trace_id"].iloc[i])
        out_keys[k] = out.coords[i]

    for k, v in in_keys.items():
        assert k in out_keys, f"present spot {k} missing from output"
        np.testing.assert_allclose(out_keys[k], v, rtol=1e-3, atol=1e-3,
                                   err_msg=f"coord scrambled at {k}")


def test_linear_dense_nan_rows_preserved():
    """When rows already exist as NaN, linear keeps the same grid and values."""
    from uchrom.im.impute import impute_linear

    cd = _make_panel_chromdata(as_absent_rows=False)  # NaN rows, full grid
    before = _present_keys(cd)

    out = impute_linear(cd)
    assert len(out.spots) == N_TRACES * N_LOCI

    out_keys = {}
    for i in range(len(out.spots)):
        k = (out.spots["chrom"].iloc[i], int(out.spots["start"].iloc[i]),
             out.spots["trace_id"].iloc[i])
        out_keys[k] = out.coords[i]
    for k, v in before.items():
        np.testing.assert_allclose(out_keys[k], v, rtol=1e-9)


def test_missing_snapfish_deps_reports_specific_module():
    """Availability check must name the actually-missing module(s)."""
    from uchrom.im.impute import _missing_snapfish_deps

    # all deps installed in this env -> empty
    assert _missing_snapfish_deps() == []
    # with an injected importer, the missing one is named precisely
    def fake_import(name):
        if name == "skimage":
            raise ImportError("no skimage")
        return None
    assert _missing_snapfish_deps(_import=fake_import) == ["scikit-image"]


def test_ann_restores_locus_absent_from_all_traces():
    """A locus missing from EVERY trace is restored when an ann panel is given.

    Union inference can only see observed loci; an explicit annotation panel
    lets imputation add a locus that no trace observed.
    """
    from uchrom.im.impute import impute_linear

    cd = _make_panel_chromdata(as_absent_rows=True)
    # Drop one panel locus from every trace entirely.
    dropped_start = int(PANEL_STARTS[3])
    keep = cd.spots["start"].to_numpy() != dropped_start
    from chromdata import ChromData
    cd = ChromData(coords=cd.coords[keep],
                   spots=cd.spots[keep].reset_index(drop=True))
    assert (cd.spots["start"] == dropped_start).sum() == 0

    # Without ann: union inference cannot resurrect the locus.
    out_union = impute_linear(cd)
    assert (out_union.spots["start"] == dropped_start).sum() == 0

    # With ann: the full panel is restored for every trace.
    ann = pd.DataFrame({
        "chrom": "chr1",
        "start": PANEL_STARTS.astype(int),
        "end": (PANEL_STARTS + 100).astype(int),
    })
    out_ann = impute_linear(cd, ann=ann)
    assert (out_ann.spots["start"] == dropped_start).sum() == N_TRACES
    assert np.isnan(out_ann.coords).sum() == 0

