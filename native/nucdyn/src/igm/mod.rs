//! Protocol "igm": population-based genome structure modelling of bulk Hi-C
//! (the A/M deconvolution of IGM, Boninsegna et al. 2022 Nat Methods 19:938,
//! doi:10.1038/s41592-022-01527-x; predecessor PGS, Tjong et al. 2016 PNAS
//! 113:E1663 and Hua et al. 2018 Nat Protoc 13:915).
//!
//! A clean re-implementation from the algorithm specification in
//! `benchmarks/bulk/pgs_spec.md` (no code of the GPL-licensed IGM / PGS /
//! alabtools / lammpgen was copied or translated).
//!
//! * `params`: parameters (IGM schema + demo annealing protocol);
//! * `genome`: diploid / multiploid bead layout, radii from occupancy;
//! * `forces`: soft-cosine excluded volume, upper-bound bonds, ellipsoidal
//!   envelope, violation counts (CPU f64);
//! * `md`: velocity creation, `nve/limit` + `temp/rescale` MD, CG (CPU f64);
//! * `astep`: activation distances and per-structure assignment (CPU f64);
//! * `driver`: the σ / iteration A/M loop, random initial population;
//! * `gpu` (feature `gpu`): the whole population on one device (f32).
//!
//! Opt-in IGM-Plus / IGM_2.0 variants (defaults = IGM 1.0, bit-identical on
//! the CPU, see `regression_tests`): user bead radius and occupancy
//! reference (`genome`), no iterative correction and GP pooling (`astep`),
//! pinned initial loci + noise and the per-kind violation report (`driver`);
//! table in `native/nucdyn/README.md`.

pub mod astep;
pub mod driver;
pub mod forces;
pub mod genome;
pub mod md;
pub mod params;

#[cfg(test)]
mod regression_tests;

#[cfg(feature = "gpu")]
pub mod gpu;
