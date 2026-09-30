//! IGM on the GPU (wgpu, f32, nm).  The whole population stays resident in
//! one buffer (`pos`, S × N vec4); the A-step reads it directly and the
//! M-step advances it in batches of structures (every kernel dispatched over
//! (particle workgroups, structures of the batch)).  Per-structure Hi-C bond
//! lists (CSR, both ends) are built on the device from the A-step rows.

use crate::gpu::{buf_init, buf_zero, open_device, storage_entry, Ctx};
use crate::igm::astep::{p_and_rank_opt, pool_combos, Candidates, PairResult};
use crate::igm::driver::{PopEngine, StructStats};
use crate::igm::forces::{ForceField, Violations, V3};
use crate::igm::genome::Genome;
use crate::igm::md::dof;
use crate::igm::params::IgmParams;
use crate::rng::hash_keys;
use bytemuck::{Pod, Zeroable};

const WG: u32 = 256;
const MS: usize = 8; // mstate vec4 per structure

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable, Default, Debug)]
struct Params {
    n: u32,
    bm: u32,
    m_off: u32,
    hc: u32,
    hb: u32,
    nb: u32,
    stencil: u32,
    n_rows: u32,
    dt: f32,
    half_dt: f32,
    vlim2: f32,
    window: f32,
    fraction: f32,
    t0: f32,
    t1: f32,
    nsteps: f32,
    ev: f32,
    env_scale: f32,
    k_env: f32,
    k_poly: f32,
    k_hic: f32,
    contact_range: f32,
    rmax: f32,
    dof: f32,
    ax: f32,
    ay: f32,
    az: f32,
    rbar: f32,
    seed_lo: u32,
    seed_hi: u32,
    stream: u32,
    tol: f32,
    dmax: f32,
    etol: f32,
    ftol: f32,
    max_iter: u32,
    max_eval: u32,
    t_create: f32,
    rows_stride: u32,
    _pad: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable, Default, Debug)]
struct AParams {
    n_pairs: u32,
    s: u32,
    n: u32,
    gx: u32,
}

const M_ENTRIES: [&str; 30] = [
    "bbox_part",
    "grid_setup",
    "cell_count_k",
    "scan_local",
    "scan_blocks",
    "scatter",
    "force_only",
    "vel_create",
    "vel_mean",
    "vel_center",
    "vel_scale_set",
    "vel_given",
    "integrate1",
    "force_int2",
    "temp_rescale",
    "vel_apply",
    "cg_prep",
    "cg_force",
    "cg_init_model",
    "cg_init_part",
    "cg_trial",
    "cg_decide",
    "cg_update",
    "cg_dir",
    "assign_total",
    "assign_count",
    "assign_scan",
    "assign_fill",
    "assign_clear",
    "violations_k",
];
const M_BINDINGS: u32 = 19;
const A_ENTRIES: [&str; 2] = ["ad_count", "ad_select"];

/// Scratch buffers of one batch (sized for `bm_cap` structures).
struct Scratch {
    bm_cap: usize,
    hic_cap: u64,
    rows_cap: u64,
    vel: wgpu::Buffer,
    frc: wgpu::Buffer,
    spos: wgpu::Buffer,
    cell_count: wgpu::Buffer,
    cell_start: wgpu::Buffer,
    block_sums: wgpu::Buffer,
    pc: wgpu::Buffer,
    hic_off: wgpu::Buffer,
    hic: wgpu::Buffer,
    partial: wgpu::Buffer,
    mstate: wgpu::Buffer,
    bpart: wgpu::Buffer,
    cgv: wgpu::Buffer,
    rows: wgpu::Buffer,
    stats: wgpu::Buffer,
}

pub struct GpuPopEngine {
    ctx: Ctx,
    mbgl: wgpu::BindGroupLayout,
    mpipes: Vec<wgpu::ComputePipeline>,
    abgl: wgpu::BindGroupLayout,
    apipes: Vec<wgpu::ComputePipeline>,
    p: IgmParams,
    n: usize,
    s: usize,
    hc: u32,
    hb: u32,
    nb: u32,
    stencil: u32,
    rmax: f32,
    axes: [f64; 3],
    /// chromosome per bead (flags inter-chromosomal Hi-C rows for the violation report)
    bead_chrom: Vec<u32>,
    b_pos: Option<wgpu::Buffer>,
    b_rad: wgpu::Buffer,
    b_poly: wgpu::Buffer,
    b_params: wgpu::Buffer,
    b_totals: Option<wgpu::Buffer>,
    scratch: Option<Scratch>,
    max_binding: u64,
    /// steps per submission
    pub chunk: usize,
    /// GPU memory budget for the batch scratch buffers (bytes)
    pub budget: u64,
}

fn uniform_entry(binding: u32) -> wgpu::BindGroupLayoutEntry {
    wgpu::BindGroupLayoutEntry {
        binding,
        visibility: wgpu::ShaderStages::COMPUTE,
        ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Uniform, has_dynamic_offset: false, min_binding_size: None },
        count: None,
    }
}

fn make_pipes(device: &wgpu::Device, src: &str, label: &str, bgl: &wgpu::BindGroupLayout, entries: &[&str]) -> Vec<wgpu::ComputePipeline> {
    let module = device.create_shader_module(wgpu::ShaderModuleDescriptor { label: Some(label), source: wgpu::ShaderSource::Wgsl(src.into()) });
    let pl = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor { label: Some(label), bind_group_layouts: &[Some(bgl)], immediate_size: 0 });
    entries
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
        .collect()
}

impl GpuPopEngine {
    pub fn new(ff: &ForceField, p: &IgmParams) -> Result<GpuPopEngine, String> {
        let ctx = open_device()?;
        let device = &ctx.device;
        let lim = device.limits();
        if lim.max_storage_buffers_per_shader_stage < M_BINDINGS {
            return Err(format!("the GPU allows {} storage buffers per stage; the IGM kernels need {M_BINDINGS}", lim.max_storage_buffers_per_shader_stage));
        }
        let max_binding = (lim.max_storage_buffer_binding_size as u64).min(lim.max_buffer_size);
        let mut entries = vec![uniform_entry(0)];
        for b in 1..=M_BINDINGS {
            entries.push(storage_entry(b, matches!(b, 2 | 10 | 17)));
        }
        let mbgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: Some("igm"), entries: &entries });
        let mpipes = make_pipes(device, include_str!("igm.wgsl"), "igm.wgsl", &mbgl, &M_ENTRIES);
        let mut aentries = vec![uniform_entry(0)];
        for b in 1..=4u32 {
            aentries.push(storage_entry(b, b != 4));
        }
        let abgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: Some("igm_astep"), entries: &aentries });
        let apipes = make_pipes(device, include_str!("astep.wgsl"), "astep.wgsl", &abgl, &A_ENTRIES);

        let n = ff.n;
        let rad: Vec<f32> = ff.radii.iter().map(|&r| r as f32).collect();
        let st = wgpu::BufferUsages::STORAGE;
        let b_rad = buf_init(device, "rad", &rad, st);
        let mut poly: Vec<u32> = ff.poly_off.clone();
        for &(j, d0) in &ff.poly {
            poly.push(j);
            poly.push((d0 as f32).to_bits());
        }
        let b_poly = buf_init(device, "poly", &poly, st);
        let b_params = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("igm_params"),
            size: std::mem::size_of::<Params>() as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let stencil = std::env::var("UCHROM_NUCDYN_GPU_STENCIL").ok().and_then(|v| v.parse().ok()).unwrap_or(2u32).clamp(1, 4);
        let hc = ((4 * n).max(256) as u32).div_ceil(WG) * WG;
        let budget_gb: f64 = std::env::var("UCHROM_IGM_GPU_BUDGET_GB").ok().and_then(|v| v.parse().ok()).unwrap_or(16.0);
        Ok(GpuPopEngine {
            ctx,
            mbgl,
            mpipes,
            abgl,
            apipes,
            p: p.clone(),
            n,
            s: 0,
            hc,
            hb: hc / WG,
            nb: (n as u32).div_ceil(WG),
            stencil,
            rmax: ff.r_max as f32,
            axes: ff.axes,
            bead_chrom: ff.bead_chrom.clone(),
            b_pos: None,
            b_rad,
            b_poly,
            b_params,
            b_totals: None,
            scratch: None,
            max_binding,
            chunk: 64,
            budget: (budget_gb * 1e9) as u64,
        })
    }

    pub fn info(&self) -> String {
        self.ctx.info.clone()
    }

    fn mpipe(&self, name: &str) -> &wgpu::ComputePipeline {
        &self.mpipes[M_ENTRIES.iter().position(|e| *e == name).unwrap_or_else(|| panic!("no kernel {name}"))]
    }

    fn apipe(&self, name: &str) -> &wgpu::ComputePipeline {
        &self.apipes[A_ENTRIES.iter().position(|e| *e == name).unwrap()]
    }

    fn poll(&self) -> Result<(), String> {
        self.ctx.device.poll(wgpu::PollType::Wait { submission_index: None, timeout: None }).map(|_| ()).map_err(|e| e.to_string())
    }

    fn read(&self, buf: &wgpu::Buffer, size: u64) -> Result<Vec<u8>, String> {
        let device = &self.ctx.device;
        let staging = device.create_buffer(&wgpu::BufferDescriptor { label: Some("readback"), size: size.max(4), usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST, mapped_at_creation: false });
        let mut enc = device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("readback") });
        enc.copy_buffer_to_buffer(buf, 0, &staging, 0, size);
        self.ctx.queue.submit(Some(enc.finish()));
        let slice = staging.slice(..size);
        let (tx, rx) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |r| {
            let _ = tx.send(r);
        });
        self.poll()?;
        rx.recv().map_err(|e| e.to_string())?.map_err(|e| e.to_string())?;
        let data = slice.get_mapped_range().map_err(|e| format!("{e:?}"))?.to_vec();
        staging.unmap();
        Ok(data)
    }

    fn base_params(&self) -> Params {
        let p = &self.p;
        let seed = hash_keys(&[p.seed, 0x6967_6d]);
        Params {
            n: self.n as u32,
            bm: 0,
            m_off: 0,
            hc: self.hc,
            hb: self.hb,
            nb: self.nb,
            stencil: self.stencil,
            n_rows: 0,
            dt: p.timestep as f32,
            half_dt: (0.5 * p.timestep) as f32,
            vlim2: ((p.max_velocity / p.timestep).powi(2)) as f32,
            window: p.rescale_window as f32,
            fraction: p.rescale_fraction as f32,
            t0: 0.0,
            t1: 0.0,
            nsteps: 1.0,
            ev: p.evfactor as f32,
            env_scale: 1.0,
            k_env: p.nucleus_kspring as f32,
            k_poly: p.polymer_kspring as f32,
            k_hic: p.contact_kspring as f32,
            contact_range: p.contact_range as f32,
            rmax: self.rmax,
            dof: dof(self.n) as f32,
            ax: self.axes[0] as f32,
            ay: self.axes[1] as f32,
            az: self.axes[2] as f32,
            rbar: ((self.axes[0] + self.axes[1] + self.axes[2]) / 3.0) as f32,
            seed_lo: seed as u32,
            seed_hi: (seed >> 32) as u32,
            stream: 0,
            tol: p.violation_tolerance as f32,
            dmax: p.cg_dmax as f32,
            etol: p.cg_etol as f32,
            ftol: p.cg_ftol as f32,
            max_iter: p.cg_max_iter as u32,
            max_eval: p.cg_max_eval as u32,
            t_create: 0.0,
            rows_stride: 0,
            _pad: 0,
        }
    }

    /// Bytes of scratch per structure of a batch (excluding Hi-C bonds).
    fn bytes_per_structure(&self) -> u64 {
        let n = self.n as u64;
        n * (16 * 3 + 8 + 48) + (n + 1) * 4 + self.hc as u64 * 12 + self.hb as u64 * 4 + self.nb as u64 * 48 + (MS as u64) * 16 + 32
    }

    fn ensure_scratch(&mut self, bm: usize, hic_entries: u64, n_rows: u64) {
        let need_new = match &self.scratch {
            None => true,
            Some(s) => s.bm_cap < bm || s.hic_cap < hic_entries || s.rows_cap < n_rows,
        };
        if !need_new {
            return;
        }
        let (bm, hic_cap, rows_cap) = match &self.scratch {
            Some(s) => (s.bm_cap.max(bm), s.hic_cap.max(hic_entries), s.rows_cap.max(n_rows)),
            None => (bm, hic_entries, n_rows),
        };
        self.scratch = None;
        let d = &self.ctx.device;
        let st = wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::COPY_SRC;
        let (b, n) = (bm as u64, self.n as u64);
        self.scratch = Some(Scratch {
            bm_cap: bm,
            hic_cap,
            rows_cap,
            vel: buf_zero(d, "vel", b * n * 16, st),
            frc: buf_zero(d, "frc", b * n * 16, st),
            spos: buf_zero(d, "spos", b * n * 16, st),
            cell_count: buf_zero(d, "cell_count", b * self.hc as u64 * 4, st),
            cell_start: buf_zero(d, "cell_start", b * self.hc as u64 * 4, st),
            block_sums: buf_zero(d, "block_sums", b * self.hb as u64 * 4, st),
            pc: buf_zero(d, "pc", b * n * 8, st),
            hic_off: buf_zero(d, "hic_off", b * (n + 1) * 4, st),
            hic: buf_zero(d, "hic", hic_cap.max(1) * 4, st),
            partial: buf_zero(d, "partial", b * self.nb as u64 * 16, st),
            mstate: buf_zero(d, "mstate", b * MS as u64 * 16, st),
            bpart: buf_zero(d, "bpart", b * self.nb as u64 * 32, st),
            cgv: buf_zero(d, "cgv", b * n * 48, st),
            rows: buf_zero(d, "rows", rows_cap.max(1) * 16, st),
            stats: buf_zero(d, "stats", b * 32, st),
        });
    }

    fn bind_group(&self) -> wgpu::BindGroup {
        let s = self.scratch.as_ref().unwrap();
        let bufs: [&wgpu::Buffer; 20] = [
            &self.b_params,
            self.b_pos.as_ref().unwrap(),
            &self.b_rad,
            &s.vel,
            &s.frc,
            &s.spos,
            &s.cell_count,
            &s.cell_start,
            &s.block_sums,
            &s.pc,
            &self.b_poly,
            &s.hic_off,
            &s.hic,
            &s.partial,
            &s.mstate,
            &s.bpart,
            &s.cgv,
            &s.rows,
            &s.stats,
            self.b_totals.as_ref().unwrap(),
        ];
        let entries: Vec<wgpu::BindGroupEntry> = bufs.iter().enumerate().map(|(k, b)| wgpu::BindGroupEntry { binding: k as u32, resource: b.as_entire_binding() }).collect();
        self.ctx.device.create_bind_group(&wgpu::BindGroupDescriptor { label: Some("igm"), layout: &self.mbgl, entries: &entries })
    }

    /// Encode `f(pass)` into one submission.
    fn submit(&self, bg: &wgpu::BindGroup, f: impl FnOnce(&mut dyn FnMut(&str, u32, u32))) {
        let device = &self.ctx.device;
        let mut enc = device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("igm") });
        {
            let mut pass = enc.begin_compute_pass(&wgpu::ComputePassDescriptor { label: None, timestamp_writes: None });
            pass.set_bind_group(0, bg, &[]);
            let mut run = |name: &str, x: u32, y: u32| {
                pass.set_pipeline(self.mpipe(name));
                pass.dispatch_workgroups(x.max(1), y.max(1), 1);
            };
            f(&mut run);
        }
        self.ctx.queue.submit(Some(enc.finish()));
    }

    fn write_params(&self, prm: &Params) {
        self.ctx.queue.write_buffer(&self.b_params, 0, bytemuck::bytes_of(prm));
    }

    fn grid_kernels(run: &mut dyn FnMut(&str, u32, u32), nb: u32, hb: u32, bm: u32) {
        run("grid_setup", 1, bm);
        run("cell_count_k", nb, bm);
        run("scan_local", hb, bm);
        run("scan_blocks", 1, bm);
        run("scatter", nb, bm);
    }

    /// One MD run of the current batch (new velocities at `t_create` unless `given_vel`).
    fn md_run(&self, bg: &wgpu::BindGroup, prm: &Params, given_vel: bool) -> Result<(), String> {
        self.write_params(prm);
        let (nb, hb, bm) = (self.nb, self.hb, prm.bm);
        self.submit(bg, |run| {
            if given_vel {
                run("vel_given", 1, bm);
            } else {
                run("vel_create", nb, bm);
                run("vel_mean", 1, bm);
                run("vel_center", nb, bm);
                run("vel_scale_set", 1, bm);
            }
            run("bbox_part", nb, bm);
            Self::grid_kernels(run, nb, hb, bm);
            run("force_only", nb, bm);
        });
        let steps = prm.nsteps as usize;
        let mut done = 0;
        let mut k = 0;
        while done < steps {
            let c = self.chunk.min(steps - done);
            self.submit(bg, |run| {
                for _ in 0..c {
                    run("integrate1", nb, bm);
                    Self::grid_kernels(run, nb, hb, bm);
                    run("force_int2", nb, bm);
                    run("temp_rescale", 1, bm);
                }
            });
            done += c;
            k += 1;
            if k % 8 == 0 {
                self.poll()?;
            }
        }
        Ok(())
    }

    fn cg_run(&self, bg: &wgpu::BindGroup, prm: &Params) -> Result<(), String> {
        self.write_params(prm);
        let (nb, hb, bm) = (self.nb, self.hb, prm.bm);
        self.submit(bg, |run| {
            run("cg_prep", 1, bm);
            run("bbox_part", nb, bm);
            Self::grid_kernels(run, nb, hb, bm);
            run("cg_force", nb, bm);
            run("cg_init_model", 1, bm);
            run("cg_init_part", nb, bm);
            run("cg_dir", 1, bm);
        });
        let evals = self.p.cg_max_eval.saturating_sub(1);
        let mut done = 0;
        let mut k = 0;
        while done < evals {
            let c = self.chunk.min(evals - done);
            self.submit(bg, |run| {
                for _ in 0..c {
                    run("cg_trial", nb, bm);
                    Self::grid_kernels(run, nb, hb, bm);
                    run("cg_force", nb, bm);
                    run("cg_decide", 1, bm);
                    run("cg_update", nb, bm);
                    run("cg_dir", 1, bm);
                }
            });
            done += c;
            k += 1;
            if k % 8 == 0 {
                self.poll()?;
            }
        }
        Ok(())
    }

    fn upload_rows(&mut self, rows: &[(u32, u32, f64)]) -> u64 {
        let bc = &self.bead_chrom;
        let inter = |a: u32, b: u32| (!bc.is_empty() && bc[a as usize] != bc[b as usize]) as u32;
        let data: Vec<[u32; 4]> = rows.iter().map(|r| [r.0, r.1, (r.2 as f32).to_bits(), inter(r.0, r.1)]).collect();
        let s = self.scratch.as_ref().unwrap();
        if !data.is_empty() {
            self.ctx.queue.write_buffer(&s.rows, 0, bytemuck::cast_slice(&data));
        }
        data.len() as u64
    }

    fn rows_dispatch_x(n_rows: u32) -> u32 {
        n_rows.div_ceil(WG).clamp(1, 4096)
    }

    /// Hi-C bond ends per structure over the whole population.
    fn totals(&mut self, n_rows: u32) -> Result<Vec<u32>, String> {
        let bg = self.bind_group();
        let t = self.b_totals.as_ref().unwrap();
        let mut enc = self.ctx.device.create_command_encoder(&Default::default());
        enc.clear_buffer(t, 0, None);
        self.ctx.queue.submit(Some(enc.finish()));
        let mut out = vec![0u32; self.s];
        let ymax = 65535usize;
        let mut s0 = 0;
        while s0 < self.s {
            let bm = (self.s - s0).min(ymax);
            let prm = Params { bm: bm as u32, m_off: s0 as u32, n_rows, ..self.base_params() };
            self.write_params(&prm);
            if n_rows > 0 {
                let x = Self::rows_dispatch_x(n_rows);
                self.submit(&bg, |run| run("assign_total", x, bm as u32));
            }
            self.poll()?;
            s0 += bm;
        }
        let data = self.read(self.b_totals.as_ref().unwrap(), (self.s * 4) as u64)?;
        out.copy_from_slice(bytemuck::cast_slice(&data));
        Ok(out)
    }

    /// Batches of structures [start, end) with their Hi-C bond-end totals.
    fn plan_batches(&self, totals: &[u32]) -> Vec<(usize, usize, u64)> {
        let per = self.bytes_per_structure();
        let n = self.n as u64;
        let mut bm_max = if self.p.batch_size > 0 { self.p.batch_size } else { ((self.budget / per).max(1)) as usize };
        // every scratch buffer must fit one binding
        let largest_per = (n * 48).max(self.hc as u64 * 4);
        bm_max = bm_max.min((self.max_binding / largest_per).max(1) as usize).min(65535);
        let hic_max = self.max_binding / 4;
        let mut out = vec![];
        let mut s0 = 0;
        while s0 < totals.len() {
            let mut e = s0;
            let mut h = 0u64;
            while e < totals.len() && e - s0 < bm_max && (e == s0 || h + totals[e] as u64 <= hic_max) {
                h += totals[e] as u64;
                e += 1;
            }
            out.push((s0, e, h));
            s0 = e;
        }
        out
    }

    /// Run `f` on each batch after building its Hi-C CSR; returns per-structure stats.
    fn for_batches(&mut self, rows: &[(u32, u32, f64)], mut f: impl FnMut(&Self, &wgpu::BindGroup, &Params) -> Result<(), String>) -> Result<Vec<StructStats>, String> {
        let n_rows = rows.len() as u64;
        self.ensure_scratch(1, 1, n_rows);
        self.upload_rows(rows);
        let totals = self.totals(n_rows as u32)?;
        let batches = self.plan_batches(&totals);
        let bm_cap = batches.iter().map(|b| b.1 - b.0).max().unwrap_or(1);
        let hic_cap = batches.iter().map(|b| b.2).max().unwrap_or(1);
        let had = self.scratch.as_ref().map(|s| (s.bm_cap, s.hic_cap, s.rows_cap));
        self.ensure_scratch(bm_cap, hic_cap, n_rows);
        if self.scratch.as_ref().map(|s| (s.bm_cap, s.hic_cap, s.rows_cap)) != had {
            self.upload_rows(rows);
        }
        let bg = self.bind_group();
        let mut stats = Vec::with_capacity(self.s);
        for &(s0, s1, _) in &batches {
            let bm = (s1 - s0) as u32;
            // mstate: zero + Hi-C base offsets per structure
            let mut ms = vec![[0u32; 4]; bm as usize * MS];
            let mut base = 0u32;
            for m in 0..bm as usize {
                ms[m * MS + 7][0] = base;
                base += totals[s0 + m];
            }
            let sc = self.scratch.as_ref().unwrap();
            self.ctx.queue.write_buffer(&sc.mstate, 0, bytemuck::cast_slice(&ms));
            let mut enc = self.ctx.device.create_command_encoder(&Default::default());
            enc.clear_buffer(&sc.stats, 0, None);
            enc.clear_buffer(&sc.cell_count, 0, None);
            self.ctx.queue.submit(Some(enc.finish()));
            let prm = Params { bm, m_off: s0 as u32, n_rows: n_rows as u32, ..self.base_params() };
            self.write_params(&prm);
            let (nb, x) = (self.nb, Self::rows_dispatch_x(n_rows as u32));
            self.submit(&bg, |run| {
                if n_rows > 0 {
                    run("assign_count", x, bm);
                }
                run("assign_scan", 1, bm);
                if n_rows > 0 {
                    run("assign_fill", x, bm);
                }
                run("assign_clear", nb, bm);
            });
            f(self, &bg, &prm)?;
            self.write_params(&prm);
            self.submit(&bg, |run| run("violations_k", nb, bm));
            stats.extend(self.batch_stats(bm as usize)?);
        }
        Ok(stats)
    }

    fn batch_stats(&self, bm: usize) -> Result<Vec<StructStats>, String> {
        let sc = self.scratch.as_ref().unwrap();
        let st = self.read(&sc.stats, (bm * 32) as u64)?;
        let st: &[u32] = bytemuck::cast_slice(&st);
        let ms = self.read(&sc.mstate, (bm * MS * 16) as u64)?;
        let ms: &[f32] = bytemuck::cast_slice(&ms);
        Ok((0..bm)
            .map(|m| {
                let c = &st[8 * m..8 * m + 8];
                let b = m * MS * 4;
                StructStats {
                    viol: Violations {
                        hic_imposed: c[0] as u64,
                        hic_violated: c[1] as u64,
                        poly_imposed: c[2] as u64,
                        poly_violated: c[3] as u64,
                        env_imposed: c[4] as u64,
                        env_violated: c[5] as u64,
                        hic_inter_imposed: c[6] as u64,
                        hic_inter_violated: c[7] as u64,
                    },
                    n_hic: c[0] as u64,
                    energy: ms[b + 3 * 4] as f64,
                    cg_iterations: ms[b + 4 * 4 + 3].to_bits(),
                    cg_evaluations: ms[b + 4 * 4 + 2].to_bits(),
                }
            })
            .collect())
    }

    /// Stage parameters of one run.
    fn run_params(&self, base: &Params, stage: usize, relax: bool, round: u64) -> Params {
        let p = &self.p;
        let sg = &p.stages[stage];
        let mut prm = Params { ev: (p.evfactor * sg.evfactor) as f32, env_scale: sg.envelope_factor as f32, ..*base };
        prm.stream = hash_keys(&[round, stage as u64, relax as u64]) as u32;
        match (&p.relax, relax) {
            (Some(r), true) => {
                prm.t_create = r.temperature as f32;
                prm.t0 = r.temperature as f32;
                prm.t1 = r.temperature as f32;
                prm.nsteps = r.mdsteps as f32;
                prm.vlim2 = ((r.max_velocity / p.timestep).powi(2)) as f32;
            }
            _ => {
                prm.t_create = sg.tstart as f32;
                prm.t0 = sg.tstart as f32;
                prm.t1 = sg.tstop as f32;
                prm.nsteps = sg.mdsteps as f32;
            }
        }
        prm
    }

    fn upload_population(&mut self, pop: &[Vec<V3>]) -> Result<(), String> {
        let s = pop.len();
        let n = self.n;
        let bytes = (s * n * 16) as u64;
        if bytes > self.max_binding {
            return Err(format!(
                "population of {s} x {n} beads needs {bytes} bytes in one GPU buffer; the device allows {} (use fewer structures)",
                self.max_binding
            ));
        }
        let mut data = Vec::with_capacity(s * n * 4);
        for st in pop {
            if st.len() != n {
                return Err("structure size differs from the genome".into());
            }
            for q in st {
                data.extend_from_slice(&[q[0] as f32, q[1] as f32, q[2] as f32, 0.0]);
            }
        }
        let d = &self.ctx.device;
        let usage = wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::COPY_SRC;
        if self.s != s || self.b_pos.is_none() {
            self.b_pos = Some(buf_init(d, "pos", &data, usage));
            self.b_totals = Some(buf_zero(d, "totals", (s * 4) as u64, usage));
            self.s = s;
        } else {
            self.ctx.queue.write_buffer(self.b_pos.as_ref().unwrap(), 0, bytemuck::cast_slice(&data));
        }
        Ok(())
    }

    fn download_population(&self) -> Result<Vec<Vec<V3>>, String> {
        let n = self.n;
        let data = self.read(self.b_pos.as_ref().ok_or("no population")?, (self.s * n * 16) as u64)?;
        let f: &[f32] = bytemuck::cast_slice(&data);
        let mut out = Vec::with_capacity(self.s);
        for s in 0..self.s {
            let mut v = Vec::with_capacity(n);
            for i in 0..n {
                let k = (s * n + i) * 4;
                let q = [f[k] as f64, f[k + 1] as f64, f[k + 2] as f64];
                if !(q[0].is_finite() && q[1].is_finite() && q[2].is_finite()) {
                    return Err(format!("GPU produced non-finite coordinates (structure {s}, bead {i})"));
                }
                v.push(q);
            }
            out.push(v);
        }
        Ok(out)
    }

    /// A-step kernel over one list of pairs (count or select).
    fn astep_pass(&self, entry: &str, pairs: &[[u32; 4]], combos: &[[u32; 2]]) -> Result<Vec<u32>, String> {
        let d = &self.ctx.device;
        let np = pairs.len();
        if np == 0 {
            return Ok(vec![]);
        }
        let st = wgpu::BufferUsages::STORAGE;
        let b_pairs = buf_init(d, "pairs", pairs, st);
        let b_combos = buf_init(d, "combos", combos, st);
        let b_res = buf_zero(d, "result", (np * 4) as u64, st | wgpu::BufferUsages::COPY_SRC);
        let gx = (np as u32).min(65535);
        let gy = (np as u32).div_ceil(gx);
        let ap = AParams { n_pairs: np as u32, s: self.s as u32, n: self.n as u32, gx };
        let b_ap = buf_init(d, "aparams", std::slice::from_ref(&ap), wgpu::BufferUsages::UNIFORM);
        let bufs = [&b_ap, self.b_pos.as_ref().unwrap(), &b_pairs, &b_combos, &b_res];
        let entries: Vec<wgpu::BindGroupEntry> = bufs.iter().enumerate().map(|(k, b)| wgpu::BindGroupEntry { binding: k as u32, resource: b.as_entire_binding() }).collect();
        let bg = d.create_bind_group(&wgpu::BindGroupDescriptor { label: Some("astep"), layout: &self.abgl, entries: &entries });
        let mut enc = d.create_command_encoder(&Default::default());
        {
            let mut pass = enc.begin_compute_pass(&wgpu::ComputePassDescriptor { label: None, timestamp_writes: None });
            pass.set_bind_group(0, &bg, &[]);
            pass.set_pipeline(self.apipe(entry));
            pass.dispatch_workgroups(gx, gy, 1);
        }
        self.ctx.queue.submit(Some(enc.finish()));
        let data = self.read(&b_res, (np * 4) as u64)?;
        Ok(bytemuck::cast_slice(&data).to_vec())
    }

    /// Test hook: MD of the population with given velocities and bonds from `rows`.
    #[allow(clippy::too_many_arguments)]
    pub fn debug_md(&mut self, pop: &[Vec<V3>], vel: &[Vec<V3>], rows: &[(u32, u32, f64)], n_steps: usize, t0: f64, t1: f64, xlimit: f64, ev: f64, env: f64) -> Result<Vec<Vec<V3>>, String> {
        self.upload_population(pop)?;
        let p = self.p.clone();
        let mut vdata = Vec::new();
        for st in vel {
            for q in st {
                vdata.extend_from_slice(&[q[0] as f32, q[1] as f32, q[2] as f32, 0.0]);
            }
        }
        self.for_batches(rows, |e, bg, prm| {
            let (s0, bm) = (prm.m_off as usize, prm.bm as usize);
            let n = e.n;
            e.ctx.queue.write_buffer(&e.scratch.as_ref().unwrap().vel, 0, bytemuck::cast_slice(&vdata[s0 * n * 4..(s0 + bm) * n * 4]));
            let mut r = Params { t0: t0 as f32, t1: t1 as f32, nsteps: n_steps as f32, ev: (p.evfactor * ev) as f32, env_scale: env as f32, ..*prm };
            r.vlim2 = ((xlimit / p.timestep).powi(2)) as f32;
            e.md_run(bg, &r, true)
        })?;
        self.download_population()
    }

    /// Test hook: CG of every structure (stage factors ev, env); returns (population, stats).
    pub fn debug_cg(&mut self, pop: &[Vec<V3>], rows: &[(u32, u32, f64)], ev: f64, env: f64) -> Result<(Vec<Vec<V3>>, Vec<StructStats>), String> {
        self.upload_population(pop)?;
        let p = self.p.clone();
        let stats = self.for_batches(rows, |e, bg, prm| {
            let r = Params { ev: (p.evfactor * ev) as f32, env_scale: env as f32, ..*prm };
            e.cg_run(bg, &r)
        })?;
        Ok((self.download_population()?, stats))
    }
}

impl PopEngine for GpuPopEngine {
    fn name(&self) -> String {
        format!("gpu[{}]", self.ctx.info)
    }

    fn set_population(&mut self, pop: &[Vec<V3>]) -> Result<(), String> {
        self.upload_population(pop)
    }

    fn population(&mut self) -> Result<Vec<Vec<V3>>, String> {
        self.download_population()
    }

    fn actdist(&mut self, g: &Genome, cand: &Candidates, sel: &[u32]) -> Result<Vec<PairResult>, String> {
        let s = self.s as u64;
        let (ic, gp) = (self.p.iterative_correction, self.p.gp_pooling());
        let mut pairs = Vec::with_capacity(sel.len());
        let mut npos = Vec::with_capacity(sel.len());
        let mut cmb: Vec<[u32; 2]> = Vec::new();
        for &k in sel {
            let k = k as usize;
            let (cb, np) = pool_combos(g, cand.i[k], cand.j[k], cand.intra[k], gp);
            let rc = self.p.contact_range * (g.radii[cb[0][0] as usize] + g.radii[cb[0][1] as usize]);
            // 4th word: n_possible per structure for GP pooling (0 = every combination)
            pairs.push([cmb.len() as u32, cb.len() as u32, ((rc * rc) as f32).to_bits(), if gp { np as u32 } else { 0 }]);
            npos.push(np as u64);
            cmb.extend_from_slice(&cb);
        }
        // pairs in chunks, so no buffer exceeds a binding
        let chunk = ((self.max_binding / 64).max(1024) as usize).min(1 << 24);
        let mut counts = Vec::with_capacity(pairs.len());
        for ch in pairs.chunks(chunk) {
            counts.extend(self.astep_pass("ad_count", ch, &cmb)?);
        }
        let mut res = Vec::with_capacity(sel.len());
        let mut sel_pairs = vec![];
        let mut sel_idx = vec![];
        for (q, &k) in sel.iter().enumerate() {
            let k = k as usize;
            let nt = npos[q] * s;
            let (p_now, p, o) = p_and_rank_opt(cand.f[k], cand.p_last[k], counts[q] as u64, nt, ic);
            match o {
                Some(o) => {
                    sel_pairs.push([pairs[q][0], pairs[q][1], o as u32, pairs[q][3]]);
                    sel_idx.push(q);
                    res.push(PairResult { p_now, p, rank: o, d2_act: 0.0 });
                }
                None => res.push(PairResult { p_now, p, rank: 0, d2_act: -1.0 }),
            }
        }
        let mut bits = Vec::with_capacity(sel_pairs.len());
        for ch in sel_pairs.chunks(chunk) {
            bits.extend(self.astep_pass("ad_select", ch, &cmb)?);
        }
        for (q, b) in sel_idx.into_iter().zip(bits) {
            res[q].d2_act = f32::from_bits(b) as f64;
        }
        Ok(res)
    }

    fn mstep(&mut self, rows: &[(u32, u32, f64)], round: u64) -> Result<Vec<StructStats>, String> {
        let nst = self.p.stages.len();
        let has_relax = self.p.relax.is_some();
        self.for_batches(rows, |e, bg, prm| {
            for k in 0..nst {
                if has_relax {
                    e.md_run(bg, &e.run_params(prm, k, true, round), false)?;
                }
                e.md_run(bg, &e.run_params(prm, k, false, round), false)?;
            }
            let last = e.run_params(prm, nst - 1, false, round);
            e.cg_run(bg, &last)
        })
    }
}

#[cfg(test)]
#[path = "gpu_tests.rs"]
mod tests;
