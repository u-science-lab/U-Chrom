//! uchrom-maps: native kernels of U-Chrom's Hi-C map callers.
//!
//! * [`hiccups`]: the scoring of one chromosome by HiCCUPS (`uchrom.strc.loop.hiccups._score_chrom`):
//!   locally adjusted expecteds of the four kernels, λ-chunks, histograms, candidates.
//! * [`mustache`]: the Mustache scale-space scan (`uchrom.strc.loop.mustache._scan`): Gaussian scale
//!   space, differences of Gaussians, 3 x 3 maxima, best response per pixel, per-layer statistics.
//! * [`rwr`]: random walk with restart on single-cell maps (SnapHiC / scHiCluster imputation, sliding
//!   windows) and SnapHiC's per-diagonal z-scores, local backgrounds and sums over cells
//!   (`uchrom.fea.impute_rwr`, `uchrom.strc.loop.snaphic`).
//! * [`gauss`], [`pairwise`]: `scipy.ndimage.gaussian_filter` and `np.sum` in their exact arithmetic.
//!
//! The HiCCUPS and Mustache kernels reproduce the numpy reference bit for bit (same tiles, same order of
//! floating-point operations) and run tiles in parallel with rayon.  The RWR solves the same linear systems
//! as the numpy reference by another factorisation (profile Cholesky + selected inversion instead of a dense
//! inverse): equal to rounding (relative differences ~1e-13), not bit for bit.

pub mod gauss;
pub mod hiccups;
pub mod mustache;
pub mod pairwise;
pub mod rwr;

#[cfg(feature = "python")]
mod python;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Run `f` on `n_threads` threads (a pool of its own), or on rayon's global pool when `n_threads == 0`.
pub fn with_threads<T: Send>(n_threads: usize, f: impl FnOnce() -> T + Send) -> Result<T, String> {
    if n_threads == 0 {
        return Ok(f());
    }
    let pool = rayon::ThreadPoolBuilder::new().num_threads(n_threads).build().map_err(|e| e.to_string())?;
    Ok(pool.install(f))
}
