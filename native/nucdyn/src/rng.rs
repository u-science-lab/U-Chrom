//! Small, dependency-free random number generation.
//!
//! Every random stream is keyed by `(seed, stage, model, purpose)`, so a run
//! is reproducible for a given seed whatever the thread count or the order
//! in which models are scheduled.

/// SplitMix64 step (used to seed and to hash keys).
#[inline]
pub fn splitmix64(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// Hash a list of keys into one 64-bit value.
pub fn hash_keys(keys: &[u64]) -> u64 {
    let mut s = 0x1234_5678_9ABC_DEF0u64;
    let mut h = 0u64;
    for &k in keys {
        s ^= k.wrapping_mul(0x9E37_79B9_7F4A_7C15);
        h ^= splitmix64(&mut s);
        s = s.rotate_left(17) ^ h;
    }
    h
}

/// Purposes of random streams.
pub const STREAM_COORDS: u64 = 1;
pub const STREAM_VELOC: u64 = 2;

/// xoshiro256++ generator.
#[derive(Clone, Debug)]
pub struct Rng {
    s: [u64; 4],
    spare: Option<f64>,
}

impl Rng {
    pub fn new(seed: u64) -> Self {
        let mut sm = seed;
        let s = [
            splitmix64(&mut sm),
            splitmix64(&mut sm),
            splitmix64(&mut sm),
            splitmix64(&mut sm),
        ];
        Rng { s, spare: None }
    }

    pub fn from_keys(keys: &[u64]) -> Self {
        Rng::new(hash_keys(keys))
    }

    #[inline]
    pub fn next_u64(&mut self) -> u64 {
        let s = &mut self.s;
        let result = (s[0].wrapping_add(s[3])).rotate_left(23).wrapping_add(s[0]);
        let t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = s[3].rotate_left(45);
        result
    }

    /// Uniform in [0, 1).
    #[inline]
    pub fn uniform(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }

    /// Standard normal (Marsaglia polar method).
    pub fn normal(&mut self) -> f64 {
        if let Some(v) = self.spare.take() {
            return v;
        }
        loop {
            let u = 2.0 * self.uniform() - 1.0;
            let v = 2.0 * self.uniform() - 1.0;
            let s = u * u + v * v;
            if s > 0.0 && s < 1.0 {
                let m = (-2.0 * s.ln() / s).sqrt();
                self.spare = Some(v * m);
                return u * m;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normal_moments() {
        let mut r = Rng::new(7);
        let n = 200_000;
        let xs: Vec<f64> = (0..n).map(|_| r.normal()).collect();
        let mean = xs.iter().sum::<f64>() / n as f64;
        let var = xs.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / n as f64;
        assert!(mean.abs() < 0.01, "mean {mean}");
        assert!((var - 1.0).abs() < 0.01, "var {var}");
    }

    #[test]
    fn keyed_streams_differ() {
        let a = Rng::from_keys(&[1, 0, 0, STREAM_VELOC]).next_u64();
        let b = Rng::from_keys(&[1, 0, 1, STREAM_VELOC]).next_u64();
        assert_ne!(a, b);
    }
}
