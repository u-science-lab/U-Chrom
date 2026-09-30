// IGM M-step on the GPU (f32, nm), a batch of structures at once.
//
// Per-particle kernels are dispatched as (NB, BM) workgroups of 256 threads
// (NB = ceil(N / 256), BM = structures in the batch), so a workgroup never
// straddles two structures.  Batch-local arrays are indexed m * N + i; the
// resident population `pos` is indexed (m_off + m) * N + i.
//
// MD step (LAMMPS fix nve/limit + fix temp/rescale):
//   integrate1 -> grid_setup -> cell_count_k -> scan_local -> scan_blocks ->
//   scatter -> force_int2 -> temp_rescale
// The temp/rescale factor of a step is applied at the start of the next
// integrate1 (same arithmetic as rescaling at the end of the step).

struct Params {
    n: u32,          // beads per structure
    bm: u32,         // structures in the batch
    m_off: u32,      // first structure of the batch
    hc: u32,         // cell capacity per structure (multiple of 256)
    hb: u32,         // cell blocks per structure
    nb: u32,         // particle workgroups per structure
    stencil: u32,
    n_rows: u32,     // assignment rows
    dt: f32,
    half_dt: f32,
    vlim2: f32,
    window: f32,
    fraction: f32,
    t0: f32,
    t1: f32,
    nsteps: f32,
    ev: f32,         // evfactor x stage factor
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
    t_create: f32,   // velocity-creation temperature
    rows_stride: u32,
    _pad: u32,
};

@group(0) @binding(0) var<uniform> P: Params;
@group(0) @binding(1) var<storage, read_write> pos: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> rad: array<f32>;
@group(0) @binding(3) var<storage, read_write> vel: array<vec4<f32>>;
@group(0) @binding(4) var<storage, read_write> frc: array<vec4<f32>>;
@group(0) @binding(5) var<storage, read_write> spos: array<vec4<f32>>;
@group(0) @binding(6) var<storage, read_write> cell_count: array<atomic<u32>>;
@group(0) @binding(7) var<storage, read_write> cell_start: array<u32>;
@group(0) @binding(8) var<storage, read_write> block_sums: array<u32>;
@group(0) @binding(9) var<storage, read_write> pc: array<vec2<u32>>;
// polymer bonds: [0, N] offsets, then (partner, d0 bits) pairs
@group(0) @binding(10) var<storage, read> poly: array<u32>;
// per structure: N + 1 absolute offsets into `hic`
@group(0) @binding(11) var<storage, read_write> hic_off: array<atomic<u32>>;
@group(0) @binding(12) var<storage, read_write> hic: array<u32>;
@group(0) @binding(13) var<storage, read_write> partial: array<vec4<f32>>;
// per structure 8 x vec4 (see MS_* below)
@group(0) @binding(14) var<storage, read_write> mstate: array<vec4<f32>>;
@group(0) @binding(15) var<storage, read_write> bpart: array<vec4<f32>>;
// per structure and bead: x0, g, h
@group(0) @binding(16) var<storage, read_write> cgv: array<vec4<f32>>;
// assignment rows: (bead a, bead b, d_act^2 bits, 0)
@group(0) @binding(17) var<storage, read> rows: array<vec4<u32>>;
// per structure 8 counters: hic imposed / violated, poly imposed / violated, env imposed / violated
@group(0) @binding(18) var<storage, read_write> stats: array<atomic<u32>>;
// per structure (whole population): Hi-C bond ends (2 per bond)
@group(0) @binding(19) var<storage, read_write> totals: array<atomic<u32>>;

const WG: u32 = 256u;
const BIG: f32 = 3.0e38;
const PI: f32 = 3.141592653589793;
const MS: u32 = 8u;
// mstate slots: 0 (kin, factor, step, inv_cell) 1 (origin, _) 2 (dims bits, ncell)
// 3 (e0, alpha, fdoth, gg) 4 (beta, status bits, neval bits, niter bits)
// 5 (e_start, _, _, op bits) 6 (mean v xyz, _) 7 (hic base bits, _, _, _)
const ST_ACTIVE: u32 = 0u;
const ST_DONE: u32 = 1u;
const OP_NONE: u32 = 0u;
const OP_ACCEPT: u32 = 1u;
const OP_RETRY: u32 = 2u;
const OP_RESTORE: u32 = 3u;
const OP_RESETH: u32 = 4u;

var<workgroup> sh: array<vec4<f32>, 256>;
var<workgroup> shu: array<u32, 256>;
var<workgroup> smin: array<vec3<f32>, 256>;
var<workgroup> smax: array<vec3<f32>, 256>;
var<workgroup> wflag: u32;
var<workgroup> wop: u32;

fn pcg(v: u32) -> u32 {
    let state = v * 747796405u + 2891336453u;
    let word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
    return (word >> 22u) ^ word;
}

fn rand01(k: u32) -> f32 {
    return (f32(pcg(k) >> 8u) + 0.5) / 16777216.0;
}

fn gidx(m: u32, i: u32) -> u32 {
    return (P.m_off + m) * P.n + i;
}

// Reduce v over the workgroup: components < nsum summed, the rest max'ed.
fn wg_reduce(v: vec4<f32>, lid: u32, nsum: u32) -> vec4<f32> {
    sh[lid] = v;
    workgroupBarrier();
    for (var s = 128u; s > 0u; s = s >> 1u) {
        if (lid < s) {
            let a = sh[lid];
            let b = sh[lid + s];
            var r = a + b;
            let mx = max(a, b);
            if (nsum <= 3u) { r.w = mx.w; }
            if (nsum <= 2u) { r.z = mx.z; }
            if (nsum <= 1u) { r.y = mx.y; }
            sh[lid] = r;
        }
        workgroupBarrier();
    }
    return sh[0];
}

fn write_partial(v: vec4<f32>, lid: u32, wgx: u32, m: u32, nsum: u32) {
    let r = wg_reduce(v, lid, nsum);
    if (lid == 0u) {
        partial[m * P.nb + wgx] = r;
    }
}

// Per-structure reduction of the partials (one workgroup per structure).
fn model_reduce(m: u32, lid: u32, nsum: u32) -> vec4<f32> {
    var acc = vec4<f32>(0.0);
    for (var k = lid; k < P.nb; k = k + WG) {
        let v = partial[m * P.nb + k];
        var r = acc + v;
        let mx = max(acc, v);
        if (nsum <= 3u) { r.w = mx.w; }
        if (nsum <= 2u) { r.z = mx.z; }
        if (nsum <= 1u) { r.y = mx.y; }
        acc = r;
    }
    return wg_reduce(acc, lid, nsum);
}

fn bbox_partials(x: vec3<f32>, valid: bool, lid: u32, wgx: u32, m: u32) {
    smin[lid] = select(vec3<f32>(BIG), x, valid);
    smax[lid] = select(vec3<f32>(-BIG), x, valid);
    workgroupBarrier();
    for (var s = 128u; s > 0u; s = s >> 1u) {
        if (lid < s) {
            smin[lid] = min(smin[lid], smin[lid + s]);
            smax[lid] = max(smax[lid], smax[lid + s]);
        }
        workgroupBarrier();
    }
    if (lid == 0u) {
        let k = m * P.nb + wgx;
        bpart[2u * k] = vec4<f32>(smin[0], 0.0);
        bpart[2u * k + 1u] = vec4<f32>(smax[0], 0.0);
    }
}

fn st_u(m: u32, slot: u32, c: u32) -> u32 {
    return bitcast<u32>(mstate[MS * m + slot][c]);
}

fn model_status(m: u32, lid: u32) -> u32 {
    if (lid == 0u) {
        wflag = st_u(m, 4u, 1u);
    }
    return workgroupUniformLoad(&wflag);
}

fn model_op(m: u32, lid: u32) -> u32 {
    if (lid == 0u) {
        wop = st_u(m, 5u, 3u);
    }
    return workgroupUniformLoad(&wop);
}

// ---------------------------------------------------------------- cell grid

@compute @workgroup_size(256)
fn bbox_part(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    let valid = i < P.n;
    var x = vec3<f32>(0.0);
    if (valid) {
        x = pos[gidx(m, i)].xyz;
    }
    bbox_partials(x, valid, l.x, wg.x, m);
}

@compute @workgroup_size(256)
fn grid_setup(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let lid = l.x;
    var lo = vec3<f32>(BIG);
    var hi = vec3<f32>(-BIG);
    for (var k = lid; k < P.nb; k = k + WG) {
        let q = m * P.nb + k;
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
        var cs = 2.0 * P.rmax / f32(P.stencil);
        var d = vec3<u32>(floor(ext / cs)) + vec3<u32>(1u);
        for (var it = 0u; it < 64u; it = it + 1u) {
            if (f32(d.x) * f32(d.y) * f32(d.z) <= f32(P.hc)) {
                break;
            }
            cs = cs * 1.26;
            d = vec3<u32>(floor(ext / cs)) + vec3<u32>(1u);
        }
        let b = MS * m;
        mstate[b].w = 1.0 / cs;
        mstate[b + 1u] = vec4<f32>(o, 0.0);
        mstate[b + 2u] = vec4<f32>(bitcast<f32>(d.x), bitcast<f32>(d.y), bitcast<f32>(d.z), bitcast<f32>(d.x * d.y * d.z));
    }
}

fn grid_dims(m: u32) -> vec3<u32> {
    let g = mstate[MS * m + 2u];
    return vec3<u32>(bitcast<u32>(g.x), bitcast<u32>(g.y), bitcast<u32>(g.z));
}

fn cell_coord(m: u32, p: vec3<f32>, d: vec3<u32>) -> vec3<u32> {
    let o = mstate[MS * m + 1u].xyz;
    let inv = mstate[MS * m].w;
    let c = max(floor((p - o) * inv), vec3<f32>(0.0));
    return min(vec3<u32>(c), d - vec3<u32>(1u));
}

fn cell_lin(c: vec3<u32>, d: vec3<u32>) -> u32 {
    return (c.z * d.y + c.y) * d.x + c.x;
}

@compute @workgroup_size(256)
fn cell_count_k(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    if (i < P.n) {
        let d = grid_dims(m);
        let c = cell_lin(cell_coord(m, pos[gidx(m, i)].xyz, d), d);
        let slot = atomicAdd(&cell_count[m * P.hc + c], 1u);
        pc[m * P.n + i] = vec2<u32>(c, slot);
    }
}

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
        let cs = pc[m * P.n + i];
        let idx = cell_begin(m, cs.x) + cs.y;
        spos[m * P.n + idx] = vec4<f32>(pos[gidx(m, i)].xyz, bitcast<f32>(i));
    }
}

// ---------------------------------------------------------------- forces

fn upper_bond(dv: vec3<f32>, d0: f32, k: f32) -> vec4<f32> {
    // dv = p_i - p_j; returns (force on i, energy)
    let r = length(dv);
    if (r <= d0 || r == 0.0) {
        return vec4<f32>(0.0);
    }
    let x = r - d0;
    return vec4<f32>(dv * (-2.0 * k * x / r), k * x * x);
}

// Force on bead i (xyz) and its energy share (w).
fn total_force(i: u32, m: u32, p: vec3<f32>) -> vec4<f32> {
    var f = vec3<f32>(0.0);
    var e = 0.0;
    let ri = rad[i];
    if (P.ev != 0.0) {
        let d = grid_dims(m);
        let c = vec3<i32>(cell_coord(m, p, d));
        let di = vec3<i32>(d);
        let st = i32(P.stencil);
        let sb = m * P.n;
        let x0 = u32(max(c.x - st, 0));
        let x1 = u32(min(c.x + st, di.x - 1));
        for (var z = max(c.z - st, 0); z <= min(c.z + st, di.z - 1); z = z + 1) {
            for (var y = max(c.y - st, 0); y <= min(c.y + st, di.y - 1); y = y + 1) {
                let row = (u32(z) * d.y + u32(y)) * d.x;
                let b = cell_begin(m, row + x0);
                let en = cell_begin(m, row + x1 + 1u);
                for (var t = b; t < en; t = t + 1u) {
                    let q4 = spos[sb + t];
                    let j = bitcast<u32>(q4.w);
                    let dv = p - q4.xyz;
                    let d2 = dot(dv, dv);
                    let rc = ri + rad[j];
                    if (j == i || d2 >= rc * rc) {
                        continue;
                    }
                    let a = P.ev * (rc / PI) * (rc / PI);
                    let r = sqrt(d2);
                    let arg = PI * r / rc;
                    if (r > 0.0) {
                        f = f + dv * (a * sin(arg) * PI / rc / r);
                    }
                    e = e + 0.5 * a * (1.0 + cos(arg));
                }
            }
        }
    }
    let gb = (P.m_off + m) * P.n;
    // polymer bonds
    let p0 = poly[i];
    let p1 = poly[i + 1u];
    for (var q = p0; q < p1; q = q + 1u) {
        let k = P.n + 1u + 2u * q;
        let j = poly[k];
        let d0 = bitcast<f32>(poly[k + 1u]);
        let r = upper_bond(p - pos[gb + j].xyz, d0, P.k_poly);
        f = f + r.xyz;
        e = e + 0.5 * r.w;
    }
    // Hi-C bonds of this structure
    let hb = m * (P.n + 1u);
    let h0 = atomicLoad(&hic_off[hb + i]);
    let h1 = atomicLoad(&hic_off[hb + i + 1u]);
    for (var q = h0; q < h1; q = q + 1u) {
        let j = hic[q];
        let d0 = P.contact_range * (ri + rad[j]);
        let r = upper_bond(p - pos[gb + j].xyz, d0, P.k_hic);
        f = f + r.xyz;
        e = e + 0.5 * r.w;
    }
    // ellipsoidal envelope
    let s = vec3<f32>(P.ax, P.ay, P.az) * P.env_scale - vec3<f32>(ri);
    let s2 = s * s;
    let k2 = dot(p * p, 1.0 / s2);
    if (k2 > 1.0) {
        let t = (1.0 - 1.0 / sqrt(k2)) * length(p);
        let g = p / s2;
        let gn = length(g);
        if (gn > 0.0) {
            f = f - g * (P.k_env * t / gn);
        }
        e = e + 0.5 * P.k_env * t * t;
    }
    return vec4<f32>(f, e);
}

fn limit_v(v: vec3<f32>) -> vec3<f32> {
    let s = dot(v, v);
    if (s > P.vlim2) {
        return v * sqrt(P.vlim2 / s);
    }
    return v;
}

// Forces only (start of a run); walks particles in cell order.
@compute @workgroup_size(256)
fn force_only(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let t = wg.x * WG + l.x;
    let m = wg.y;
    if (t < P.n) {
        let q4 = spos[m * P.n + t];
        let i = bitcast<u32>(q4.w);
        let fe = total_force(i, m, q4.xyz);
        frc[m * P.n + i] = vec4<f32>(fe.xyz, 0.0);
    }
}

// ---------------------------------------------------------------- velocities

// LAMMPS velocity create (dist uniform): components uniform in [-1/2, 1/2).
@compute @workgroup_size(256)
fn vel_create(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    var v = vec3<f32>(0.0);
    if (i < P.n) {
        let s = P.m_off + m;
        let base = pcg(P.seed_lo ^ pcg(P.seed_hi ^ pcg(P.stream ^ pcg(s ^ pcg(i)))));
        v = vec3<f32>(rand01(base ^ 0x68e31da4u), rand01(base ^ 0xb5297a4du), rand01(base ^ 0x1b56c4e9u)) - vec3<f32>(0.5);
        vel[m * P.n + i] = vec4<f32>(v, 0.0);
    }
    write_partial(vec4<f32>(v, 0.0), l.x, wg.x, m, 4u);
}

@compute @workgroup_size(256)
fn vel_mean(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let r = model_reduce(m, l.x, 4u);
    if (l.x == 0u) {
        mstate[MS * m + 6u] = vec4<f32>(r.xyz / f32(P.n), 0.0);
    }
}

@compute @workgroup_size(256)
fn vel_center(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    var s = 0.0;
    if (i < P.n) {
        let k = m * P.n + i;
        let v = vel[k].xyz - mstate[MS * m + 6u].xyz;
        vel[k] = vec4<f32>(v, 0.0);
        s = dot(v, v);
    }
    write_partial(vec4<f32>(s, 0.0, 0.0, 0.0), l.x, wg.x, m, 4u);
}

// Scale factor to t_create (applied by the next integrate1); resets the step counter.
@compute @workgroup_size(256)
fn vel_scale_set(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let r = model_reduce(m, l.x, 4u);
    if (l.x == 0u) {
        let t = r.x / P.dof;
        var sc = 0.0;
        if (t > 0.0) {
            sc = sqrt(P.t_create / t);
        }
        let b = MS * m;
        mstate[b] = vec4<f32>(0.0, sc, 0.0, mstate[b].w);
    }
}

// Velocities uploaded by the host (tests): factor 1, step 0.
@compute @workgroup_size(256)
fn vel_given(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    if (l.x == 0u) {
        let b = MS * m;
        mstate[b] = vec4<f32>(0.0, 1.0, 0.0, mstate[b].w);
    }
}

// ---------------------------------------------------------------- MD

@compute @workgroup_size(256)
fn integrate1(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    let valid = i < P.n;
    var x = vec3<f32>(0.0);
    if (valid) {
        let k = m * P.n + i;
        let g = gidx(m, i);
        let fct = mstate[MS * m].y;
        var v = vel[k].xyz * fct;
        v = limit_v(v + P.half_dt * frc[k].xyz);
        x = pos[g].xyz + P.dt * v;
        pos[g] = vec4<f32>(x, 0.0);
        vel[k] = vec4<f32>(v, 0.0);
    }
    bbox_partials(x, valid, l.x, wg.x, m);
}

@compute @workgroup_size(256)
fn force_int2(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let t = wg.x * WG + l.x;
    let m = wg.y;
    var s = 0.0;
    if (t < P.n) {
        let q4 = spos[m * P.n + t];
        let i = bitcast<u32>(q4.w);
        let k = m * P.n + i;
        let f = total_force(i, m, q4.xyz).xyz;
        frc[k] = vec4<f32>(f, 0.0);
        let v = limit_v(vel[k].xyz + P.half_dt * f);
        vel[k] = vec4<f32>(v, 0.0);
        s = dot(v, v);
    }
    write_partial(vec4<f32>(s, 0.0, 0.0, 0.0), l.x, wg.x, m, 4u);
}

// fix temp/rescale (every step): target ramps t0 -> t1 over the run.
@compute @workgroup_size(256)
fn temp_rescale(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let r = model_reduce(m, l.x, 4u);
    if (l.x == 0u) {
        let b = MS * m;
        let step = mstate[b].z + 1.0;
        let t = r.x / P.dof;
        let tgt = P.t0 + (step / P.nsteps) * (P.t1 - P.t0);
        var fct = 1.0;
        if (t > 0.0 && abs(t - tgt) > P.window) {
            let tt = t - P.fraction * (t - tgt);
            fct = sqrt(max(tt, 0.0) / t);
        }
        mstate[b] = vec4<f32>(r.x, fct, step, mstate[b].w);
    }
}

// Apply the pending rescale factor (end of a run; tests read velocities).
@compute @workgroup_size(256)
fn vel_apply(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    if (i < P.n) {
        let k = m * P.n + i;
        vel[k] = vec4<f32>(vel[k].xyz * mstate[MS * m].y, 0.0);
    }
}

// ---------------------------------------------------------------- CG
// Polak-Ribiere with backtracking (LAMMPS min cg, linestyle backtrack), one
// state machine per structure; every kernel skips finished structures.

@compute @workgroup_size(256)
fn cg_force(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let t = wg.x * WG + l.x;
    let m = wg.y;
    if (model_status(m, l.x) != ST_ACTIVE) {
        return;
    }
    var v = vec4<f32>(0.0);
    if (t < P.n) {
        let q4 = spos[m * P.n + t];
        let i = bitcast<u32>(q4.w);
        let k = m * P.n + i;
        let fe = total_force(i, m, q4.xyz);
        frc[k] = vec4<f32>(fe.xyz, 0.0);
        let g = cgv[3u * k + 1u].xyz;
        v = vec4<f32>(fe.w, dot(fe.xyz, fe.xyz), dot(fe.xyz, g), 0.0);
    }
    write_partial(v, l.x, wg.x, m, 4u);
}

// Before a minimisation: every structure active.
@compute @workgroup_size(256)
fn cg_prep(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    if (l.x == 0u) {
        let b = MS * m;
        mstate[b + 4u] = vec4<f32>(0.0, bitcast<f32>(ST_ACTIVE), bitcast<f32>(0u), bitcast<f32>(0u));
        mstate[b + 5u] = vec4<f32>(0.0, 0.0, 0.0, bitcast<f32>(OP_NONE));
    }
}

// After the first cg_force: e0, gg; op = ACCEPT so cg_dir sets up the line search.
@compute @workgroup_size(256)
fn cg_init_model(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let r = model_reduce(m, l.x, 4u);
    if (l.x == 0u) {
        let b = MS * m;
        mstate[b + 3u] = vec4<f32>(r.x, 0.0, 0.0, r.y);
        mstate[b + 4u] = vec4<f32>(0.0, bitcast<f32>(ST_ACTIVE), bitcast<f32>(1u), bitcast<f32>(0u));
        mstate[b + 5u] = vec4<f32>(r.x, r.x, 0.0, bitcast<f32>(OP_ACCEPT));
    }
}

@compute @workgroup_size(256)
fn cg_init_part(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    var v = vec4<f32>(0.0);
    if (i < P.n) {
        let k = m * P.n + i;
        let f = frc[k].xyz;
        cgv[3u * k] = pos[gidx(m, i)];
        cgv[3u * k + 1u] = vec4<f32>(f, 0.0);
        cgv[3u * k + 2u] = vec4<f32>(f, 0.0);
        let af = abs(f);
        v = vec4<f32>(dot(f, f), 0.0, max(af.x, max(af.y, af.z)), max(af.x, max(af.y, af.z)));
    }
    write_partial(v, l.x, wg.x, m, 2u);
}

// Trial point x = x0 + alpha h (+ bounding box).
@compute @workgroup_size(256)
fn cg_trial(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    let is_active = model_status(m, l.x) == ST_ACTIVE;
    let op = model_op(m, l.x);
    let valid = i < P.n;
    var x = vec3<f32>(0.0);
    if (valid) {
        let g = gidx(m, i);
        if (is_active) {
            let k = m * P.n + i;
            var h = cgv[3u * k + 2u].xyz;
            if (op == OP_RESETH) {
                h = cgv[3u * k + 1u].xyz;
                cgv[3u * k + 2u] = vec4<f32>(h, 0.0);
            }
            let alpha = mstate[MS * m + 3u].y;
            x = cgv[3u * k].xyz + alpha * h;
            pos[g] = vec4<f32>(x, 0.0);
        } else {
            x = pos[g].xyz;
        }
    }
    bbox_partials(x, valid, l.x, wg.x, m);
}

// Armijo test and the next operation.
@compute @workgroup_size(256)
fn cg_decide(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    if (model_status(m, l.x) != ST_ACTIVE) {
        return;
    }
    let r = model_reduce(m, l.x, 4u);
    if (l.x == 0u) {
        let b = MS * m;
        var c = mstate[b + 3u];   // e0, alpha, fdoth, gg
        var s4 = mstate[b + 4u];  // beta, status, neval, niter
        var s5 = mstate[b + 5u];
        let e = r.x;
        let neval = bitcast<u32>(s4.z) + 1u;
        var niter = bitcast<u32>(s4.w);
        var status = ST_ACTIVE;
        var op = OP_NONE;
        let de_ideal = -0.4 * c.y * c.z;
        if (e - c.x <= de_ideal) {
            niter = niter + 1u;
            let conv_e = abs(e - c.x) < P.etol * 0.5 * (abs(e) + abs(c.x) + 1e-8);
            let dot0 = r.y;
            let dot1 = r.z;
            c.x = e;
            if (conv_e || dot0 < P.ftol * P.ftol || neval >= P.max_eval || niter >= P.max_iter) {
                status = ST_DONE;
            } else {
                var beta = max(0.0, (dot0 - dot1) / c.w);
                if (niter % (3u * P.n) == 0u) {
                    beta = 0.0;
                }
                s4.x = beta;
                c.w = dot0;
                op = OP_ACCEPT;
            }
            s5.y = e;
        } else {
            c.y = c.y * 0.5;
            if (c.y <= 0.0 || de_ideal >= -1e-8 || neval >= P.max_eval) {
                status = ST_DONE;
                op = OP_RESTORE;
            } else {
                op = OP_RETRY;
            }
        }
        mstate[b + 3u] = c;
        mstate[b + 4u] = vec4<f32>(s4.x, bitcast<f32>(status), bitcast<f32>(neval), bitcast<f32>(niter));
        mstate[b + 5u] = vec4<f32>(s5.x, s5.y, s5.z, bitcast<f32>(op));
    }
}

// New direction after an accepted step, or restore x0 after a failed search.
@compute @workgroup_size(256)
fn cg_update(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    let op = model_op(m, l.x);
    var v = vec4<f32>(0.0);
    if (i < P.n) {
        let k = m * P.n + i;
        let g = gidx(m, i);
        if (op == OP_ACCEPT) {
            let f = frc[k].xyz;
            let beta = mstate[MS * m + 4u].x;
            let h = f + beta * cgv[3u * k + 2u].xyz;
            cgv[3u * k] = pos[g];
            cgv[3u * k + 1u] = vec4<f32>(f, 0.0);
            cgv[3u * k + 2u] = vec4<f32>(h, 0.0);
            let ah = abs(h);
            let af = abs(f);
            v = vec4<f32>(dot(h, f), 0.0, max(ah.x, max(ah.y, ah.z)), max(af.x, max(af.y, af.z)));
        } else if (op == OP_RESTORE) {
            pos[g] = cgv[3u * k];
        }
    }
    write_partial(v, l.x, wg.x, m, 2u);
}

// Line-search setup: fdoth, alpha = min(1, dmax / max|h|); h = g if not downhill.
@compute @workgroup_size(256)
fn cg_dir(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let op = model_op(m, l.x);
    if (op != OP_ACCEPT) {
        return;
    }
    let r = model_reduce(m, l.x, 2u);
    if (l.x == 0u) {
        let b = MS * m;
        var c = mstate[b + 3u];
        var s5 = mstate[b + 5u];
        var fdoth = r.x;
        var hmax = r.z;
        var nop = OP_NONE;
        if (fdoth <= 0.0) {
            fdoth = c.w;
            hmax = r.w;
            nop = OP_RESETH;
        }
        if (hmax <= 0.0 || fdoth <= 0.0) {
            var s4 = mstate[b + 4u];
            s4.y = bitcast<f32>(ST_DONE);
            mstate[b + 4u] = s4;
        }
        c.y = min(1.0, P.dmax / max(hmax, 1e-30));
        c.z = fdoth;
        mstate[b + 3u] = c;
        s5.w = bitcast<f32>(nop);
        mstate[b + 5u] = s5;
    }
}

// ---------------------------------------------------------------- A-step assignment

fn row_in(m: u32, r: vec4<u32>) -> bool {
    let gb = (P.m_off + m) * P.n;
    let dv = pos[gb + r.x].xyz - pos[gb + r.y].xyz;
    return dot(dv, dv) <= bitcast<f32>(r.z);
}

// Pre-pass over the whole population (bm = S, m_off = 0): bond ends per structure.
@compute @workgroup_size(256)
fn assign_total(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
    let m = wg.y;
    var c = 0u;
    for (var q = wg.x * WG + l.x; q < P.n_rows; q = q + nw.x * WG) {
        if (row_in(m, rows[q])) {
            c = c + 2u;
        }
    }
    shu[l.x] = c;
    workgroupBarrier();
    for (var s = 128u; s > 0u; s = s >> 1u) {
        if (l.x < s) {
            shu[l.x] = shu[l.x] + shu[l.x + s];
        }
        workgroupBarrier();
    }
    if (l.x == 0u && shu[0] > 0u) {
        atomicAdd(&totals[P.m_off + m], shu[0]);
    }
}

// Count bond ends per bead (cursor array = cell_count, zero on entry).
@compute @workgroup_size(256)
fn assign_count(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
    let m = wg.y;
    for (var q = wg.x * WG + l.x; q < P.n_rows; q = q + nw.x * WG) {
        let r = rows[q];
        if (row_in(m, r)) {
            atomicAdd(&cell_count[m * P.hc + r.x], 1u);
            atomicAdd(&cell_count[m * P.hc + r.y], 1u);
        }
    }
}

// Exclusive scan of the counts of one structure into hic_off (+ base); cursor := offset.
@compute @workgroup_size(256)
fn assign_scan(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let m = wg.y;
    let base = bitcast<u32>(mstate[MS * m + 7u].x);
    var carry = 0u;
    let hb = m * (P.n + 1u);
    for (var c0 = 0u; c0 < P.n; c0 = c0 + WG) {
        let i = c0 + l.x;
        var v = 0u;
        if (i < P.n) {
            v = atomicLoad(&cell_count[m * P.hc + i]);
        }
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
        if (i < P.n) {
            let o = base + carry + shu[l.x] - v;
            atomicStore(&hic_off[hb + i], o);
            atomicStore(&cell_count[m * P.hc + i], o);
        }
        let tot = shu[WG - 1u];
        workgroupBarrier();
        carry = carry + tot;
    }
    if (l.x == 0u) {
        atomicStore(&hic_off[hb + P.n], base + carry);
    }
}

@compute @workgroup_size(256)
fn assign_fill(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
    let m = wg.y;
    for (var q = wg.x * WG + l.x; q < P.n_rows; q = q + nw.x * WG) {
        let r = rows[q];
        if (row_in(m, r)) {
            let sa = atomicAdd(&cell_count[m * P.hc + r.x], 1u);
            hic[sa] = r.y;
            let sb = atomicAdd(&cell_count[m * P.hc + r.y], 1u);
            hic[sb] = r.x;
        }
    }
}

// Zero the cursors (cell_count must be zero for the cell grid).
@compute @workgroup_size(256)
fn assign_clear(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    if (i < P.n) {
        atomicStore(&cell_count[m * P.hc + i], 0u);
    }
}

// ---------------------------------------------------------------- violations

@compute @workgroup_size(256)
fn violations_k(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let i = wg.x * WG + l.x;
    let m = wg.y;
    if (i >= P.n) {
        return;
    }
    let gb = (P.m_off + m) * P.n;
    let p = pos[gb + i].xyz;
    let ri = rad[i];
    var c = array<u32, 6>(0u, 0u, 0u, 0u, 0u, 0u);
    let p0 = poly[i];
    let p1 = poly[i + 1u];
    for (var q = p0; q < p1; q = q + 1u) {
        let k = P.n + 1u + 2u * q;
        let j = poly[k];
        if (j > i) {
            let d0 = bitcast<f32>(poly[k + 1u]);
            c[2] = c[2] + 1u;
            if ((length(p - pos[gb + j].xyz) - d0) / d0 > P.tol) {
                c[3] = c[3] + 1u;
            }
        }
    }
    let hb = m * (P.n + 1u);
    let h0 = atomicLoad(&hic_off[hb + i]);
    let h1 = atomicLoad(&hic_off[hb + i + 1u]);
    for (var q = h0; q < h1; q = q + 1u) {
        let j = hic[q];
        if (j > i) {
            let d0 = P.contact_range * (ri + rad[j]);
            c[0] = c[0] + 1u;
            if ((length(p - pos[gb + j].xyz) - d0) / d0 > P.tol) {
                c[1] = c[1] + 1u;
            }
        }
    }
    c[4] = 1u;
    let s = vec3<f32>(P.ax, P.ay, P.az) - vec3<f32>(ri);
    let k2 = dot(p * p, 1.0 / (s * s));
    if (k2 > 1.0) {
        let t = (1.0 - 1.0 / sqrt(k2)) * length(p);
        if (t / (P.k_env * 0.1 * P.rbar) > P.tol) {
            c[5] = 1u;
        }
    }
    for (var k = 0u; k < 6u; k = k + 1u) {
        if (c[k] > 0u) {
            atomicAdd(&stats[8u * m + k], c[k]);
        }
    }
}
