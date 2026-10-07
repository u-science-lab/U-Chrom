"""GM12878 single-cell loaders built from contact pairs (uchrom.datasets._load_schic): Tan 2018 Dip-C and
Wu 2025 scMicro-C, per-cell maps at 5 kb; and a pseudo-bulk of their cells.  Need the downloads
(``python -m uchrom.datasets fetch tan2018_gm12878`` / ``fetch wu2025_scmicroc --no-extract``) in the data
directory; skipped without them."""

import pytest

import uchrom.datasets as ds
from tests import DATA_DIR

cooler = pytest.importorskip("cooler")

TAN = DATA_DIR / "tan2018_gm12878"
WU = DATA_DIR / "wu2025_scmicroc"


@pytest.mark.skipif(len(list(TAN.glob("GSM*_gm12878_*.tar.gz"))) < 14, reason="tan2018_gm12878 not downloaded")
def test_tan2018_gm12878_cells_and_maps(tmp_path):
    cd = ds.load("tan2018_gm12878", root=DATA_DIR)
    assert len(cd.cells) == 14 and "gm12878_04" not in cd.cells.index      # no hickit pairs for 4, 8, 16
    assert cd.cells.loc["gm12878_01", "n_contacts"] == 1_048_961           # the file's contacts, each once
    assert cd.uns["genome_assembly"] == "hg19"
    rec = cd.uns["linked_scool"]["per_cell"]
    assert rec["bin_size"] == 5000 and rec["path"] == "tan2018_gm12878_5kb.scool"
    clr = cooler.Cooler(f"{cd.resolve_link_path(rec['path'])}::/cells/gm12878_01")
    assert clr.binsize == 5000 and int(clr.pixels()[:]["count"].sum()) == 1_048_961 and clr.chromnames[0] == "chr1"

    from uchrom.fea import pseudobulk

    two = ["gm12878_01", "gm12878_02"]
    s = pseudobulk(cd, None, cells=two, resolution=1_000_000, trans=False, key_prefix="test_pb",
                   out_dir=tmp_path)
    assert s["n_cis"].iloc[0] == s["n_contacts"].iloc[0] == int(cd.cells.loc[two, "n_cis"].sum())


@pytest.mark.skipif(len(list(WU.glob("GSM*_cell_*.impute.pairs.gz"))) < 12, reason="wu2025_scmicroc not downloaded")
def test_wu2025_scmicroc_cells_and_qc():
    cd = ds.load("wu2025_scmicroc", root=DATA_DIR)
    assert len(cd.cells) == 12 and cd.uns["genome_assembly"] == "hg38"
    assert cd.cells.loc["cell_035", "n_contacts"] == 3_006_012
    assert sorted(cd.cells.index[~cd.cells["qc_pass"].astype(bool)]) == ["cell_026", "cell_051"]
    assert cd.uns["linked_scool"]["per_cell"]["bin_size"] == 5000
