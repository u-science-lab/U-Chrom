# uchrom-maps

Native kernels of the Hi-C map callers of [U-Chrom](../../README.md), written in Rust with PyO3
bindings: the two hot loops of the bulk callers that profiling on a 5-kb map of human chr1 (49,851 bins,
26.5 M pixels) singled out, and the imputation of single-cell maps.

* **HiCCUPS scoring** (`hiccups_score`, used by `uchrom.strc.loop.hiccups`): for every testable pixel of
  one chromosome's band, the four locally adjusted expecteds (donut, vertical, horizontal, lower-left
  kernels), the λ-chunk of each, the per-kernel (λ-chunk × count) histograms and the candidate filter.
* **Mustache scan** (`mustache_scan`, used by `uchrom.strc.loop.mustache`): the Gaussian scale space of the
  normalised band, differences of Gaussians, 3 × 3 maxima, the best response and detection layer of every
  pixel and the per-layer statistics of the exponential fits.

* **Random walk with restart** (`rwr_band`, used by `uchrom.fea.impute_rwr` and `uchrom.strc.loop.snaphic`):
  the imputation of one cell's chromosome as SnapHiC (Yu et al. 2021) and scHiCluster (Zhou et al. 2019) do
  it, per whole chromosome or in sliding windows (SnapHiC2), as the band of `R = rp (G D + D G)`,
  `G = (D - (1 - rp) A)^-1`.  Per chromosome / window a Cholesky factorisation in *profile* storage (each row from its leftmost neighbour or the band,
  whichever is further) and the selected inversion of Takahashi et al. (1973): only the entries of `G`
  inside the profile, `O(sum_j |S_j|^2)` instead of the `O(m^3)` dense inverse of the numpy reference;
  windows in parallel.  `zscore_band` / `local_background` / `snaphic_chrom`: SnapHiC's per-diagonal
  z-scores (trimmed mean and sd by selection, not sorting), local backgrounds (row prefix sums) and the
  sums over cells of its paired t-test, cells in parallel batches — memory one chromosome's sums plus the
  bands of the cells in flight.

The HiCCUPS and Mustache kernels reproduce the numpy reference in `uchrom` **bit for bit** (one exception: on
x86-64 numpy's SIMD loops sum in another order, so Mustache's per-layer |L| sums — and the scores from them —
agree to ~1e-16 relative there, with the same calls): the same row tiles, the same summed-area
tables built in the order `np.cumsum` builds them, Gaussians in the arithmetic of
`scipy.ndimage.correlate1d`, sums in numpy's pairwise order.  How scipy's compiled `correlate1d`
accumulates depends on the build: the macOS arm64 wheels (scipy 1.18) fuse multiply-adds, except in a
vectorised loop that takes the first `8 * floor(s / 8)` of `s >= 10` terms unfused (read from the
disassembly of `NI_Correlate1D`); a build for the x86-64 baseline has no FMA instruction and should round
every operation (not verified here).  `uchrom_maps.scipy_arithmetic()` finds the scheme of the installed scipy once
per process (a small probe against `scipy.ndimage.gaussian_filter`) and the scan copies it; when no
known scheme matches, `uchrom` falls back to scipy.  The calls, the enriched
pixels, the histograms and every value are identical; only time and memory change.  Tiles run in
parallel (rayon); HiCCUPS keeps only the `2w + 2` summed-area-table rows a pixel row needs instead of
dense tiles, Mustache filters only the band around the eligible pixels.

The RWR kernel solves the same systems as the numpy reference by another factorisation (the reference
inverts each window's dense matrix with LAPACK), so it agrees to rounding — on real cells (Nagano 2017 mES,
10 kb) at most 9e-15 relatively on the bands, 9e-14 on the z-scores, 2e-15 on the sums over cells — and gives
the same calls (`packages/uchrom/tests/fea/test_impute_maps.py`, `tests/strc/test_snaphic.py`,
`benchmarks/sc_structures/impute_speed.py`, `snaphic_mesc.py`).  Per cell it is 7x faster than the numpy
reference on one thread and ~60x on 16 (chr1 at 10 kb, AMD EPYC 9754); SnapHiC on 742 cells genome-wide takes
4 min (10 Mb windows) or 98 min (whole chromosomes) on 32 threads.  With `holes=True` it reproduces the pixels
SnapHiC v0.2's own sliding windows leave at 0, and then the authors' code exactly (identical z-scores to
1e-13 and identical loops; `benchmarks/sc_structures/snaphic_reference.py`).

Import name `uchrom_maps`, pip name `uchrom-maps`.  U-Chrom uses it whenever it is installed and falls
back to numpy otherwise; `uchrom.strc.loop.hiccups.BACKEND` / `uchrom.strc.loop.mustache.BACKEND`
(`"auto"`, `"native"`, `"numpy"`) force either path.

```bash
pip install ./packages/uchrom-maps                   # from the repository root (needs Rust; = u-chrom[maps])
cd packages/uchrom-maps && maturin develop --release  # into the active virtualenv, for development
cargo test --release                                 # Rust tests (in packages/uchrom-maps)
cargo run --release --example bench -- [threads] [hiccups|mustache|both]   # timing on a synthetic chr1-sized map
```

```python
import uchrom_maps
uchrom_maps.default_threads()        # rayon's pool: RAYON_NUM_THREADS or all cores
res = uchrom_maps.hiccups_score(n, bi, bj, count, weight, expected, p, w, max_diag, tile_rows,
                                edges, cmin, n_threads=0)
band = uchrom_maps.rwr_band(n, i, j, 0.05, window, step, max_diag)   # (n, max_diag + 1) float64
a = uchrom_maps.scipy_arithmetic()  # {"fma": True, "block": 8, "min_terms": 10} on macOS arm64
best, layer, st_sum, st_cnt, st_min = uchrom_maps.mustache_scan(
    x, y, z, ex, ey, n, max_diag, min_diag, 2.0, weights, halo, tile, a["fma"], a["block"], a["min_terms"])
```

The argument conventions are those of the private functions that call them
(`uchrom.strc.loop.hiccups._score_chrom`, `uchrom.strc.loop.mustache._scan`,
`uchrom.fea.impute_rwr.rwr_band`, `uchrom.strc.loop.snaphic.snaphic_sums`); the Python tests in
`packages/uchrom/tests/strc/test_native_maps.py` compare both paths, and
`benchmarks/hic_structures/native_speed.py` does so on real maps (Rao 2014 chr21 at 5 / 10 / 25 kb, chr1
at 5 kb) and measures time and memory.

## Licence

MIT, like the rest of U-Chrom (`LICENSE` at the repository root).  The kernels are re-implementations of U-Chrom's own numpy code (HiCCUPS: Rao et al. 2014,
*Cell* 159:1665, in the formulation of cooltools `dots`; Mustache: Roayaei Ardakany et al. 2020, *Genome
Biology* 21:256; the RWR: Zhou et al. 2019, *PNAS* 116:14011, Yu et al. 2021, *Nat Methods* 18:1056, Li et al.
2022, *Comput Struct Biotechnol J* 20:2778, solved by Takahashi, Fagan & Chin 1973's selected inversion); no
third-party code was copied (SnapHiC's GPL-3.0 code was read for the method only).
