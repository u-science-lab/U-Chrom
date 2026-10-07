//! Structure-free symmetry breaking for the few-cell deconvolution (`mix.rs`): triangle
//! consistency of the pooled long-range contact graph.
//!
//! In one cell, loci in contact with a common locus are close to each other, so two contacts
//! (u, v) and (u, w) of the same cell are often "closed" by a third contact (v, w); two contacts
//! of different cells much less often (development pool takei2021_1mb k2_p1: 66 % vs 28 % of the
//! partner pairs at 1 Mb, contacts >= 5 Mb apart).  The long-range contacts are binned on a
//! locus grid (`res`); every edge (locus pair) gets a cell label q_e (a distribution over the k
//! cells) by mean-field annealing of a Potts model whose couplings are the log likelihood ratios
//! of "same cell" for every pair of edges sharing a locus: ln(a / b) when the pair is closed by an
//! edge, ln((1 - a) / (1 - b)) when not (a, b: closure probabilities of same- and different-cell
//! pairs, re-estimated from the current labels at every iteration).  The field of an edge is
//! averaged over its sampled neighbours (at most `max_nei` per end) and divided by a temperature
//! falling from `t0` to `t1`.

use crate::mix::MixContact;
use crate::rng::Rng;
use rayon::prelude::*;
use std::collections::HashMap;

/// Edge graph of the long-range contacts.
pub struct TriGraph {
    pub n_edges: usize,
    /// edge of every contact (-1: not long-range / not kept)
    pub edge_of: Vec<i64>,
    /// neighbour records of edge e: `rec[off[e]..off[e + 1]]` = (f, closed)
    pub off: Vec<usize>,
    pub rec_f: Vec<u32>,
    pub rec_closed: Vec<bool>,
}

/// Build the edge graph.  `min_sep`: cis contacts closer than this are left out.
pub fn build_graph(contacts: &[MixContact], keep: &[bool], res: i64, min_sep: i64, max_nei: usize, seed: u64) -> TriGraph {
    let n = contacts.len();
    let mut locus: HashMap<(u32, i64), u32> = HashMap::new();
    let lid = |c: u32, p: i64, locus: &mut HashMap<(u32, i64), u32>| -> u32 {
        let l = locus.len() as u32;
        *locus.entry((c, p / res)).or_insert(l)
    };
    let mut edge_key: HashMap<(u32, u32), u32> = HashMap::new();
    let mut edge_of = vec![-1i64; n];
    let mut edges: Vec<(u32, u32)> = vec![];
    for (i, c) in contacts.iter().enumerate() {
        if !keep[i] || c.sep() < min_sep {
            continue;
        }
        let (a, b) = (lid(c.ca, c.pa, &mut locus), lid(c.cb, c.pb, &mut locus));
        if a == b {
            continue;
        }
        let key = (a.min(b), a.max(b));
        let e = *edge_key.entry(key).or_insert_with(|| {
            edges.push(key);
            (edges.len() - 1) as u32
        });
        edge_of[i] = e as i64;
    }
    let nl = locus.len();
    let ne = edges.len();
    // adjacency: per locus, (partner, edge) sorted by partner
    let mut adj: Vec<Vec<(u32, u32)>> = vec![vec![]; nl];
    for (e, &(a, b)) in edges.iter().enumerate() {
        adj[a as usize].push((b, e as u32));
        adj[b as usize].push((a, e as u32));
    }
    for v in adj.iter_mut() {
        v.sort_unstable();
    }
    let find = |u: u32, w: u32| -> Option<u32> {
        let v = &adj[u as usize];
        v.binary_search_by_key(&w, |x| x.0).ok().map(|i| v[i].1)
    };
    let recs: Vec<Vec<(u32, bool)>> = (0..ne)
        .into_par_iter()
        .map(|e| {
            let (u, v) = edges[e];
            let mut rng = Rng::from_keys(&[seed, 0x7472_69u64, e as u64]);
            let mut out = vec![];
            for (x, y) in [(u, v), (v, u)] {
                // edges (x, w), w != y; closed when (y, w) is an edge
                let cand: Vec<(u32, u32)> = adj[x as usize].iter().copied().filter(|&(w, _)| w != y).collect();
                let pick: Vec<(u32, u32)> = if cand.len() <= max_nei {
                    cand
                } else {
                    // partial Fisher-Yates
                    let mut c = cand;
                    for i in 0..max_nei {
                        let j = i + ((rng.uniform() * (c.len() - i) as f64) as usize).min(c.len() - i - 1);
                        c.swap(i, j);
                    }
                    c.truncate(max_nei);
                    c
                };
                for (w, f) in pick {
                    out.push((f, find(y, w).is_some()));
                }
            }
            out
        })
        .collect();
    let mut off = vec![0usize];
    let mut rec_f = vec![];
    let mut rec_closed = vec![];
    for r in recs {
        for (f, c) in r {
            rec_f.push(f);
            rec_closed.push(c);
        }
        off.push(rec_f.len());
    }
    TriGraph { n_edges: ne, edge_of, off, rec_f, rec_closed }
}

/// Settings of the mean-field annealing.
#[derive(Clone, Copy, Debug)]
pub struct TriParams {
    pub iters: usize,
    pub t0: f64,
    pub t1: f64,
    pub damping: f64,
    /// learn the cell proportions (else uniform)
    pub learn_pi: bool,
}

/// Mean-field labels of the edges (k per edge) and the final closure probabilities (a, b).
pub fn mean_field(g: &TriGraph, k: usize, tp: &TriParams, seed: u64) -> (Vec<f64>, f64, f64, Vec<(usize, f64, f64, f64)>) {
    let ne = g.n_edges;
    let mut rng = Rng::from_keys(&[seed, 0x6d66_u64]);
    let mut q: Vec<f64> = (0..ne * k).map(|_| 1.0 + 0.2 * rng.uniform()).collect();
    for e in 0..ne {
        let t: f64 = q[e * k..(e + 1) * k].iter().sum();
        for x in 0..k {
            q[e * k + x] /= t;
        }
    }
    let mut pi = vec![1.0 / k as f64; k];
    let (mut a, mut b) = (0.5, 0.25);
    let mut trace = vec![];
    for it in 0..tp.iters {
        let frac = if tp.iters > 1 { it as f64 / (tp.iters - 1) as f64 } else { 1.0 };
        let temp = tp.t0 * (tp.t1 / tp.t0).powf(frac);
        // closure probabilities of same- / different-cell pairs under the current labels
        let (ss, sc, ds, dc) = (0..ne)
            .into_par_iter()
            .map(|e| {
                let mut acc = (0.0, 0.0, 0.0, 0.0);
                for r in g.off[e]..g.off[e + 1] {
                    let f = g.rec_f[r] as usize;
                    let same: f64 = (0..k).map(|x| q[e * k + x] * q[f * k + x]).sum();
                    let cl = g.rec_closed[r] as u8 as f64;
                    acc.0 += same;
                    acc.1 += same * cl;
                    acc.2 += 1.0 - same;
                    acc.3 += (1.0 - same) * cl;
                }
                acc
            })
            .reduce(|| (0.0, 0.0, 0.0, 0.0), |x, y| (x.0 + y.0, x.1 + y.1, x.2 + y.2, x.3 + y.3));
        a = (sc / ss.max(1e-12)).clamp(1e-3, 0.999);
        b = (dc / ds.max(1e-12)).clamp(1e-3, 0.999);
        // labels are exchangeable at the start (a ~ b): use at least a mild contrast
        if a < b * 1.05 {
            a = (b * 1.05).min(0.999);
        }
        let (wc, wo) = ((a / b).ln(), ((1.0 - a) / (1.0 - b)).ln());
        trace.push((it, temp, a, b));
        let newq: Vec<f64> = (0..ne)
            .into_par_iter()
            .flat_map_iter(|e| {
                let mut field = vec![0.0f64; k];
                let nr = (g.off[e + 1] - g.off[e]).max(1) as f64;
                for r in g.off[e]..g.off[e + 1] {
                    let f = g.rec_f[r] as usize;
                    let w = if g.rec_closed[r] { wc } else { wo };
                    for x in 0..k {
                        field[x] += w * q[f * k + x];
                    }
                }
                let mx = field.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
                let mut v: Vec<f64> = (0..k).map(|x| pi[x] * ((field[x] - mx) / (nr * temp) * nr.sqrt()).exp()).collect();
                let t: f64 = v.iter().sum();
                for x in v.iter_mut() {
                    *x /= t;
                }
                v.into_iter()
            })
            .collect();
        for (o, nn) in q.iter_mut().zip(&newq) {
            *o = tp.damping * *o + (1.0 - tp.damping) * nn;
        }
        if tp.learn_pi {
            let mut s = vec![0.0; k];
            for e in 0..ne {
                for x in 0..k {
                    s[x] += q[e * k + x];
                }
            }
            let t: f64 = s.iter().sum();
            for x in 0..k {
                pi[x] = (s[x] / t).max(0.01);
            }
        }
    }
    (q, a, b, trace)
}

/// The triangle seed of every contact: q of its edge, uniform for the others (k per contact).
pub fn triangle_seed(contacts: &[MixContact], keep: &[bool], k: usize, res: i64, min_sep: i64, max_nei: usize, tp: &TriParams, seed: u64) -> Vec<f64> {
    let g = build_graph(contacts, keep, res, min_sep, max_nei, seed);
    let (q, _, _, _) = mean_field(&g, k, tp, seed);
    let mut out = vec![1.0 / k as f64; contacts.len() * k];
    for (i, &e) in g.edge_of.iter().enumerate() {
        if e >= 0 {
            out[i * k..(i + 1) * k].copy_from_slice(&q[e as usize * k..(e as usize + 1) * k]);
        }
    }
    out
}

/// Trans-triangle links: trans contacts binned on a locus grid (`res`) are edges; two edges are
/// linked when they form a closed triangle with a third trans edge, the three loci on three
/// different chromosomes.  Such triangles are almost always of one cell (development pools:
/// closure 12 % vs 1.9 % for same- vs different-cell partner pairs in the simulations, 18 % vs
/// 0.3 % in Stevens 2017 pools).  Returns the edge of every contact (-1 = none) and the linked
/// edges of every edge.
pub fn trans_triangle_links(contacts: &[MixContact], keep: &[bool], res: i64) -> (Vec<i64>, Vec<Vec<u32>>) {
    let n = contacts.len();
    let mut locus: HashMap<(u32, i64), u32> = HashMap::new();
    let mut lchrom: Vec<u32> = vec![];
    let mut edge_key: HashMap<(u32, u32), u32> = HashMap::new();
    let mut edges: Vec<(u32, u32)> = vec![];
    let mut edge_of = vec![-1i64; n];
    for (i, c) in contacts.iter().enumerate() {
        if !keep[i] || c.ca == c.cb {
            continue;
        }
        let mut lid = |ch: u32, p: i64| -> u32 {
            let l = locus.len() as u32;
            *locus.entry((ch, p / res)).or_insert_with(|| {
                lchrom.push(ch);
                l
            })
        };
        let (a, b) = (lid(c.ca, c.pa), lid(c.cb, c.pb));
        let key = (a.min(b), a.max(b));
        let e = *edge_key.entry(key).or_insert_with(|| {
            edges.push(key);
            (edges.len() - 1) as u32
        });
        edge_of[i] = e as i64;
    }
    let nl = locus.len();
    let mut adj: Vec<Vec<(u32, u32)>> = vec![vec![]; nl];
    for (e, &(a, b)) in edges.iter().enumerate() {
        adj[a as usize].push((b, e as u32));
        adj[b as usize].push((a, e as u32));
    }
    for v in adj.iter_mut() {
        v.sort_unstable();
    }
    let links: Vec<Vec<u32>> = (0..edges.len())
        .into_par_iter()
        .map(|e| {
            let (u, v) = edges[e];
            let (cu, cv) = (lchrom[u as usize], lchrom[v as usize]);
            let (au, av) = (&adj[u as usize], &adj[v as usize]);
            // common neighbours w (sorted merge) on a third chromosome
            let (mut i, mut j) = (0, 0);
            let mut out = vec![];
            while i < au.len() && j < av.len() {
                if au[i].0 < av[j].0 {
                    i += 1;
                } else if au[i].0 > av[j].0 {
                    j += 1;
                } else {
                    let cw = lchrom[au[i].0 as usize];
                    if cw != cu && cw != cv {
                        out.push(au[i].1);
                        out.push(av[j].1);
                    }
                    i += 1;
                    j += 1;
                }
            }
            out.sort_unstable();
            out.dedup();
            out
        })
        .collect();
    (edge_of, links)
}

fn uf_find(parent: &mut [u32], mut x: u32) -> u32 {
    while parent[x as usize] != x {
        let p = parent[parent[x as usize] as usize];
        parent[x as usize] = p;
        x = p;
    }
    x
}

/// Must-link groups of the kept long-range contacts (cis >= `min_sep`, trans): single linkage in
/// 2-D (both ends within `radius`, same chromosome pair) — a 2-D blob of long-range contacts is
/// almost always of one cell (development pools: purity 0.92-0.97 at 0.5-1 Mb) — optionally
/// merged across chromosome pairs when two trans groups share at least `tri_min` trans-triangle
/// links (`trans_triangle_links` on the `res` grid).  Returns the group of every contact
/// (u32::MAX = none), numbered 0..n_groups.
pub fn blob_groups(contacts: &[MixContact], keep: &[bool], radius: i64, min_sep: i64, tri_min: u32, res: i64) -> Vec<u32> {
    let n = contacts.len();
    let elig: Vec<bool> = (0..n).map(|i| keep[i] && contacts[i].sep() >= min_sep).collect();
    let mut parent: Vec<u32> = (0..n as u32).collect();
    let mut by: HashMap<(u32, u32), Vec<usize>> = HashMap::new();
    for i in 0..n {
        if elig[i] {
            by.entry((contacts[i].ca, contacts[i].cb)).or_default().push(i);
        }
    }
    let mut keys: Vec<(u32, u32)> = by.keys().copied().collect();
    keys.sort_unstable();
    for key in keys {
        let mut v = by.remove(&key).unwrap();
        v.sort_by_key(|&i| (contacts[i].pa, contacts[i].pb));
        for x in 0..v.len() {
            let ci = &contacts[v[x]];
            for &j in &v[x + 1..] {
                let cj = &contacts[j];
                if cj.pa - ci.pa > radius {
                    break;
                }
                if (cj.pb - ci.pb).abs() <= radius {
                    let (a, b) = (uf_find(&mut parent, v[x] as u32), uf_find(&mut parent, j as u32));
                    if a != b {
                        parent[a.max(b) as usize] = a.min(b);
                    }
                }
            }
        }
    }
    if tri_min > 0 {
        let (edge_of, links) = trans_triangle_links(contacts, &elig, res);
        // group of every edge: the root of one of its contacts
        let mut egroup = vec![u32::MAX; links.len()];
        for i in 0..n {
            if edge_of[i] >= 0 && elig[i] {
                egroup[edge_of[i] as usize] = uf_find(&mut parent, i as u32);
            }
        }
        let mut cnt: HashMap<(u32, u32), u32> = HashMap::new();
        for (e, l) in links.iter().enumerate() {
            for &f in l {
                if (f as usize) > e {
                    let (a, b) = (egroup[e], egroup[f as usize]);
                    if a != b && a != u32::MAX && b != u32::MAX {
                        *cnt.entry((a.min(b), a.max(b))).or_insert(0) += 1;
                    }
                }
            }
        }
        let mut pairs: Vec<((u32, u32), u32)> = cnt.into_iter().filter(|x| x.1 >= tri_min).collect();
        pairs.sort_unstable();
        for ((a, b), _) in pairs {
            let (ra, rb) = (uf_find(&mut parent, a), uf_find(&mut parent, b));
            if ra != rb {
                parent[ra.max(rb) as usize] = ra.min(rb);
            }
        }
    }
    let mut id: HashMap<u32, u32> = HashMap::new();
    let mut out = vec![u32::MAX; n];
    for i in 0..n {
        if elig[i] {
            let r = uf_find(&mut parent, i as u32);
            let l = id.len() as u32;
            out[i] = *id.entry(r).or_insert(l);
        }
    }
    out
}
