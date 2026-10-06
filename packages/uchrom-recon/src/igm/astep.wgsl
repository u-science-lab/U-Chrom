// IGM A-step on the GPU: per candidate pair, over the whole population,
// (1) the number of copy-combination distances within the contact
// distance, (2) the exact order statistic of rank o of the squared
// distances (radix select on the f32 bit patterns, 4 passes of 8 bits; the
// squares are non-negative so their bit patterns sort like the values).
// One workgroup per pair; pairs are laid out over (x, y) workgroup ids.
//
// GP pooling (pad = n_possible > 0; alberlab/IGM_2.0 GP_ActivationDistanceStep):
// the values are, per structure, the n_possible smallest of the nc
// combination distances (item q: structure q % S, order q / S).

struct AParams {
    n_pairs: u32,
    s: u32,        // structures
    n: u32,        // beads per structure
    gx: u32,       // workgroups along x
};

// per pair: (first combination, combinations, rc^2 bits (count) / rank (select),
// n_possible per structure for GP pooling, 0 = every combination)
struct Pair {
    c0: u32,
    nc: u32,
    val: u32,
    pad: u32,
};

const GP_MAX: u32 = 16u;

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

// Number of values of a pair.
fn n_items(pr: Pair) -> u32 {
    if (pr.pad == 0u) {
        return pr.nc * A.s;
    }
    return pr.pad * A.s;
}

// Value q of a pair: IGM, combination q / S in structure q % S; GP, the
// (q / S)-th smallest combination distance of structure q % S (ties by index).
fn item(pr: Pair, q: u32) -> f32 {
    if (pr.pad == 0u) {
        return d2_of(combos[pr.c0 + q / A.s], q % A.s);
    }
    let s = q % A.s;
    let r = q / A.s;
    let nc = min(pr.nc, GP_MAX);
    var d: array<f32, 16>;
    for (var c = 0u; c < nc; c = c + 1u) {
        d[c] = d2_of(combos[pr.c0 + c], s);
    }
    for (var c = 0u; c < nc; c = c + 1u) {
        var rank = 0u;
        for (var m = 0u; m < nc; m = m + 1u) {
            if (d[m] < d[c] || (d[m] == d[c] && m < c)) {
                rank = rank + 1u;
            }
        }
        if (rank == r) {
            return d[c];
        }
    }
    return d[0];
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
    let total = n_items(pr);
    var c = 0u;
    for (var q = l.x; q < total; q = q + WG) {
        if (item(pr, q) <= rc2) {
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
    let total = n_items(pr);
    if (l.x == 0u) {
        sel = vec3<u32>(0u, 0u, pr.val);
    }
    for (var ps = 0u; ps < 4u; ps = ps + 1u) {
        let shift = 24u - 8u * ps;
        atomicStore(&hist[l.x], 0u);
        let st = workgroupUniformLoad(&sel);
        for (var q = l.x; q < total; q = q + WG) {
            let v = bitcast<u32>(item(pr, q));
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
