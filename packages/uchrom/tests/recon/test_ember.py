"""EMber (``uchrom.recon.sc.reconstruct_ember``): a thin public wrapper over the native engine's
protocol ``"robust"``.  Skipped when the native engine is not installed."""

from pathlib import Path

import numpy as np
import pytest
from tests import REPO

un = pytest.importorskip("uchrom_recon")

PAIRS = REPO / "example-data" / "cell1.pairs"
QUICK = dict(particle_sizes=[2e6, 4e5, 2e5], n_models=2, seed=5, device="cpu")


@pytest.fixture(autouse=True)
def _need_data():
    if not PAIRS.exists():
        pytest.skip("example-data/cell1.pairs missing")


def test_ember_equals_protocol_robust_and_records_provenance():
    from uchrom.recon.sc import reconstruct_ember, reconstruct_nucdyn

    e = reconstruct_ember(str(PAIRS), chrom="chr19", **QUICK)
    r = reconstruct_nucdyn(str(PAIRS), genome_ranges="chr19", protocol="robust", **QUICK)
    a = reconstruct_nucdyn(str(PAIRS), genome_ranges="chr19", protocol="ember", **QUICK)
    for k in r.layers:
        np.testing.assert_array_equal(e.layers[k], r.layers[k])
        np.testing.assert_array_equal(a.layers[k], r.layers[k])
    info = e.uns["ember"]
    assert info["method"] == "ember" and info["protocol"] == "robust"
    assert "EMber" in info["citation"]
    assert e.results.record("ember.stages").function == "uchrom.recon.sc.ember.reconstruct_ember"
    n = e.results.record("ember.stages").inputs["n_contacts"]  # chr19 contacts
    assert e.results["ember.contact_weights"].shape == (n,)
    assert r.uns["nucdyn"]["method"] == "nucdyn"


def test_tl_alias_dispatches():
    import uchrom as uc

    e = uc.tl.reconstruct_sc(str(PAIRS), chrom="chr19", **QUICK)
    assert e.uns["ember"]["method"] == "ember"
    with pytest.raises(ValueError):
        uc.tl.reconstruct_sc(str(PAIRS), method="nope")
