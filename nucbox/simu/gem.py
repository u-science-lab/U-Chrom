import sys
from copy import copy

import fire
import numpy as np
import pandas as pd
import taichi as ti

from .base import SimulationBase, deal_input


def get_backbones(particles):
    chroms = set(particles['chrom'].unique())
    backbones = []
    for chr in chroms:
        sub_df = particles[particles['chrom'] == chr]
        if sub_df.shape[0] < 3: # skip short chrom
            continue
        a = sub_df[:-1].index.values
        b = sub_df[1:].index.values
        backbones.append(pd.DataFrame({
            'a': a,
            'b': b,
        }))
    df = pd.concat(backbones)
    return df


def get_restraints(contacts, prams):
    d_target = (contacts['count'] * prams['scale']) ** prams['pow']
    return pd.DataFrame({
        'a': contacts['particle_1'],
        'b': contacts['particle_2'],
        'd': d_target,
    })


@ti.func
def vec_angle(a, b) -> ti.f64:
    f1 = a.dot(b) - 0.0001
    f2 = a.norm() * b.norm()
    r = min(max(f1 / f2, -0.999999999), 0.999999999)
    res = ti.acos(r)
    return res


@ti.kernel
def compute_E_strach(
        E_count: ti.template(),
        E: ti.template(), pos: ti.template(),
        backbones: ti.template(), half_bond_factor: ti.f64):
    for i in backbones:
        a, b = backbones[i]
        diff = pos[b] - pos[a]
        e = half_bond_factor * (diff.norm() - 1.0) ** 2
        E[None] += e
        E_count[None] += e


@ti.kernel
def compute_E_bend(
        E_count: ti.template(),
        E: ti.template(), pos: ti.template(),
        backbones: ti.template(), half_angle_factor: ti.f64):
    for i in range(0, backbones.shape[0]-1):
        a, b = backbones[i]
        b_, c = backbones[i+1]
        if b == b_:
            pa, pb, pc = pos[a], pos[b], pos[c]
            v1 = pb-pa
            v2 = pc-pb
            angle = vec_angle(v1, v2)
            e = half_angle_factor * angle ** 2
            E[None] += e
            E_count[None] += e


@ti.kernel
def compute_E_exclude(
        E_exclude: ti.template(),
        E: ti.template(), pos: ti.template(),
        exclude_factor: ti.f64):
    for j in range(1, pos.shape[0]):
        for i in range(j):
            r = (pos[j] - pos[i]).norm()
            if r < 1.0:
                e = exclude_factor * 0.5 * (r - 1.0)**2
                E[None] += e
                E_exclude[None] += e


@ti.kernel
def compute_E_contact(
        E_contact: ti.template(),
        E: ti.template(), pos: ti.template(),
        contact_idx: ti.template(), restraint_distances: ti.template(),
        contact_factor: ti.f64):
    for i in contact_idx:
        a, b = contact_idx[i]
        r = (pos[b] - pos[a]).norm()
        d = restraint_distances[i]
        e = contact_factor * 0.5 * (r - d)**2
        E[None] += e
        E_contact[None] += e


@ti.data_oriented
class Simulation(SimulationBase):
    def __init__(
            self, particles, backbones, restraints,
            time_step,
            shrunk_freq, shrunk_max,
            bond_factor, angle_factor, exclude_factor, contact_factor):
        self.particles = particles
        self.time_step = time_step
        self.shrunk_freq = shrunk_freq
        self.shrunk_max = shrunk_max
        self.bond_factor = bond_factor
        self.angle_factor = angle_factor
        self.exclude_factor = exclude_factor
        self.contact_factor = contact_factor
        # init fields
        self.E = ti.field(dtype=ti.f64, shape=(), needs_grad=True)
        self.pos = ti.Vector.field(3, ti.f64, shape=particles.shape[0], needs_grad=True)
        self.vel = ti.Vector.field(3, ti.f64, shape=particles.shape[0])
        self.backbones = ti.Vector.field(2, ti.i32, shape=backbones.shape[0])
        self.contacts_idx = ti.Vector.field(2, ti.i32)
        self.restraint_distances = ti.field(ti.f64)
        ti.root.dense(ti.i, restraints.shape[0]).place(self.contacts_idx, self.restraint_distances)
        # load data into fields
        self.pos.from_numpy(particles[['x', 'y', 'z']].values)
        self.backbones.from_numpy(backbones[['a', 'b']].values)
        self.contacts_idx.from_numpy(restraints[['a', 'b']].values)
        self.restraint_distances.from_numpy(restraints['d'].values)
        # count value
        self.E_strach = ti.field(dtype=ti.f64, shape=())
        self.E_bend = ti.field(dtype=ti.f64, shape=())
        self.E_exclude = ti.field(dtype=ti.f64, shape=())
        self.E_contact = ti.field(dtype=ti.f64, shape=())

    @ti.kernel
    def step(self):
        time_step = self.time_step
        for i in self.pos:
            self.vel[i] = -self.pos.grad[i]
        for i in self.vel:
            self.pos[i] += time_step * self.vel[i]

    def run(self):
        for step, (exclude_factor,) in enumerate(self.schedule):
            self.E[None] = 0.0
            self.E_strach[None] = 0.0
            self.E_bend[None] = 0.0
            self.E_exclude[None] = 0.0
            self.E_contact[None] = 0.0
            with ti.Tape(loss=self.E):
                compute_E_strach(self.E_strach, self.E, self.pos, self.backbones, self.bond_factor/2)
                compute_E_bend(self.E_bend, self.E, self.pos, self.backbones, self.angle_factor/2)
                compute_E_exclude(self.E_exclude, self.E, self.pos, exclude_factor)
                compute_E_contact(self.E_contact, self.E, self.pos, self.contacts_idx, self.restraint_distances, self.contact_factor)
            self.step()
            self.log_step(step)
            if np.isnan(self.E[None]):
                sys.exit(1)

    def setup_schedule(self, num_steps, e_start, e_end):
        schedule = []
        decay = np.log(e_start / e_end)
        for step in range(num_steps):
            r = step / num_steps
            e = e_start * np.exp(-decay * r)
            schedule.append((e, ))
        self.schedule = schedule

    def log_step(self, step):
        print(f"step:{step} E:{self.E} E_strach:{self.E_strach} E_bend:{self.E_bend} E_exclude:{self.E_exclude} E_contact:{self.E_contact}")


default_prams = {
    "genome_ranges": None,
    "random_seed": 0,
    "steps": 10000,
    "shrunk_freq": 10,
    "shrunk_max": 2000,
    "max_radius": 300.0,
    "size_steps": [1.28],#, 0.64, 0.32, 0.16, 0.08, 0.04, 0.02, 0.01]
    "scale": 1.0,
    "pow": -0.33,
    "bond_factor": 0.1,
    "angle_factor": 0.01,
    "exclude_factor": 0.01,
    "contact_factor": 0.1,
    "steps": 10000,
    "time_step": 0.01,
    "min_skip": 2,
}



def main(in_file, out_file, arch="gpu", **kwargs):
    prams = copy(default_prams)
    prams.update(kwargs)
    print(in_file)
    df, create_particles, create_contacts = deal_input(in_file, prams)
    print(prams)
    ti.init(arch=getattr(ti, arch))
    Mb = 10**6
    particles = None
    for size in prams['size_steps']:
        particle_size = int(Mb * size)
        print(f"particle_size:{particle_size}")
        particles = create_particles(df, particle_size, prev_particles=particles, random_seed=prams['random_seed'], max_radius=prams['max_radius'])
        backbones = get_backbones(particles)
        contacts = create_contacts(df, particles, min_skip=prams['min_skip'])
        restraints = get_restraints(contacts, prams)
        simu = Simulation(particles, backbones, restraints,
            prams['time_step'], prams['shrunk_freq'], prams['shrunk_max'],
            prams['bond_factor'], prams['angle_factor'], prams['exclude_factor'], prams['contact_factor'])
        simu.setup_schedule(prams['steps'], 0.0001, 0.01)
        simu.run()
        particles = simu.get_results()
    particles.to_csv(out_file)


if __name__ == "__main__":
    fire.Fire(main)
