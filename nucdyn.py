from copy import copy
import fire
import gzip
import io
import pandas as pd
import taichi as ti
import numpy as np


def open_file(path, mode="r"):
    if path.endswith(".gz"):
        mode += "b"
        return io.TextIOWrapper(gzip.open(path, mode))
    return open(path, mode)


def read_pairs(path):
    assert path.endswith(".pairs") or path.endswith(".pairs.gz")
    with open_file(path) as f:
        df = pd.read_csv(f, sep="\t", header=None)
    df.columns = ["read", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    return df


def create_praticles(df, praticle_size, prev_praticles=None, random_seed=0, max_radius=10):
    np.random.seed(random_seed)
    chroms = sorted(set(df['chr1'].unique()) | \
                    set(df['chr2'].unique()))
    praticles = {}
    for chr in chroms:
        min_ = df[df['chr1'] == chr]['pos1'].min()
        max_ = df[df['chr2'] == chr]['pos2'].max()
        if any([np.isnan(i) for i in (min_, max_)]):
            continue
        n_praticle = (max_ - min_) // praticle_size
        space = np.linspace(min_, max_, n_praticle+1)
        starts, ends = [s.astype(np.int64) for s in [space[:-1], space[1:]]]
        pos = {}
        if prev_praticles is None:
            # generate random positions inside a sphere
            radius = np.random.randn(n_praticle) * max_radius
            theta, phi = [np.random.randn(n_praticle) * (2 * np.pi) for _ in range(2)]
            pos['x'] = radius * np.cos(theta) * np.sin(phi)
            pos['y'] = radius * np.sin(theta) * np.cos(phi)
            pos['z'] = radius * np.cos(phi)
        else:
            # generate positions with interpolation
            prev = prev_praticles[prev_praticles['chrom'] == chr]
            xp = np.concatenate([
                [0], (prev['start'] + prev['end']) / 2, [prev['end'].iloc[-1] + praticle_size / 2],
            ])
            for _d in ['x', 'y', 'z']:
                _p_d = prev[_d]
                diff_1 = _p_d.iloc[0]  - _p_d.iloc[1]
                diff_2 = _p_d.iloc[-1] - _p_d.iloc[-2]
                fp = np.concatenate([[_p_d.iloc[0] + diff_1/2], _p_d, [_p_d.iloc[-1] + diff_2/2]])
                pos[_d] = np.interp((starts + ends)/2, xp, fp)
        p_df = pd.DataFrame({
            "chrom": chr,
            "start": starts,
            "end": ends,
            "x": pos['x'],
            "y": pos['y'],
            "z": pos['z']
        })
        praticles[chr] = p_df
    praticles = pd.concat(praticles.values()).reset_index()
    return praticles



def count_contacts(df, praticles):
    """Count contacts between all praticles."""
    contacts = {}
    chroms = set(praticles['chrom'].unique())
    for (chr1, chr2), sub_df in df.groupby(by=['chr1', 'chr2']):
        if any([c not in chroms for c in (chr1, chr2)]):
            continue
        idxs = []
        for (c, p) in [(chr1, 'pos1'), (chr2, 'pos2')]:
            sub_prat = praticles[praticles['chrom'] == c]
            ix = np.searchsorted(sub_prat['start'], sub_df[p], side='right') - 1
            idxs.append(sub_prat.iloc[ix,:].index)
        idx_pair = np.sort(np.c_[idxs[0], idxs[1]], axis=0)
        pair, cnt = np.unique(idx_pair, axis=0, return_counts=True)
        count = np.c_[pair, cnt]
        count = pd.DataFrame({
            "chr1": chr1,
            "chr2": chr2,
            "praticle_1": pair[:, 0],
            "praticle_2": pair[:, 1],
            "count": cnt,
        })
        if chr1 == chr2:
            count = count[count['praticle_1'] != count['praticle_2']]
            count = count[(count['praticle_2'] - count['praticle_1']) > 1]
        contacts[(chr1, chr2)] = count
    contacts = pd.concat(contacts.values()).reset_index(drop=True)
    return contacts


def get_restraints(praticles, contacts, prams, scale=1.0):
    chroms = set(praticles['chrom'].unique())
    restraints = []
    # backbone restraints
    for chr in chroms:
        sub_df = praticles[praticles['chrom'] == chr]
        if sub_df.shape[0] < 3: # skip short chrom
            continue
        a = sub_df[:-1].index.values
        b = sub_df[1:].index.values
        restraints.append(pd.DataFrame({
            'a': a,
            'b': b,
            'type': 0,
            'd_min': prams['bb_lower'],
            'd_max': prams['bb_upper'],
        }))
    # contact restraints
    d_target = (contacts['count'] * scale) ** prams['pow']
    d_lower = d_target * prams['lower']
    d_upper = d_target * prams['upper']
    restraints.append(pd.DataFrame({
        'a': contacts['praticle_1'],
        'b': contacts['praticle_2'],
        'type': 1,
        'd_min': d_lower,
        'd_max': d_upper,
    }))
    restraints = pd.concat(restraints)
    return restraints


default_prams = {
    "bb_lower": 0.1,
    "bb_upper": 1.1, 
    "lower": 0.8,
    "upper": 1.2,
    "pow": -0.33,
    "hot": 5000.0,
    "cold": 10.0,
    "temp_steps": 500,
    "dyns": 100,
    "random_seed": 0,
    "time_step": 0.001,
    "size_steps": [8, 4, 2, 0.4, 0.2, 0.1],
}


@ti.kernel
def get_repulsive_force(force: ti.template(), pos: ti.template(), k1: ti.f32) -> ti.f32:
    total = 0.0
    d_lim = 2.0
    for i in range(0, pos.shape[0]-2):
        for j in range(i+2, pos.shape[0]):
            pos_i = pos[i]
            pos_j = pos[j]
            diff = pos_j - pos_i
            dist = diff.norm()
            if dist > d_lim:
                continue
            d = dist - d_lim
            f = k1*d**2
            total += f
            for k in ti.static(range(3)):
                f_ = f * diff[k]
                force[i][k] += -f_
                force[j][k] += f_
    return total


@ti.kernel
def get_restraint_force(
        force: ti.template(), pos: ti.template(),
        rest_idx: ti.template(), rest_dist: ti.template(),
        ) -> ti.f32:
    total = 0.0
    k2 = 25.0
    dist_switch = 0.5
    asymptote = 1.0
    exponent = 2.0

    B = asymptote*(dist_switch**2) - exponent*(dist_switch**3)
    A = dist_switch**2 - asymptote*dist_switch - B/dist_switch

    for i in rest_idx:
        a, b, tp = rest_idx[i]
        d_min, d_max = rest_dist[i]
        pos_a = pos[a]
        pos_b = pos[b]
        diff = pos_b - pos_a
        dist = diff.norm()
        f = 0.0
        if dist < d_min:
            d = d_min - dist
            f = k2 * 2 * d
            total += k2 * d * d
        elif dist > d_max:
            d = dist - d_max
            if dist <= d_max + dist_switch:
                f = - k2 * 2 * d
                total += k2 * d * d
            else:
                f = - k2 * (A + asymptote*d + B/(d**2))
                total += k2 * (A + asymptote*d + B/d)
        else:
            continue
        for j in ti.static(range(3)):
            f_ = diff[j] * f / dist
            force[a][j] += -f_
            force[b][j] += f_
    return total


@ti.kernel
def get_rmsd(
        pos: ti.template(), rest_idx: ti.template(), rest_dist: ti.template(),
        rmsd_backbone: ti.template(), rmsd_contact: ti.template()) -> ti.f32:
    total = 0.0
    backbone = 0.0
    contact = 0.0
    for i in rest_idx:
        a, b, tp = rest_idx[i]
        d_min, d_max = rest_dist[i]
        pos_a = pos[a]
        pos_b = pos[b]
        diff = pos_b - pos_a
        dist = diff.norm()
        viol = 0.0
        if dist < d_min:
            viol = d_min - dist
        elif dist > d_max:
            viol = dist - d_max
        else:
            continue
        sq = viol * viol
        if tp == 0:
            backbone += sq
        else:
            contact += sq
        total += sq
    rmsd_backbone[None] = ti.sqrt(backbone/rest_idx.shape[0])
    rmsd_contact[None] = ti.sqrt(contact/rest_idx.shape[0])
    return ti.sqrt(total/rest_idx.shape[0])


@ti.func
def get_temp(vel):
    kin = 0.0
    BOLTZMANN_K = 0.0019872041
    n = vel.shape[0]
    for i in range(0, n):
        v = vel[i]
        kin += v.norm()
    return kin / (3 * n * BOLTZMANN_K)


@ti.kernel
def update_motion(
        pos: ti.template(), force: ti.template(),
        vel: ti.template(), accel: ti.template(),
        time_step: ti.f32, temp_ref: ti.f32) -> ti.f32:
    rt_step = 0.5 * time_step**2
    temp = get_temp(vel)
    temp = max(temp, 0.001)
    beta = 10.0 / 20.458
    r = beta * (temp_ref/temp - 1.0)
    #print(force[0], force[1])
    #print(vel[0], vel[1])
    #print(pos[0], pos[1])
    #print((pos[1] - pos[0]).norm())
    for i in range(force.shape[0]):
        for j in ti.static(range(3)):
            a = force[i][j] + r * vel[i][j]
            pos[i][j] += time_step * vel[i][j] + rt_step * a
            vel[i][j] += time_step * a
            accel[i][j] = a
            force[i][j] = 0.0
    return temp


@ti.kernel
def update_vel(force: ti.template(), vel: ti.template(), accel: ti.template(), time_step: ti.f32, temp_ref: ti.f32) -> ti.f32:
    temp = get_temp(vel)
    temp = max(temp, 0.001)
    beta = 10.0 / 20.458
    r = beta * (temp_ref/temp - 1.0)
    for i in range(force.shape[0]):
        for j in ti.static(range(3)):
            vel[i][j] += 0.5 + time_step * (force[i][j] + r * vel[i][j] - accel[i][j])
    return temp


def run_dyn(praticle_size, praticles, restraints, prams):
    # init fields
    pos = ti.Vector.field(3, ti.f32)
    vel = ti.Vector.field(3, ti.f32)
    force = ti.Vector.field(3, ti.f32)
    accel = ti.Vector.field(3, ti.f32)
    ti.root.dense(ti.i, praticles.shape[0]).place(pos, force, vel, accel)
    rest_idx = ti.Vector.field(3, ti.i32)
    rest_dist = ti.Vector.field(2, ti.f32)
    ti.root.dense(ti.i, restraints.shape[0]).place(rest_idx, rest_dist)
    pos.from_numpy(praticles[['x', 'y', 'z']].values)
    rest_idx.from_numpy(restraints[['a', 'b', 'type']].values)
    rest_dist.from_numpy(restraints[['d_min', 'd_max']].values)
    # count value
    rmsd_backbone = ti.field(ti.f32, shape=())
    rmsd_contact = ti.field(ti.f32, shape=())
    # setup annealing schedule
    num_steps = prams['dyns']
    temp_start = prams['hot']
    temp_end = prams['cold']
    adj = 1.0 / np.arctan(10)
    decay = np.log(temp_start / temp_end)
    schedule = []
    for step in range(num_steps):
        r = step / num_steps
        k1 = float(0.5 + adj * np.arctan(r * 20.0 - 10.0) / np.pi)
        temp = temp_start * np.exp(-decay * r)
        schedule.append((temp, k1))
        c_temp = update_motion(pos, force, vel, accel, prams['time_step'], temp)
        t_rep = get_repulsive_force(force, pos, k1)
        t_res = get_restraint_force(force, pos, rest_idx, rest_dist)
        c_temp = update_vel(force, vel, accel, prams['time_step'], temp)
        rmsd = get_rmsd(pos, rest_idx, rest_dist, rmsd_backbone, rmsd_contact)
        print(f"temp:{temp} c_temp:{c_temp} k1:{k1} total_force:{t_rep+t_res} repulsive:{t_rep} restraint:{t_res} rmsd:{rmsd} rmsd_backbone:{rmsd_backbone} rmsd_contact:{rmsd_contact}")
        rmsd_backbone[None] = 0.0
        rmsd_contact[None] = 0.0
    # results
    praticles[['x', 'y', 'z']] = pos.to_numpy()
    center = praticles[['x', 'y', 'z']].mean(axis=0)
    praticles[['x', 'y', 'z']] -= center  # shift center to (0,0,0)
    return praticles


def main(in_file, out_file, arch="gpu", **kwargs):
    prams = copy(default_prams)
    prams.update(kwargs)
    print(in_file)
    print(prams)
    ti.init(arch=getattr(ti, arch))
    df = read_pairs(in_file)
    Mb = 10**6
    praticles = None
    for size in prams['size_steps']:
        praticle_size = int(Mb * size)
        print(f"praticle_size:{praticle_size}")
        praticles = create_praticles(df, praticle_size, prev_praticles=praticles, random_seed=prams['random_seed'])
        contacts = count_contacts(df, praticles)
        restraints = get_restraints(praticles, contacts, prams)
        praticles = run_dyn(praticle_size, praticles, restraints, prams)
    praticles.to_csv(out_file)


if __name__ == "__main__":
    fire.Fire(main)
