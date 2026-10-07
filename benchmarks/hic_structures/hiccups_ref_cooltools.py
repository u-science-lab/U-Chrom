"""Reference numbers from cooltools ``dots`` for ``hiccups.py`` — run in a separate environment with cooltools
(never imported by uchrom)::

    <venv-with-cooltools>/bin/python hiccups_ref_cooltools.py MAP.cool OUT_PREFIX MAX_SEPARATION_BP [--no-pixels]

Writes ``OUT_PREFIX_pixels.tsv`` (``dots(..., clustering_radius=None)``: the enriched pixels before
clustering, with their locally adjusted expecteds and q-values; skipped with ``--no-pixels``) and
``OUT_PREFIX_dots.tsv`` (``dots`` with its defaults: Birch clustering at 20 kb, the HiCCUPS filter), and prints
one JSON line with the run times (s) and the peak memory (GB, ``ru_maxrss``).  The expected is
``expected_cis`` (whole chromosomes, ``ignore_diags=2``), ``max_loci_separation`` as given, one process.
"""

import json
import logging
import resource
import sys
import time
import warnings

warnings.filterwarnings("ignore")


def main(argv):
    logging.disable(logging.WARNING)
    import cooler
    import cooltools
    import pandas as pd

    pixels = "--no-pixels" not in argv
    path, prefix, max_sep = [a for a in argv if a != "--no-pixels"][:3]
    clr = cooler.Cooler(path)
    view = pd.DataFrame({"chrom": list(clr.chromnames), "start": 0,
                         "end": [int(clr.chromsizes[c]) for c in clr.chromnames], "name": list(clr.chromnames)})
    out = {}
    t = time.time()
    exp = cooltools.expected_cis(clr, view_df=view, nproc=1)
    out["expected_s"] = time.time() - t
    if pixels:
        t = time.time()
        px = cooltools.dots(clr, expected=exp, view_df=view, max_loci_separation=int(max_sep),
                            clustering_radius=None, nproc=1)
        out["pixels_s"] = time.time() - t
        px.to_csv(prefix + "_pixels.tsv", sep="\t", index=False)
        out["n_pixels"] = len(px)
    t = time.time()
    d = cooltools.dots(clr, expected=exp, view_df=view, max_loci_separation=int(max_sep), nproc=1)
    out["dots_s"] = time.time() - t
    d.to_csv(prefix + "_dots.tsv", sep="\t", index=False)
    out["n_dots"] = len(d)
    out["max_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e9 if sys.platform == "darwin" else 1e6)
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1:])
