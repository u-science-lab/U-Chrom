# hic_structures — structure calling on bulk / pseudo-bulk Hi-C maps

Validation of U-Chrom's own implementations of the standard map-based callers (no cooltools / Mustache /
chromosight dependency; those tools run only here, as references, in a separate environment):

| library function | method | script |
| --- | --- | --- |
| `uchrom.strc.comp.call_compartments_eig`, `compartment_strength` | cis eigenvector, phased by GC; saddle strength | `compartments.py`, `compartments_profile.py` |
| `uchrom.strc.tad.call_tads_insulation`, `insulation_score` | diamond insulation score (Crane 2015), Li threshold | `insulation.py` |
| `uchrom.strc.loop.call_loops_hiccups` | HiCCUPS (Rao 2014) in cooltools' formulation | `hiccups.py` |
| `uchrom.strc.loop.call_loops_mustache` | Mustache scale-space detection (Roayaei Ardakany 2020) | `mustache_validate.py` |
| `uchrom.fea.pileup` | aggregate peak analysis of known loops / boundaries | `pileup.py` |
| `uchrom.fea.pseudobulk` | per-cell maps summed per cell group, ICE | `pseudobulk_dschic.py`, `pseudobulk_gm12878.py` |

All of them read the map banded and sparse (`uchrom.fea.band.read_band`), so a 5 kb map of chr1 (49,851
bins) runs on a laptop.  Data (registered, documented in `apps/atlas/recipes/README.md`, section "Hi-C
structure calling on maps"): `rao2014_imr90_chr21`, `rao2014_imr90_chr1`, `rao2014_gm12878_chr21` (Rao 2014
slices, 5 kb, hg19), `rao2014_annotations` (the authors' HiCCUPS loops and Arrowhead domains), `hg19_chr21`
/ `hg19_chr1` (GC phasing), `hg38_to_hg19_chain`; single cells `tan2018_gm12878`, `wu2025_scmicroc`
(loaders) and the atlas store `dschic_aging_cortex`.

Every script prints its tables and writes JSON to `--out` (a scratch directory; nothing is written into the
repository).  The reference tools run in a separate environment given by `--ref-python` /
`--cooltools-python` (the `*_ref_*.py` / `mustache_reference_blocks.py` helpers run inside it):

```sh
python3.12 -m venv ctenv
ctenv/bin/pip install "numpy<2" "pandas<3" "scipy<1.15" cooltools==0.7.1 mustache-hic==1.3.3
```

(cooltools 0.7.1 `dots` fails on pandas 3 and mustache-hic 1.3.3 on numpy 2; `expected_cis`, `insulation`
and `eigs_cis` also work in a numpy 2 / pandas 3 environment.)

## Results (2026-10-07, a macOS laptop shared with other jobs: times are approximate)

**Agreement with the reference implementations** (same balanced maps):

- compartments vs cooltools `eigs_cis` / `saddle`: E1 r = 1, max difference ~1e-14, identical eigenvalues
  and saddle strength on 5 maps (IMR90 / GM12878 chr21, IMR90 chr1; 100 and 25 kb).
- insulation vs cooltools `insulation`: log2 scores within 1.5e-13, identical boundaries in all 20
  map × window combinations (IMR90 / GM12878 chr21, 10 / 25 kb, windows 3–25 bins).
- HiCCUPS vs cooltools `dots` (`pvalue="cooltools"`): identical enriched pixels on all 6 maps (IMR90 /
  GM12878 chr21 at 5 / 10 / 25 kb), local expecteds within 4e-11; final summits 91 / 96 and 68 / 68 in
  common at 10 kb (the clustering differs on purpose: HiCCUPS' greedy radius, not Birch).
- Mustache vs mustache-hic 1.3.3: the reference's kernels give our values; calls within ±2 bins agree
  89–96 % (82 % on GM12878 5 kb; we take statistics per chromosome instead of per 10 Mb block).

**Against the published Rao 2014 calls** (IMR90 chr21: 92 HiCCUPS loops, 86 Arrowhead domains):

| caller | map | recall | precision | tolerance |
| --- | --- | --- | --- | --- |
| HiCCUPS | 10 kb (5 + 10 kb merged) | 0.76 (0.79) | 0.74 (0.74) | anchors within 25 kb |
| HiCCUPS | GM12878 10 kb (merged) | 0.62 (0.72) | 0.90 (0.90) | 25 kb |
| HiCCUPS | IMR90 chr1 5 kb (827 loops) | 0.52 | 0.85 | 25 kb |
| Mustache | 5 kb / 10 kb | 0.95 / 0.72 | 0.41 / 0.42 | 25 kb (mustache-hic: 0.92 / 0.73 recall) |
| insulation | 10 kb / 25 kb (Arrowhead edges) | 0.69 / 0.71 | 0.86 / 0.97 | 2 bins (chance 0.15–0.24 / 0.23–0.42) |
| insulation | IMR90 chr1 10 kb / 25 kb | 0.71 / 0.71 | 0.88 / 0.96 | 2 bins |

Compartments against imaging: E1 of the Rao IMR90 map vs Su 2020 tracing (`call_compartments_axes_pc`,
hg38 → hg19 by offset): A/B agreement 0.936, r = 0.913.  Insulation boundaries vs ArcFISH boundaries of the
same tracing: 0.88 near an imaged boundary (chance 0.41).

**Depth** (binomial thinning of IMR90 chr21, 100 % = 10.3 M chr21 contacts; atlas cell-type pseudo-bulks are
~2–20 %):

| depth | HiCCUPS recall 10 kb | Mustache recall 10 kb | APA of the published loops 10 kb (random p95) | insulation: full-depth boundaries recovered 25 kb | saddle strength |
| --- | --- | --- | --- | --- | --- |
| 100 % | 0.76 | 0.72 | 4.22 (1.21) | 1 | 1 |
| 20 % | 0.33 | 0.54 | 4.25 | 0.97 | |
| 5 % | 0.01 | 0.11 | 3.84 (1.66) | 0.91 | |
| 2 % | 0 | 0 | 4.67 (1.77) | 0.88 | +16 % |

Loops can be *called* only at bulk depth; below ~5 % score known loops by pileup (APA stays ~4).  Saddle
strength rises as depth falls: compare strengths at matched depth.

**Pseudo-bulk**: on dscHi-C (32,777 cells, 1 Mb, over HTTP) the 7 cell-type maps sum to the store's
all-cells map pixel for pixel (2.6 G contacts), 78 s, 2.5 GB peak.  GM12878 from 24 single cells (Dip-C +
scMicro-C, ~1 % of Rao's chr21 depth): SCC with Rao GM12878 0.55 at 100 kb, below the depth-matched ceiling
(Rao thinned to the same depth: 0.73) but above Rao IMR90 (0.36); APA of the published GM12878 loops 4.96
(z 19) where HiCCUPS calls 12 loops (recall 0.05).

**Run time on IMR90 chr1 at 5 kb** (49,851 bins, 26.5 M pixels):

| step | time | peak memory | reference |
| --- | --- | --- | --- |
| `read_band` (whole chromosome) | 0.8 s | 1.3 GB (the pixels) | |
| insulation (100 kb window) | 1.5 s | ~0.3 GB | cooltools 3.1 s |
| compartments (E1..E3) | 8.2 s | 2.8 GB | cooltools: dense, ~20 GB |
| HiCCUPS, loops ≤ 2 / 10 Mb | 6.1 / 15.8 s | 1.3 / 2.3 GB | cooltools 93 s, 4.1 GB (2 Mb) |
| Mustache | 16–19 s | 1.5 GB | mustache-hic 184 s |
| ICE (`rebin_map` to 10 kb) | 2.9 s | | `cooler balance` 70 s |

The two hot loops — the kernel sums of HiCCUPS (`hiccups._score_chrom`) and the Gaussian scale space of
Mustache (`mustache._scan`) — run natively when `packages/uchrom-maps` is installed (Rust, rayon;
`u-chrom[maps]`).  `native_speed.py` checks the two paths against each other and times them:

- **identical results**: on IMR90 / GM12878 chr21 at 5 / 10 / 25 kb and IMR90 chr1 at 5 kb, native and
  numpy give the same HiCCUPS scores, histograms, enriched pixels and calls (chr1 10 Mb: 64.8 M tested
  pixels, 1.14 M candidates) and the same Mustache scans and calls, bit for bit.  The Mustache scan copies
  scipy's Gaussian arithmetic, which depends on the scipy build: `uchrom_maps.scipy_arithmetic()` finds
  it (macOS arm64: fused multiply-adds with an unfused vector block; Linux x86-64 and arm64 wheels of
  scipy 1.18: every product and sum rounded — checked in Docker); no match → numpy, with a warning.
- **speed** (chr1 5 kb, best of 3 on a loaded 18-core laptop):

  | case | numpy: whole call / ported part | native, 1 thread | 4 threads | 18 threads |
  | --- | --- | --- | --- | --- |
  | HiCCUPS, loops ≤ 2 Mb | 8.4 / 5.7 s | 3.7 / 1.2 s | 3.9 / 0.5 s | 2.6 / 0.4 s |
  | HiCCUPS, loops ≤ 10 Mb | 26.3 / 23.5 s | 6.7 / 4.4 s | 5.5 / 2.1 s | 4.1 / 1.1 s |
  | Mustache | 22.8 / 16.6 s | 7.7 / 3.7 s | 7.6 / 1.8 s | 6.3 / 1.1 s |

  The ported parts are 15–21× faster on all cores; whole calls are now bound by what stays in Python
  (`read_band` ~1 s, the expected, clustering, Mustache's normalisation) and peak memory by the band read.
