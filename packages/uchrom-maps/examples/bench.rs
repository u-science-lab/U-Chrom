//! Timing of the kernels on a synthetic map the size of human chr1 at 5 kb (50,000 bins, loops up to
//! 10 Mb; the Mustache band to 2 Mb):
//! `cargo run --release --example bench -- [threads] [hiccups|mustache|both] [repeats]`
use std::time::Instant;
use uchrom_maps::{gauss, hiccups, mustache, with_threads};

fn lcg(s: &mut u64) -> f64 {
    *s = s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
    ((*s >> 11) as f64) / ((1u64 << 53) as f64)
}

fn main() {
    let threads: usize = std::env::args().nth(1).map(|a| a.parse().unwrap()).unwrap_or(0);
    let which = std::env::args().nth(2).unwrap_or_else(|| "both".into());
    let reps: usize = std::env::args().nth(3).map(|a| a.parse().unwrap()).unwrap_or(3);
    let n = 50_000usize;
    let (p, w, dmax) = (4usize, 7usize, 2000usize);
    let band = dmax + 2 * w + 1;
    let mut s = 1u64;
    let (mut bi, mut bj, mut cnt) = (vec![], vec![], vec![]);
    for i in 0..n {
        for j in i..(i + band + 1).min(n) {
            let lam = 400.0 / (1.0 + (j - i) as f64);
            let pr = lam.min(1.0) * 0.9;
            if lcg(&mut s) < pr {
                bi.push(i as i64);
                bj.push(j as i64);
                cnt.push((lam.max(1.0) * (0.5 + lcg(&mut s))).round());
            }
        }
    }
    let weight: Vec<f64> = (0..n).map(|k| if k % 997 == 0 { f64::NAN } else { 0.8 + 0.4 * lcg(&mut s) }).collect();
    let mut expected: Vec<f64> = (0..band + 2).map(|d| 300.0 / (1.0 + d as f64)).collect();
    expected[0] = f64::NAN;
    expected[1] = f64::NAN;
    let edges: Vec<f64> = (0..160).map(|k| 2f64.powf(k as f64 / 3.0)).collect();
    let cmin: Vec<i64> = edges.iter().map(|&e| (e * 1.5 + 3.0) as i64).collect();
    let tile = {
        let a = (dmax + 4 * w) as f64;
        ((-a + (a * a + 8e6).sqrt()) / 2.0) as usize
    };
    println!("{} pixels, tile {} rows, threads {}", bi.len(), tile, if threads == 0 { rayon::current_num_threads() } else { threads });
    for rep in 0..reps {
        if which == "mustache" {
            break;
        }
        let inp = hiccups::Input {
            n, bi: &bi, bj: &bj, count: &cnt, weight: &weight, expected: &expected, p, w, max_diag: dmax,
            tile_rows: tile, edges: &edges, cmin: &cmin,
        };
        let t = Instant::now();
        let out = with_threads(threads, || hiccups::score_chrom(&inp)).unwrap().unwrap();
        println!("hiccups rep {rep}: {:.3} s, {} tested, {} candidates", t.elapsed().as_secs_f64(), out.n_tested, out.i.len());
    }
    // Mustache: the band to 400 bins, z-scores with absent pixels
    let dm = 400usize;
    let (mut x, mut y, mut z) = (vec![], vec![], vec![]);
    for i in 0..n {
        for j in i..(i + dm + 1).min(n) {
            if lcg(&mut s) < 0.9 {
                x.push(i as i64);
                y.push(j as i64);
                z.push(lcg(&mut s) * 3.0 - 1.0);
            }
        }
    }
    let el: Vec<usize> = (0..x.len()).filter(|&q| z[q] != 0.0 && y[q] - x[q] >= 4).collect();
    let ex: Vec<i64> = el.iter().map(|&q| x[q]).collect();
    let ey: Vec<i64> = el.iter().map(|&q| y[q]).collect();
    let mut ws = vec![];
    let mut rmax = 0;
    for q in 0..2 {
        let o = 1.6 * 2f64.powi(q);
        let mut ks = vec![];
        for k in 1..=12 {
            let sg = o * 2f64.powf((k as f64 - 1.0) / 10.0);
            let r = (2.0 * sg).ceil() as usize;
            rmax = rmax.max(r);
            ks.push(gauss::gaussian_weights(sg, r));
        }
        ws.push(ks);
    }
    println!("{} eligible pixels", ex.len());
    for rep in 0..reps {
        if which == "hiccups" {
            break;
        }
        let inp = mustache::Input {
            x: &x, y: &y, z: &z, ex: &ex, ey: &ey, n, max_diag: dm, min_diag: 4, fill: 2.0, weights: &ws,
            halo: rmax + 2, tile: 256, arith: gauss::Arith { fma: true, block: 8, min_terms: 10 },
        };
        let t = Instant::now();
        let out = with_threads(threads, || mustache::scan(&inp)).unwrap().unwrap();
        println!("mustache rep {rep}: {:.3} s, {} extrema", t.elapsed().as_secs_f64(), out.layer.iter().filter(|&&l| l >= 0).count());
    }
}
