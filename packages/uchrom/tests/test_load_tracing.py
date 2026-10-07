"""Tracing loaders of ``uchrom.datasets``: the Su et al. 2020 chr21 loader on a miniature of its original
files (offline), and on the real files when they are in the data directory."""

import numpy as np
import pandas as pd
import pytest

import uchrom.datasets as ds

from tests import DATA_DIR

HEADER = "Z(nm)\tX(nm)\tY(nm)\tGenomic coordinate\tChromosome copy number\tGene names\tTranscription\tTSS ZXY(nm)\n"
LOCI = ["chr21:10400001-10450001", "chr21:10500001-10550001", "chr21:13250001-13300001"]


def _mini_su2020(folder):
    folder.mkdir(parents=True)
    rows = []
    for copy in (1, 2):
        for k, locus in enumerate(LOCI):
            z, x, y = (100 * copy + k, 200 + k, 300 + k)
            if copy == 2 and k == 1:
                z = x = y = ""                                   # not detected
            genes = {0: "", 1: "GENE1;GENE2;", 2: "GENE3;"}[k]
            rows.append(f"{z}\t{x}\t{y}\t{locus}\t{copy}\t{genes}\t\t\n")
    (folder / "chromosome21.tsv").write_text(HEADER + "".join(rows))
    counts = np.array([[10, 4, 1], [4, 12, 3], [1, 3, 9]])
    pd.DataFrame(counts, index=LOCI, columns=LOCI).to_csv(folder / "Hi-C_contacts_chromosome21.tsv", sep="\t")
    return counts


def test_su2020_chr21_loader_on_a_miniature(monkeypatch, tmp_path):
    import cooler
    from chromdata import ChromData
    from uchrom.datasets import _load_tracing

    folder = tmp_path / "data" / "su2020_imr90"
    counts = _mini_su2020(folder)
    monkeypatch.setattr(ds, "fetch", lambda name, root=None, **kw: folder)
    out = tmp_path / "data" / "su2020_chr21" / "su2020_chr21.chromdata.zarr"
    cd = _load_tracing.build_su2020_chr21(tmp_path / "data", out)
    assert cd.n_spots == 5 and cd.n_traces == 2 and cd.n_bins == 3
    assert cd.bins["start"].tolist() == [10_400_000, 10_500_000, 13_250_000]
    assert cd.bins["end"].tolist() == [10_450_000, 10_550_000, 13_300_000]
    assert cd.bin_tracks["n_genes"].tolist() == [0, 2, 1]
    assert sorted(cd.spots["trace_id"].unique().tolist()) == [1, 2]
    first = cd.get_trace(1).to_dataframe().sort_values("start")
    assert np.allclose(first[["x", "y", "z"]].to_numpy(), [[0.2, 0.3, 0.1], [0.201, 0.301, 0.101], [0.202, 0.302, 0.102]])
    assert cd.uns["xyz_unit"] == "micron" and cd.uns["genome_assembly"] == "hg38"

    cd.write(out)                                            # as ds.load does; the link is relative
    back = ChromData.read(out)
    assert back.uns["linked_cool"]["rao2014"]["path"] == "su2020_chr21_rao2014.cool"
    clr = cooler.Cooler(back.linked_cool_path("rao2014"))
    assert clr.bins()[:]["start"].tolist() == [0, 10_400_000, 10_500_000, 13_250_000]
    m = clr.matrix(balance=False)[:]
    assert m[0].sum() == 0 and np.array_equal(m[1:, 1:], counts)
    assert "weight" in clr.bins().columns


def test_su2020_chr21_loader_rejects_other_hic_loci(monkeypatch, tmp_path):
    from uchrom.datasets import _load_tracing

    folder = tmp_path / "su2020_imr90"
    _mini_su2020(folder)
    hic = pd.read_csv(folder / "Hi-C_contacts_chromosome21.tsv", sep="\t", index_col=0)
    hic.index = hic.columns = ["chr21:1-50001"] + list(hic.index[1:])
    hic.to_csv(folder / "Hi-C_contacts_chromosome21.tsv", sep="\t")
    monkeypatch.setattr(ds, "fetch", lambda name, root=None, **kw: folder)
    with pytest.raises(ValueError, match="not the imaged loci"):
        _load_tracing.build_su2020_chr21(tmp_path, tmp_path / "x" / "x.chromdata.zarr")


@pytest.mark.slow
def test_su2020_chr21_real_files():
    if not (DATA_DIR / "su2020_imr90" / "chromosome21.tsv").exists():
        pytest.skip("Su 2020 chr21 not in the data directory (python -m uchrom.datasets fetch su2020_chr21)")
    cd = ds.load("su2020_chr21", root=DATA_DIR)
    assert (cd.n_spots, cd.n_traces, cd.n_bins) == (4_622_909, 7_591, 651)
    assert int(cd.bin_tracks["n_genes"].sum()) > 0
    assert "rao2014" in cd.uns["linked_cool"]


@pytest.mark.slow
def test_su2020_chr21_build_matches_the_stored_dataset(tmp_path):
    """The loader, run again on the original files, gives the stored dataset (spots, coordinates, loci, gene
    counts) and the same Hi-C (raw counts and ICE weights)."""
    import cooler
    from uchrom.datasets import _load_tracing

    if not (DATA_DIR / "su2020_imr90" / "chromosome21.tsv").exists():
        pytest.skip("Su 2020 chr21 not in the data directory (python -m uchrom.datasets fetch su2020_chr21)")
    stored = ds.load("su2020_chr21", root=DATA_DIR)
    built = _load_tracing.build_su2020_chr21(DATA_DIR, tmp_path / "su2020_chr21" / "su2020_chr21.chromdata.zarr")
    order = lambda c: np.lexsort((c.spots["bin_id"].to_numpy(), c.spots["trace_id"].to_numpy()))  # noqa: E731
    a, b = order(stored), order(built)
    assert np.array_equal(stored.coords[a], built.coords[b])
    assert np.array_equal(stored.spots["bin_id"].to_numpy()[a], built.spots["bin_id"].to_numpy()[b])
    assert np.array_equal(stored.spots["trace_id"].to_numpy()[a], built.spots["trace_id"].to_numpy()[b])
    pd.testing.assert_frame_equal(stored.bins, built.bins)
    pd.testing.assert_frame_equal(stored.bin_tracks, built.bin_tracks)
    old = cooler.Cooler(stored.linked_cool_path("rao2014"))
    new = cooler.Cooler(str(tmp_path / "su2020_chr21" / built.uns["linked_cool"]["rao2014"]["path"]))
    pd.testing.assert_frame_equal(old.bins()[:], new.bins()[:])
    pd.testing.assert_frame_equal(old.pixels()[:], new.pixels()[:])
    assert int(new.pixels()[:]["count"].sum()) == 9_898_707
