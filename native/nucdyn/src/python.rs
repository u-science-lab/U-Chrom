//! Python bindings (`uchrom_nucdyn._engine`).

use crate::dynamics::{run_dynamics as rd, DynParams, Model, System, V3};
use crate::params::Params;
use crate::pipeline::{calc_genome_structure as cgs, CpuEngine, Input, StageEngine};
use crate::rng::Rng;
use numpy::ndarray::Array3;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

fn make_engine(p: &Params) -> PyResult<Box<dyn StageEngine + Send>> {
    match p.device.as_str() {
        "cpu" => Ok(Box::new(CpuEngine::new(p.n_threads).map_err(PyRuntimeError::new_err)?)),
        "gpu" => {
            #[cfg(feature = "gpu")]
            {
                let e = crate::gpu::GpuEngine::new(p.n_threads).map_err(PyRuntimeError::new_err)?;
                Ok(Box::new(e))
            }
            #[cfg(not(feature = "gpu"))]
            {
                Err(PyRuntimeError::new_err("uchrom_nucdyn was built without the `gpu` feature"))
            }
        }
        d => Err(PyValueError::new_err(format!("unknown device {d:?}"))),
    }
}

/// Run the full NucDynamics protocol.  `params_json` holds `Params` fields.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn calc_genome_structure<'py>(
    py: Python<'py>,
    names: Vec<String>,
    chr_a: PyReadonlyArray1<'py, u32>,
    pos_a: PyReadonlyArray1<'py, i64>,
    chr_b: PyReadonlyArray1<'py, u32>,
    pos_b: PyReadonlyArray1<'py, i64>,
    ambig: PyReadonlyArray1<'py, i64>,
    active: PyReadonlyArray1<'py, bool>,
    params_json: &str,
) -> PyResult<Bound<'py, PyDict>> {
    let p: Params = serde_json::from_str(params_json).map_err(|e| PyValueError::new_err(e.to_string()))?;
    p.validate().map_err(PyValueError::new_err)?;
    let (ca, pa, cb, pb, am, ac) = (
        chr_a.as_slice()?.to_vec(),
        pos_a.as_slice()?.to_vec(),
        chr_b.as_slice()?.to_vec(),
        pos_b.as_slice()?.to_vec(),
        ambig.as_slice()?.to_vec(),
        active.as_slice()?.to_vec(),
    );
    let mut engine = make_engine(&p)?;
    let res = py.detach(move || {
        let input = Input { names: &names, chr_a: &ca, pos_a: &pa, chr_b: &cb, pos_b: &pb, ambig: &am, active: &ac };
        cgs(&input, &p, engine.as_mut())
    });
    let out = res.map_err(PyRuntimeError::new_err)?;
    let d = PyDict::new(py);
    let nm = out.coords.len();
    let n = out.coords.first().map(|c| c.len()).unwrap_or(0);
    let mut flat = Vec::with_capacity(nm * n * 3);
    for c in &out.coords {
        for q in c {
            flat.extend_from_slice(q);
        }
    }
    let arr = Array3::from_shape_vec((nm, n, 3), flat).map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
    d.set_item("coords", arr.into_pyarray(py))?;
    d.set_item("chroms", out.chroms.clone())?;
    let sp: Vec<Bound<'py, numpy::PyArray1<i64>>> = out.seq_pos.into_iter().map(|v| v.into_pyarray(py)).collect();
    d.set_item("seq_pos", sp)?;
    d.set_item("model_rmsds", out.model_rmsds)?;
    d.set_item("particle_size", out.particle_size)?;
    d.set_item("seconds_total", out.seconds_total)?;
    d.set_item("stages_json", serde_json::to_string(&out.stages).unwrap())?;
    Ok(d)
}

fn to_v3(a: &PyReadonlyArray2<'_, f64>) -> PyResult<Vec<V3>> {
    let v = a.as_array();
    if v.ncols() != 3 {
        return Err(PyValueError::new_err("expected an (n, 3) array"));
    }
    Ok(v.rows().into_iter().map(|r| [r[0], r[1], r[2]]).collect())
}

fn from_v3<'py>(py: Python<'py>, v: &[V3]) -> Bound<'py, PyArray2<f64>> {
    let flat: Vec<f64> = v.iter().flat_map(|q| q.iter().copied()).collect();
    numpy::ndarray::Array2::from_shape_vec((v.len(), 3), flat).unwrap().into_pyarray(py)
}

/// One `run_dynamics` call on the CPU engine, with the original's arguments
/// (for cross-checks against the Cython code).  Returns (coords, veloc).
#[pyfunction]
#[pyo3(signature = (coords, masses, radii, rest_indices, rest_limits, rest_weight, rest_ambig, t_ref, t_step, n_steps, f_rep, f_dist, beta=10.0, tot0=20.458, veloc=None, skin=None, parallel=false, seed=0, original_nl_schedule=false, use_cells=false, protocol="nuc_dynamics_2017", emulate_overflow=false))]
#[allow(clippy::too_many_arguments)]
fn run_dynamics<'py>(
    py: Python<'py>,
    coords: PyReadonlyArray2<'py, f64>,
    masses: PyReadonlyArray1<'py, f64>,
    radii: PyReadonlyArray1<'py, f64>,
    rest_indices: PyReadonlyArray2<'py, i32>,
    rest_limits: PyReadonlyArray2<'py, f64>,
    rest_weight: PyReadonlyArray1<'py, f64>,
    rest_ambig: PyReadonlyArray1<'py, i32>,
    t_ref: f64,
    t_step: f64,
    n_steps: usize,
    f_rep: f64,
    f_dist: f64,
    beta: f64,
    tot0: f64,
    veloc: Option<PyReadonlyArray2<'py, f64>>,
    skin: Option<f64>,
    parallel: bool,
    seed: u64,
    original_nl_schedule: bool,
    use_cells: bool,
    protocol: &str,
    emulate_overflow: bool,
) -> PyResult<(Bound<'py, PyArray2<f64>>, Bound<'py, PyArray2<f64>>)> {
    let pos = to_v3(&coords)?;
    let n = pos.len();
    let masses = masses.as_slice()?.to_vec();
    let radii = radii.as_slice()?.to_vec();
    let ri = rest_indices.as_array();
    let rl = rest_limits.as_array();
    let pairs: Vec<[u32; 2]> = ri.rows().into_iter().map(|r| [r[0] as u32, r[1] as u32]).collect();
    let lims: Vec<[f64; 2]> = rl.rows().into_iter().map(|r| [r[0], r[1]]).collect();
    let w = rest_weight.as_slice()?.to_vec();
    let master = match protocol {
        "nuc_dynamics_2017" => true,
        "release_1.3" => false,
        p => return Err(PyValueError::new_err(format!("unknown protocol {p:?}"))),
    };
    let amb = rest_ambig.as_slice()?;
    // 2017: per-restraint ambiguity strides; release_1.3: group offsets
    let groups: Vec<u32> = if master {
        let mut g = vec![];
        let mut i = 0usize;
        while i < amb.len() {
            g.push(i as u32);
            i += (amb[i].max(1)) as usize;
        }
        g.push(amb.len() as u32);
        g
    } else {
        amb.iter().map(|&x| x as u32).collect()
    };
    if masses.len() != n || radii.len() != n || pairs.len() != lims.len() || pairs.len() != w.len() {
        return Err(PyValueError::new_err("array sizes do not match"));
    }
    if pairs.iter().any(|p| p[0] as usize >= n || p[1] as usize >= n) {
        return Err(PyValueError::new_err("restraint index out of range"));
    }
    let vel0 = match veloc {
        Some(v) => Some(to_v3(&v)?),
        None => None,
    };
    let max_r = radii.iter().cloned().fold(0.0, f64::max);
    let skin = skin.unwrap_or(2.0 * max_r);
    let (pos, vel) = py.detach(move || {
        let form = if master { crate::dynamics::RestraintForm::Master2017 } else { crate::dynamics::RestraintForm::Release13 };
        let sys = System::from_arrays(n, masses, radii, pairs, lims, w, groups).with_form(form);
        let mut m = Model::new(pos, Rng::new(seed));
        let dp = DynParams { t_ref, t_step, n_steps, f_rep, f_dist, beta, tot0, skin, original_nl_schedule, use_cells, emulate_overflow };
        rd(&sys, &mut m, &dp, parallel, vel0.as_deref());
        (m.pos, m.vel)
    });
    Ok((from_v3(py, &pos), from_v3(py, &vel)))
}

/// First-stage setup only (isolation filter, particles, restraints) for a
/// given particle size: returns the restraint arrays and constants, for
/// comparison with the original's `anneal_genome` inputs.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn debug_setup_stage<'py>(
    py: Python<'py>,
    names: Vec<String>,
    chr_a: PyReadonlyArray1<'py, u32>,
    pos_a: PyReadonlyArray1<'py, i64>,
    chr_b: PyReadonlyArray1<'py, u32>,
    pos_b: PyReadonlyArray1<'py, i64>,
    ambig: PyReadonlyArray1<'py, i64>,
    active: PyReadonlyArray1<'py, bool>,
    params_json: &str,
    particle_size: f64,
) -> PyResult<Bound<'py, PyDict>> {
    use crate::contacts::{build_contact_dict, initial_clean_contacts};
    let p: Params = serde_json::from_str(params_json).map_err(|e| PyValueError::new_err(e.to_string()))?;
    let d = build_contact_dict(
        chr_a.as_slice()?,
        pos_a.as_slice()?,
        chr_b.as_slice()?,
        pos_b.as_slice()?,
        ambig.as_slice()?,
        active.as_slice()?,
        false,
    );
    let _ = &names;
    let (st, sys, f_dist, n_contacts) = if p.protocol == "nuc_dynamics_2017" {
        let mut d = d;
        crate::protocol2017::remove_isolated_contacts(&mut d, p.isolation_threshold_cis, p.isolation_pos_error);
        let mut chroms: Vec<u32> = chr_a.as_slice()?.iter().chain(chr_b.as_slice()?).copied().collect();
        chroms.sort_unstable();
        chroms.dedup();
        let (st, sys, n) = crate::protocol2017::setup_stage(&d, &chroms, 1, particle_size, None, &p, 0)
            .map_err(PyRuntimeError::new_err)?;
        (st, sys, p.dist_force_const, n)
    } else {
        let d = initial_clean_contacts(&d, p.isolation_threshold_cis, p.isolation_threshold_trans, p.isolation_pos_error);
        let s = crate::pipeline::setup_stage(&d, 1, particle_size, None, &p, 0).map_err(PyRuntimeError::new_err)?;
        (s.st, s.sys, s.f_dist, s.n_contacts)
    };
    struct S {
        st: crate::contacts::Structure,
        sys: System,
        f_dist: f64,
        n_contacts: usize,
    }
    let s = S { st, sys, f_dist, n_contacts };
    let out = PyDict::new(py);
    let pairs: Vec<i64> = s.sys.rest_pairs.iter().flat_map(|q| [q[0] as i64, q[1] as i64]).collect();
    let lims: Vec<f64> = s.sys.rest_lim.iter().flat_map(|q| [q[0], q[1]]).collect();
    out.set_item("rest_pairs", pairs.into_pyarray(py))?;
    out.set_item("rest_lim", lims.into_pyarray(py))?;
    out.set_item("rest_w", s.sys.rest_w.clone().into_pyarray(py))?;
    out.set_item("groups", s.sys.groups.clone().into_pyarray(py))?;
    out.set_item("f_dist", s.f_dist)?;
    out.set_item("n_contacts", s.n_contacts)?;
    out.set_item("chroms", s.st.chroms.clone())?;
    let sp: Vec<Bound<'py, numpy::PyArray1<i64>>> = s.st.seq_pos.into_iter().map(|v| v.into_pyarray(py)).collect();
    out.set_item("seq_pos", sp)?;
    Ok(out)
}

#[pyfunction]
fn gpu_available() -> bool {
    #[cfg(feature = "gpu")]
    {
        crate::gpu::adapter_info().is_ok()
    }
    #[cfg(not(feature = "gpu"))]
    {
        false
    }
}

#[pyfunction]
fn gpu_info() -> String {
    #[cfg(feature = "gpu")]
    {
        crate::gpu::adapter_info().unwrap_or_else(|e| format!("unavailable: {e}"))
    }
    #[cfg(not(feature = "gpu"))]
    {
        "unavailable: built without the gpu feature".to_string()
    }
}

#[pyfunction]
fn default_params_json() -> String {
    serde_json::to_string(&Params::default()).unwrap()
}

#[pymodule]
fn _engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(calc_genome_structure, m)?)?;
    m.add_function(wrap_pyfunction!(run_dynamics, m)?)?;
    m.add_function(wrap_pyfunction!(debug_setup_stage, m)?)?;
    m.add_function(wrap_pyfunction!(gpu_available, m)?)?;
    m.add_function(wrap_pyfunction!(gpu_info, m)?)?;
    m.add_function(wrap_pyfunction!(default_params_json, m)?)?;
    m.add("__version__", crate::VERSION)?;
    m.add("HAS_GPU", cfg!(feature = "gpu"))?;
    Ok(())
}
