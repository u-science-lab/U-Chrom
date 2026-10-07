"""Structure callers store typed intervals (``cd.intervals``) and bin tracks, and both survive a round trip."""
import numpy as np
import pandas as pd

from chromdata import ChromData


def test_callers_expose_intervals_and_bin_tracks(tmp_path):
    from tests._synth import chain_traces, domain_traces
    from uchrom.strc.comp import call_compartments_axes_pc
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval

    cd = domain_traces(n_traces=60)
    tads = call_tads_by_pval(cd, params=TADCallerParams(window_bp=1.5e5), device="cpu")
    assert cd.intervals["tads.arcfish"] is tads is cd.results["tads.arcfish"]
    assert tads.kind == "domain" and tads.source_result == "tads.arcfish"

    cc = chain_traces(n_traces=60, n_bins=30)
    comp = call_compartments_axes_pc(cc, device="cpu")
    seg = cc.intervals["compartments.axes_pc"]
    assert seg.kind == "segment" and seg["n_bins"].sum() == len(comp) == cc.n_bins
    np.testing.assert_allclose(cc.bin_tracks["compartments.axes_pc.pc2"], comp["pc2"])

    cd.write(tmp_path / "t.chromdata.zarr")
    back = ChromData.read(tmp_path / "t.chromdata.zarr")
    assert back.results["tads.arcfish"] is back.intervals["tads.arcfish"]
    assert back.intervals["tads.arcfish"].kind == "domain"
    pd.testing.assert_frame_equal(pd.DataFrame(back.intervals["tads.arcfish"]), pd.DataFrame(tads))
    assert back.results.record("tads.arcfish").provenance == cd.results.record("tads.arcfish").provenance
