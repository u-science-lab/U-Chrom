"""Bulk MDS: recover a known structure from its distance / contact matrix."""
import numpy as np
import torch
from scipy.spatial.distance import pdist, squareform
from scipy.stats import spearmanr


def _helix(n=60):
    t = np.linspace(0, 4 * np.pi, n)
    return np.c_[np.cos(t), np.sin(t), 0.3 * t]


def test_smacof_recovers_exact_distances():
    from uchrom.recon.bulk.mds.torch_mds import compute_stress, smacof

    X = _helix()
    D = squareform(pdist(X))
    Y = smacof(torch.as_tensor(D), device="cpu", n_iter=300)
    assert Y.shape == X.shape
    assert np.allclose(Y.mean(0), 0, atol=1e-6)
    r = np.corrcoef(pdist(Y), pdist(X))[0, 1]
    assert r > 0.999
    stress = float(compute_stress(torch.as_tensor(Y), torch.as_tensor(D)))
    assert np.isfinite(stress)


def test_run_mds_from_contacts_preserves_distance_ranks():
    from uchrom.recon.bulk.mds import run_mds

    X = _helix()
    D = squareform(pdist(X))
    C = np.zeros_like(D)
    off = ~np.eye(len(D), dtype=bool)
    C[off] = D[off] ** -3.0          # contact ∝ d^-α, α = 3
    C[:, 5] = C[5, :] = 0.0          # an empty bin → must be dropped
    Y, keep = run_mds(torch.as_tensor(C), alpha=3.0, device="cpu", weight=0.0,
                      n_iter=300)
    assert keep.sum() == len(D) - 1 and not keep[5]
    assert Y.shape == (len(D) - 1, 3)
    rho = spearmanr(pdist(Y), pdist(X[keep])).correlation
    assert rho > 0.95


def _linked_helix_map(tmp_path, chroms=("chr1",), n=60, res=10_000):
    """A ChromData holding a .cool whose counts follow a known helix per chromosome (contact ∝ d^-3)."""
    import cooler
    import pandas as pd
    from chromdata import ChromData

    X = _helix(n)
    D = squareform(pdist(X))
    i, j = np.triu_indices(n, 1)
    bins, pixels = [], []
    for k, c in enumerate(chroms):
        bins.append(pd.DataFrame({"chrom": c, "start": np.arange(n) * res, "end": np.arange(1, n + 1) * res}))
        pixels.append(pd.DataFrame({"bin1_id": i + k * n, "bin2_id": j + k * n,
                                    "count": np.rint(1e4 * D[i, j] ** -3.0).astype(int) + 1}))
    path = tmp_path / "helix.cool"
    cooler.create_cooler(str(path), pd.concat(bins, ignore_index=True), pd.concat(pixels, ignore_index=True),
                         ordered=True, assembly="toy")
    cooler.balance_cooler(cooler.Cooler(str(path)), store=True)
    cd = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                   "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str)}),
                   uns={"genome_assembly": "toy"})
    cd.link_cool(str(path), key="bulk")
    return cd, X, path


def test_reconstruct_mds_on_a_linked_map(tmp_path):
    from uchrom.recon.bulk.mds import reconstruct_mds

    import cooler

    cd, X, path = _linked_helix_map(tmp_path, chroms=("chr1", "chr2"))
    balanced = cooler.Cooler(str(path)).bins()[:]["weight"].notna().to_numpy()   # ICE masks a few end bins
    out = reconstruct_mds(cd, contacts="bulk", alpha=3.0, weight=0.0, device="cpu", n_iter=300, cell_id="toy")
    assert out.n_spots == balanced.sum() and out.n_traces == 2 and set(out.spots["cell_id"]) == {"toy"}
    assert out.uns["xyz_unit"] == "arbitrary (MDS)" and out.uns["genome_assembly"] == "toy"
    assert out.uns["mds"]["contacts"] == "bulk" and out.uns["mds"]["resolution"] == 10_000
    table = out.results["mds.chroms"]
    assert table["chrom"].tolist() == ["chr1", "chr2"] and table["n_kept"].tolist() == [balanced[:60].sum()] * 2
    chr1 = out.get_chrom("chr1")
    truth = X[chr1.spots_with_loci()["start"].to_numpy() // 10_000]
    assert spearmanr(pdist(chr1.coords), pdist(truth)).correlation > 0.9          # ICE bends d^-3 a little
    raw = reconstruct_mds(cd, chrom="chr1", balance=False, alpha=3.0, weight=0.0, device="cpu", n_iter=300)
    assert raw.n_spots == 60 and spearmanr(pdist(raw.coords), pdist(X)).correlation > 0.95
    same = reconstruct_mds(str(path), chrom="chr2", alpha=3.0, weight=0.0, device="cpu", n_iter=300, key_added=None)
    assert same.n_spots == balanced[60:].sum() and "mds" not in same.uns
    assert np.allclose(same.coords, out.get_chrom("chr2").coords)       # the path form: the same structure
    adam = reconstruct_mds(cd, chrom="chr1", alpha=3.0, weight=0.0, device="cpu", n_iter=300, method="adam")
    assert adam.uns["mds"]["solver"] == "adam" and adam.n_spots == balanced[:60].sum()
    part = reconstruct_mds(cd, chrom="chr1", balance=False, alpha=3.0, device="cpu", n_iter=100, mode="partitioned",
                           res_ratio=6)
    assert part.n_spots == 60 and np.isfinite(part.coords).all()


def test_mds_command_line_reads_a_store(tmp_path):
    from chromdata import ChromData

    from uchrom.recon.bulk.mds import reconstruct_mds

    from uchrom.recon.bulk.mds.__main__ import main

    cd, X, path = _linked_helix_map(tmp_path)
    store = tmp_path / "hic.chromdata.zarr"
    cd.link_cool(path.name, key="bulk")                      # relative to the store's folder
    cd.write(store)
    out = tmp_path / "mds.chromdata.zarr"
    main(str(store), str(out), contacts="bulk", device="cpu", alpha=3.0, weight=0.0, n_iter=300)
    s = ChromData.read(out)
    direct = reconstruct_mds(ChromData.read(store), contacts="bulk", device="cpu", alpha=3.0, weight=0.0, n_iter=300)
    assert s.n_spots == direct.n_spots > 40 and s.uns["mds"]["contacts"] == "bulk"
