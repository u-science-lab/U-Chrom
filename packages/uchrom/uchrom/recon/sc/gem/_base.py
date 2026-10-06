from functools import partial

import taichi as ti

from uchrom.io import (
    create_particles_from_pairs, create_contacts_from_pairs,
    create_particles_from_cool, create_contacts_from_cool,
    filter_contacts,
    read_pairs, load_cool,
)


class SimulationBase:
    def __init__(self, prams) -> None:
        self.prams = prams

    @ti.kernel
    def shift_to_center(self):
        pos = ti.static(self.pos)
        center = ti.Vector([0.0, 0.0, 0.0])
        for i in pos:
            center += pos[i]
        center /= pos.shape[0]
        for i in pos:
            pos[i] -= center

    def log_step(self, step, **kwargs):
        print(f"-------------------- step:{step}")

    def get_results(self, shift_center=True):
        self.particles[['x', 'y', 'z']] = self.pos.to_numpy()
        if shift_center:
            center = self.particles[['x', 'y', 'z']].mean(axis=0)
            self.particles[['x', 'y', 'z']] -= center  # shift center to (0,0,0)
        return self.particles

    def destroy_fields(self):
        self.fb_snode_tree.destroy()


def deal_input(in_file, prams):
    input_type = "cool" if any([s in in_file for s in [".scool", '.cool', '.mcool']]) else "pairs"
    if input_type == "cool":
        prams.update({"min_count": 0})
        read_func = load_cool
        create_particles = create_particles_from_cool
        create_contacts = partial(create_contacts_from_cool, min_count=prams['min_count'])
    else:
        read_func = read_pairs
        create_particles = create_particles_from_pairs
        create_contacts = create_contacts_from_pairs
    print("Loading data")
    df = read_func(in_file)
    print(f"num_pixels:{df.shape[0]}")
    if prams['genome_ranges'] is not None:
        print("Filtering data")
        df = filter_contacts(df, prams['genome_ranges'])
        print(f"num_pixels_filtered:{df.shape[0]}")
    return df, create_particles, create_contacts
