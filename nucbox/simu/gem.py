from copy import copy
import fire
import pandas as pd
import taichi as ti

from ..utils.particles import create_particles_from_pairs, create_contacts_from_pairs
from ..utils.io import read_pairs


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


@ti.kernel
def compute_E_strach(
        E: ti.template(), pos: ti.template(),
        backbones: ti.template(), half_bond_factor: ti.f32):
    for i in backbones:
        a, b = backbones[i]
        diff = pos[b] - pos[a]
        E[None] += half_bond_factor * (diff.norm() - 2.0) ** 2


@ti.data_oriented
class Simulation:
    def __init__(
            self, particles, backbones, contacts,
            steps, time_step,
            shrunk_freq, shrunk_max,
            bond_factor, distance_thresh):
        self.particles = particles
        self.steps = steps
        self.time_step = time_step
        self.shrunk_freq = shrunk_freq
        self.shrunk_max = shrunk_max
        self.bond_factor = bond_factor
        self.distance_thresh = distance_thresh
        # init fields
        self.E = ti.field(dtype=ti.f32, shape=(), needs_grad=True)
        self.pos = ti.Vector.field(3, ti.f32, shape=particles.shape[0], needs_grad=True)
        self.vel = ti.Vector.field(3, ti.f32, shape=particles.shape[0])
        self.backbones = ti.Vector.field(2, ti.i32, shape=backbones.shape[0])
        self.contacts_idx = ti.Vector.field(2, ti.i32)
        self.contacts_val = ti.field(ti.f32)
        ti.root.dense(ti.i, contacts.shape[0]).place(self.contacts_idx, self.contacts_val)
        # load data into fields
        self.pos.from_numpy(particles[['x', 'y', 'z']].values)
        self.backbones.from_numpy(backbones[['a', 'b']].values)
        self.contacts_idx.from_numpy(contacts[['particle_1', 'particle_2']].values)
        self.contacts_val.from_numpy(contacts['count'].values)

    @ti.kernel
    def step(self):
        time_step = self.time_step
        for i in self.pos:
            self.vel[i] = -self.pos.grad[i]
        vel_max = 0.0
        if True:
            # find max
            for i in self.vel:
                vel = self.vel[i].norm()
                if vel > vel_max:
                    vel_max = vel
        vel_max_inv = 1 / ti.sqrt(vel_max)
        for i in self.vel:
            self.pos[i] += time_step * self.vel[i] * vel_max_inv

    @ti.kernel
    def shrunk(self):
        r_sum = 0.0
        a_sum = 0.0
        for i in self.contacts_idx:
            a, b = self.contacts_idx[i]
            dist = (self.pos[b] - self.pos[a]).norm()
            r_sum += dist
            a_sum += 1.0
        factor = (a_sum / r_sum) ** 0.05
        for i in self.pos:
            for k in ti.static(range(3)):
                self.pos[i][k] *= factor

    def run(self):
        for step in range(self.steps):
            with ti.Tape(loss=self.E):
                compute_E_physics(self.E, self.pos, self.backbones, self.bond_factor/2)
            self.step()
            if (step < self.shrunk_max) and (step % self.shrunk_freq == 0):
                self.shrunk()
            self.log_step(step)

    def log_step(self, step):
        print(f"step:{step} E:{self.E}")

    def get_results(self, shift_center=True):
        self.particles[['x', 'y', 'z']] = self.pos.to_numpy()
        if shift_center:
            center = self.particles[['x', 'y', 'z']].mean(axis=0)
            self.particles[['x', 'y', 'z']] -= center  # shift center to (0,0,0)
        return self.particles

    def destroy_fields(self):
        self.fb_snode_tree.destroy()


default_prams = {
    "random_seed": 0,
    "steps": 10000,
    "shrunk_freq": 10,
    "shrunk_max": 2000,
    "size_steps": [1.28],#, 0.64, 0.32, 0.16, 0.08, 0.04, 0.02, 0.01]
    "bond_factor": 100.0,
    "distance_thresh": 2.0,
    "steps": 10000,
    "time_step": 0.1,
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
        print(f"particle_size:{particle_size}")
        particles = create_particles_from_pairs(df, particle_size, prev_particles=particles, random_seed=prams['random_seed'])
        backbones = get_backbones(particles)
        contacts = create_contacts_from_pairs(df, particles)
        simu = Simulation(particles, backbones, contacts,
            prams['steps'], prams['time_step'], prams['shrunk_freq'], prams['shrunk_max'],
            prams['bond_factor'], prams['distance_thresh'])
        simu.run()
        particles = simu.get_results()
    particles.to_csv(out_file)


if __name__ == "__main__":
    fire.Fire(main)
