# uchrom-maps

Native kernels of the Hi-C map callers of [U-Chrom](../../README.md), written in Rust with PyO3
bindings: the two hot loops that profiling on a 5-kb map of human chr1 (49,851 bins, 26.5 M pixels)
singled out.

* **HiCCUPS scoring** (`hiccups_score`, used by `uchrom.strc.loop.hiccups`): for every testable pixel of
  one chromosome's band, the four locally adjusted expecteds (donut, vertical, horizontal, lower-left
  kernels), the λ-chunk of each, the per-kernel (λ-chunk × count) histograms and the candidate filter.
* **Mustache scan** (`mustache_scan`, used by `uchrom.strc.loop.mustache`): the Gaussian scale space of the
  normalised band, differences of Gaussians, 3 × 3 maxima, the best response and detection layer of every
  pixel and the per-layer statistics of the exponential fits.

Both reproduce the numpy reference in `uchrom` **bit for bit**: the same row tiles, the same summed-area
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
a = uchrom_maps.scipy_arithmetic()  # {"fma": True, "block": 8, "min_terms": 10} on macOS arm64
best, layer, st_sum, st_cnt, st_min = uchrom_maps.mustache_scan(
    x, y, z, ex, ey, n, max_diag, min_diag, 2.0, weights, halo, tile, a["fma"], a["block"], a["min_terms"])
```

The argument conventions are those of the private functions that call them
(`uchrom.strc.loop.hiccups._score_chrom`, `uchrom.strc.loop.mustache._scan`); the Python tests in
`packages/uchrom/tests/strc/test_native_maps.py` compare both paths, and
`benchmarks/hic_structures/native_speed.py` does so on real maps (Rao 2014 chr21 at 5 / 10 / 25 kb, chr1
at 5 kb) and measures time and memory.

## Licence

MIT, like the rest of U-Chrom (`LICENSE` at the repository root).  The kernels are re-implementations of U-Chrom's own numpy code (HiCCUPS: Rao et al. 2014,
*Cell* 159:1665, in the formulation of cooltools `dots`; Mustache: Roayaei Ardakany et al. 2020, *Genome
Biology* 21:256); no third-party code was copied.
