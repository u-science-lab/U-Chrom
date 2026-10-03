// NucDynamics particle dynamics on the GPU (f32), all models of an
// ensemble batched: per-particle kernels are dispatched as (NB, M) workgroups
// of 256 threads (NB = ceil(N / 256), M = number of models), so a workgroup
// never straddles two models.
//
// Per MD step:
//   motion -> temp_reduce_grid -> cell_count -> scan_local -> scan_blocks ->
//   scatter -> restraints -> force_update -> temp_reduce
// Repulsion pairs come from a dense cell grid over each model's bounding box,
// rebuilt every step (cell size = cutoff / stencil), so every pair within the
// cutoff is found; particles are sorted by cell and the force kernel walks
// them in that order.

struct Params {
    n: u32,        // particles per model
    m: u32,        // models
    hc: u32,       // cell capacity per model (multiple of 256)
    nb: u32,       // particle workgroups per model
    g: u32,        // restraint groups
    r: u32,        // restraints
    hb: u32,       // cell blocks (of 256) per model
    form: u32,     // 0: 2017 master restraint form, 1: release_1.3 form, 2: 2017 weighted (robust), 3: as 2 with per-model weights
    dt: f32,       // time step (x tot0)
    rt_step: f32,  // 0.5 dt^2
    beta: f32,     // thermostat coupling / tot0
    t_ref: f32,
    f_rep: f32,
    f_dist: f32,
    stencil: u32,  // cells per cutoff
    rep: f32,      // repulsion distance r_i + r_j
    three_nk: f32, // 3 N k_B
    seed_lo: u32,
    seed_hi: u32,
    tstep: u32,    // temperature step (velocity stream)
    cut: f32,      // cell-grid cutoff: max(rep, no-contact cutoff)
    nc_lambda: f32, // robust no-contact term (0: off)
    nc_d0: f32,
    nc_s: f32,
};

struct Rest {
    i: u32,
    j: u32,
    lo: f32,
    hi: f32,
    w: f32,
};

@group(0) @binding(0) var<uniform> P: Params;
@group(0) @binding(1) var<storage, read_write> pos: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read_write> vel: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read_write> acc: array<vec4<f32>>;
@group(0) @binding(4) var<storage, read_write> frc: array<vec4<f32>>;
@group(0) @binding(5) var<storage, read_write> spos: array<vec4<f32>>;
@group(0) @binding(6) var<storage, read_write> cell_count: array<atomic<u32>>;
@group(0) @binding(7) var<storage, read_write> cell_start: array<u32>;
@group(0) @binding(8) var<storage, read_write> block_sums: array<u32>;
@group(0) @binding(9) var<storage, read_write> pc: array<vec2<u32>>;
@group(0) @binding(10) var<storage, read> rest: array<Rest>;
@group(0) @binding(11) var<storage, read> groups: array<u32>;
@group(0) @binding(12) var<storage, read_write> rest_f: array<vec4<f32>>;
@group(0) @binding(13) var<storage, read> incs: array<u32>;
@group(0) @binding(14) var<storage, read_write> partial: array<f32>;
// per model: [kin, r, scale, inv_cell], [origin xyz, _], [dims xyz (as u32 bits), ncell]
@group(0) @binding(15) var<storage, read_write> mstate: array<vec4<f32>>;
// per model and particle workgroup: bounding-box min, max
@group(0) @binding(16) var<storage, read_write> bpart: array<vec4<f32>>;

const WG: u32 = 256u;
const TAU: f32 = 6.283185307179586;
const BIG: f32 = 3.0e38;

var<workgroup> sh: array<f32, 256>;
var<workgroup> shu: array<u32, 256>;
var<workgroup> smin: array<vec3<f32>, 256>;
var<workgroup> smax: array<vec3<f32>, 256>;

fn pcg(v: u32) -> u32 {
    let state = v * 747796405u + 2891336453u;
    let word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
    return (word >> 22u) ^ word;
}

fn rand01(k: u32) -> f32 {
    return (f32(pcg(k) >> 8u) + 0.5) / 16777216.0;
}

// Sum `v` and the bounding box of `x` (if `valid`) over the workgroup;
// thread 0 writes the model's partials.  Called by every thread.
fn wg_partials(v: f32, x: vec3<f32>, valid: bool, lid: u32, wgx: u32, model: u32) {
    sh[lid] = v;
    smin[lid] = select(vec3<f32>(BIG), x, valid);
    smax[lid] = select(vec3<f32>(-BIG), x, valid);
    workgroupBarrier();
    for (var s = 128u; s > 0u; s = s >> 1u) {
        if (lid < s) {
            sh[lid] = sh[lid] + sh[lid + s];
            smin[lid] = min(smin[lid], smin[lid + s]);
            smax[lid] = max(smax[lid], smax[lid + s]);
        }
        workgroupBarrier();
    }
    if (lid == 0u) {
        let k = model * P.nb + wgx;
        partial[k] = sh[0];
        bpart[2u * k] = vec4<f32>(smin[0], 0.0);
        bpart[2u * k + 1u] = vec4<f32>(smax[0], 0.0);
    }
}

// Sum `v` over the workgroup (kinetic energy only).
fn wg_partial(v: f32, lid: u32, wgx: u32, model: u32) {
    sh[lid] = v;
    workgroupBarrier();
    for (var s = 128u; s > 0u; s = s >> 1u) {
        if (lid < s) {
            sh[lid] = sh[lid] + sh[lid + s];
        }
        workgroupBarrier();
    }
    if (lid == 0u) {
        partial[model * P.nb + wgx] = sh[0];
    }
}

// Sum the model's kinetic partials (one workgroup per model).
fn reduce_kin(model: u32, lid: u32) -> f32 {
    var s = 0.0;
    for (var k = lid; k < P.nb; k = k + WG) {
        s = s + partial[model * P.nb + k];
    }
    sh[lid] = s;
    workgroupBarrier();
    for (var t = 128u; t > 0u; t = t >> 1u) {
        if (lid < t) {
            sh[lid] = sh[lid] + sh[lid + t];
        }
        workgroupBarrier();
    }
    return sh[0];
}

// Reduce the bounding box and lay out the model's cell grid (thread 0).
fn setup_grid(model: u32, lid: u32) {
    var lo = vec3<f32>(BIG);
    var hi = vec3<f32>(-BIG);
    for (var k = lid; k < P.nb; k = k + WG) {
        let q = model * P.nb + k;
        lo = min(lo, bpart[2u * q].xyz);
        hi = max(hi, bpart[2u * q + 1u].xyz);
    }
    smin[lid] = lo;
    smax[lid] = hi;
    workgroupBarrier();
    for (var t = 128u; t > 0u; t = t >> 1u) {
        if (lid < t) {
            smin[lid] = min(smin[lid], smin[lid + t]);
            smax[lid] = max(smax[lid], smax[lid + t]);
        }
        workgroupBarrier();
    }
    if (lid == 0u) {
        let o = smin[0];
        let ext = max(smax[0] - o, vec3<f32>(0.0));
        var cs = P.cut / f32(P.stencil);
        var d = vec3<u32>(floor(ext / cs)) + vec3<u32>(1u);
        for (var it = 0u; it < 64u; it = it + 1u) {
            if (f32(d.x) * f32(d.y) * f32(d.z) <= f32(P.hc)) {
                break;
            }
            cs = cs * 1.26;
            d = vec3<u32>(floor(ext / cs)) + vec3<u32>(1u);
        }
        let b = 3u * model;
        mstate[b].w = 1.0 / cs;
        mstate[b + 1u] = vec4<f32>(o, 0.0);
        mstate[b + 2u] = vec4<f32>(bitcast<f32>(d.x), bitcast<f32>(d.y), bitcast<f32>(d.z), bitcast<f32>(d.x * d.y * d.z));
    }
}

fn grid_dims(m: u32) -> vec3<u32> {
    let g = mstate[3u * m + 2u];
    return vec3<u32>(bitcast<u32>(g.x), bitcast<u32>(g.y), bitcast<u32>(g.z));
}

fn cell_coord(m: u32, p: vec3<f32>, d: vec3<u32>) -> vec3<u32> {
    let o = mstate[3u * m + 1u].xyz;
    let inv = mstate[3u * m].w;
    let c = max(floor((p - o) * inv), vec3<f32>(0.0));
    return min(vec3<u32>(c), d - vec3<u32>(1u));
}

fn cell_lin(c: vec3<u32>, d: vec3<u32>) -> u32 {
    return (c.z * d.y + c.y) * d.x + c.x;
}

@compute @workgroup_size(256)
fn vel_init(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    var s = 0.0;
    var x = vec3<f32>(0.0);
    let valid = i < P.n;
    if (valid) {
        let base = pcg(P.seed_lo ^ pcg(P.seed_hi ^ pcg(P.tstep ^ pcg(m ^ pcg(i)))));
        let u1 = rand01(base ^ 0x68e31da4u);
        let u2 = rand01(base ^ 0xb5297a4du);
        let u3 = rand01(base ^ 0x1b56c4e9u);
        let u4 = rand01(base ^ 0x7f4a7c15u);
        let r1 = sqrt(-2.0 * log(u1));
        let r2 = sqrt(-2.0 * log(u3));
        let v = vec3<f32>(r1 * cos(TAU * u2), r1 * sin(TAU * u2), r2 * cos(TAU * u4));
        vel[m * P.n + i] = vec4<f32>(v, 0.0);
        s = dot(v, v);
        x = pos[m * P.n + i].xyz;
    }
    wg_partials(s, x, valid, l.x, wg.x, m);
}

// Velocities uploaded by the host (tests): partial sums only.
@compute @workgroup_size(256)
fn vel_given(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    var s = 0.0;
    var x = vec3<f32>(0.0);
    let valid = i < P.n;
    if (valid) {
        let v = vel[m * P.n + i].xyz;
        s = dot(v, v);
        x = pos[m * P.n + i].xyz;
    }
    wg_partials(s, x, valid, l.x, wg.x, m);
}

// After vel_init: scale factor to the reference temperature, the thermostat
// term of the first step, and the cell grid of the current positions.
@compute @workgroup_size(256)
fn temp_reduce_vinit(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let kin = reduce_kin(m, l.x);
    if (l.x == 0u) {
        let t = kin / P.three_nk;
        let scale = sqrt(P.t_ref / t);
        let t2 = max(t * scale * scale, 0.001);
        let r = P.beta * (P.t_ref / t2 - 1.0);
        let b = 3u * m;
        mstate[b] = vec4<f32>(kin * scale * scale, r, scale, mstate[b].w);
    }
    setup_grid(m, l.x);
}

// Thermostat term from the latest velocities (after force_update).
@compute @workgroup_size(256)
fn temp_reduce(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let kin = reduce_kin(m, l.x);
    if (l.x == 0u) {
        let t = max(kin / P.three_nk, 0.001);
        let r = P.beta * (P.t_ref / t - 1.0);
        let b = 3u * m;
        mstate[b] = vec4<f32>(kin, r, 1.0, mstate[b].w);
    }
}

// Thermostat term after motion + the cell grid of the new positions.
@compute @workgroup_size(256)
fn temp_reduce_grid(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let kin = reduce_kin(m, l.x);
    if (l.x == 0u) {
        let t = max(kin / P.three_nk, 0.001);
        let r = P.beta * (P.t_ref / t - 1.0);
        let b = 3u * m;
        mstate[b] = vec4<f32>(kin, r, 1.0, mstate[b].w);
    }
    setup_grid(m, l.x);
}

@compute @workgroup_size(256)
fn vel_scale(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    if (i < P.n) {
        let k = m * P.n + i;
        vel[k] = vec4<f32>(vel[k].xyz * mstate[3u * m].z, 0.0);
    }
}

// updateMotion (unit masses).
@compute @workgroup_size(256)
fn motion(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    var s = 0.0;
    var x = vec3<f32>(0.0);
    let valid = i < P.n;
    if (valid) {
        let k = m * P.n + i;
        let r = mstate[3u * m].y;
        var v = vel[k].xyz;
        let a = frc[k].xyz + r * v;
        x = pos[k].xyz + P.dt * v + P.rt_step * a;
        v = v + P.dt * a;
        pos[k] = vec4<f32>(x, 0.0);
        vel[k] = vec4<f32>(v, 0.0);
        acc[k] = vec4<f32>(a, 0.0);
        s = dot(v, v);
    }
    wg_partials(s, x, valid, l.x, wg.x, m);
}

@compute @workgroup_size(256)
fn cell_count_k(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    if (i < P.n) {
        let k = m * P.n + i;
        let d = grid_dims(m);
        let c = cell_lin(cell_coord(m, pos[k].xyz, d), d);
        let slot = atomicAdd(&cell_count[m * P.hc + c], 1u);
        pc[k] = vec2<u32>(c, slot);
    }
}

// Exclusive scan of the cell counts within blocks of 256 cells; clears the counts.
@compute @workgroup_size(256)
fn scan_local(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let c = wg.x * WG + l.x;
    let idx = m * P.hc + c;
    let v = atomicLoad(&cell_count[idx]);
    atomicStore(&cell_count[idx], 0u);
    shu[l.x] = v;
    workgroupBarrier();
    for (var off = 1u; off < WG; off = off << 1u) {
        var t = 0u;
        if (l.x >= off) {
            t = shu[l.x - off];
        }
        workgroupBarrier();
        shu[l.x] = shu[l.x] + t;
        workgroupBarrier();
    }
    cell_start[idx] = shu[l.x] - v;
    if (l.x == WG - 1u) {
        block_sums[m * P.hb + wg.x] = shu[l.x];
    }
}

// Exclusive scan of the block sums of one model (in place).
@compute @workgroup_size(256)
fn scan_blocks(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let per = (P.hb + WG - 1u) / WG;
    let b0 = l.x * per;
    var tot = 0u;
    for (var k = 0u; k < per; k = k + 1u) {
        if (b0 + k < P.hb) {
            tot = tot + block_sums[m * P.hb + b0 + k];
        }
    }
    shu[l.x] = tot;
    workgroupBarrier();
    for (var off = 1u; off < WG; off = off << 1u) {
        var t = 0u;
        if (l.x >= off) {
            t = shu[l.x - off];
        }
        workgroupBarrier();
        shu[l.x] = shu[l.x] + t;
        workgroupBarrier();
    }
    var run = shu[l.x] - tot;
    for (var k = 0u; k < per; k = k + 1u) {
        if (b0 + k < P.hb) {
            let v = block_sums[m * P.hb + b0 + k];
            block_sums[m * P.hb + b0 + k] = run;
            run = run + v;
        }
    }
}

fn cell_begin(m: u32, c: u32) -> u32 {
    if (c >= P.hc) {
        return P.n;
    }
    return cell_start[m * P.hc + c] + block_sums[m * P.hb + (c >> 8u)];
}

@compute @workgroup_size(256)
fn scatter(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    if (i < P.n) {
        let k = m * P.n + i;
        let cs = pc[k];
        let idx = cell_begin(m, cs.x) + cs.y;
        spos[m * P.n + idx] = vec4<f32>(pos[k].xyz, bitcast<f32>(i));
    }
}

// Distance restraints: one thread per (possibly ambiguous) group.
@compute @workgroup_size(256)
fn restraints(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let g = wg.x * WG + l.x;
    let m = wg.y;
    if (g >= P.g) {
        return;
    }
    let s = groups[g];
    let e = groups[g + 1u];
    let base = m * P.n;
    let fb = m * P.r;
    // forms 0 (2017), 2 / 3 (2017 weighted, robust; 3: one restraint table per model)
    let master = P.form != 1u;
    let rb = select(0u, m * P.r, P.form == 3u);
    var r2 = 0.0;
    let single = (e - s) == 1u;
    for (var q = s; q < e; q = q + 1u) {
        rest_f[fb + q] = vec4<f32>(0.0);
        let rr = rest[rb + q];
        if (rr.i != rr.j) {
            let d = pos[base + rr.i].xyz - pos[base + rr.j].xyz;
            let dd = dot(d, d);
            if (single && master) {
                r2 = dd;
            } else {
                let x = select(dd, max(dd, 1e-8), P.form == 1u);
                r2 = r2 + 1.0 / (x * x);
            }
        }
    }
    if (!(single && master)) {
        if (r2 <= 0.0) {
            return;
        }
        r2 = 1.0 / sqrt(r2);
    }
    if (r2 <= 0.0) {
        return;
    }
    let dmin = rest[rb + s].lo;
    let dmax = rest[rb + s].hi;
    var rjk = 0.0;
    var r = 1.0;
    if (master) {
        // 2017: distSwitch 0.5 (absolute), asymptote 1, exponent 2
        let ds = 0.5;
        let b = ds * ds - 2.0 * ds * ds * ds;
        if (r2 < dmin * dmin) {
            r2 = max(r2, 1e-8);
            r = sqrt(r2);
            rjk = P.f_dist * 2.0 * (dmin - r);
        } else if (r2 > dmax * dmax) {
            r = sqrt(r2);
            let d = r - dmax;
            if (r <= dmax + ds) {
                rjk = -P.f_dist * 2.0 * d;
            } else {
                rjk = -P.f_dist * (1.0 - b / (d * d));
            }
        } else {
            return;
        }
    } else {
        // release_1.3: switch at 0.5 dmax, constant force beyond
        let ds = dmax * 0.5;
        if (r2 < dmin * dmin) {
            r2 = max(r2, 1e-8);
            r = sqrt(r2);
            rjk = P.f_dist * 2.0 * (dmin - r);
        } else if (r2 <= dmax * dmax) {
            return;
        } else if (r2 <= (dmax + ds) * (dmax + ds)) {
            r = sqrt(r2);
            rjk = -P.f_dist * 2.0 * (r - dmax);
        } else {
            r = sqrt(r2);
            rjk = -P.f_dist * (ds * 2.0);
        }
    }
    for (var q = s; q < e; q = q + 1u) {
        let rr = rest[rb + q];
        if (rr.i == rr.j) {
            continue;
        }
        let d = pos[base + rr.i].xyz - pos[base + rr.j].xyz;
        var t: f32;
        if (single && master) {
            t = rjk / r;
            if (P.form >= 2u) {
                t = t * rr.w;
            }
        } else {
            let s2 = max(dot(d, d), select(0.0, 1e-8, P.form == 1u));
            t = rjk * r2 * r2 * r / (s2 * s2 * s2);
            if (P.form == 1u) {
                t = t * rr.w;
            } else if (P.form >= 2u) {
                t = t * rest[rb + s].w;  // group weight, as the CPU
            }
        }
        rest_f[fb + q] = vec4<f32>(d * t, 0.0);
    }
}

fn total_force(i: u32, m: u32, p: vec3<f32>) -> vec3<f32> {
    var f = vec3<f32>(0.0);
    if (P.f_rep != 0.0 || P.nc_lambda > 0.0) {
        let d = grid_dims(m);
        let c = vec3<i32>(cell_coord(m, p, d));
        let di = vec3<i32>(d);
        let st = i32(P.stencil);
        let rep2 = P.rep * P.rep;
        let cut2 = P.cut * P.cut;
        let nc_end = P.nc_d0 + 3.0 * P.nc_s;
        let kf = 4.0 * P.f_rep;
        let sb = m * P.n;
        let x0 = u32(max(c.x - st, 0));
        let x1 = u32(min(c.x + st, di.x - 1));
        for (var z = max(c.z - st, 0); z <= min(c.z + st, di.z - 1); z = z + 1) {
            for (var y = max(c.y - st, 0); y <= min(c.y + st, di.y - 1); y = y + 1) {
                let row = (u32(z) * d.y + u32(y)) * d.x;
                let b = cell_begin(m, row + x0);
                let e = cell_begin(m, row + x1 + 1u);
                for (var t = b; t < e; t = t + 1u) {
                    let q4 = spos[sb + t];
                    let j = bitcast<u32>(q4.w);
                    let dv = q4.xyz - p;
                    let d2 = dot(dv, dv);
                    if (d2 > cut2 || (j + 1u >= i && j <= i + 1u)) {
                        continue;
                    }
                    if (d2 <= rep2) {
                        f = f - dv * (kf * (rep2 - d2));
                    }
                    if (P.nc_lambda > 0.0) {
                        // robust "no contact" term: lambda exp(-((d - d0) / s)^2) for d0 < d < d0 + 3 s
                        let dd = sqrt(d2);
                        if (dd > P.nc_d0 && dd < nc_end) {
                            let x = (dd - P.nc_d0) / P.nc_s;
                            let en = P.nc_lambda * exp(-x * x);
                            f = f - dv * (2.0 * en * x / (P.nc_s * dd));
                        }
                    }
                }
            }
        }
    }
    let fb = m * P.r;
    let i0 = incs[i];
    let i1 = incs[i + 1u];
    for (var q = i0; q < i1; q = q + 1u) {
        let w = incs[q];
        let rf = rest_f[fb + (w >> 1u)].xyz;
        if ((w & 1u) == 0u) {
            f = f + rf;
        } else {
            f = f - rf;
        }
    }
    return f;
}

// Threads walk the particles in cell order (spos), so neighbouring threads
// visit the same cells.
@compute @workgroup_size(256)
fn force_only(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let t = wg.x * WG + l.x;
    let m = wg.y;
    if (t < P.n) {
        let q4 = spos[m * P.n + t];
        let i = bitcast<u32>(q4.w);
        frc[m * P.n + i] = vec4<f32>(total_force(i, m, q4.xyz), 0.0);
    }
}

// Forces at the new positions + updateVelocity (unit masses).
@compute @workgroup_size(256)
fn force_update(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let t = wg.x * WG + l.x;
    let m = wg.y;
    var s = 0.0;
    if (t < P.n) {
        let q4 = spos[m * P.n + t];
        let i = bitcast<u32>(q4.w);
        let k = m * P.n + i;
        let f = total_force(i, m, q4.xyz);
        frc[k] = vec4<f32>(f, 0.0);
        let r = mstate[3u * m].y;
        var v = vel[k].xyz;
        v = v + 0.5 * P.dt * (f + r * v - acc[k].xyz);
        vel[k] = vec4<f32>(v, 0.0);
        s = dot(v, v);
    }
    wg_partial(s, l.x, wg.x, m);
}
