//! Model superposition and model selection (`align_coord_models`,
//! `remove_models` of the original).

use nalgebra::{Matrix3, SVD};

pub type V3 = [f64; 3];

fn center(c: &[V3], w: &[f64]) -> Vec<V3> {
    let sw: f64 = w.iter().sum();
    let mut t = [0.0; 3];
    for (p, &wi) in c.iter().zip(w) {
        for k in 0..3 {
            t[k] += p[k] * wi;
        }
    }
    let cen = [t[0] / sw, t[1] / sw, t[2] / sw];
    c.iter().map(|p| [p[0] - cen[0], p[1] - cen[1], p[2] - cen[2]]).collect()
}

/// `svd_rotate`: rotate `b` onto `a` (weighted, proper rotation).
fn svd_rotate(a: &[V3], b: &[V3], w: &[f64]) -> Vec<V3> {
    let mut mat = Matrix3::<f64>::zeros();
    for ((pa, pb), &wi) in a.iter().zip(b).zip(w) {
        for r in 0..3 {
            for c in 0..3 {
                mat[(r, c)] += pb[r] * wi * pa[c];
            }
        }
    }
    let svd = SVD::new(mat, true, true);
    let (Some(mut u), Some(vt)) = (svd.u, svd.v_t) else {
        return b.to_vec();
    };
    if !svd.singular_values.iter().all(|x| x.is_finite()) {
        return b.to_vec();
    }
    if u.determinant() * vt.determinant() < 0.0 {
        // flip the column of the smallest singular value (numpy's last column)
        let s = svd.singular_values;
        let kmin = (0..3).min_by(|&x, &y| s[x].partial_cmp(&s[y]).unwrap()).unwrap();
        for r in 0..3 {
            u[(r, kmin)] *= -1.0;
        }
    }
    let rot = u * vt;
    b.iter()
        .map(|p| {
            let mut o = [0.0; 3];
            for c in 0..3 {
                o[c] = p[0] * rot[(0, c)] + p[1] * rot[(1, c)] + p[2] * rot[(2, c)];
            }
            o
        })
        .collect()
}

/// `calc_rmsds`: per-model value sqrt(sum w d^2) / sum w (the original's
/// definition) and per-particle RMSD over models.
fn calc_rmsds(refc: &[V3], models: &[Vec<V3>], w: &[f64]) -> (Vec<f64>, Vec<f64>) {
    let n = refc.len();
    let sw: f64 = w.iter().sum();
    let mut sum_d2 = vec![0.0; n];
    let mut model_rmsds = vec![];
    for c in models {
        let mut s = 0.0;
        for i in 0..n {
            let d2 = (c[i][0] - refc[i][0]).powi(2) + (c[i][1] - refc[i][1]).powi(2) + (c[i][2] - refc[i][2]).powi(2);
            sum_d2[i] += d2;
            s += w[i] * d2;
        }
        model_rmsds.push(s.sqrt() / sw);
    }
    let prmsd = sum_d2.iter().map(|x| (x / models.len() as f64).sqrt()).collect();
    (model_rmsds, prmsd)
}

fn median(v: &[f64]) -> f64 {
    crate::contacts::percentile(v, 50.0)
}

/// `align_coord_pair`: superpose b on a (mirror allowed), then refine with
/// weights exp(-(rmsd_i / dist_scale)^2 * median rmsd).
fn align_coord_pair(a: &[V3], b: &[V3], dist_scale: f64) -> (Vec<V3>, Vec<V3>) {
    let n = a.len();
    let ones = vec![1.0; n];
    let ca = center(a, &ones);
    let cb = center(b, &ones);
    let b1 = svd_rotate(&ca, &cb, &ones);
    let (r1, p1) = calc_rmsds(&ca, std::slice::from_ref(&b1), &ones);
    let mb: Vec<V3> = cb.iter().map(|p| [-p[0], -p[1], -p[2]]).collect();
    let b2 = svd_rotate(&ca, &mb, &ones);
    let (r2, p2) = calc_rmsds(&ca, std::slice::from_ref(&b2), &ones);
    let (mut cb, prmsd) = if r1[0] < r2[0] { (b1, p1) } else { (b2, p2) };
    let mut ca = ca;
    if dist_scale != 0.0 {
        let med = median(&prmsd);
        let we: Vec<f64> = prmsd
            .iter()
            .map(|r| {
                let s = r / dist_scale;
                (-s * s * med).exp()
            })
            .collect();
        ca = center(&ca, &we);
        cb = center(&cb, &we);
        cb = svd_rotate(&ca, &cb, &we);
    }
    (ca, cb)
}

/// `align_coord_models` with n_iter = 1 and automatic distance scale.
/// Returns aligned models and each model's RMSD to the mean (original definition).
pub fn align_coord_models(models: &[Vec<V3>]) -> (Vec<Vec<V3>>, Vec<f64>) {
    let mut cm: Vec<Vec<V3>> = models.to_vec();
    let nm = cm.len();
    if nm < 2 {
        return (cm, vec![0.0; nm]);
    }
    let n = cm[0].len();
    let ones = vec![1.0; n];
    let ref0 = cm[0].clone();
    let mut last_a = ref0.clone();
    for i in 1..nm {
        let (a, b) = align_coord_pair(&ref0, &cm[i], 0.0);
        cm[i] = b;
        last_a = a;
    }
    cm[0] = last_a;
    let mean = mean_coords(&cm);
    let (model_rmsds, prmsd) = calc_rmsds(&mean, &cm, &ones);
    let dist_scale = crate::contacts::percentile(&prmsd, 99.0);
    let j = argmin(&model_rmsds);
    let refj = cm[j].clone();
    for i in 0..nm {
        if i != j {
            let (_, b) = align_coord_pair(&refj, &cm[i], dist_scale);
            cm[i] = b;
        }
    }
    let refm = mean_coords(&cm);
    for i in 0..nm {
        let (_, b) = align_coord_pair(&refm, &cm[i], dist_scale);
        cm[i] = b;
    }
    let mean = mean_coords(&cm);
    let (model_rmsds, _) = calc_rmsds(&mean, &cm, &ones);
    (cm, model_rmsds)
}

fn mean_coords(cm: &[Vec<V3>]) -> Vec<V3> {
    let n = cm[0].len();
    let mut m = vec![[0.0; 3]; n];
    for c in cm {
        for i in 0..n {
            for k in 0..3 {
                m[i][k] += c[i][k];
            }
        }
    }
    let k = cm.len() as f64;
    m.iter().map(|p| [p[0] / k, p[1] / k, p[2] / k]).collect()
}

fn argmin(v: &[f64]) -> usize {
    let mut j = 0;
    for i in 1..v.len() {
        if v[i] < v[j] {
            j = i;
        }
    }
    j
}

/// `remove_models`: align, then keep the `keep` models closest to the mean
/// (ties by index), in that order.
pub fn remove_models(models: &[Vec<V3>], keep: usize) -> (Vec<Vec<V3>>, Vec<usize>) {
    let (aligned, rmsds) = align_coord_models(models);
    let mut idx: Vec<usize> = (0..models.len()).collect();
    idx.sort_by(|&a, &b| rmsds[a].partial_cmp(&rmsds[b]).unwrap().then(a.cmp(&b)));
    idx.truncate(keep);
    (idx.iter().map(|&i| aligned[i].clone()).collect(), idx)
}

/// Plain RMSD after optimal superposition (no weights, mirror allowed):
/// used for reporting.
pub fn rmsd_superposed(a: &[V3], b: &[V3]) -> f64 {
    let (ca, cb) = align_coord_pair(a, b, 0.0);
    let n = ca.len() as f64;
    let s: f64 = ca
        .iter()
        .zip(&cb)
        .map(|(p, q)| (p[0] - q[0]).powi(2) + (p[1] - q[1]).powi(2) + (p[2] - q[2]).powi(2))
        .sum();
    (s / n).sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recovers_rotation_and_mirror() {
        let mut r = crate::rng::Rng::new(1);
        let a: Vec<V3> = (0..200).map(|_| [r.normal(), r.normal() * 2.0, r.normal() * 3.0]).collect();
        let (c, s) = (0.3f64.cos(), 0.3f64.sin());
        let b: Vec<V3> = a.iter().map(|p| [c * p[0] - s * p[1] + 5.0, s * p[0] + c * p[1], p[2] - 2.0]).collect();
        assert!(rmsd_superposed(&a, &b) < 1e-9);
        let m: Vec<V3> = b.iter().map(|p| [-p[0], p[1], p[2]]).collect();
        assert!(rmsd_superposed(&a, &m) < 1e-9);
    }

    #[test]
    fn selection_drops_outlier() {
        let mut r = crate::rng::Rng::new(2);
        let base: Vec<V3> = (0..100).map(|_| [r.normal() * 5.0, r.normal() * 5.0, r.normal() * 5.0]).collect();
        let mut models = vec![];
        for k in 0..6 {
            let noise = if k == 3 { 3.0 } else { 0.1 };
            models.push(base.iter().map(|p| [p[0] + r.normal() * noise, p[1] + r.normal() * noise, p[2] + r.normal() * noise]).collect::<Vec<V3>>());
        }
        let (_, idx) = remove_models(&models, 5);
        assert!(!idx.contains(&3));
    }
}
