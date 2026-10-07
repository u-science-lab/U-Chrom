"""Tables of the EMber-pop held-back test (PREREG_POP.md sections 4 and 10) for pop_pair.sbatch.

    python benchmarks/bulk/sherlock/pop_test_tables.py --out benchmarks/bulk/sherlock/pop_tables

* ``test_main.tsv``: (su_test, takei_test) x (C1, C2, C3) x seeds 1-3, S = 1,000, full schedule:
  EMber-pop, IGM-sphere, IGM-ellipsoid back to back on one GPU;
* ``test_real.tsv``: real_imr90 (input ``real.npz``), seeds 1-3, the same three methods;
* ``test_sweep.tsv``: su_test C1, seed 1, S = 200 / 500 / 1,000 / 2,000: EMber-pop and IGM-sphere;
* ``test_ablation.tsv``: (su_test, takei_test) x (C1, C2, C3), seed 1, S = 1,000: EMber-pop without the
  non-contact restraints, with IGM's sphere instead of the gyration prior, with the radius-of-gyration
  cap (one imaging scalar) instead of the gyration prior, and with the gyration spring 1.
"""

from __future__ import annotations

import argparse
from pathlib import Path

PLOIDY = {"su_test": "diploid", "takei_test": "male", "real_imr90": "diploid"}
MAIN = [("ember_pop", "ember_pop", "{}"), ("igm_sphere", "igm_sphere", "{}"), ("igm_ellipsoid", "igm_ellipsoid", "{}")]
ABLATIONS = [
    ("ember_pop_no_nc", "ember_pop", '{"noncontact_kspring":0.0}'),
    ("ember_pop_sphere", "ember_pop", '{"nucleus_shape":"sphere","gyration_prior":[0,0,0]}'),
    ("ember_pop_rgcap", "ember_pop", '{"gyration_prior":[0,0,0],"rg_cap":"imaging"}'),
    ("ember_pop_gyr_k1", "ember_pop", '{"gyration_kspring":1.0}'),
]


def line(unit, cond, S, steps, seed, methods):
    f = [unit, cond, str(S), str(steps), str(seed), PLOIDY[unit]]
    for name, meth, par in methods:
        f += [name, meth, par]
    return "\t".join(f)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    units = ["su_test", "takei_test"]
    conds = ["C1", "C2", "C3"]
    tables = {
        "test_main.tsv": [line(u, c, 1000, 1.0, s, MAIN) for s in (1, 2, 3) for u in units for c in conds],
        "test_real.tsv": [line("real_imr90", "real", 1000, 1.0, s, MAIN) for s in (1, 2, 3)],
        "test_sweep.tsv": [line("su_test", "C1", S, 1.0, 1, [(f"{n}_S{S}", m, p) for n, m, p in MAIN[:2]])
                           for S in (200, 500, 1000, 2000)],
        "test_ablation.tsv": [line(u, c, 1000, 1.0, 1, ABLATIONS) for u in units for c in conds],
    }
    for name, rows in tables.items():
        (out / name).write_text("\n".join(rows) + "\n")
        print(name, len(rows))


if __name__ == "__main__":
    main()
