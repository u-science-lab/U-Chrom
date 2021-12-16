from copy import copy
import fire
import pandas as pd
import taichi as ti
import numpy as np
from sklearn.neighbors import KDTree

from .particles import create_particles, count_contacts
from .io import read_pairs


def get_restraints(particles, contacts, prams, scale=1.0):
    chroms = set(particles['chrom'].unique())
    restraints = []
    # backbone restraints
    for chr in chroms:
        sub_df = particles[particles['chrom'] == chr]
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
        'a': contacts['particle_1'],
        'b': contacts['particle_2'],
        'type': 1,
        'd_min': d_lower,
        'd_max': d_upper,
    }))
    restraints = pd.concat(restraints)
    return restraints


@ti.kernel
def get_repulsive_force(force: ti.template(), pos: ti.template(), k1: ti.f32, d_lim: ti.f32) -> ti.f32:
    total = 0.0
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


def run_dyn(particle_size, particles, restraints, prams):
    # init fields
    fb = ti.FieldsBuilder()
    pos = ti.Vector.field(3, ti.f32)
    vel = ti.Vector.field(3, ti.f32)
    force = ti.Vector.field(3, ti.f32)
    accel = ti.Vector.field(3, ti.f32)
    fb.dense(ti.i, particles.shape[0]).place(pos, force, vel, accel)
    rest_idx = ti.Vector.field(3, ti.i32) # restraint pair, index and type(0: backbone, 1: contact)
    rest_dist = ti.Vector.field(2, ti.f32) # min and max restraint distance
    fb.dense(ti.i, restraints.shape[0]).place(rest_idx, rest_dist)
    fb_snode_tree = fb.finalize()
    # load data into fields
    pos.from_numpy(particles[['x', 'y', 'z']].values)
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
    # simulation loop
    for step in range(num_steps):
        r = step / num_steps
        k1 = float(0.5 + adj * np.arctan(r * 20.0 - 10.0) / np.pi)
        temp = temp_start * np.exp(-decay * r)
        schedule.append((temp, k1))
        c_temp = update_motion(pos, force, vel, accel, prams['time_step'], temp)
        t_rep = get_repulsive_force(force, pos, k1, prams['repulsive_lim'])
        t_res = get_restraint_force(force, pos, rest_idx, rest_dist)
        c_temp = update_vel(force, vel, accel, prams['time_step'], temp)
        rmsd = get_rmsd(pos, rest_idx, rest_dist, rmsd_backbone, rmsd_contact)
        print(f"-------------------- step:{step}")
        print(f"temp:{temp} c_temp:{c_temp} k1:{k1} total_force:{t_rep+t_res} repulsive:{t_rep} restraint:{t_res} rmsd:{rmsd} rmsd_backbone:{rmsd_backbone} rmsd_contact:{rmsd_contact}")
        rmsd_backbone[None] = 0.0
        rmsd_contact[None] = 0.0
    # results
    particles[['x', 'y', 'z']] = pos.to_numpy()
    center = particles[['x', 'y', 'z']].mean(axis=0)
    particles[['x', 'y', 'z']] -= center  # shift center to (0,0,0)
    # destroy all fields
    fb_snode_tree.destroy()
    return particles


default_prams = {
    "bb_lower": 0.1,
    "bb_upper": 1.1, 
    "lower": 0.8,
    "upper": 1.2,
    "repulsive_lim": 2.0,
    "max_radius": 10.0,
    "pow": -0.33,
    "hot": 5000.0,
    "cold": 10.0,
    "temp_steps": 500,
    "dyns": 100,
    "random_seed": 0,
    "time_step": 0.001,
    "size_steps": [8, 4, 2, 0.4, 0.2, 0.1],
}


def main(in_file, out_file, arch="gpu", **kwargs):
    prams = copy(default_prams)
    prams.update(kwargs)
    print(in_file)
    print(prams)
    ti.init(arch=getattr(ti, arch))
    df = read_pairs(in_file)
    Mb = 10**6
    particles = None
    for size in prams['size_steps']:
        particle_size = int(Mb * size)
        print("====================")
        particles = create_particles(df, particle_size, prev_particles=particles, random_seed=prams['random_seed'], max_radius=prams['max_radius'])
        print(f"particle_size:{particle_size} num_particles:{particles.shape[0]}")
        contacts = count_contacts(df, particles)
        restraints = get_restraints(particles, contacts, prams)
        particles = run_dyn(particle_size, particles, restraints, prams)
    particles.to_csv(out_file)


if __name__ == "__main__":
    fire.Fire(main)
