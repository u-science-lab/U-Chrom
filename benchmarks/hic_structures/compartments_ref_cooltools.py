"""Reference numbers from cooltools for ``compartments.py`` — run in a separate environment with cooltools
(never imported by uchrom)::

    <venv-with-cooltools>/bin/python compartments_ref_cooltools.py MAP.cool PHASING.tsv OUT.npz [N_BINS]

``PHASING.tsv``: ``chrom, start, end, value`` on the map's bins (the GC content uchrom computed).  Writes
``eigvals`` / ``E1..E3`` (``eigs_cis``, defaults: clip 99.9, ignore_diags from the weights, whole
chromosomes), ``exp_*`` (``expected_cis``), the saddle ``S`` / ``C`` (``saddle`` on cooltools' own E1,
``qrange=(0.025, 0.975)``, ``n_bins`` groups, ``min_diag=3``), ``strength`` (``saddle_strength``) and the run
times.
"""

import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


def main(path, phasing, out, n_bins=38):
    import cooler
    import cooltools

    clr = cooler.Cooler(path)
    view = pd.DataFrame({"chrom": list(clr.chromnames), "start": 0,
                         "end": [int(clr.chromsizes[c]) for c in clr.chromnames], "name": list(clr.chromnames)})
    track = pd.read_csv(phasing, sep="\t")
    t = time.time()
    eigvals, eigvecs = cooltools.eigs_cis(clr, phasing_track=track, view_df=view, n_eigs=3)
    t_eig = time.time() - t
    t = time.time()
    exp = cooltools.expected_cis(clr, view_df=view, smooth=False, aggregate_smoothed=False)
    S, C = cooltools.saddle(clr, exp, eigvecs[["chrom", "start", "end", "E1"]], "cis", n_bins=int(n_bins),
                            qrange=(0.025, 0.975), view_df=view, min_diag=3)
    t_saddle = time.time() - t
    from cooltools.api.saddle import saddle_strength

    np.savez(out, chrom=np.asarray(eigvecs["chrom"].astype(str), dtype=str), start=eigvecs["start"].to_numpy(),
             E1=eigvecs["E1"].to_numpy(), E2=eigvecs["E2"].to_numpy(), E3=eigvecs["E3"].to_numpy(),
             eigvals=eigvals[["eigval1", "eigval2", "eigval3"]].to_numpy(),
             exp_diag=exp["dist"].to_numpy(), exp_avg=exp["balanced.avg"].to_numpy(),
             S=S, C=C, strength=saddle_strength(S, C), t_eig=t_eig, t_saddle=t_saddle)


if __name__ == "__main__":
    main(*sys.argv[1:4], *([int(sys.argv[4])] if len(sys.argv) > 4 else []))
