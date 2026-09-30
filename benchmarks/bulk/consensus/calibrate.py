"""Imaging calibration of the contact → distance power law (the "oracle" alpha / scale).

Fits ``median distance = d0 * f^(-1/alpha)`` (log-log least squares, ``fit_power_law``) over the cis
locus pairs of an imaging set, f = the balanced Hi-C frequency (normalised by the adjacent-bin
expectation f_nn, as the method's targets) of the bins holding the two loci.  alpha is used by
``tasks_real.tsv`` (``alpha=@<cell>``); d0 converts the model unit (adjacent-bin distance) to nm
(``scale_nm``).  This uses the validation data, so runs with it are flagged "calibrated (oracle)".

    python benchmarks/bulk/consensus/calibrate.py --imaging IMG/su2020_genome.npz --cell imr90 \
        --resolution 250000 --out CAL/imr90.json
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import _bc
from _bc import hic_source, map_loci_to_bins, write_json


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imaging", required=True)
    ap.add_argument("--cell", required=True, choices=sorted(_bc.CELLS))
    ap.add_argument("--resolution", type=int, default=250_000)
    ap.add_argument("--min-count", type=int, default=20)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from mds_baselines import balanced_genome
    from uchrom.recon.bulk.consensus import ConsensusParams, fit_power_law

    z = np.load(a.imaging, allow_pickle=True)
    loci = pd.DataFrame({"chrom": z["chrom"].astype(str), "start": z["start"], "end": z["end"]})
    M, bins, valid, ch = balanced_genome(hic_source(a.cell), a.resolution, list(dict.fromkeys(loci.chrom)),
                                         ConsensusParams())
    bc = bins["chrom"].to_numpy()
    adj = np.array([M[t, t + 1] for t in np.flatnonzero(bc[1:] == bc[:-1]) if valid[t] and valid[t + 1]])
    f_nn = float(adj[adj > 0].mean())
    idx = map_loci_to_bins(loci, bins)
    iu = np.triu_indices(len(loci), 1)
    a_i, a_j = idx[iu[0]], idx[iu[1]]
    ok = (a_i >= 0) & (a_j >= 0) & (a_i != a_j) & (loci.chrom.to_numpy()[iu[0]] == loci.chrom.to_numpy()[iu[1]])
    f = np.where(ok, M[np.maximum(a_i, 0), np.maximum(a_j, 0)] / f_nn, np.nan)
    d = z["median"][iu].astype(float)
    k = ok & (f > 0) & np.isfinite(d) & (z["count"][iu] >= a.min_count)
    alpha, d0 = fit_power_law(f[k], d[k])
    out = {"cell": a.cell, "imaging": a.imaging, "resolution": a.resolution, "alpha": alpha,
           "d0_nm_at_f_nn": d0, "n_pairs": int(k.sum()), "f_nn": f_nn,
           "note": "oracle calibration on the validation imaging (cis pairs); d0 = nm per adjacent-bin distance"}
    write_json(a.out, out)
    print(out)


if __name__ == "__main__":
    main()
