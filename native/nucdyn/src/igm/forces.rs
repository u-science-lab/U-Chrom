//! IGM potentials on the CPU (f64), as the lammpgen C++ executes them
//! (spec §3.2):
//!
//! * excluded volume, LAMMPS `pair soft` with IGM's coefficients:
//!   `U = A (1 + cos(π d / r_c))` for `d < r_c = r_i + r_j`,
//!   `A = evfactor · stage_ev · ((r_i + r_j) / π)²`, **all** pairs (bonded
//!   neighbours and homologs included; `special_bonds 1 1 1`);
//! * upper-bound bonds (`bond_style harmonic_upper_bound`):
//!   `U = k (d − d0)²` for `d > d0` (no ½), force `−2k (d − d0)`; polymer
//!   bonds (shared by every structure) and Hi-C bonds (per structure,
//!   `d0 = contact_range (r_i + r_j)`);
//! * nuclear envelope (`fix ellipsoidalenvelope a b c k`), semi-axes × the
//!   stage factor, reduced by the bead radius:
//!   `k² = Σ x_α² / (a_α − r_i)²`; if `k² > 1`: `t = (1 − 1/√k²) |x|`,
//!   `U = ½ k t²`, force `k t` along the normalised `−(x/(a−r)², y/(b−r)², z/(c−r)²)`.
//!   For a sphere this is the exact gradient of U; for an ellipsoid the
//!   original's force is not (it is the surface normal, not ∂t/∂x) and is
//!   reproduced as is.
//!
//! Everything is gathered per particle; one structure is evaluated
//! serially (structures run in parallel), so results are deterministic.

pub type V3 = [f64; 3];

/// Force field of one population (radii, polymer bonds, constants).
#[derive(Clone, Debug)]
pub struct ForceField {
    pub n: usize,
    pub radii: Vec<f64>,
    pub r_max: f64,
    /// base semi-axes (nm)
    pub axes: [f64; 3],
    pub k_env: f64,
    pub evfactor: f64,
    pub k_poly: f64,
    pub k_hic: f64,
    pub contact_range: f64,
    /// polymer bonds, CSR per particle: (partner, d0); every bond at both ends
    pub poly_off: Vec<u32>,
    pub poly: Vec<(u32, f64)>,
}

/// Per-stage scaling (`fix adapt` excluded-volume prefactor, envelope factor).
#[derive(Clone, Copy, Debug)]
pub struct Scale {
    pub ev: f64,
    pub env: f64,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Energies {
    pub ev: f64,
    pub poly: f64,
    pub hic: f64,
    pub env: f64,
}

impl Energies {
    pub fn total(&self) -> f64 {
        self.ev + self.poly + self.hic + self.env
    }
}

/// Build a symmetric CSR (both ends) from a bond list.
pub fn csr_both_ends(n: usize, bonds: &[(u32, u32, f64)]) -> (Vec<u32>, Vec<(u32, f64)>) {
    let mut off = vec![0u32; n + 1];
    for &(i, j, _) in bonds {
        off[i as usize + 1] += 1;
        off[j as usize + 1] += 1;
    }
    for i in 0..n {
        off[i + 1] += off[i];
    }
    let mut fill = off.clone();
    let mut e = vec![(0u32, 0.0); off[n] as usize];
    for &(i, j, d0) in bonds {
        e[fill[i as usize] as usize] = (j, d0);
        fill[i as usize] += 1;
        e[fill[j as usize] as usize] = (i, d0);
        fill[j as usize] += 1;
    }
    // sort each list by partner (deterministic order)
    for i in 0..n {
        e[off[i] as usize..off[i + 1] as usize].sort_by(|a, b| a.0.cmp(&b.0).then(a.1.total_cmp(&b.1)));
    }
    (off, e)
}

/// Per-structure Hi-C restraints: CSR of partners per particle (both ends).
#[derive(Clone, Debug, Default)]
pub struct HicBonds {
    pub off: Vec<u32>,
    pub partner: Vec<u32>,
}

impl HicBonds {
    pub fn from_pairs(n: usize, pairs: &[[u32; 2]]) -> HicBonds {
        let tmp: Vec<(u32, u32, f64)> = pairs.iter().map(|p| (p[0], p[1], 0.0)).collect();
        let (off, e) = csr_both_ends(n, &tmp);
        HicBonds { off, partner: e.into_iter().map(|x| x.0).collect() }
    }
    pub fn empty(n: usize) -> HicBonds {
        HicBonds { off: vec![0; n + 1], partner: vec![] }
    }
    pub fn n_bonds(&self) -> usize {
        self.partner.len() / 2
    }
}

impl ForceField {
    pub fn new(radii: Vec<f64>, poly_bonds: &[(u32, u32, f64)], axes: [f64; 3], p: &crate::igm::params::IgmParams) -> ForceField {
        let n = radii.len();
        let (poly_off, poly) = csr_both_ends(n, poly_bonds);
        let r_max = radii.iter().cloned().fold(0.0, f64::max);
        ForceField {
            n,
            radii,
            r_max,
            axes,
            k_env: p.nucleus_kspring,
            evfactor: p.evfactor,
            k_poly: p.polymer_kspring,
            k_hic: p.contact_kspring,
            contact_range: p.contact_range,
            poly_off,
            poly,
        }
    }

    #[inline]
    pub fn hic_d0(&self, i: usize, j: usize) -> f64 {
        self.contact_range * (self.radii[i] + self.radii[j])
    }
}

/// Upper-bound bond on particle i from j: adds the force on i, returns U.
#[inline]
pub fn upper_bond(p: &V3, q: &V3, d0: f64, k: f64, f: &mut V3) -> f64 {
    let d = [p[0] - q[0], p[1] - q[1], p[2] - q[2]];
    let r = (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt();
    if r <= d0 || r == 0.0 {
        return 0.0;
    }
    let x = r - d0;
    let t = -2.0 * k * x / r;
    for a in 0..3 {
        f[a] += t * d[a];
    }
    k * x * x
}

/// Soft-cosine repulsion on particle i from j: adds the force on i, returns U (full pair energy).
#[inline]
pub fn soft_pair(p: &V3, q: &V3, ri: f64, rj: f64, ev: f64, f: &mut V3) -> f64 {
    let rc = ri + rj;
    let d = [p[0] - q[0], p[1] - q[1], p[2] - q[2]];
    let r2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
    if r2 >= rc * rc {
        return 0.0;
    }
    let pi = std::f64::consts::PI;
    let a = ev * (rc / pi) * (rc / pi);
    let r = r2.sqrt();
    let arg = pi * r / rc;
    if r > 0.0 {
        // LAMMPS pair soft: fpair = A sin(arg) π / rc / r (repulsive)
        let t = a * arg.sin() * pi / rc / r;
        for k in 0..3 {
            f[k] += t * d[k];
        }
    }
    a * (1.0 + arg.cos())
}

/// Ellipsoidal envelope on one particle: adds the force, returns U.
#[inline]
pub fn envelope(p: &V3, r: f64, axes: &[f64; 3], k: f64, f: &mut V3) -> f64 {
    let s = [axes[0] - r, axes[1] - r, axes[2] - r];
    let k2 = p[0] * p[0] / (s[0] * s[0]) + p[1] * p[1] / (s[1] * s[1]) + p[2] * p[2] / (s[2] * s[2]);
    if k2 <= 1.0 {
        return 0.0;
    }
    let norm = (p[0] * p[0] + p[1] * p[1] + p[2] * p[2]).sqrt();
    let t = (1.0 - 1.0 / k2.sqrt()) * norm;
    let g = [p[0] / (s[0] * s[0]), p[1] / (s[1] * s[1]), p[2] / (s[2] * s[2])];
    let gn = (g[0] * g[0] + g[1] * g[1] + g[2] * g[2]).sqrt();
    if gn > 0.0 {
        let m = k * t / gn;
        for a in 0..3 {
            f[a] -= m * g[a];
        }
    }
    0.5 * k * t * t
}

/// Simple cell grid (cell size >= 2 r_max) over one structure.
#[derive(Clone, Debug, Default)]
pub struct Grid {
    dims: [usize; 3],
    mn: V3,
    inv: f64,
    start: Vec<u32>,
    items: Vec<u32>,
    cell: Vec<usize>,
}

impl Grid {
    pub fn build(&mut self, pos: &[V3], cs: f64) {
        let n = pos.len();
        let mut mn = [f64::INFINITY; 3];
        let mut mx = [f64::NEG_INFINITY; 3];
        for p in pos {
            for k in 0..3 {
                mn[k] = mn[k].min(p[k]);
                mx[k] = mx[k].max(p[k]);
            }
        }
        let mut cs = cs;
        let max_cells = (8 * n).max(64) as f64;
        let mut dims;
        loop {
            dims = [0usize; 3];
            for k in 0..3 {
                dims[k] = (((mx[k] - mn[k]) / cs).floor() as usize) + 1;
            }
            if (dims[0] as f64) * (dims[1] as f64) * (dims[2] as f64) <= max_cells || !cs.is_finite() {
                break;
            }
            cs *= 1.26;
        }
        self.dims = dims;
        self.mn = mn;
        self.inv = 1.0 / cs;
        let nc = dims[0] * dims[1] * dims[2];
        self.start.clear();
        self.start.resize(nc + 1, 0);
        self.cell.resize(n, 0);
        for (i, p) in pos.iter().enumerate() {
            let l = self.lin(self.coord(p));
            self.cell[i] = l;
            self.start[l + 1] += 1;
        }
        for c in 0..nc {
            self.start[c + 1] += self.start[c];
        }
        let mut fill = self.start.clone();
        self.items.resize(n, 0);
        for i in 0..n {
            let l = self.cell[i];
            self.items[fill[l] as usize] = i as u32;
            fill[l] += 1;
        }
    }
    #[inline]
    fn coord(&self, p: &V3) -> [usize; 3] {
        let mut c = [0usize; 3];
        for k in 0..3 {
            let v = ((p[k] - self.mn[k]) * self.inv).floor();
            c[k] = if v < 0.0 { 0 } else { (v as usize).min(self.dims[k] - 1) };
        }
        c
    }
    #[inline]
    fn lin(&self, c: [usize; 3]) -> usize {
        (c[2] * self.dims[1] + c[1]) * self.dims[0] + c[0]
    }
    /// Visit every particle j != i in the 27 cells around i.
    #[inline]
    pub fn for_neighbours(&self, pos: &[V3], i: usize, mut f: impl FnMut(usize)) {
        let c = self.coord(&pos[i]);
        let d = self.dims;
        for z in c[2].saturating_sub(1)..=(c[2] + 1).min(d[2] - 1) {
            for y in c[1].saturating_sub(1)..=(c[1] + 1).min(d[1] - 1) {
                let row = (z * d[1] + y) * d[0];
                let (x0, x1) = (c[0].saturating_sub(1), (c[0] + 1).min(d[0] - 1));
                for &j in &self.items[self.start[row + x0] as usize..self.start[row + x1 + 1] as usize] {
                    if j as usize != i {
                        f(j as usize);
                    }
                }
            }
        }
    }
}

/// Forces (into `out`) and energies of one structure.
pub fn compute(ff: &ForceField, hic: &HicBonds, pos: &[V3], sc: Scale, grid: &mut Grid, out: &mut [V3]) -> Energies {
    let n = ff.n;
    grid.build(pos, 2.0 * ff.r_max);
    let ev = ff.evfactor * sc.ev;
    let axes = [ff.axes[0] * sc.env, ff.axes[1] * sc.env, ff.axes[2] * sc.env];
    let mut e = Energies::default();
    for i in 0..n {
        let p = pos[i];
        let ri = ff.radii[i];
        let mut f = [0.0; 3];
        if ev != 0.0 {
            let mut u = 0.0;
            grid.for_neighbours(pos, i, |j| {
                u += soft_pair(&p, &pos[j], ri, ff.radii[j], ev, &mut f);
            });
            e.ev += 0.5 * u;
        }
        for &(j, d0) in &ff.poly[ff.poly_off[i] as usize..ff.poly_off[i + 1] as usize] {
            e.poly += 0.5 * upper_bond(&p, &pos[j as usize], d0, ff.k_poly, &mut f);
        }
        for &j in &hic.partner[hic.off[i] as usize..hic.off[i + 1] as usize] {
            let d0 = ff.hic_d0(i, j as usize);
            e.hic += 0.5 * upper_bond(&p, &pos[j as usize], d0, ff.k_hic, &mut f);
        }
        e.env += envelope(&p, ri, &axes, ff.k_env, &mut f);
        out[i] = f;
    }
    e
}

/// Violation counts of one structure (spec §5, IGM `getViolationRatio`):
/// Hi-C / polymer `(d − d0)/d0 > tol`; envelope `t / (k · 0.1 R̄) > tol`
/// with `R̄` the mean semi-axis.  Excluded volume is not monitored.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, serde::Serialize)]
pub struct Violations {
    pub hic_imposed: u64,
    pub hic_violated: u64,
    pub poly_imposed: u64,
    pub poly_violated: u64,
    pub env_imposed: u64,
    pub env_violated: u64,
}

impl Violations {
    pub fn add(&mut self, o: &Violations) {
        self.hic_imposed += o.hic_imposed;
        self.hic_violated += o.hic_violated;
        self.poly_imposed += o.poly_imposed;
        self.poly_violated += o.poly_violated;
        self.env_imposed += o.env_imposed;
        self.env_violated += o.env_violated;
    }
    pub fn imposed(&self) -> u64 {
        self.hic_imposed + self.poly_imposed + self.env_imposed
    }
    pub fn violated(&self) -> u64 {
        self.hic_violated + self.poly_violated + self.env_violated
    }
}

pub fn violations(ff: &ForceField, hic: &HicBonds, pos: &[V3], tol: f64) -> Violations {
    let mut v = Violations::default();
    let dist = |i: usize, j: usize| {
        let (p, q) = (pos[i], pos[j]);
        ((p[0] - q[0]).powi(2) + (p[1] - q[1]).powi(2) + (p[2] - q[2]).powi(2)).sqrt()
    };
    let rbar = (ff.axes[0] + ff.axes[1] + ff.axes[2]) / 3.0;
    for i in 0..ff.n {
        for &(j, d0) in &ff.poly[ff.poly_off[i] as usize..ff.poly_off[i + 1] as usize] {
            if (j as usize) > i {
                v.poly_imposed += 1;
                if (dist(i, j as usize) - d0) / d0 > tol {
                    v.poly_violated += 1;
                }
            }
        }
        for &j in &hic.partner[hic.off[i] as usize..hic.off[i + 1] as usize] {
            if (j as usize) > i {
                v.hic_imposed += 1;
                let d0 = ff.hic_d0(i, j as usize);
                if (dist(i, j as usize) - d0) / d0 > tol {
                    v.hic_violated += 1;
                }
            }
        }
        v.env_imposed += 1;
        let mut f = [0.0; 3];
        let u = envelope(&pos[i], ff.radii[i], &ff.axes, ff.k_env, &mut f);
        if u > 0.0 {
            let t = (2.0 * u / ff.k_env).sqrt();
            if t / (ff.k_env * 0.1 * rbar) > tol {
                v.env_violated += 1;
            }
        }
    }
    v
}

#[cfg(test)]
pub mod tests_support {
    use super::*;
    use crate::igm::params::IgmParams;
    use crate::rng::Rng;

    pub fn toy(n: usize, seed: u64, sphere: bool) -> (ForceField, HicBonds, Vec<V3>) {
        let mut rng = Rng::new(seed);
        let radii: Vec<f64> = (0..n).map(|i| if i % 7 == 6 { 60.0 } else { 100.0 }).collect();
        let mut pos = vec![];
        let mut p = [0.0f64; 3];
        for _ in 0..n {
            p = [p[0] + rng.normal() * 150.0, p[1] + rng.normal() * 150.0, p[2] + rng.normal() * 150.0];
            pos.push(p);
        }
        let poly: Vec<(u32, u32, f64)> = (0..n as u32 - 1).filter(|i| i % 50 != 49).map(|i| (i, i + 1, 2.0 * (radii[i as usize] + radii[i as usize + 1]))).collect();
        let axes = if sphere { [900.0; 3] } else { [1100.0, 800.0, 600.0] };
        let p = IgmParams { evfactor: 1.0, ..Default::default() };
        let ff = ForceField::new(radii, &poly, axes, &p);
        let mut pairs = vec![];
        for _ in 0..n {
            let i = (rng.uniform() * n as f64) as u32;
            let j = (rng.uniform() * n as f64) as u32;
            if i != j {
                pairs.push([i.min(j), i.max(j)]);
            }
        }
        (ff, HicBonds::from_pairs(n, &pairs), pos)
    }

}

#[cfg(test)]
mod tests {
    use super::*;
    use super::tests_support::toy;

    fn energy(ff: &ForceField, hic: &HicBonds, pos: &[V3], sc: Scale) -> Energies {
        let mut g = Grid::default();
        let mut f = vec![[0.0; 3]; pos.len()];
        compute(ff, hic, pos, sc, &mut g, &mut f)
    }

    /// Finite differences of each term separately.
    #[test]
    fn forces_match_finite_differences() {
        let (ff, hic, pos) = toy(300, 3, true);
        let sc = Scale { ev: 0.7, env: 1.1 };
        let mut g = Grid::default();
        let mut f = vec![[0.0; 3]; pos.len()];
        let e0 = compute(&ff, &hic, &pos, sc, &mut g, &mut f);
        assert!(e0.ev > 0.0 && e0.poly > 0.0 && e0.hic > 0.0 && e0.env > 0.0, "{e0:?}");
        let h = 1e-5;
        let (mut max_err, mut max_f) = (0.0f64, 0.0f64);
        for i in 0..pos.len() {
            for d in 0..3 {
                let mut p1 = pos.clone();
                p1[i][d] += h;
                let mut p2 = pos.clone();
                p2[i][d] -= h;
                let num = -(energy(&ff, &hic, &p1, sc).total() - energy(&ff, &hic, &p2, sc).total()) / (2.0 * h);
                max_err = max_err.max((num - f[i][d]).abs());
                max_f = max_f.max(num.abs());
            }
        }
        assert!(max_f > 10.0);
        // (energies ~1e7: the central difference itself carries ~1e-6 relative noise)
        assert!(max_err / max_f < 1e-5, "max_err {max_err} max_f {max_f}");
    }

    /// Each term alone (so a cancellation cannot hide an error).
    #[test]
    fn each_term_matches_finite_differences() {
        let (ff0, hic0, pos) = toy(120, 8, true);
        let h = 1e-5;
        for term in 0..4 {
            let mut ff = ff0.clone();
            let mut hic = hic0.clone();
            let mut sc = Scale { ev: 1.0, env: 1.0 };
            if term != 0 {
                sc.ev = 0.0;
            }
            if term != 1 {
                ff.poly.clear();
                ff.poly_off = vec![0; ff.n + 1];
            }
            if term != 2 {
                hic = HicBonds::empty(ff.n);
            }
            if term != 3 {
                ff.axes = [1e9; 3];
            }
            let mut g = Grid::default();
            let mut f = vec![[0.0; 3]; pos.len()];
            compute(&ff, &hic, &pos, sc, &mut g, &mut f);
            let (mut max_err, mut max_f) = (0.0f64, 0.0f64);
            for i in 0..pos.len() {
                for d in 0..3 {
                    let mut p1 = pos.clone();
                    p1[i][d] += h;
                    let mut p2 = pos.clone();
                    p2[i][d] -= h;
                    let num = -(energy(&ff, &hic, &p1, sc).total() - energy(&ff, &hic, &p2, sc).total()) / (2.0 * h);
                    max_err = max_err.max((num - f[i][d]).abs());
                    max_f = max_f.max(num.abs());
                }
            }
            assert!(max_f > 1.0, "term {term}: no force");
            assert!(max_err / max_f < 1e-6, "term {term}: max_err {max_err} max_f {max_f}");
        }
    }

    #[test]
    fn soft_pair_constants() {
        // U(0) = 2A, U(rc) = 0, max force A π / rc at rc / 2
        let (ri, rj, ev) = (100.0, 50.0, 1.0);
        let a = ev * (150.0f64 / std::f64::consts::PI).powi(2);
        let mut f = [0.0; 3];
        let u0 = soft_pair(&[0.0, 0.0, 1e-12], &[0.0; 3], ri, rj, ev, &mut f);
        assert!((u0 / (2.0 * a) - 1.0).abs() < 1e-12);
        let mut f = [0.0; 3];
        soft_pair(&[75.0, 0.0, 0.0], &[0.0; 3], ri, rj, ev, &mut f);
        assert!((f[0] - a * std::f64::consts::PI / 150.0).abs() < 1e-9);
        assert!((f[0] - 150.0 / std::f64::consts::PI).abs() < 1e-9);
        let mut f = [0.0; 3];
        assert_eq!(soft_pair(&[150.0, 0.0, 0.0], &[0.0; 3], ri, rj, ev, &mut f), 0.0);
    }

    #[test]
    fn envelope_sphere_and_ellipsoid() {
        let mut f = [0.0; 3];
        // sphere R = 1000, r = 100: surface at 900 from the centre
        let u = envelope(&[950.0, 0.0, 0.0], 100.0, &[1000.0; 3], 2.0, &mut f);
        assert!((u - 0.5 * 2.0 * 50.0 * 50.0).abs() < 1e-9);
        assert!((f[0] + 2.0 * 50.0).abs() < 1e-9 && f[1] == 0.0);
        let mut f = [0.0; 3];
        assert_eq!(envelope(&[899.0, 0.0, 0.0], 100.0, &[1000.0; 3], 2.0, &mut f), 0.0);
        // ellipsoid: on the y axis, the reduced semi-axis b - r
        let mut f = [0.0; 3];
        let u = envelope(&[0.0, 800.0, 0.0], 100.0, &[2000.0, 600.0, 400.0], 1.0, &mut f);
        assert!((u - 0.5 * 300.0 * 300.0).abs() < 1e-9, "{u}");
        assert!((f[1] + 300.0).abs() < 1e-9);
        // force along the normalised ellipsoid normal, magnitude k t
        let mut f = [0.0; 3];
        let p = [700.0, 500.0, 300.0];
        let ax = [900.0, 700.0, 500.0];
        let u = envelope(&p, 100.0, &ax, 1.5, &mut f);
        let t = (2.0 * u / 1.5).sqrt();
        let fm = (f[0] * f[0] + f[1] * f[1] + f[2] * f[2]).sqrt();
        assert!((fm - 1.5 * t).abs() < 1e-9);
        let g = [p[0] / 800.0f64.powi(2), p[1] / 600.0f64.powi(2), p[2] / 400.0f64.powi(2)];
        let cross = [g[1] * f[2] - g[2] * f[1], g[2] * f[0] - g[0] * f[2], g[0] * f[1] - g[1] * f[0]];
        assert!(cross.iter().all(|c| c.abs() < 1e-9 * fm));
    }

    #[test]
    fn upper_bond_lammps_convention() {
        let mut f = [0.0; 3];
        let u = upper_bond(&[13.0, 0.0, 0.0], &[0.0; 3], 10.0, 0.5, &mut f);
        assert!((u - 0.5 * 9.0).abs() < 1e-12); // k (d - d0)^2, no 1/2
        assert!((f[0] + 2.0 * 0.5 * 3.0).abs() < 1e-12);
    }

    #[test]
    fn grid_finds_all_overlaps() {
        let (ff, _, pos) = toy(800, 5, true);
        let mut g = Grid::default();
        g.build(&pos, 2.0 * ff.r_max);
        for i in 0..pos.len() {
            let mut found = vec![];
            g.for_neighbours(&pos, i, |j| {
                let d2: f64 = (0..3).map(|k| (pos[i][k] - pos[j][k]).powi(2)).sum();
                if d2 < (ff.radii[i] + ff.radii[j]).powi(2) {
                    found.push(j);
                }
            });
            found.sort();
            let brute: Vec<usize> = (0..pos.len())
                .filter(|&j| j != i && (0..3).map(|k| (pos[i][k] - pos[j][k]).powi(2)).sum::<f64>() < (ff.radii[i] + ff.radii[j]).powi(2))
                .collect();
            assert_eq!(found, brute);
        }
    }
}
