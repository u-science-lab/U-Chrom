//! uchrom-recon: the native 3-D reconstruction engine of U-Chrom.  A
//! re-implementation of NucDynamics (Stevens et al. 2017, Nature 544:59; original
//! code github.com/tjs23/nuc_dynamics, LGPL-3.0) for single-cell Hi-C genome
//! structure calculation, with EMber (`robust`) and IGM population modelling (`igm`)
//! on the same particle dynamics.
//!
//! * `contacts`, `restraints`, `pipeline`: contact preprocessing, restraints
//!   and the hierarchical annealing protocol of the original.
//! * `dynamics`: the particle dynamics on the CPU (f64, rayon).
//! * `gpu` (feature `gpu`): all models of an ensemble in one batched wgpu
//!   dispatch (f32).

pub mod align;
pub mod contacts;
pub mod diploid;
pub mod dynamics;
pub mod igm;
pub mod params;
pub mod pipeline;
pub mod protocol2017;
pub mod restraints;
pub mod robust;
pub mod rng;
pub mod support;

#[cfg(feature = "gpu")]
pub mod gpu;

#[cfg(feature = "python")]
mod python;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
