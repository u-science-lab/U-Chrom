"""uchrom.emb.metrics: cluster agreement, kNN purity, embedding scores."""

import numpy as np
import pandas as pd
import pytest


def test_cluster_agreement_and_knn_purity():
    from uchrom.emb import cluster_agreement, knn_purity

    truth = np.array(list("aaabbb"))
    assert cluster_agreement([1, 1, 1, 0, 0, 0], truth) == {"ARI": 1.0, "NMI": 1.0}
    assert cluster_agreement([1, 0, 1, 0, 1, 0], truth)["ARI"] < 0.1
    x = np.r_[np.zeros((3, 2)), np.ones((3, 2)) * 10] + np.random.default_rng(0).normal(0, 0.1, (6, 2))
    assert knn_purity(x, truth, k=2) == 1.0
    with pytest.raises(ValueError):
        cluster_agreement([1, 2], truth)


def test_score_embedding_masks_and_depth():
    from chromdata import ChromData
    from uchrom.emb import score_embedding

    rng = np.random.default_rng(1)
    n = 40
    truth = np.repeat(["x", "y"], n // 2)
    emb = np.where(truth[:, None] == "x", 0.0, 5.0) + rng.normal(0, 0.3, (n, 3))
    emb[0] = np.nan                                         # a cell that was not embedded
    no_spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                             [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str), ("cell_id", str)]})
    cells = pd.DataFrame({"type": truth, "depth": rng.integers(100, 1000, n),
                          "qc": np.where(np.arange(n) % 4 == 0, "fail", "pass")},
                         index=pd.Index([f"c{i}" for i in range(n)], name="cell_id"))
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells, cellm={"e": emb})
    s = score_embedding(cd, "e", "type", depth="depth")
    assert s["n_cells"] == n - 1 and s["ARI"] == 1.0 and s["kNN purity"] == 1.0
    assert 0 <= s["|r| dim 1 ~ log depth"] <= 1
    assert score_embedding(cd, "e", "type", cells="qc")["n_cells"] == 30         # the cells marked "pass"
    assert score_embedding(cd, "e", "type", cells=["c1", "c2", "c30", "c31"])["n_cells"] == 4
