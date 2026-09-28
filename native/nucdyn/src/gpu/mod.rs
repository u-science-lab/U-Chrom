//! GPU engine (placeholder, filled in below).

use crate::dynamics::{System, V3};
use crate::params::Params;
use crate::pipeline::StageEngine;

pub fn adapter_info() -> Result<String, String> {
    Err("not implemented".into())
}

pub struct GpuEngine;

impl GpuEngine {
    pub fn new(_n_threads: usize) -> Result<GpuEngine, String> {
        Err("not implemented".into())
    }
}

impl StageEngine for GpuEngine {
    fn anneal(
        &mut self,
        _sys: &System,
        _start: Vec<Vec<V3>>,
        _schedule: &[(f64, f64)],
        _dyn_steps: usize,
        _f_dist: f64,
        _bead: f64,
        _stage: usize,
        _params: &Params,
    ) -> Result<Vec<Vec<V3>>, String> {
        Err("not implemented".into())
    }
    fn name(&self) -> String {
        "gpu".into()
    }
}
