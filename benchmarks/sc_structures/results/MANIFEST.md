# sc_structures — committed results

The numbers behind `../README.md` and the docs page *Calling structures from single cells*, as the benchmark
scripts wrote them on Sherlock (node sh04-05n13, 2 × AMD EPYC 9754, 256 CPUs, shared, load 50-130; numpy 2.2.6).
Collected after the fact (2026-10-08), before `benchmarks/_record.py`: no `provenance` block, this table is it.
The large outputs of the same runs (call tables, imputed maps, models, logs; SnapHiC's own run without its
per-cell files) are archived on Oak: `$OAK/uchrom/results/sc_structures/2026-10-08_ad141a7/{scab,snaphic,structures,logs}.tar`
(see its `MANIFEST.txt`).

| Files | What | Script | Sherlock jobs |
| --- | --- | --- | --- |
| `snaphic/snaphic_mesc_summary.json` | SnapHiC vs the paper (precision / recall / APA) by N, whole chromosomes and windows, pooled HiCCUPS | `snaphic_mesc.py` | 46956631 |
| `snaphic/snaphic_N*_r*[_whole].json`, `pseudobulk_N*_r*.json` | each run of that summary (cells N, replicate r) | `snaphic_mesc.py` | 46951979, 46955046, 46956471, 46956505, 46956512 |
| `snaphic/bonev.json` | HiCCUPS on bulk Bonev 2017 (the reference) | `snaphic_mesc.py` | 46950649 |
| `snaphic/snaphic_reference.json` | U-Chrom vs the authors' SnapHiC on 100 cells | `snaphic_reference.py` | 46956454, 46958403 |
| `snaphic/impute_speed.json`, `window.json` | RWR / SnapHiC native vs numpy, threads | `impute_speed.py` | 46949527 |
| `snaphic/impute_domains.json` | single-cell boundaries vs bulk insulation | `impute_domains.py` | 46956721 |
| `snaphic/snaphic_gm12878.json` | GM12878 (24 cells) vs Rao 2014 | `snaphic_gm12878.py` | 46967685 |
| `snaphic/snaphic_data.json` | the Nagano 2017 store build | `snaphic_data.py` | 46949523 |
| `scab/scab_{tan2021,dschic,gm12878,kim2020}.json` | scA/B vs Dip-C / scHiCluster, cell types, E1, depth | `scab_*.py` | 46947615, 46946721, 46946722 (env venv-consensus: numpy 2.2.6, pandas 2.2.3, scipy 1.14.1) |
| `structures/gm12878_callers.json` | tracing callers on Dip-C structures vs Rao 2014, by traces | `structures_callers.py` | 46949011 |
| `structures/imaging_su2020_takei2021.json` | the same callers on imaging, by traces | `structures_imaging.py` | 46948060 |
| `structures/stevens2017_mesc.json` | Stevens 2017 structures vs Bonev E1 | `structures_imaging.py` | 46962743 |
| `structures/ember_gm12878.json` | EMber reconstructions through the callers | `structures_ember.py` | 46948062 |

Code: branch `Nanguage/sc-structures` (work in progress d54248b and its uncommitted changes, squashed into
ad141a7).
