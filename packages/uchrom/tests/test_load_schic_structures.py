"""Tan 2018 Dip-C GM12878 as one ChromData: the authors' structures (homologs as traces, replicate runs as
layers) next to the per-cell maps (uchrom.datasets._load_schic).  Needs the download
(``python -m uchrom.datasets fetch tan2018_gm12878``) in the data directory; skipped without it."""

import numpy as np
import pytest

import uchrom.datasets as ds
from tests import DATA_DIR

TAN = DATA_DIR / "tan2018_gm12878"


@pytest.mark.skipif(len(list(TAN.glob("GSM*_gm12878_*.impute3.round4.clean.3dg.txt.gz"))) < 48
                    or len(list(TAN.glob("GSM*_gm12878_*.tar.gz"))) < 14, reason="tan2018_gm12878 not downloaded")
def test_tan2018_structures_and_maps():
    cd = ds.load("tan2018_gm12878", root=DATA_DIR, backed=True)
    assert len(cd.cells) == 14 and cd.uns["genome_assembly"] == "hg19"
    assert cd.uns["linked_scool"]["per_cell"]["bin_size"] == 5000          # the maps are still linked
    s = cd.uns["structures"]
    assert s["format"] == "dipc" and s["particle_size"] == 20_000 and s["particle_position"] == "end"
    assert set(cd.layers) == {"rep1", "rep2"} and "rep_deviation" in cd.spot_tracks.columns
    tr = cd.traces
    assert set(tr["homolog"]) == {"pat", "mat"} and tr["cell_id"].nunique() == 14
    c21 = cd.get_chrom("chr21")
    assert c21.n_traces == 28                                                # 14 cells x 2 homologs
    loci = c21.spots_with_loci()
    assert (loci["start"] % 20_000 == 0).all() and ((loci["end"] - loci["start"]) == 20_000).all()
    # the first chr21 particle of cell 1's maternal copy: file position 15,320,000 -> (15.30, 15.32 Mb]
    first = loci[loci["trace_id"] == "gm12878_01_chr21_mat"].sort_values("start").iloc[0]
    assert (first["start"], first["end"]) == (15_300_000, 15_320_000)
    # replicate runs: ~1 particle radius apart after superposition (Tan et al. 2018)
    assert 0.3 < float(cd.cells["rmsd_rep1"].median()) < 2.0
    rep = np.asarray(c21.layers["rep1"])
    assert np.isfinite(rep).all(1).mean() > 0.99
