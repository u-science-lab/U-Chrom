//! Gaussian smoothing in the arithmetic of `scipy.ndimage.gaussian_filter(..., mode="reflect")`.
//!
//! scipy filters a 2-D array along axis 0, then along axis 1, each time with `correlate1d` and the
//! weights `_gaussian_kernel1d(sigma, 0, radius)[::-1]` (`radius = int(truncate * sigma + 0.5)`).  For a
//! symmetric odd kernel `NI_Correlate1D` computes, per output value,
//!
//! ```text
//! out = x[c] * w[s]
//! for jj in -s..0:  out += (x[c + jj] + x[c - jj]) * w[s + jj]
//! ```
//!
//! with the line extended by `reflect` (half-sample symmetric: `d c b a | a b c d | d c b a`, repeated
//! for short lines).  How the compiler turned the accumulation into machine arithmetic depends on how
//! scipy was built, and [`Arith`] describes it: a build without FMA instructions (the x86-64 baseline)
//! should round every product and sum (`fma = false`; not verified here); the macOS arm64 wheels (scipy 1.18, clang) fuse it into an FMA, except that for
//! `s >= 10` terms the first `8 * floor(s / 8)` terms run in a vectorised loop that multiplies and adds
//! separately (`block = 8`, `min_terms = 10`; read from the disassembly of `NI_Correlate1D`).  The
//! caller finds the scheme of its scipy (`uchrom_maps.scipy_arithmetic()`).  The weights are taken from
//! the caller, so they are scipy's own.

/// How scipy's `correlate1d` accumulates `s` symmetric terms: the first [`Arith::n_plain`] terms as
/// `out + a * w` (two roundings), the rest as `fma(a, w, out)` when `fma` (else also plain).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Arith {
    pub fma: bool,
    /// terms of the vectorised (unfused) part come in multiples of `block` (0: none)
    pub block: usize,
    /// ... and only when there are at least `min_terms` terms
    pub min_terms: usize,
}

impl Arith {
    pub const PLAIN: Arith = Arith { fma: false, block: 0, min_terms: 0 };
    pub const FUSED: Arith = Arith { fma: true, block: 0, min_terms: 0 };

    /// Leading terms (of `s`) added without fusing.
    pub fn n_plain(&self, s: usize) -> usize {
        if !self.fma {
            s
        } else if self.block == 0 || s < self.min_terms {
            0
        } else {
            s - s % self.block
        }
    }
}

/// Index of `i` in a line of `len` values extended by half-sample reflection (period `2 len`).
#[inline]
pub fn reflect(i: isize, len: usize) -> usize {
    let period = 2 * len as isize;
    let m = i.rem_euclid(period);
    if m < len as isize {
        m as usize
    } else {
        (period - 1 - m) as usize
    }
}

#[inline(always)]
fn acc<const FMA: bool>(o: f64, a: f64, w: f64) -> f64 {
    if FMA {
        a.mul_add(w, o)
    } else {
        o + a * w
    }
}

/// `out[i] = center[i] * k[s]`, then for `t = 0 .. s` (the reference's `jj = -s .. -1`)
/// `out[i] += (pairs[t].0[i] + pairs[t].1[i]) * k[t]` — unfused for `t < n_plain`, else fused.  One pass
/// over the row per term (vectorised; holding blocks of columns in registers was not faster): every value
/// sees the same operations in the same order as in scipy's loop.
#[inline(always)]
fn correlate_pairs(center: &[f64], pairs: &[(&[f64], &[f64])], k: &[f64], n_plain: usize, out: &mut [f64]) {
    let s = pairs.len();
    let c0 = k[s];
    for (o, &v) in out.iter_mut().zip(center) {
        *o = v * c0;
    }
    for (t, &(a, b)) in pairs.iter().enumerate() {
        let wt = k[t];
        if t < n_plain {
            for ((o, &x), &y) in out.iter_mut().zip(a).zip(b) {
                *o = acc::<false>(*o, x + y, wt);
            }
        } else {
            for ((o, &x), &y) in out.iter_mut().zip(a).zip(b) {
                *o = acc::<true>(*o, x + y, wt);
            }
        }
    }
}

/// Axis-0 pass over output rows `rows` of an `h x w` image: `out` row `r - rows.0` gets, in the columns
/// `cols(r)` (a half-open range within `0..w`), the filtered values.  Other columns are left untouched.
/// `n_plain`: leading terms accumulated without fusing (see [`Arith`]); the others are fused.
#[allow(clippy::too_many_arguments)]
pub fn axis0(
    img: &[f64],
    h: usize,
    w: usize,
    k: &[f64],
    n_plain: usize,
    rows: (usize, usize),
    cols: impl Fn(usize) -> (usize, usize),
    out: &mut [f64],
) {
    let s = (k.len() - 1) / 2;
    let mut pairs: Vec<(&[f64], &[f64])> = Vec::with_capacity(s);
    for r in rows.0..rows.1 {
        let (lo, hi) = cols(r);
        if lo >= hi {
            continue;
        }
        pairs.clear();
        for t in 0..s {
            let jj = t as isize - s as isize; // -s .. -1
            let ra = reflect(r as isize + jj, h);
            let rb = reflect(r as isize - jj, h);
            pairs.push((&img[ra * w + lo..ra * w + hi], &img[rb * w + lo..rb * w + hi]));
        }
        let o = &mut out[(r - rows.0) * w + lo..(r - rows.0) * w + hi];
        correlate_pairs(&img[r * w + lo..r * w + hi], &pairs, k, n_plain, o);
    }
}

/// Axis-1 pass of one row: `out[c - lo]` for `c` in `lo..hi`, from `row` (length `w`, reflect at both
/// ends; only the columns reachable from `lo..hi` are read).  `ext` is scratch space.
pub fn axis1_row(row: &[f64], k: &[f64], n_plain: usize, lo: usize, hi: usize, ext: &mut Vec<f64>, out: &mut [f64]) {
    let s = (k.len() - 1) / 2;
    let w = row.len();
    let m = hi - lo;
    ext.clear();
    // the line from lo - s to hi + s: reflected only where it leaves the row
    let a = lo as isize - s as isize;
    let b = (hi + s) as isize;
    let (in0, in1) = (a.max(0), b.min(w as isize));
    ext.extend((a..in0.min(b)).map(|i| row[reflect(i, w)]));
    if in0 < in1 {
        ext.extend_from_slice(&row[in0 as usize..in1 as usize]);
    }
    ext.extend((in1.max(a)..b).map(|i| row[reflect(i, w)]));
    debug_assert_eq!(ext.len(), m + 2 * s);
    // x[c + jj] = ext[i + t], x[c - jj] = ext[i + 2 s - t] for jj = t - s
    let pairs: Vec<(&[f64], &[f64])> = (0..s).map(|t| (&ext[t..t + m], &ext[2 * s - t..2 * s - t + m])).collect();
    correlate_pairs(&ext[s..s + m], &pairs, k, n_plain, &mut out[..m]);
}

/// `scipy.ndimage.gaussian_filter(img, sigma, mode="reflect", truncate=...)` of a whole `h x w` image,
/// given the correlation weights scipy uses (`_gaussian_kernel1d(sigma, 0, radius)[::-1]`).
pub fn gaussian_filter(img: &[f64], h: usize, w: usize, k: &[f64], arith: Arith) -> Vec<f64> {
    let mut tmp = vec![0.0; h * w];
    let mut out = vec![0.0; h * w];
    let mut ext = Vec::new();
    let np = arith.n_plain((k.len() - 1) / 2);
    axis0(img, h, w, k, np, (0, h), |_| (0, w), &mut tmp);
    for r in 0..h {
        axis1_row(&tmp[r * w..(r + 1) * w], k, np, 0, w, &mut ext, &mut out[r * w..(r + 1) * w]);
    }
    out
}

/// Normalised Gaussian weights `exp(-x² / 2σ²)`, `x = -radius..=radius` (for tests; the Python side
/// passes scipy's own weights).
pub fn gaussian_weights(sigma: f64, radius: usize) -> Vec<f64> {
    let r = radius as isize;
    let s2 = sigma * sigma;
    let v: Vec<f64> = (-r..=r).map(|x| (-0.5 / s2 * (x * x) as f64).exp()).collect();
    let tot: f64 = v.iter().sum();
    v.iter().map(|x| x / tot).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lcg(seed: &mut u64) -> f64 {
        *seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((*seed >> 11) as f64) / ((1u64 << 53) as f64) - 0.5
    }

    /// Direct 2-D convolution with the separable kernel and reflect boundaries (no reordering tricks).
    fn direct(img: &[f64], h: usize, w: usize, k: &[f64]) -> Vec<f64> {
        let s = (k.len() - 1) as isize / 2;
        let mut out = vec![0.0; h * w];
        for r in 0..h {
            for c in 0..w {
                let mut acc = 0.0;
                for dy in -s..=s {
                    for dx in -s..=s {
                        let rr = reflect(r as isize + dy, h);
                        let cc = reflect(c as isize + dx, w);
                        acc += k[(dy + s) as usize] * k[(dx + s) as usize] * img[rr * w + cc];
                    }
                }
                out[r * w + c] = acc;
            }
        }
        out
    }

    #[test]
    fn reflect_is_half_sample_symmetric_and_periodic() {
        // a b c d -> left: a b c d d c | right: d c b a a b
        let got: Vec<usize> = (-6..10).map(|i| reflect(i, 4)).collect();
        assert_eq!(got, vec![2, 3, 3, 2, 1, 0, 0, 1, 2, 3, 3, 2, 1, 0, 0, 1]);
        assert!((-5..5).all(|i| reflect(i, 1) == 0));
    }

    #[test]
    fn gaussian_matches_a_direct_convolution() {
        let mut seed = 7;
        for &(h, w, sigma, radius) in &[(23usize, 31usize, 1.6, 4usize), (9, 40, 3.2, 7), (5, 6, 2.0, 9), (1, 12, 1.0, 2), (40, 33, 5.0, 13)] {
            let img: Vec<f64> = (0..h * w).map(|_| lcg(&mut seed)).collect();
            let k = gaussian_weights(sigma, radius);
            let want = direct(&img, h, w, &k);
            for arith in [Arith::PLAIN, Arith::FUSED, Arith { fma: true, block: 8, min_terms: 10 }] {
                let got = gaussian_filter(&img, h, w, &k, arith);
                for (a, b) in got.iter().zip(&want) {
                    assert!((a - b).abs() <= 1e-12, "{h}x{w} sigma {sigma}: {a} vs {b}");
                }
            }
        }
    }

    #[test]
    fn windowed_passes_equal_the_full_filter_bitwise() {
        let mut seed = 3;
        let (h, w) = (30usize, 50usize);
        let img: Vec<f64> = (0..h * w).map(|_| lcg(&mut seed)).collect();
        let s = 11;
        let k = gaussian_weights(4.5, s);
        let arith = Arith { fma: true, block: 8, min_terms: 10 };
        let np = arith.n_plain(s);
        assert_eq!(np, 8);
        let full = gaussian_filter(&img, h, w, &k, arith);
        let (r0, r1) = (4usize, 22usize);
        let win = |r: usize| ((r + 3).min(w), (r + 20).min(w)); // a band, as in the Mustache scan
        let mut tmp = vec![f64::NAN; (r1 - r0) * w];
        axis0(&img, h, w, &k, np, (r0, r1), |r| {
            let (lo, hi) = win(r);
            (lo.saturating_sub(s), (hi + s).min(w))
        }, &mut tmp);
        let mut ext = Vec::new();
        for r in r0..r1 {
            let (lo, hi) = win(r);
            if lo >= hi {
                continue;
            }
            let mut out = vec![0.0; hi - lo];
            axis1_row(&tmp[(r - r0) * w..(r - r0 + 1) * w], &k, np, lo, hi, &mut ext, &mut out);
            for c in lo..hi {
                assert_eq!(out[c - lo].to_bits(), full[r * w + c].to_bits(), "({r}, {c})");
            }
        }
    }
}
