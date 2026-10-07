//! Bead layout of a (multi)ploid genome and bead radii (spec §2.1–2.2).
//!
//! Bead order follows alabtools `make_diploid` / `make_multiploid`: the
//! haploid index (chromosomes in genome order) for copy 0, then again for
//! copy 1 (only the chromosomes with >= 2 copies), and so on.  Every
//! chromosome copy is one contiguous chain.

use crate::igm::params::IgmParams;

#[derive(Clone, Debug)]
pub struct Genome {
    /// haploid bins
    pub hap_chrom: Vec<u32>,
    pub hap_start: Vec<i64>,
    pub hap_end: Vec<i64>,
    /// per bead: haploid bin, copy number, chain
    pub bead_hap: Vec<u32>,
    pub bead_copy: Vec<u32>,
    pub bead_chain: Vec<u32>,
    /// radii (nm)
    pub radii: Vec<f64>,
    /// haploid bin -> its beads (copy order)
    pub copy_index: Vec<Vec<u32>>,
    /// chains: (chromosome, copy, first bead, end bead)
    pub chains: Vec<(u32, u32, u32, u32)>,
}

impl Genome {
    /// `copies[c]`: number of copies of chromosome `c` (0 drops it).
    pub fn new(hap_chrom: &[u32], hap_start: &[i64], hap_end: &[i64], copies: &[u32], p: &IgmParams) -> Result<Genome, String> {
        let nh = hap_chrom.len();
        if hap_start.len() != nh || hap_end.len() != nh {
            return Err("bin arrays differ in length".into());
        }
        for w in hap_chrom.windows(2) {
            if w[1] < w[0] {
                return Err("bins must be sorted by chromosome (genome order)".into());
            }
        }
        if let Some(&c) = hap_chrom.iter().max() {
            if c as usize >= copies.len() {
                return Err(format!("chromosome index {c} has no copy number"));
            }
        }
        if (0..nh).any(|i| hap_end[i] <= hap_start[i]) {
            return Err("every bin needs end > start".into());
        }
        let max_copy = copies.iter().copied().max().unwrap_or(0);
        let mut g = Genome {
            hap_chrom: hap_chrom.to_vec(),
            hap_start: hap_start.to_vec(),
            hap_end: hap_end.to_vec(),
            bead_hap: vec![],
            bead_copy: vec![],
            bead_chain: vec![],
            radii: vec![],
            copy_index: vec![vec![]; nh],
            chains: vec![],
        };
        for copy in 0..max_copy {
            let mut i = 0;
            while i < nh {
                let c = hap_chrom[i];
                let mut e = i;
                while e < nh && hap_chrom[e] == c {
                    e += 1;
                }
                if copies[c as usize] > copy {
                    let first = g.bead_hap.len() as u32;
                    let chain = g.chains.len() as u32;
                    for h in i..e {
                        g.copy_index[h].push(g.bead_hap.len() as u32);
                        g.bead_hap.push(h as u32);
                        g.bead_copy.push(copy);
                        g.bead_chain.push(chain);
                    }
                    g.chains.push((c, copy, first, g.bead_hap.len() as u32));
                }
                i = e;
            }
        }
        if g.bead_hap.is_empty() {
            return Err("no beads".into());
        }
        if p.bead_radius > 0.0 {
            // user-set uniform radius (IGM-Plus `model/bead_radius`)
            g.radii = vec![p.bead_radius; g.bead_hap.len()];
            return Ok(g);
        }
        // radii from the volume occupancy (IGM `Preprocess`); the occupancy
        // refers to the modelled beads unless `occupancy_total_bp` is set
        let modelled: f64 = g.bead_hap.iter().map(|&h| (hap_end[h as usize] - hap_start[h as usize]) as f64).sum();
        let total = if p.occupancy_total_bp > 0.0 {
            if p.occupancy_total_bp < modelled {
                return Err(format!("occupancy_total_bp ({}) is smaller than the modelled genome ({modelled} bp)", p.occupancy_total_bp));
            }
            p.occupancy_total_bp
        } else {
            modelled
        };
        let rho = p.occupancy * p.nucleus_volume() / total;
        let k = 4.0 * std::f64::consts::PI / 3.0;
        g.radii = g.bead_hap.iter().map(|&h| (rho * (hap_end[h as usize] - hap_start[h as usize]) as f64 / k).cbrt()).collect();
        Ok(g)
    }

    /// Consecutive beads of one chain (polymer-bonded).
    pub fn polymer_neighbours(&self, a: u32, b: u32) -> bool {
        let (a, b) = (a.min(b) as usize, a.max(b) as usize);
        b == a + 1 && self.bead_chain[a] == self.bead_chain[b]
    }

    pub fn n_beads(&self) -> usize {
        self.bead_hap.len()
    }

    pub fn n_hap(&self) -> usize {
        self.hap_chrom.len()
    }

    /// Consecutive-bead polymer bonds `(i, i+1, d0)` (spec §3.2 `Polymer`).
    /// `nn_prob(h)`: input probability of haploid pair (h, h+1), used by the
    /// "hic" style.
    pub fn polymer_bonds(&self, p: &IgmParams, nn_prob: &dyn Fn(usize) -> f64) -> Vec<(u32, u32, f64)> {
        let mut out = vec![];
        for &(_, _, a, b) in &self.chains {
            for i in a..b.saturating_sub(1) {
                let (i, j) = (i as usize, i as usize + 1);
                let (ri, rj) = (self.radii[i], self.radii[j]);
                let d0 = if p.polymer_bonds_style == "hic" {
                    let mut f = nn_prob(self.bead_hap[i] as usize);
                    if !(0.5..=1.0).contains(&f) {
                        f = 0.5;
                    }
                    let d00 = ri + rj;
                    let d1 = 2.0 * d00;
                    ((d1.powi(3) + (f - 1.0) * d00.powi(3)) / f).cbrt()
                } else {
                    p.contact_range * (ri + rj)
                };
                out.push((i as u32, j as u32, d0));
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diploid_layout_and_radii() {
        let p = IgmParams::default();
        let chrom = [0u32, 0, 0, 1, 1];
        let start = [0i64, 100, 200, 0, 100];
        let end = [100i64, 200, 250, 100, 200];
        let g = Genome::new(&chrom, &start, &end, &[2, 1], &p).unwrap();
        // copy 0: chr0 (3) chr1 (2); copy 1: chr0 (3)
        assert_eq!(g.n_beads(), 8);
        assert_eq!(g.bead_hap, vec![0, 1, 2, 3, 4, 0, 1, 2]);
        assert_eq!(g.bead_copy, vec![0, 0, 0, 0, 0, 1, 1, 1]);
        assert_eq!(g.chains.len(), 3);
        assert_eq!(g.copy_index[1], vec![1, 6]);
        assert_eq!(g.copy_index[3], vec![3]);
        let vol: f64 = g.radii.iter().map(|r| 4.0 / 3.0 * std::f64::consts::PI * r.powi(3)).sum();
        assert!((vol / (p.occupancy * p.nucleus_volume()) - 1.0).abs() < 1e-12);
        // shorter last bin -> smaller bead
        assert!(g.radii[2] < g.radii[1]);
        let pb = g.polymer_bonds(&p, &|_| 1.0);
        assert_eq!(pb.len(), 2 + 1 + 2);
        assert!(pb.iter().all(|&(i, j, _)| g.bead_chain[i as usize] == g.bead_chain[j as usize]));
    }

    #[test]
    fn user_bead_radius_and_occupancy_reference() {
        let chrom = [0u32, 0, 0, 1, 1];
        let start = [0i64, 100, 200, 0, 100];
        let end = [100i64, 200, 250, 100, 200];
        // bead_radius: uniform, occupancy must be 0
        let p = IgmParams { bead_radius: 120.0, occupancy: 0.0, ..Default::default() };
        p.validate().unwrap();
        let g = Genome::new(&chrom, &start, &end, &[2, 1], &p).unwrap();
        assert!(g.radii.iter().all(|&r| r == 120.0));
        let bad = IgmParams { bead_radius: 120.0, ..Default::default() };
        assert!(bad.validate().unwrap_err().contains("mutually exclusive"));
        // single chromosome (chr0, 2 copies): occupancy over the modelled beads (IGM-Plus)
        // vs over the whole genome (whole-genome bead sizes)
        let p = IgmParams::default();
        let whole = Genome::new(&chrom, &start, &end, &[2, 2], &p).unwrap();
        let sub = Genome::new(&chrom[..3], &start[..3], &end[..3], &[2], &p).unwrap();
        let vol = |g: &Genome| g.radii.iter().map(|r| 4.0 / 3.0 * std::f64::consts::PI * r.powi(3)).sum::<f64>();
        assert!((vol(&sub) / (p.occupancy * p.nucleus_volume()) - 1.0).abs() < 1e-12);
        let total_bp = 2.0 * (250.0 + 200.0);
        let p2 = IgmParams { occupancy_total_bp: total_bp, ..Default::default() };
        let sub2 = Genome::new(&chrom[..3], &start[..3], &end[..3], &[2], &p2).unwrap();
        for k in 0..3 {
            assert!((sub2.radii[k] - whole.radii[k]).abs() < 1e-9 * whole.radii[k]);
        }
        assert!(sub2.radii[0] < sub.radii[0]);
        let p3 = IgmParams { occupancy_total_bp: 10.0, ..Default::default() };
        assert!(Genome::new(&chrom[..3], &start[..3], &end[..3], &[2], &p3).is_err());
    }
}
