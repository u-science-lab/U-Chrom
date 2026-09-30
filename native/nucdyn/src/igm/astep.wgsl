// IGM A-step on the GPU: per candidate pair, over the whole population,
// (1) the number of copy-combination distances within the contact
// distance, (2) the exact order statistic of rank o of the squared
// distances (radix select on the f32 bit patterns, 4 passes of 8 bits; the
// squares are non-negative so their bit patterns sort like the values).
// One workgroup per pair; pairs are laid out over (x, y) workgroup ids.

struct AParams {
    n_pairs: u32,
    s: u32,        // structures
    n: u32,        // beads per structure
    gx: u32,       // workgroups along x
};

// per pair: (first combination, combinations, rc^2 bits (count) / rank (select), 0)
struct Pair {
    c0: u32,
    nc: u32,
    val: u32,
    pad: u32,
};

@group(0) @binding(0) var<uniform> A: AParams;
@group(0) @binding(1) var<storage, read> pos: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> pairs: array<Pair>;
@group(0) @binding(3) var<storage, read> combos: array<vec2<u32>>;
@group(0) @binding(4) var<storage, read_write> result: array<u32>;

const WG: u32 = 256u;

var<workgroup> hist: array<atomic<u32>, 256>;
var<workgroup> cnt: atomic<u32>;
var<workgroup> sel: vec3<u32>; // prefix, mask, remaining rank

fn d2_of(c: vec2<u32>, s: u32) -> f32 {
    let dv = pos[s * A.n + c.x].xyz - pos[s * A.n + c.y].xyz;
    return dot(dv, dv);
}

@compute @workgroup_size(256)
fn ad_count(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let pi = wg.y * A.gx + wg.x;
    if (l.x == 0u) {
        atomicStore(&cnt, 0u);
    }
    workgroupBarrier();
    let valid = pi < A.n_pairs;
    var pr = Pair(0u, 0u, 0u, 0u);
    if (valid) {
        pr = pairs[pi];
    }
    let rc2 = bitcast<f32>(pr.val);
    let total = pr.nc * A.s;
    var c = 0u;
    for (var q = l.x; q < total; q = q + WG) {
        let cb = combos[pr.c0 + q / A.s];
        if (d2_of(cb, q % A.s) <= rc2) {
            c = c + 1u;
        }
    }
    if (c > 0u) {
        atomicAdd(&cnt, c);
    }
    workgroupBarrier();
    if (l.x == 0u && valid) {
        result[pi] = atomicLoad(&cnt);
    }
}

@compute @workgroup_size(256)
fn ad_select(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_id) l: vec3<u32>) {
    let pi = wg.y * A.gx + wg.x;
    let valid = pi < A.n_pairs;
    var pr = Pair(0u, 0u, 0u, 0u);
    if (valid) {
        pr = pairs[pi];
    }
    let total = pr.nc * A.s;
    if (l.x == 0u) {
        sel = vec3<u32>(0u, 0u, pr.val);
    }
    for (var ps = 0u; ps < 4u; ps = ps + 1u) {
        let shift = 24u - 8u * ps;
        atomicStore(&hist[l.x], 0u);
        let st = workgroupUniformLoad(&sel);
        for (var q = l.x; q < total; q = q + WG) {
            let cb = combos[pr.c0 + q / A.s];
            let v = bitcast<u32>(d2_of(cb, q % A.s));
            if ((v & st.y) == st.x) {
                atomicAdd(&hist[(v >> shift) & 255u], 1u);
            }
        }
        workgroupBarrier();
        if (l.x == 0u) {
            var k = st.z;
            var b = 0u;
            for (; b < 255u; b = b + 1u) {
                let h = atomicLoad(&hist[b]);
                if (k < h) {
                    break;
                }
                k = k - h;
            }
            sel = vec3<u32>(st.x | (b << shift), st.y | (255u << shift), k);
        }
        workgroupBarrier();
    }
    let fin = workgroupUniformLoad(&sel);
    if (l.x == 0u && valid) {
        result[pi] = fin.x;
    }
}
