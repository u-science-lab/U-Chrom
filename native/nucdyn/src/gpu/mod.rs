//! GPU engine (wgpu; Metal on macOS, Vulkan on Linux, DX12 on Windows).
//!
//! All models of a stage are annealed together: every buffer holds the
//! models side by side and every kernel is dispatched over (particles,
//! models).  Arithmetic is f32 (WGSL has no f64); the release_1.3 protocol
//! runs in bead units (positions / bead) so the numbers stay O(1).  One
//! temperature step (new velocities + `dyn_steps` MD steps) is one
//! submission; nothing is read back until the end of the stage.

use crate::dynamics::{RestraintForm, System, BOLTZMANN_K, V3};
use crate::params::Params;
use crate::pipeline::StageEngine;
use crate::rng::hash_keys;
use bytemuck::{Pod, Zeroable};
use wgpu::util::DeviceExt;

const WG: u32 = 256;

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable, Default, Debug)]
struct GpuParams {
    n: u32,
    m: u32,
    hc: u32,
    nb: u32,
    g: u32,
    r: u32,
    hb: u32,
    form: u32,
    dt: f32,
    rt_step: f32,
    beta: f32,
    t_ref: f32,
    f_rep: f32,
    f_dist: f32,
    stencil: u32,
    rep: f32,
    three_nk: f32,
    seed_lo: u32,
    seed_hi: u32,
    tstep: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
struct GpuRest {
    i: u32,
    j: u32,
    lo: f32,
    hi: f32,
    w: f32,
}

const ENTRY_POINTS: [&str; 14] = [
    "vel_init",
    "vel_given",
    "temp_reduce_vinit",
    "temp_reduce",
    "temp_reduce_grid",
    "cell_count_k",
    "vel_scale",
    "motion",
    "scan_local",
    "scan_blocks",
    "scatter",
    "restraints",
    "force_only",
    "force_update",
];

struct Ctx {
    device: wgpu::Device,
    queue: wgpu::Queue,
    info: String,
}

fn open_device() -> Result<Ctx, String> {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::PRIMARY,
        ..wgpu::InstanceDescriptor::new_without_display_handle()
    });
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::HighPerformance,
        force_fallback_adapter: false,
        compatible_surface: None,
        apply_limit_buckets: false,
    }))
    .map_err(|e| format!("no GPU adapter: {e}"))?;
    let ai = adapter.get_info();
    if ai.device_type == wgpu::DeviceType::Cpu {
        return Err(format!("only a software adapter is available ({})", ai.name));
    }
    let lim = adapter.limits();
    if lim.max_storage_buffers_per_shader_stage < 16 {
        return Err(format!(
            "adapter {} allows only {} storage buffers per stage (need 16)",
            ai.name, lim.max_storage_buffers_per_shader_stage
        ));
    }
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
        label: Some("uchrom_nucdyn"),
        required_features: wgpu::Features::empty(),
        required_limits: lim.clone(),
        memory_hints: wgpu::MemoryHints::Performance,
        ..Default::default()
    }))
    .map_err(|e| format!("request_device failed: {e}"))?;
    let info = format!("{} ({:?}, {:?})", ai.name, ai.backend, ai.device_type);
    Ok(Ctx { device, queue, info })
}

/// Name / backend of the GPU that would be used.
pub fn adapter_info() -> Result<String, String> {
    open_device().map(|c| c.info)
}

pub struct GpuEngine {
    ctx: Ctx,
    /// cells per repulsion cutoff in the force kernel grid (default 2: cell = cutoff / 2, 5x5x5 stencil)
    pub stencil: u32,
    bgl: wgpu::BindGroupLayout,
    pipelines: Vec<wgpu::ComputePipeline>,
}

fn storage_entry(binding: u32, read_only: bool) -> wgpu::BindGroupLayoutEntry {
    wgpu::BindGroupLayoutEntry {
        binding,
        visibility: wgpu::ShaderStages::COMPUTE,
        ty: wgpu::BindingType::Buffer {
            ty: wgpu::BufferBindingType::Storage { read_only },
            has_dynamic_offset: false,
            min_binding_size: None,
        },
        count: None,
    }
}

impl GpuEngine {
    pub fn new(_n_threads: usize) -> Result<GpuEngine, String> {
        let ctx = open_device()?;
        let device = &ctx.device;
        let module = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("nucdyn.wgsl"),
            source: wgpu::ShaderSource::Wgsl(include_str!("nucdyn.wgsl").into()),
        });
        let mut entries = vec![wgpu::BindGroupLayoutEntry {
            binding: 0,
            visibility: wgpu::ShaderStages::COMPUTE,
            ty: wgpu::BindingType::Buffer {
                ty: wgpu::BufferBindingType::Uniform,
                has_dynamic_offset: false,
                min_binding_size: None,
            },
            count: None,
        }];
        for b in 1..=16u32 {
            let ro = matches!(b, 10 | 11 | 13);
            entries.push(storage_entry(b, ro));
        }
        let bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: Some("nucdyn"), entries: &entries });
        let pl = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("nucdyn"),
            bind_group_layouts: &[Some(&bgl)],
            immediate_size: 0,
        });
        let pipelines = ENTRY_POINTS
            .iter()
            .map(|ep| {
                device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
                    label: Some(ep),
                    layout: Some(&pl),
                    module: &module,
                    entry_point: Some(ep),
                    compilation_options: Default::default(),
                    cache: None,
                })
            })
            .collect();
        let stencil = std::env::var("UCHROM_NUCDYN_GPU_STENCIL").ok().and_then(|v| v.parse().ok()).unwrap_or(2);
        Ok(GpuEngine { ctx, bgl, pipelines, stencil })
    }

    fn pipe(&self, name: &str) -> &wgpu::ComputePipeline {
        &self.pipelines[ENTRY_POINTS.iter().position(|e| *e == name).unwrap()]
    }
}

fn buf_init<T: Pod>(device: &wgpu::Device, label: &str, data: &[T], usage: wgpu::BufferUsages) -> wgpu::Buffer {
    // wgpu rejects empty buffers bound as storage: pad to at least 16 bytes
    let bytes: &[u8] = bytemuck::cast_slice(data);
    let mut v = bytes.to_vec();
    if v.len() < 16 {
        v.resize(16, 0);
    }
    while v.len() % 4 != 0 {
        v.push(0);
    }
    device.create_buffer_init(&wgpu::util::BufferInitDescriptor { label: Some(label), contents: &v, usage })
}

fn buf_zero(device: &wgpu::Device, label: &str, bytes: u64, usage: wgpu::BufferUsages) -> wgpu::Buffer {
    device.create_buffer(&wgpu::BufferDescriptor {
        label: Some(label),
        size: bytes.max(16).div_ceil(4) * 4,
        usage,
        mapped_at_creation: false,
    })
}

impl StageEngine for GpuEngine {
    fn anneal(
        &mut self,
        sys: &System,
        start: Vec<Vec<V3>>,
        schedule: &[(f64, f64)],
        dyn_steps: usize,
        f_dist: f64,
        bead: f64,
        stage: usize,
        p: &Params,
    ) -> Result<Vec<Vec<V3>>, String> {
        let seed = hash_keys(&[p.seed, stage as u64, 0x6770_75u64]);
        let dt = p.time_step * p.tot0;
        self.stencil = p.gpu_stencil.clamp(1, 4) as u32;
        self.run_schedule(sys, start, schedule, dyn_steps, f_dist, bead, dt, p.beta / p.tot0, seed, None)
    }

    fn name(&self) -> String {
        format!("gpu[{}]", self.ctx.info)
    }
}

impl GpuEngine {
    /// Anneal all models through `schedule` ((t_ref, f_rep) per temperature
    /// step, `dyn_steps` MD steps each).  `init_vel` (tests): velocities to
    /// start every temperature step from instead of fresh random ones.
    #[allow(clippy::too_many_arguments)]
    pub fn run_schedule(
        &mut self,
        sys: &System,
        start: Vec<Vec<V3>>,
        schedule: &[(f64, f64)],
        dyn_steps: usize,
        f_dist: f64,
        bead: f64,
        dt: f64,
        beta: f64,
        seed: u64,
        init_vel: Option<&[Vec<V3>]>,
    ) -> Result<Vec<Vec<V3>>, String> {
        let n = sys.n;
        let m = start.len();
        if n == 0 || m == 0 {
            return Ok(start);
        }
        if sys.masses.iter().any(|&x| x != 1.0) {
            return Err("GPU engine supports unit masses only".into());
        }
        let r0 = sys.radii[0];
        if sys.radii.iter().any(|&x| x != r0) {
            return Err("GPU engine supports equal radii only".into());
        }
        let master = matches!(sys.form, RestraintForm::Master2017 | RestraintForm::Weighted2017);
        // per-model weights (robust): one restraint table per model
        let per_model = sys.form == RestraintForm::Weighted2017 && sys.model_w.is_some();
        if let Some(w) = &sys.model_w {
            if w.len() != m {
                return Err(format!("{} weight sets for {m} models", w.len()));
            }
        }
        // work in units of the particle radius scale `u` (1 for 2017, bead for release_1.3)
        let u = if master { 1.0 } else { bead };
        let device = &self.ctx.device;
        let queue = &self.ctx.queue;
        // dense cell grid capacity per model (cells), a multiple of 256
        let hc = ((4 * n).max(256) as u32).div_ceil(WG) * WG;
        let hb = hc / WG;
        let nb = (n as u32).div_ceil(WG);
        let g = (sys.groups.len() - 1) as u32;
        let nr = sys.n_restraints() as u32;

        let st = wgpu::BufferUsages::STORAGE;
        let mut pos = Vec::with_capacity(m * n * 4);
        for c in &start {
            for q in c {
                pos.extend_from_slice(&[(q[0] / u) as f32, (q[1] / u) as f32, (q[2] / u) as f32, 0.0]);
            }
        }
        let b_pos = buf_init(device, "pos", &pos, st | wgpu::BufferUsages::COPY_SRC);
        let v4 = (m * n * 16) as u64;
        let b_vel = buf_zero(device, "vel", v4, st | wgpu::BufferUsages::COPY_DST);
        let b_acc = buf_zero(device, "acc", v4, st);
        let b_frc = buf_zero(device, "frc", v4, st);
        let b_spos = buf_zero(device, "spos", v4, st);
        let b_count = buf_zero(device, "cell_count", (m as u64) * hc as u64 * 4, st);
        let b_start = buf_zero(device, "cell_start", (m as u64) * hc as u64 * 4, st);
        let b_blocks = buf_zero(device, "block_sums", (m as u64) * hb as u64 * 4, st);
        let b_pc = buf_zero(device, "pc", (m * n * 8) as u64, st);
        let table = |w: &[f64]| -> Vec<GpuRest> {
            (0..nr as usize)
                .map(|k| GpuRest {
                    i: sys.rest_pairs[k][0],
                    j: sys.rest_pairs[k][1],
                    lo: (sys.rest_lim[k][0] / u) as f32,
                    hi: (sys.rest_lim[k][1] / u) as f32,
                    w: w[k] as f32,
                })
                .collect()
        };
        let rest: Vec<GpuRest> = match (&sys.model_w, per_model) {
            (Some(w), true) => w.iter().flat_map(|row| table(row)).collect(),
            _ => table(&sys.rest_w),
        };
        let b_rest = buf_init(device, "rest", &rest, st);
        let b_groups = buf_init(device, "groups", &sys.groups, st);
        let b_restf = buf_zero(device, "rest_f", (m as u64) * (nr.max(1) as u64) * 16, st);
        let mut incs: Vec<u32> = sys.inc_off.iter().map(|&x| x + (n as u32 + 1)).collect();
        incs.extend_from_slice(&sys.inc);
        let b_incs = buf_init(device, "incs", &incs, st);
        let b_partial = buf_zero(device, "partial", (m as u64) * nb as u64 * 4, st);
        let b_mstate = buf_zero(device, "mstate", (m as u64) * 48, st);
        let b_bpart = buf_zero(device, "bpart", (m as u64) * nb as u64 * 32, st);
        let b_params = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("params"),
            size: std::mem::size_of::<GpuParams>() as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let buffers = [
            &b_params, &b_pos, &b_vel, &b_acc, &b_frc, &b_spos, &b_count, &b_start, &b_blocks, &b_pc, &b_rest, &b_groups,
            &b_restf, &b_incs, &b_partial, &b_mstate, &b_bpart,
        ];
        let bg_entries: Vec<wgpu::BindGroupEntry> = buffers
            .iter()
            .enumerate()
            .map(|(k, b)| wgpu::BindGroupEntry { binding: k as u32, resource: b.as_entire_binding() })
            .collect();
        let bg = device.create_bind_group(&wgpu::BindGroupDescriptor { label: Some("nucdyn"), layout: &self.bgl, entries: &bg_entries });

        let dt = dt as f32;
        let rep = 2.0 * r0 / u;
        let mut prm = GpuParams {
            n: n as u32,
            m: m as u32,
            hc,
            nb,
            g,
            r: nr,
            hb,
            form: match sys.form {
                RestraintForm::Master2017 => 0,
                RestraintForm::Release13 => 1,
                RestraintForm::Weighted2017 if per_model => 3,
                RestraintForm::Weighted2017 => 2,
            },
            dt,
            rt_step: 0.5 * dt * dt,
            beta: beta as f32,
            t_ref: 0.0,
            f_rep: 0.0,
            f_dist: f_dist as f32,
            stencil: self.stencil,
            rep: rep as f32,
            three_nk: (3.0 * n as f64 * BOLTZMANN_K) as f32,
            seed_lo: seed as u32,
            seed_hi: (seed >> 32) as u32,
            tstep: 0,
        };
        let (px, gx) = (nb, g.div_ceil(WG).max(1));
        let (mm, hbx) = (m as u32, hb);
        let vel0: Option<Vec<f32>> = init_vel.map(|v| {
            let mut out = Vec::with_capacity(m * n * 4);
            for c in v {
                for q in c {
                    out.extend_from_slice(&[(q[0] / u) as f32, (q[1] / u) as f32, (q[2] / u) as f32, 0.0]);
                }
            }
            out
        });
        for (ti, &(t_ref, f_rep)) in schedule.iter().enumerate() {
            prm.t_ref = (t_ref / (u * u)) as f32;
            prm.f_rep = (f_rep * u * u) as f32;
            prm.tstep = ti as u32;
            queue.write_buffer(&b_params, 0, bytemuck::bytes_of(&prm));
            if let Some(v) = &vel0 {
                queue.write_buffer(&b_vel, 0, bytemuck::cast_slice(v));
            }
            let mut enc = device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("temp step") });
            {
                let mut pass = enc.begin_compute_pass(&wgpu::ComputePassDescriptor { label: None, timestamp_writes: None });
                pass.set_bind_group(0, &bg, &[]);
                let mut run = |name: &str, x: u32, y: u32| {
                    pass.set_pipeline(self.pipe(name));
                    pass.dispatch_workgroups(x, y, 1);
                };
                // new velocities at t_ref, forces at the current positions
                run(if vel0.is_some() { "vel_given" } else { "vel_init" }, px, mm);
                run("temp_reduce_vinit", 1, mm);
                run("vel_scale", px, mm);
                run("cell_count_k", px, mm);
                run("scan_local", hbx, mm);
                run("scan_blocks", 1, mm);
                run("scatter", px, mm);
                run("restraints", gx, mm);
                run("force_only", px, mm);
                for _ in 0..dyn_steps {
                    run("motion", px, mm);
                    run("temp_reduce_grid", 1, mm);
                    run("cell_count_k", px, mm);
                    run("scan_local", hbx, mm);
                    run("scan_blocks", 1, mm);
                    run("scatter", px, mm);
                    run("restraints", gx, mm);
                    run("force_update", px, mm);
                    run("temp_reduce", 1, mm);
                }
            }
            queue.submit(Some(enc.finish()));
            // keep the queue from running far ahead of the CPU (bounded memory for command buffers)
            if ti % 8 == 7 {
                device.poll(wgpu::PollType::Wait { submission_index: None, timeout: None }).map_err(|e| e.to_string())?;
            }
        }
        // read back
        let size = (m * n * 16) as u64;
        let staging = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("readback"),
            size,
            usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let mut enc = device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("readback") });
        enc.copy_buffer_to_buffer(&b_pos, 0, &staging, 0, size);
        queue.submit(Some(enc.finish()));
        let slice = staging.slice(..);
        let (tx, rx) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |r| {
            let _ = tx.send(r);
        });
        device.poll(wgpu::PollType::Wait { submission_index: None, timeout: None }).map_err(|e| e.to_string())?;
        rx.recv().map_err(|e| e.to_string())?.map_err(|e| e.to_string())?;
        let data = slice.get_mapped_range().map_err(|e| format!("{e:?}"))?;
        let f: &[f32] = bytemuck::cast_slice(&data[..]);
        let mut out = vec![Vec::with_capacity(n); m];
        for (mi, c) in out.iter_mut().enumerate() {
            for i in 0..n {
                let k = (mi * n + i) * 4;
                let q = [f[k] as f64 * u, f[k + 1] as f64 * u, f[k + 2] as f64 * u];
                if !(q[0].is_finite() && q[1].is_finite() && q[2].is_finite()) {
                    return Err(format!("GPU produced non-finite coordinates (model {mi}, particle {i})"));
                }
                c.push(q);
            }
        }
        drop(data);
        staging.unmap();
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dynamics::{run_dynamics, DynParams, Model};
    use crate::restraints::{ambiguity_offsets, bin_restraints, Restraint, RestraintSet};
    use crate::rng::Rng;

    fn toy(n: usize, form: RestraintForm) -> (System, Vec<V3>) {
        let mut rng = Rng::new(21);
        let mut pos = vec![];
        let mut p = [0.0f64; 3];
        for _ in 0..n {
            p = [p[0] + rng.normal() * 0.7, p[1] + rng.normal() * 0.7, p[2] + rng.normal() * 0.7];
            pos.push(p);
        }
        let mut rest = vec![];
        for i in 0..n - 1 {
            rest.push(Restraint { i: i as u32, j: i as u32 + 1, lo: 0.1, hi: 1.1, ambig: 0, weight: 1.0 });
        }
        for _ in 0..n {
            let i = (rng.uniform() * n as f64) as u32;
            let j = (rng.uniform() * n as f64) as u32;
            rest.push(Restraint { i: i.min(j), j: i.max(j), lo: 0.8, hi: 1.2, ambig: 0, weight: 1.0 });
        }
        let rest = bin_restraints(rest);
        let groups = ambiguity_offsets(&rest);
        let rs = RestraintSet { rest, groups, n_contacts: 0 };
        (System::new(n, vec![1.0; n], vec![1.0; n], &rs).with_form(form), pos)
    }

    /// Same start, same velocities: f32 GPU vs f64 CPU after a few steps.
    #[test]
    fn gpu_matches_cpu_for_short_runs() {
        let Ok(mut eng) = GpuEngine::new(0) else {
            eprintln!("no GPU adapter: skipped");
            return;
        };
        for form in [RestraintForm::Master2017, RestraintForm::Release13] {
            let (sys, pos) = toy(3000, form);
            let mut rng = Rng::new(5);
            let vel: Vec<V3> = (0..sys.n).map(|_| [rng.normal(), rng.normal(), rng.normal()]).collect();
            let (t_ref, f_rep, f_dist, steps) = (300.0, 0.6, 25.0, 10);
            let mut m = Model::new(pos.clone(), Rng::new(0));
            let dp = DynParams {
                t_ref,
                t_step: 0.001,
                n_steps: steps,
                f_rep,
                f_dist,
                beta: 10.0,
                tot0: 20.458,
                skin: 1.0,
                original_nl_schedule: false,
                use_cells: true,
                emulate_overflow: false,
            };
            run_dynamics(&sys, &mut m, &dp, false, Some(&vel));
            let out = eng
                .run_schedule(&sys, vec![pos.clone(), pos.clone()], &[(t_ref, f_rep)], steps, f_dist, 1.0, 0.001 * 20.458, 10.0 / 20.458, 1, Some(&[vel.clone(), vel.clone()]))
                .unwrap();
            for c in &out {
                let mut max_d = 0.0f64;
                let mut max_move = 0.0f64;
                for i in 0..sys.n {
                    let d: f64 = (0..3).map(|k| (c[i][k] - m.pos[i][k]).powi(2)).sum::<f64>().sqrt();
                    let mv: f64 = (0..3).map(|k| (m.pos[i][k] - pos[i][k]).powi(2)).sum::<f64>().sqrt();
                    max_d = max_d.max(d);
                    max_move = max_move.max(mv);
                }
                eprintln!("{form:?}: GPU (f32) vs CPU (f64) after {steps} steps: max diff {max_d:.2e}, max move {max_move:.3}");
                assert!(max_move > 0.05, "particles hardly moved ({max_move})");
                assert!(max_d < 1e-3, "{form:?}: GPU vs CPU max difference {max_d} (max move {max_move})");
            }
        }
    }

    /// `robust` (Weighted2017): shared and per-model weights, GPU vs CPU.
    #[test]
    fn gpu_matches_cpu_weighted() {
        let Ok(mut eng) = GpuEngine::new(0) else {
            eprintln!("no GPU adapter: skipped");
            return;
        };
        let (base, pos) = toy(3000, RestraintForm::Weighted2017);
        let nr = base.n_restraints();
        let mut rng = Rng::new(17);
        let wrow = |rng: &mut Rng| -> Vec<f64> { (0..nr).map(|_| rng.uniform()).collect() };
        let shared = {
            let mut s = base.clone();
            s.rest_w = wrow(&mut rng);
            s
        };
        let per_model = {
            let mut s = base.clone();
            s.model_w = Some(vec![wrow(&mut rng), wrow(&mut rng)]);
            s
        };
        let vel: Vec<V3> = (0..base.n).map(|_| [rng.normal(), rng.normal(), rng.normal()]).collect();
        let (t_ref, f_rep, f_dist, steps) = (300.0, 0.6, 25.0, 10);
        let dp = DynParams {
            t_ref,
            t_step: 0.001,
            n_steps: steps,
            f_rep,
            f_dist,
            beta: 10.0,
            tot0: 20.458,
            skin: 1.0,
            original_nl_schedule: false,
            use_cells: true,
            emulate_overflow: false,
        };
        for (name, sys) in [("shared", &shared), ("per-model", &per_model)] {
            let out = eng
                .run_schedule(sys, vec![pos.clone(), pos.clone()], &[(t_ref, f_rep)], steps, f_dist, 1.0, 0.001 * 20.458, 10.0 / 20.458, 1, Some(&[vel.clone(), vel.clone()]))
                .unwrap();
            let mut cpu = vec![];
            for mi in 0..2 {
                let sm = sys.for_model(mi);
                let mut m = Model::new(pos.clone(), Rng::new(0));
                run_dynamics(&sm, &mut m, &dp, false, Some(&vel));
                cpu.push(m.pos);
            }
            for (mi, c) in out.iter().enumerate() {
                let max_d = (0..base.n)
                    .map(|i| (0..3).map(|k| (c[i][k] - cpu[mi][i][k]).powi(2)).sum::<f64>().sqrt())
                    .fold(0.0, f64::max);
                eprintln!("weighted {name}, model {mi}: GPU vs CPU max diff {max_d:.2e}");
                assert!(max_d < 1e-3, "{name} model {mi}: {max_d}");
            }
            if name == "per-model" {
                let diff = (0..base.n).map(|i| (cpu[0][i][0] - cpu[1][i][0]).abs()).fold(0.0, f64::max);
                assert!(diff > 1e-3, "per-model weights had no effect");
            }
        }
    }
}
