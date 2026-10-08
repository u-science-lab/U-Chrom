# hic_structures — committed results

The numbers behind `../README.md` and the docs page *Calling structures from a map*, as the benchmark scripts
wrote them.  Collected after the fact (2026-10-08): they predate `benchmarks/_record.py`, so they carry no
`provenance` block — it is this table.  New runs write theirs with `_record.save` and are checked against these
with `python benchmarks/_record.py OLD NEW --rtol ...`.  The large outputs of the same runs (maps, call tables,
thinned maps, reference-tool outputs) are archived on Sherlock's Oak:
`$OAK/uchrom/results/hic_structures/2026-10-07_1ca8197/hic_structures_runs_2026-10-07.tar`.

| File | What | Script | Produced |
| --- | --- | --- | --- |
| `insulation.json` | insulation vs cooltools, vs Arrowhead edges, vs ArcFISH, depth thinning, chr1 5 kb profile | `insulation.py` | 2026-10-07, laptop (macOS arm64, shared) |
| `compartments.json` | eig / saddle vs cooltools, vs Su 2020 tracing, depth | `compartments.py` | 2026-10-07, laptop |
| `compartments_profile.json` | chr1 at 100 / 25 / 5 kb: time and memory by stage | `compartments_profile.py` | 2026-10-07, laptop |
| `hiccups.json` | HiCCUPS vs cooltools `dots`, vs Rao 2014 loops, depth, chr1 profile | `hiccups.py` | 2026-10-07, laptop |
| `hiccups_ref/*.json` | cooltools `dots` run times (reference env) | `hiccups_ref_cooltools.py` | 2026-10-07, laptop |
| `pileup.json` | APA by depth, imaging loops, boundaries, GM12878 pseudo-bulk | `pileup.py` | 2026-10-07, laptop |
| `mustache_validate.json` | Mustache vs mustache-hic (kernels, whole chromosomes), vs Rao 2014, depth | `mustache_validate.py` | 2026-10-07, laptop |
| `mustache_chr1_profile.json` | chr1 5 kb time and memory | `mustache_validate.py` (chr1 run) | 2026-10-07, laptop |
| `pseudobulk_dschic.json` | 7 cell-type maps of dscHi-C over HTTP: time by stage, exactness | `pseudobulk_dschic.py` | 2026-10-07, laptop |
| `pseudobulk_gm12878.json` | GM12878 pseudo-bulk (Dip-C + scMicro-C) vs Rao 2014 | `pseudobulk_gm12878.py` | 2026-10-07, laptop |
| `native_speed.json` | `uchrom-maps` vs numpy: identity on 7 maps, chr1 speed by threads | `native_speed.py` | 2026-10-07, laptop (load 8-12) |

Code: branch `Nanguage/hic-structures` while it was developed (merged as PR #116, 545f168; native kernels
1ca8197).  Timings on the shared laptop are approximate; compare speeds only on the same machine.
