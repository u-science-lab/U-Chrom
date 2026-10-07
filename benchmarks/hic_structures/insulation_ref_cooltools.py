"""Reference numbers from cooltools for ``insulation.py`` — run in a separate environment with cooltools
(never imported by uchrom)::

    <venv-with-cooltools>/bin/python insulation_ref_cooltools.py MAP.cool OUT.tsv WINDOW_BP [WINDOW_BP ...]
        [--threshold Li|Otsu|<float>]

Writes the table of ``cooltools.insulation(clr, windows, threshold=...)`` (defaults otherwise: ignore_diags
from the balancing weights, ``min_frac_valid_pixels=0.66``, ``min_dist_bad_bin=0``, whole chromosomes) and
prints its run time (s) on stdout.
"""

import sys
import time
import warnings

warnings.filterwarnings("ignore")


def main(argv):
    import logging

    logging.disable(logging.INFO)
    import cooler
    import cooltools

    threshold = "Li"
    if "--threshold" in argv:
        k = argv.index("--threshold")
        threshold = argv[k + 1]
        argv = argv[:k] + argv[k + 2:]
        try:
            threshold = float(threshold)
        except ValueError:
            pass
    path, out, *windows = argv
    clr = cooler.Cooler(path)
    t = time.time()
    # cooltools 0.7.1 passes the strengths with their NaNs to skimage's threshold_otsu, which fails on them:
    # for "Otsu", call with Li and threshold the finite strengths with skimage's Otsu here
    otsu = threshold == "Otsu"
    table = cooltools.insulation(clr, [int(w) for w in windows], threshold="Li" if otsu else threshold)
    if otsu:
        import numpy as np
        from skimage.filters import threshold_otsu

        for w in windows:
            s = table[f"boundary_strength_{w}"].to_numpy()
            table[f"is_boundary_{w}"] = s >= threshold_otsu(s[np.isfinite(s)])
    print(f"{time.time() - t:.4f}")
    table.to_csv(out, sep="\t", index=False)


if __name__ == "__main__":
    main(sys.argv[1:])
