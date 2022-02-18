from copy import copy
import fire
import pandas as pd
import taichi as ti
import numpy as np

from .particles import create_particles, count_contacts
from ..io import read_pairs


def run_dyn(particles, contacts, prams):
    # init fields
    pos = ti.Vector.field(3, ti.f32)
    force = ti.Vector.field(3, ti.f32, needs_grad=True)
    ti.dense(ti.i, particles.shape[0]).place(pos, force)
    energy_phys = ti.field(dtype=ti.f32, shape=(), needs_grad=True)
    energy_count = ti.field(dtype=ti.f32, shape=(), needs_grad=True)


default_prams = {
    "steps": 10000,
    "shrunk_freq": 10,
    "shrunk_max": 2000,
    "size_steps": [1.28],#, 0.64, 0.32, 0.16, 0.08, 0.04, 0.02, 0.01]
    "bond_factor": 100,
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
        particles = create_particles(df, particle_size, prev_particles=particles, random_seed=prams['random_seed'])
        contacts = count_contacts(df, particles)
        particles = run_dyn(praticles, contacts, prams)
    particles.to_csv(out_file)


if __name__ == "__main__":
    fire.Fire(main)
