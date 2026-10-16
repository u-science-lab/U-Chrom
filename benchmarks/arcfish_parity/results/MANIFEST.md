# benchmarks/arcfish_parity/results

| File | What | Run |
|---|---|---|
| `parity.json` | U-Chrom's ArcFISH callers against the authors' package (github.com/hyuyu104/ArcFISH at a21d889) on five datasets (`compare.py`): loci, trace counts, axis weights, normalised variances and counts (in memory and streaming), the TAD per-locus statistics, FDR, boundary calls and domains (all levels), the insulation method (scores, boundaries, domains), the loop test matrices, candidates, clusters, summits and loops, the compartment eigenvectors and A/B calls; per dataset the run times of both. `{"results", "provenance"}` | 2026-10-13, Sherlock jobs 47732259, 47738660 (node sh04-05n13, 8 CPUs) |
| `streaming.json` | The ArcFISH part of the streaming validation (`benchmarks/cd21_streaming_validation.py`, `child_callers`) re-run with these callers (`streaming_check.py`): Takei 2021 mESC (4DN FOF-CT 4DNFIHF3JCBY, all 20 chromosomes), loop F-test and TAD caller in memory (`device="cpu"`) against `streaming=True` (`memory_budget="256MB"`); every column compared, floats by their largest difference. `{"results", "provenance"}` | 2026-10-15, Sherlock job 47904579 (sh04-05n13, 4 CPUs; uchrom b6d8873) |

## Result

Every call is identical on every dataset:

| Dataset | Loci x traces | TAD boundaries | Insulation boundaries | Loops (candidates / loops) | A/B |
|---|---|---|---|---|---|
| `takei2021_chr6` (the authors' loop / domain tutorial: Takei 2021 mESC, both replicates, chr6, 25 kb) | 60 x 921 | 6 | 2 | 51 / 2 | identical |
| `su2020_chr2p` (the authors' compartment tutorial: Su 2020 chr2 p-arm, first 100 traces) | 357 x 100 | 38 | 27 | 211 / 10 | identical |
| `takei2025_chr15_1mb` (Takei 2025 FOV 0, chr15, 1-Mb trace averages; window 4 Mb) | 101 x 86 | 7 | 10 | 0 / 0 | identical |
| `bintu2018` (Bintu 2018 IMR90 chr21, 30 kb) | 65 x 1,277 | 2 | 1 | 11 / 1 | identical |
| `su2020_chr21` (Su 2020 IMR90 chr21, 50 kb, first 1,000 traces) | 651 x 1,000 | 71 | 50 | 1,737 / 145 | identical |

(Loop counts are locus pairs; `parity.json` counts the entries of the symmetric matrices, twice these.)
Statistics agree to 1e-8 relative or better (normalised variances 1e-10, axis weights exactly); the only larger
relative differences are p-values below ~1e-15, where `1 - Cauchy.cdf(stat)` keeps no significant digits in either
implementation (the statistics themselves agree to 1e-8).

Run times on the same node (s; U-Chrom's times include recomputing the normalised cube for each caller):

| Dataset | Authors: normalise / TAD / loops / A-B | U-Chrom: normalise / TAD / loops / A-B |
|---|---|---|
| `takei2021_chr6` | 3.0 / 0.03 / 0.43 / 0.05 | 2.8 / 2.3 / 0.7 / 1.7 |
| `su2020_chr2p` | 20.7 / 0.14 / 19.5 / 0.16 | 7.1 / 6.6 / 3.2 / 3.6 |
| `su2020_chr21` (1,000 traces) | 279 / 0.3 / 462 / 0.3 | 81 / 131 / 66 / 67 |

The authors' loop caller holds every trace's pairwise differences at once: on all 7,591 traces of `su2020_chr21`
it needed more than 64 GB and was killed (U-Chrom works in row blocks, or streams).  With the defaults, loci 250 kb
or 1 Mb apart leave nothing to test and the authors' code stops in the FDR step (zero tests), so `inputs.py`
scales the TAD window and the loop background to those datasets.

## Streaming (`streaming.json`)

Streamed and in-memory calls are identical: 10 loops and 190 domains (125 boundaries) with the same positions, levels
and summits; the statistics differ by at most 3.7e-14 (loops; P values, FDR, scores and contact frequencies exactly
equal) and 3.8e-11 relative (domains).  With the callers before the parity re-implementation (2026-10-05, uchrom
1df6e89) the same check had given 5 loops and 223 domains.  Run times, in memory / streamed: loops 12.5 / 12.7 s,
domains 7.1 / 9.8 s.
