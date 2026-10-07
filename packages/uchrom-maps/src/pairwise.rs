//! numpy's pairwise summation, so that sums over many values round exactly as `np.sum` does.
//!
//! `np.add.reduce` of a contiguous float64 array starts from the identity 0 and adds
//! `DOUBLE_pairwise_sum` of the whole array (numpy `loops_utils.h.src`): blocks of at most 128
//! values are summed with eight interleaved accumulators, larger arrays are split in two (at a
//! multiple of 8) and the halves added.

const BLOCK: usize = 128;

/// `np.sum(a)` of a contiguous float64 array, bit for bit.
pub fn np_sum(a: &[f64]) -> f64 {
    0.0 + pairwise_sum(a)
}

/// numpy's `DOUBLE_pairwise_sum`.
pub fn pairwise_sum(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut res = 0.0;
        for &v in a {
            res += v;
        }
        res
    } else if n <= BLOCK {
        let mut r = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let end = n - n % 8;
        let mut i = 8;
        while i < end {
            for k in 0..8 {
                r[k] += a[i + k];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        pairwise_sum(&a[..n2]) + pairwise_sum(&a[n2..])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn small_and_large_sums_are_exact_on_integers() {
        for n in [0usize, 1, 7, 8, 9, 15, 16, 127, 128, 129, 1000, 8193, 100_003] {
            let a: Vec<f64> = (0..n).map(|i| (i % 97) as f64).collect();
            let want: f64 = (0..n).map(|i| (i % 97) as f64).sum();
            assert_eq!(np_sum(&a), want, "n = {n}");
        }
    }

    #[test]
    fn block_order_is_numpy_s() {
        // 1e16 + 1 + ... : the grouping decides which small values survive; eight accumulators
        // keep the 1.0s apart from the large value until the final combination.
        let mut a = vec![1.0; 16];
        a[0] = 1e16;
        // r[0] = 1e16 + 1 (rounds to 1e16), r[1..8] = 2 each -> (1e16 + 2) + (2 + 2) + ... = 1e16 + 16
        let r0 = 1e16 + 1.0;
        let want = ((r0 + 2.0) + (2.0 + 2.0)) + ((2.0 + 2.0) + (2.0 + 2.0));
        assert_eq!(pairwise_sum(&a), want);
    }
}
