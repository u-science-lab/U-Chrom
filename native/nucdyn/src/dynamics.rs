//! CPU particle dynamics (f64): forces, neighbour list and the integrator of
//! the original `dyn_util.run_dynamics`.
//!
//! Layout: one `System` (particles, restraints; shared by every model of a
//! stage) and one `Model` per structure (positions, velocities, ...; each an
//! array of packed xyz).  All loops run over fixed chunks of particles and
//! every force is *gathered* per particle (full neighbour list, restraint
//! incidence list), so results do not depend on the number of threads.

use crate::restraints::RestraintSet;
use crate::rng::Rng;
use rayon::prelude::*;

pub const BOLTZMANN_K: f64 = 0.0019872041;
const CHUNK: usize = 1024;

pub type V3 = [f64; 3];

/// Functional form of the distance-restraint term.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RestraintForm {
    /// `master` (2017) `getRestraintForce`: harmonic outside [d_min, d_max],
    /// linear (constant force K) beyond d_max + 0.5; weights not used.
    Master2017,
    /// `release_1.3` `getRestraintForce`: switch at d_max + 0.5 d_max,
    /// constant force 2 K 0.5 d_max beyond; force scaled by the weight.
    Release13,
}

/// Particles and restraints of one stage.
#[derive(Clone, Debug)]
pub struct System {
    pub n: usize,
    pub form: RestraintForm,
    pub masses: Vec<f64>,
    pub radii: Vec<f64>,
    pub rest_pairs: Vec<[u32; 2]>,
    pub rest_lim: Vec<[f64; 2]>,
    pub rest_w: Vec<f64>,
    pub groups: Vec<u32>,
    /// particle -> incident restraints, `(restraint << 1) | side`
    /// (side 0: first particle, gets +f; side 1: second, gets -f).
    pub inc_off: Vec<u32>,
    pub inc: Vec<u32>,
}

impl System {
    pub fn new(n: usize, masses: Vec<f64>, radii: Vec<f64>, rs: &RestraintSet) -> System {
        let rest_pairs: Vec<[u32; 2]> = rs.rest.iter().map(|r| [r.i, r.j]).collect();
        let rest_lim: Vec<[f64; 2]> = rs.rest.iter().map(|r| [r.lo, r.hi]).collect();
        let rest_w: Vec<f64> = rs.rest.iter().map(|r| r.weight).collect();
        Self::from_arrays(n, masses, radii, rest_pairs, rest_lim, rest_w, rs.groups.clone())
    }

    pub fn from_arrays(
        n: usize,
        masses: Vec<f64>,
        radii: Vec<f64>,
        rest_pairs: Vec<[u32; 2]>,
        rest_lim: Vec<[f64; 2]>,
        rest_w: Vec<f64>,
        groups: Vec<u32>,
    ) -> System {
        let mut cnt = vec![0u32; n + 1];
        for p in &rest_pairs {
            if p[0] != p[1] {
                cnt[p[0] as usize + 1] += 1;
                cnt[p[1] as usize + 1] += 1;
            }
        }
        for i in 0..n {
            cnt[i + 1] += cnt[i];
        }
        let mut fill = cnt.clone();
        let mut inc = vec![0u32; cnt[n] as usize];
        for (r, p) in rest_pairs.iter().enumerate() {
            if p[0] != p[1] {
                for side in 0..2 {
                    let i = p[side] as usize;
                    inc[fill[i] as usize] = ((r as u32) << 1) | side as u32;
                    fill[i] += 1;
                }
            }
        }
        System { n, form: RestraintForm::Release13, masses, radii, rest_pairs, rest_lim, rest_w, groups, inc_off: cnt, inc }
    }

    pub fn n_restraints(&self) -> usize {
        self.rest_pairs.len()
    }

    pub fn with_form(mut self, form: RestraintForm) -> System {
        self.form = form;
        self
    }
}

/// Verlet neighbour list (full: every pair appears for both particles),
/// built with a cell grid.  Holds pairs |i - j| >= 2 closer than
/// r_i + r_j + skin; valid until a particle moves more than skin / 2.
#[derive(Clone, Debug, Default)]
pub struct NeighbourList {
    pub off: Vec<u32>,
    pub nb: Vec<u32>,
    pub ref_pos: Vec<V3>,
    pub valid: bool,
    pub skin: f64,
    pub n_builds: u64,
}

impl NeighbourList {
    pub fn build(&mut self, pos: &[V3], radii: &[f64], skin: f64, parallel: bool) {
        let n = pos.len();
        self.skin = skin;
        self.ref_pos.clear();
        self.ref_pos.extend_from_slice(pos);
        self.valid = true;
        self.n_builds += 1;
        self.off.clear();
        self.nb.clear();
        self.off.push(0);
        if n == 0 {
            return;
        }
        let max_r = radii.iter().cloned().fold(0.0, f64::max);
        let mut cs = 2.0 * max_r + skin;
        let mut mn = [f64::INFINITY; 3];
        let mut mx = [f64::NEG_INFINITY; 3];
        for p in pos {
            for k in 0..3 {
                mn[k] = mn[k].min(p[k]);
                mx[k] = mx[k].max(p[k]);
            }
        }
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
        let ncell = dims[0] * dims[1] * dims[2];
        let cell_of = |p: &V3| -> [usize; 3] {
            let mut c = [0usize; 3];
            for k in 0..3 {
                let v = ((p[k] - mn[k]) / cs).floor();
                c[k] = if v < 0.0 { 0 } else { (v as usize).min(dims[k] - 1) };
            }
            c
        };
        let lin = |c: [usize; 3]| (c[2] * dims[1] + c[1]) * dims[0] + c[0];
        let pcell: Vec<[usize; 3]> = pos.iter().map(cell_of).collect();
        let mut start = vec![0u32; ncell + 1];
        for c in &pcell {
            start[lin(*c) + 1] += 1;
        }
        for k in 0..ncell {
            start[k + 1] += start[k];
        }
        let mut fill = start.clone();
        let mut items = vec![0u32; n];
        for (i, c) in pcell.iter().enumerate() {
            let l = lin(*c);
            items[fill[l] as usize] = i as u32;
            fill[l] += 1;
        }
        let query = |i: usize, out: &mut Vec<u32>| {
            let c = pcell[i];
            let p = pos[i];
            let ri = radii[i];
            let s0 = out.len();
            for z in c[2].saturating_sub(1)..=(c[2] + 1).min(dims[2] - 1) {
                for y in c[1].saturating_sub(1)..=(c[1] + 1).min(dims[1] - 1) {
                    for x in c[0].saturating_sub(1)..=(c[0] + 1).min(dims[0] - 1) {
                        let l = lin([x, y, z]);
                        for &j in &items[start[l] as usize..start[l + 1] as usize] {
                            let j = j as usize;
                            if j + 1 >= i && j <= i + 1 {
                                continue; // |i - j| < 2 (and i itself)
                            }
                            let q = pos[j];
                            let (dx, dy, dz) = (q[0] - p[0], q[1] - p[1], q[2] - p[2]);
                            let lim = ri + radii[j] + skin;
                            if dx * dx + dy * dy + dz * dz <= lim * lim {
                                out.push(j as u32);
                            }
                        }
                    }
                }
            }
            out[s0..].sort_unstable();
        };
        let min_len = if parallel { 1 } else { usize::MAX };
        let chunks: Vec<(Vec<u32>, Vec<u32>)> = (0..n.div_ceil(CHUNK))
            .into_par_iter()
            .with_min_len(min_len)
            .map(|c| {
                let mut nb = Vec::new();
                let mut cnt = Vec::with_capacity(CHUNK);
                for i in c * CHUNK..((c + 1) * CHUNK).min(n) {
                    let s = nb.len();
                    query(i, &mut nb);
                    cnt.push((nb.len() - s) as u32);
                }
                (cnt, nb)
            })
            .collect();
        let total: usize = chunks.iter().map(|c| c.1.len()).sum();
        self.nb.reserve(total);
        self.off.reserve(n);
        let mut acc = 0u32;
        for (cnt, nb) in chunks {
            for c in cnt {
                acc += c;
                self.off.push(acc);
            }
            self.nb.extend_from_slice(&nb);
        }
    }
}

/// One structure being annealed.
#[derive(Clone, Debug)]
pub struct Model {
    pub pos: Vec<V3>,
    pub vel: Vec<V3>,
    pub acc: Vec<V3>,
    pub force: Vec<V3>,
    pub rest_f: Vec<V3>,
    pub nl: NeighbourList,
    pub grid: CellGrid,
    pub rng: Rng,
    /// Emulated capacity of the original's repulsion list (0 = unset).
    pub rep_cap: usize,
    /// Repulsion switched off by an emulated list overflow.
    pub rep_off: bool,
    /// Number of emulated overflows / steps without repulsion.
    pub overflow_events: u64,
    pub steps_without_repulsion: u64,
    pub last_rep_found: usize,
}

impl Model {
    pub fn new(pos: Vec<V3>, rng: Rng) -> Model {
        let n = pos.len();
        Model {
            pos,
            vel: vec![[0.0; 3]; n],
            acc: vec![[0.0; 3]; n],
            force: vec![[0.0; 3]; n],
            rest_f: vec![],
            nl: NeighbourList::default(),
            grid: CellGrid::default(),
            rng,
            rep_cap: 0,
            rep_off: false,
            overflow_events: 0,
            steps_without_repulsion: 0,
            last_rep_found: 0,
        }
    }
}

/// Parameters of one `run_dynamics` call.
#[derive(Clone, Copy, Debug)]
pub struct DynParams {
    pub t_ref: f64,
    pub t_step: f64,
    pub n_steps: usize,
    pub f_rep: f64,
    pub f_dist: f64,
    pub beta: f64,
    pub tot0: f64,
    /// neighbour-list skin in absolute units
    pub skin: f64,
    /// Rebuild the neighbour list exactly when the original does: at the
    /// start of every call, and when a particle has moved more than skin/2
    /// *before* the position update of a step (the list can then miss pairs
    /// that come into range during that step).  False: check after the
    /// position update, so the list is always complete.
    pub original_nl_schedule: bool,
    /// Take repulsion pairs from a cell grid rebuilt at every step instead
    /// of a Verlet list (same pairs; faster when the list would be rebuilt
    /// often, as at high annealing temperatures).
    pub use_cells: bool,
    /// Emulate the original's repulsion-list overflow (needs the Verlet
    /// list with `original_nl_schedule`).
    pub emulate_overflow: bool,
}

#[inline]
fn kinetic(masses: &[f64], vel: &[V3]) -> f64 {
    let mut s = 0.0;
    for (m, v) in masses.iter().zip(vel) {
        s += m * (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    }
    s
}

/// Sum of per-chunk partial sums, in chunk order (deterministic).
#[inline]
fn ordered_sum(parts: &[f64]) -> f64 {
    parts.iter().sum()
}

/// Scalar restraint term of one (possibly ambiguous) group and the force
/// vectors of its members (`getRestraintForce`, exponent 2, switch ratio
/// 0.5, asymptote 1).  Returns the energy.
#[inline]
fn group_force(sys: &System, pos: &[V3], g: usize, f_const: f64, out: &mut [V3]) -> f64 {
    if sys.form == RestraintForm::Master2017 {
        return group_force_2017(sys, pos, g, f_const, out);
    }
    const EXPONENT: f64 = 2.0;
    const SWITCH_RATIO: f64 = 0.5;
    const ASYMPTOTE: f64 = 1.0;
    let (s, e) = (sys.groups[g] as usize, sys.groups[g + 1] as usize);
    let mut r2 = 0.0;
    for n in s..e {
        let [j, k] = sys.rest_pairs[n];
        if j == k {
            continue;
        }
        let (a, b) = (pos[j as usize], pos[k as usize]);
        let (dx, dy, dz) = (a[0] - b[0], a[1] - b[1], a[2] - b[2]);
        let r = (dx * dx + dy * dy + dz * dz).max(1e-08);
        r2 += 1.0 / (r * r);
    }
    for o in out.iter_mut() {
        *o = [0.0; 3];
    }
    if r2 <= 0.0 {
        return 0.0;
    }
    r2 = 1.0 / r2.sqrt();
    let [dmin, dmax] = sys.rest_lim[s];
    let dist_switch = dmax * SWITCH_RATIO;
    let (ujk, rjk);
    if r2 < dmin * dmin {
        r2 = r2.max(1e-8);
        let d = dmin - r2.sqrt();
        ujk = f_const * d * d;
        rjk = f_const * EXPONENT * d;
    } else if r2 <= dmax * dmax {
        return 0.0;
    } else if r2 <= (dmax + dist_switch) * (dmax + dist_switch) {
        let d = r2.sqrt() - dmax;
        ujk = f_const * d * d;
        rjk = -f_const * EXPONENT * d;
    } else {
        let b = dist_switch * dist_switch * dist_switch * EXPONENT * (ASYMPTOTE - 1.0);
        let a = dist_switch * dist_switch * (1.0 - 2.0 * ASYMPTOTE * EXPONENT + EXPONENT);
        let d = r2.sqrt() - dmax;
        ujk = f_const * (a + ASYMPTOTE * dist_switch * EXPONENT * d + b / d);
        rjk = -f_const * (ASYMPTOTE * dist_switch * EXPONENT - b / (d * d));
    }
    let r25 = r2 * r2 * r2.sqrt(); // r2^2.5
    for n in s..e {
        let [j, k] = sys.rest_pairs[n];
        if j == k {
            continue;
        }
        let (a, b) = (pos[j as usize], pos[k as usize]);
        let (dx, dy, dz) = (a[0] - b[0], a[1] - b[1], a[2] - b[2]);
        let s2 = (dx * dx + dy * dy + dz * dz).max(1e-08);
        let t = rjk * r25 / (s2 * s2 * s2) * sys.rest_w[n];
        out[n - s] = [dx * t, dy * t, dz * t];
    }
    ujk
}

/// `getRestraintForce` of the 2017 `master` code (exponent 2, distSwitch
/// 0.5 absolute, asymptote 1; single restraints and ambiguous groups).
#[inline]
fn group_force_2017(sys: &System, pos: &[V3], g: usize, f_const: f64, out: &mut [V3]) -> f64 {
    const DIST_SWITCH: f64 = 0.5;
    const ASYMPTOTE: f64 = 1.0;
    const EXPONENT: f64 = 2.0;
    let b = ASYMPTOTE * DIST_SWITCH * DIST_SWITCH - EXPONENT * DIST_SWITCH * DIST_SWITCH * DIST_SWITCH;
    let a = DIST_SWITCH * DIST_SWITCH - ASYMPTOTE * DIST_SWITCH - b / DIST_SWITCH;
    let (s, e) = (sys.groups[g] as usize, sys.groups[g + 1] as usize);
    let n_ambig = e - s;
    let mut r2 = 0.0;
    if n_ambig == 1 {
        let [j, k] = sys.rest_pairs[s];
        if j != k {
            let (p, q) = (pos[j as usize], pos[k as usize]);
            let (dx, dy, dz) = (p[0] - q[0], p[1] - q[1], p[2] - q[2]);
            r2 = dx * dx + dy * dy + dz * dz;
        }
    } else {
        for n in s..e {
            let [j, k] = sys.rest_pairs[n];
            if j != k {
                let (p, q) = (pos[j as usize], pos[k as usize]);
                let (dx, dy, dz) = (p[0] - q[0], p[1] - q[1], p[2] - q[2]);
                let r = dx * dx + dy * dy + dz * dz;
                r2 += 1.0 / (r * r);
            }
        }
        if r2 > 0.0 {
            r2 = 1.0 / r2.sqrt();
        }
    }
    for o in out.iter_mut() {
        *o = [0.0; 3];
    }
    if r2 <= 0.0 {
        return 0.0;
    }
    let [dmin, dmax] = sys.rest_lim[s];
    let da = dmax + DIST_SWITCH;
    let (ujk, rjk, r);
    if r2 < dmin * dmin {
        r2 = r2.max(1e-8);
        r = r2.sqrt();
        let d = dmin - r;
        ujk = f_const * d * d;
        rjk = f_const * 2.0 * d;
    } else if r2 > dmax * dmax {
        r = r2.sqrt();
        let d = r - dmax;
        if r <= da {
            ujk = f_const * d * d;
            rjk = -f_const * 2.0 * d;
        } else {
            ujk = f_const * (a + ASYMPTOTE * d + b / d);
            rjk = -f_const * (ASYMPTOTE - b / (d * d));
        }
    } else {
        return 0.0;
    }
    if n_ambig == 1 {
        let [j, k] = sys.rest_pairs[s];
        let (p, q) = (pos[j as usize], pos[k as usize]);
        let t = rjk / r;
        out[0] = [(p[0] - q[0]) * t, (p[1] - q[1]) * t, (p[2] - q[2]) * t];
    } else {
        for n in s..e {
            let [j, k] = sys.rest_pairs[n];
            if j == k {
                continue;
            }
            let (p, q) = (pos[j as usize], pos[k as usize]);
            let (dx, dy, dz) = (p[0] - q[0], p[1] - q[1], p[2] - q[2]);
            let s2 = dx * dx + dy * dy + dz * dz;
            let t = rjk * r2 * r2 * r / (s2 * s2 * s2);
            out[n - s] = [dx * t, dy * t, dz * t];
        }
    }
    ujk
}

/// Cell grid rebuilt at every force evaluation: particles sorted by cell
/// (cell size = repulsion cutoff), so each particle only visits the 27
/// cells around it.  No neighbour list to keep valid.
#[derive(Clone, Debug, Default)]
pub struct CellGrid {
    pub dims: [usize; 3],
    pub cs: f64,
    pub mn: V3,
    pub start: Vec<u32>,
    pub sidx: Vec<u32>,
    pub spos: Vec<V3>,
    pub pcell: Vec<u32>,
    pub inv: Vec<u32>,
    pub sforce: Vec<V3>,
    fill: Vec<u32>,
}

impl CellGrid {
    pub fn build(&mut self, pos: &[V3], cutoff: f64) {
        let n = pos.len();
        let mut mn = [f64::INFINITY; 3];
        let mut mx = [f64::NEG_INFINITY; 3];
        for p in pos {
            for k in 0..3 {
                mn[k] = mn[k].min(p[k]);
                mx[k] = mx[k].max(p[k]);
            }
        }
        let mut cs = cutoff;
        let max_cells = (4 * n).max(64) as f64;
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
        let ncell = dims[0] * dims[1] * dims[2];
        self.dims = dims;
        self.cs = cs;
        self.mn = mn;
        self.pcell.resize(n, 0);
        self.start.clear();
        self.start.resize(ncell + 1, 0);
        let inv_cs = 1.0 / cs;
        for (i, p) in pos.iter().enumerate() {
            let mut c = [0usize; 3];
            for k in 0..3 {
                let v = ((p[k] - mn[k]) * inv_cs).floor();
                c[k] = if v < 0.0 { 0 } else { (v as usize).min(dims[k] - 1) };
            }
            let l = (c[2] * dims[1] + c[1]) * dims[0] + c[0];
            self.pcell[i] = l as u32;
            self.start[l + 1] += 1;
        }
        for k in 0..ncell {
            self.start[k + 1] += self.start[k];
        }
        self.sidx.resize(n, 0);
        self.spos.resize(n, [0.0; 3]);
        self.inv.resize(n, 0);
        self.sforce.resize(n, [0.0; 3]);
        // stable counting sort
        self.fill.clear();
        self.fill.extend_from_slice(&self.start[..ncell]);
        for i in 0..n {
            let l = self.pcell[i] as usize;
            let k = self.fill[l] as usize;
            self.fill[l] += 1;
            self.sidx[k] = i as u32;
            self.spos[k] = pos[i];
            self.inv[i] = k as u32;
        }
    }
}

/// Restraint force vectors of every restraint (per group, chunks of groups).
fn restraint_vectors(sys: &System, pos: &[V3], rest_f: &mut Vec<V3>, f_dist: f64, min_len: usize) -> f64 {
    let nr = sys.n_restraints();
    if rest_f.len() != nr {
        *rest_f = vec![[0.0; 3]; nr];
    }
    let ng = sys.groups.len().saturating_sub(1);
    let gchunk = CHUNK;
    let nchunks = ng.div_ceil(gchunk);
    let mut slices: Vec<(usize, &mut [V3])> = Vec::with_capacity(nchunks);
    let mut rest: &mut [V3] = rest_f.as_mut_slice();
    let mut consumed = 0usize;
    for c in 0..nchunks {
        let g0 = c * gchunk;
        let g1 = ((c + 1) * gchunk).min(ng);
        let r1 = sys.groups[g1] as usize;
        let (a, b) = rest.split_at_mut(r1 - consumed);
        slices.push((g0, a));
        rest = b;
        consumed = r1;
    }
    let parts: Vec<f64> = slices
        .into_par_iter()
        .with_min_len(min_len)
        .map(|(g0, sl)| {
            let g1 = (g0 + gchunk).min(ng);
            let base = sys.groups[g0] as usize;
            let mut u = 0.0;
            for g in g0..g1 {
                let (s, e) = (sys.groups[g] as usize, sys.groups[g + 1] as usize);
                u += group_force(sys, pos, g, f_dist, &mut sl[s - base..e - base]);
            }
            u
        })
        .collect();
    ordered_sum(&parts)
}

#[inline]
fn add_restraints(sys: &System, rest_f: &[V3], i: usize, f: &mut V3) {
    for &e in &sys.inc[sys.inc_off[i] as usize..sys.inc_off[i + 1] as usize] {
        let v = rest_f[(e >> 1) as usize];
        if e & 1 == 0 {
            f[0] += v[0];
            f[1] += v[1];
            f[2] += v[2];
        } else {
            f[0] -= v[0];
            f[1] -= v[1];
            f[2] -= v[2];
        }
    }
}

/// Repulsion of particle i (position p) from particle j (position q).
#[inline(always)]
fn repulse(p: &V3, q: &V3, rep: f64, f_rep: f64, acc: &mut V3) -> f64 {
    let (dx, dy, dz) = (q[0] - p[0], q[1] - p[1], q[2] - p[2]);
    let d2 = dx * dx + dy * dy + dz * dz;
    if d2 > rep * rep {
        return 0.0;
    }
    let dr = rep * rep - d2;
    let rjk = 4.0 * f_rep * dr;
    acc[0] -= dx * rjk;
    acc[1] -= dy * rjk;
    acc[2] -= dz * rjk;
    f_rep * dr * dr
}

/// Forces on every particle: repulsion (`getRepulsiveForce`) + restraints,
/// repulsion pairs from the model's Verlet list.  Returns (repulsion
/// energy, restraint energy) when `energies`.
pub fn compute_forces(sys: &System, m: &mut Model, f_rep: f64, f_dist: f64, parallel: bool, energies: bool) -> (f64, f64) {
    compute_forces_mode(sys, m, f_rep, f_dist, parallel, energies, false)
}

/// As `compute_forces`; `use_cells`: repulsion pairs from a cell grid built
/// now (exact) instead of the Verlet list (which the caller keeps valid).
#[allow(clippy::too_many_arguments)]
pub fn compute_forces_mode(
    sys: &System,
    m: &mut Model,
    f_rep: f64,
    f_dist: f64,
    parallel: bool,
    energies: bool,
    use_cells: bool,
) -> (f64, f64) {
    let min_len = if parallel { 1 } else { usize::MAX };
    let e_dist = restraint_vectors(sys, &m.pos, &mut m.rest_f, f_dist, min_len);
    let pos = &m.pos;
    let rest_f = &m.rest_f;
    let radii = &sys.radii;
    if !use_cells {
        let nl = &m.nl;
        let parts: Vec<f64> = m
            .force
            .par_chunks_mut(CHUNK)
            .enumerate()
            .with_min_len(min_len)
            .map(|(c, fch)| {
                let mut u = 0.0;
                for (k, f) in fch.iter_mut().enumerate() {
                    let i = c * CHUNK + k;
                    let p = pos[i];
                    let mut acc = [0.0f64; 3];
                    if f_rep != 0.0 {
                        for &j in &nl.nb[nl.off[i] as usize..nl.off[i + 1] as usize] {
                            let j = j as usize;
                            let e = repulse(&p, &pos[j], radii[i] + radii[j], f_rep, &mut acc);
                            if energies && i < j {
                                u += e;
                            }
                        }
                    }
                    add_restraints(sys, rest_f, i, &mut acc);
                    *f = acc;
                }
                u
            })
            .collect();
        return (ordered_sum(&parts), e_dist);
    }
    // cell-grid path
    let max_r = radii.iter().cloned().fold(0.0, f64::max);
    m.grid.build(pos, 2.0 * max_r);
    let mut sforce = std::mem::take(&mut m.grid.sforce);
    let g = &m.grid;
    let [dx_, dy_, dz_] = g.dims;
    let (sidx, spos, start, pcell) = (&g.sidx, &g.spos, &g.start, &g.pcell);
    let parts: Vec<f64> = sforce
        .par_chunks_mut(CHUNK)
        .enumerate()
        .with_min_len(min_len)
        .map(|(c, fch)| {
            let mut u = 0.0;
            for (kk, f) in fch.iter_mut().enumerate() {
                let k = c * CHUNK + kk;
                let i = sidx[k] as usize;
                let p = spos[k];
                let ri = radii[i];
                let mut acc = [0.0f64; 3];
                if f_rep != 0.0 {
                    let l = pcell[i] as usize;
                    let cx = l % dx_;
                    let cy = (l / dx_) % dy_;
                    let cz = l / (dx_ * dy_);
                    let (x0, x1) = (cx.saturating_sub(1), (cx + 1).min(dx_ - 1));
                    for z in cz.saturating_sub(1)..=(cz + 1).min(dz_ - 1) {
                        for y in cy.saturating_sub(1)..=(cy + 1).min(dy_ - 1) {
                            let row = (z * dy_ + y) * dx_;
                            let (s, e) = (start[row + x0] as usize, start[row + x1 + 1] as usize);
                            for t in s..e {
                                let j = sidx[t] as usize;
                                if j + 1 >= i && j <= i + 1 {
                                    continue; // |i - j| < 2
                                }
                                let e = repulse(&p, &spos[t], ri + radii[j], f_rep, &mut acc);
                                if energies && i < j {
                                    u += e;
                                }
                            }
                        }
                    }
                }
                add_restraints(sys, rest_f, i, &mut acc);
                *f = acc;
            }
            u
        })
        .collect();
    let inv = &m.grid.inv;
    let sf = &sforce;
    m.force.par_chunks_mut(CHUNK).enumerate().with_min_len(min_len).for_each(|(c, fch)| {
        for (k, f) in fch.iter_mut().enumerate() {
            *f = sf[inv[c * CHUNK + k] as usize];
        }
    });
    m.grid.sforce = sforce;
    (ordered_sum(&parts), e_dist)
}

/// `getStats`: number of violated restraints and RMS violation.
pub fn restraint_stats(sys: &System, pos: &[V3]) -> (usize, f64) {
    let mut nviol = 0;
    let mut s = 0.0;
    for (p, l) in sys.rest_pairs.iter().zip(&sys.rest_lim) {
        if p[0] == p[1] {
            continue;
        }
        let (a, b) = (pos[p[0] as usize], pos[p[1] as usize]);
        let r = ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt();
        let viol = if r < l[0] {
            nviol += 1;
            l[0] - r
        } else if r > l[1] {
            nviol += 1;
            r - l[1]
        } else {
            0.0
        };
        s += viol * viol;
    }
    (nviol, (s / sys.n_restraints().max(1) as f64).sqrt())
}

pub fn temperature(masses: &[f64], vel: &[V3]) -> f64 {
    kinetic(masses, vel) / (3.0 * vel.len() as f64 * BOLTZMANN_K)
}

/// One `run_dynamics` call: new random velocities at `t_ref`, then
/// `n_steps` velocity-Verlet steps with the Berendsen-like thermostat of the
/// original (`updateMotion` / `updateVelocity`).
pub fn run_dynamics(sys: &System, m: &mut Model, dp: &DynParams, parallel: bool, init_vel: Option<&[V3]>) {
    let n = sys.n;
    if n == 0 {
        return;
    }
    let t_step0 = dp.t_step * dp.tot0;
    let beta = dp.beta / dp.tot0;
    let rt_step = 0.5 * t_step0 * t_step0;
    let three_nk = 3.0 * n as f64 * BOLTZMANN_K;
    let min_len = if parallel { 1 } else { usize::MAX };

    // velocities ~ N(0, 1), scaled to the reference temperature
    match init_vel {
        Some(v) => m.vel.copy_from_slice(v),
        None => {
            for v in m.vel.iter_mut() {
                *v = [m.rng.normal(), m.rng.normal(), m.rng.normal()];
            }
        }
    }
    let scale = (dp.t_ref / (kinetic(&sys.masses, &m.vel) / three_nk)).sqrt();
    for (v, &mass) in m.vel.iter_mut().zip(&sys.masses) {
        if mass.is_infinite() {
            *v = [0.0; 3];
        } else {
            *v = [v[0] * scale, v[1] * scale, v[2] * scale];
        }
    }
    let half_skin2 = 0.25 * dp.skin * dp.skin;
    let cells = dp.use_cells;
    if !cells {
        if dp.original_nl_schedule {
            m.nl.valid = false;
        }
        if !m.nl.valid || (m.nl.skin - dp.skin).abs() > 0.0 || m.nl.ref_pos.len() != n {
            rebuild_nl(sys, m, dp, parallel);
        } else if max_disp2(&m.pos, &m.nl.ref_pos, parallel) > half_skin2 {
            rebuild_nl(sys, m, dp, parallel);
        }
    }
    let f_rep_eff = |m: &Model| if m.rep_off { 0.0 } else { dp.f_rep };
    let fr = f_rep_eff(m);
    compute_forces_mode(sys, m, fr, dp.f_dist, parallel, false, cells);
    let mut kin = kinetic(&sys.masses, &m.vel);

    for step in 0..dp.n_steps {
        if !cells && dp.original_nl_schedule && step > 0 && max_disp2(&m.pos, &m.nl.ref_pos, parallel) > half_skin2 {
            rebuild_nl(sys, m, dp, parallel);
        }
        // updateMotion
        let temp = (kin / three_nk).max(0.001);
        let r = beta * (dp.t_ref / temp - 1.0);
        let masses = &sys.masses;
        let ref_pos: &[V3] = if cells { &[] } else { &m.nl.ref_pos };
        let parts: Vec<(f64, f64)> = m
            .pos
            .par_chunks_mut(CHUNK)
            .zip(m.vel.par_chunks_mut(CHUNK))
            .zip(m.acc.par_chunks_mut(CHUNK))
            .zip(m.force.par_chunks(CHUNK))
            .enumerate()
            .with_min_len(min_len)
            .map(|(c, (((p, v), a), f))| {
                let mut kin = 0.0;
                let mut md = 0.0f64;
                for k in 0..p.len() {
                    let i = c * CHUNK + k;
                    let mass = masses[i];
                    for d in 0..3 {
                        a[k][d] = f[k][d] / mass + r * v[k][d];
                        p[k][d] += t_step0 * v[k][d] + rt_step * a[k][d];
                        v[k][d] += t_step0 * a[k][d];
                    }
                    kin += mass * (v[k][0] * v[k][0] + v[k][1] * v[k][1] + v[k][2] * v[k][2]);
                    if !cells {
                        let q = ref_pos[i];
                        let (dx, dy, dz) = (p[k][0] - q[0], p[k][1] - q[1], p[k][2] - q[2]);
                        md = md.max(dx * dx + dy * dy + dz * dz);
                    }
                }
                (kin, md)
            })
            .collect();
        let kin_mid: f64 = parts.iter().map(|x| x.0).sum();
        let md = parts.iter().map(|x| x.1).fold(0.0, f64::max);
        if !cells && md > half_skin2 && !dp.original_nl_schedule {
            rebuild_nl(sys, m, dp, parallel);
        }
        let fr = f_rep_eff(m);
        if m.rep_off {
            m.steps_without_repulsion += 1;
        }
        compute_forces_mode(sys, m, fr, dp.f_dist, parallel, false, cells);
        // updateVelocity
        let temp = (kin_mid / three_nk).max(0.001);
        let r = beta * (dp.t_ref / temp - 1.0);
        let parts: Vec<f64> = m
            .vel
            .par_chunks_mut(CHUNK)
            .zip(m.acc.par_chunks(CHUNK))
            .zip(m.force.par_chunks(CHUNK))
            .enumerate()
            .with_min_len(min_len)
            .map(|(c, ((v, a), f))| {
                let mut kin = 0.0;
                for k in 0..v.len() {
                    let mass = masses[c * CHUNK + k];
                    for d in 0..3 {
                        v[k][d] += 0.5 * t_step0 * (f[k][d] / mass + r * v[k][d] - a[k][d]);
                    }
                    kin += mass * (v[k][0] * v[k][0] + v[k][1] * v[k][1] + v[k][2] * v[k][2]);
                }
                kin
            })
            .collect();
        kin = ordered_sum(&parts);
    }
    if dp.emulate_overflow {
        m.rep_cap = (1.05 * m.last_rep_found as f64) as i32 as usize;
    }
}

/// (Re)build the Verlet list; with `emulate_overflow`, apply the original's
/// capacity rule: more pairs than the capacity -> capacity 1.1 x found and
/// no repulsion until the next build.
fn rebuild_nl(sys: &System, m: &mut Model, dp: &DynParams, parallel: bool) {
    m.nl.build(&m.pos, &sys.radii, dp.skin, parallel);
    if dp.emulate_overflow {
        let found = m.nl.nb.len() / 2;
        if m.rep_cap == 0 {
            m.rep_cap = sys.n * 10;
        }
        if found > m.rep_cap {
            m.rep_cap = (found as f64 * 1.1) as i32 as usize;
            m.rep_off = true;
            m.overflow_events += 1;
        } else {
            m.rep_off = false;
        }
        m.last_rep_found = found;
    }
}

fn max_disp2(pos: &[V3], refp: &[V3], parallel: bool) -> f64 {
    let min_len = if parallel { 1 } else { usize::MAX };
    pos.par_chunks(CHUNK)
        .zip(refp.par_chunks(CHUNK))
        .with_min_len(min_len)
        .map(|(p, q)| {
            p.iter()
                .zip(q)
                .map(|(a, b)| (a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2))
                .fold(0.0, f64::max)
        })
        .reduce(|| 0.0, f64::max)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::restraints::{ambiguity_offsets, Restraint, RestraintSet};

    fn toy_chain(n: usize, seed: u64) -> (System, Vec<V3>) {
        toy_chain_w(n, seed, true)
    }

    fn toy_chain_w(n: usize, seed: u64, weights: bool) -> (System, Vec<V3>) {
        let mut rng = Rng::new(seed);
        let mut pos = vec![];
        let mut p = [0.0f64; 3];
        for _ in 0..n {
            p = [p[0] + rng.normal() * 0.6, p[1] + rng.normal() * 0.6, p[2] + rng.normal() * 0.6];
            pos.push(p);
        }
        let mut rest = vec![];
        for i in 0..n - 1 {
            rest.push(Restraint { i: i as u32, j: i as u32 + 1, lo: 0.1, hi: 1.1, ambig: 0, weight: 1.0 });
        }
        let mut seen = std::collections::HashSet::new();
        for k in 0..n / 2 {
            let i = (rng.uniform() * n as f64) as u32;
            let j = (rng.uniform() * n as f64) as u32;
            // (duplicates are binned into one restraint of weight 2, which
            // scales the force but not the energy, as in the original)
            if !weights && !seen.insert((i.min(j), i.max(j))) {
                continue;
            }
            rest.push(Restraint { i: i.min(j), j: i.max(j), lo: 0.8, hi: 1.2, ambig: 0, weight: if weights { 1.0 + (k % 3) as f64 } else { 1.0 } });
        }
        // one ambiguous group of three
        for (a, b) in [(1u32, 20u32), (2, 30), (3, 40)] {
            rest.push(Restraint { i: a, j: b, lo: 0.8, hi: 1.2, ambig: 77, weight: 1.0 });
        }
        let rest = crate::restraints::bin_restraints(rest);
        let groups = ambiguity_offsets(&rest);
        let rs = RestraintSet { rest, groups, n_contacts: 0 };
        (System::new(n, vec![1.0; n], vec![1.0; n], &rs), pos)
    }

    fn energy(sys: &System, pos: &[V3], f_rep: f64, f_dist: f64) -> f64 {
        let mut m = Model::new(pos.to_vec(), Rng::new(0));
        m.nl.build(pos, &sys.radii, 100.0, false);
        let (a, b) = compute_forces(sys, &mut m, f_rep, f_dist, false, true);
        a + b
    }

    #[test]
    fn forces_match_finite_differences() {
        // unit weights: the original scales restraint forces (not energies) by weight
        let (sys, pos) = toy_chain_w(60, 11, false);
        let (f_rep, f_dist) = (0.7, 25.0);
        let mut m = Model::new(pos.clone(), Rng::new(0));
        m.nl.build(&pos, &sys.radii, 100.0, false);
        compute_forces(&sys, &mut m, f_rep, f_dist, false, false);
        let h = 1e-6;
        let mut max_err = 0.0f64;
        let mut max_f = 0.0f64;
        for i in 0..sys.n {
            for d in 0..3 {
                let mut p1 = pos.clone();
                p1[i][d] += h;
                let mut p2 = pos.clone();
                p2[i][d] -= h;
                let num = -(energy(&sys, &p1, f_rep, f_dist) - energy(&sys, &p2, f_rep, f_dist)) / (2.0 * h);
                max_err = max_err.max((num - m.force[i][d]).abs());
                max_f = max_f.max(num.abs());
            }
        }
        assert!(max_f > 1.0);
        assert!(max_err / max_f < 1e-5 || max_err < 1e-4, "max_err {max_err} max_f {max_f}");
    }

    #[test]
    fn neighbour_list_matches_brute_force() {
        let (sys, pos) = toy_chain(700, 5);
        let mut nl = NeighbourList::default();
        let skin = 0.8;
        nl.build(&pos, &sys.radii, skin, true);
        for i in 0..sys.n {
            let mut brute: Vec<u32> = (0..sys.n)
                .filter(|&j| (j as i64 - i as i64).abs() >= 2)
                .filter(|&j| {
                    let d2: f64 = (0..3).map(|k| (pos[i][k] - pos[j][k]).powi(2)).sum();
                    d2 <= (2.0 + skin) * (2.0 + skin)
                })
                .map(|j| j as u32)
                .collect();
            brute.sort();
            assert_eq!(&nl.nb[nl.off[i] as usize..nl.off[i + 1] as usize], brute.as_slice());
        }
    }

    #[test]
    fn cell_grid_forces_match_verlet_list() {
        let (sys, pos) = toy_chain(3000, 12);
        let mut a = Model::new(pos.clone(), Rng::new(0));
        a.nl.build(&pos, &sys.radii, 0.5, false);
        let ea = compute_forces_mode(&sys, &mut a, 0.7, 25.0, false, true, false);
        let mut b = Model::new(pos, Rng::new(0));
        let eb = compute_forces_mode(&sys, &mut b, 0.7, 25.0, true, true, true);
        assert!((ea.0 - eb.0).abs() <= 1e-9 * ea.0.abs().max(1.0), "{ea:?} {eb:?}");
        for i in 0..sys.n {
            for d in 0..3 {
                let (x, y) = (a.force[i][d], b.force[i][d]);
                assert!((x - y).abs() <= 1e-9 * (1.0 + x.abs()), "particle {i}: {x} vs {y}");
            }
        }
    }

    #[test]
    fn thermostat_holds_temperature_on_free_chain() {
        let (sys, pos) = toy_chain(400, 9);
        let mut m = Model::new(pos, Rng::new(1));
        let dp = DynParams { t_ref: 300.0, t_step: 0.001, n_steps: 2000, f_rep: 0.5, f_dist: 25.0, beta: 10.0, tot0: 20.458, skin: 1.0, original_nl_schedule: false, use_cells: false, emulate_overflow: false };
        run_dynamics(&sys, &mut m, &dp, false, None);
        let t = temperature(&sys.masses, &m.vel);
        assert!((t / 300.0 - 1.0).abs() < 0.1, "temperature {t}");
    }

    #[test]
    fn deterministic_across_parallel_modes() {
        let (sys, pos) = toy_chain(5000, 2);
        let dp = DynParams { t_ref: 1000.0, t_step: 0.001, n_steps: 50, f_rep: 0.5, f_dist: 25.0, beta: 10.0, tot0: 20.458, skin: 1.0, original_nl_schedule: false, use_cells: false, emulate_overflow: false };
        let mut a = Model::new(pos.clone(), Rng::new(3));
        let mut b = Model::new(pos, Rng::new(3));
        run_dynamics(&sys, &mut a, &dp, false, None);
        run_dynamics(&sys, &mut b, &dp, true, None);
        assert_eq!(a.pos, b.pos);
    }

    #[test]
    fn energy_conserved_without_thermostat_coupling() {
        // with beta = 0 the integrator is plain velocity Verlet
        let (sys, pos) = toy_chain_w(200, 4, false);
        let mut m = Model::new(pos, Rng::new(8));
        let dp = DynParams { t_ref: 50.0, t_step: 0.0002, n_steps: 1, f_rep: 0.5, f_dist: 5.0, beta: 0.0, tot0: 20.458, skin: 2.0, original_nl_schedule: false, use_cells: false, emulate_overflow: false };
        run_dynamics(&sys, &mut m, &dp, false, None);
        let total = |m: &mut Model| {
            let (a, b) = compute_forces(&sys, m, 0.5, 5.0, false, true);
            a + b + 0.5 * kinetic(&sys.masses, &m.vel)
        };
        let e0 = total(&mut m);
        let v0 = m.vel.clone();
        let dp2 = DynParams { n_steps: 2000, t_ref: temperature(&sys.masses, &v0), ..dp };
        run_dynamics(&sys, &mut m, &dp2, false, Some(&v0));
        let e1 = total(&mut m);
        assert!(((e1 - e0) / e0).abs() < 0.02, "energy drift {e0} -> {e1}");
    }
}
