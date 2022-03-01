from functools import partial

import taichi as ti

from ..utils.particles import (
    create_particles_from_pairs, create_contacts_from_pairs,
    create_particles_from_cool, create_contacts_from_cool,
    filter_contacts,
)
from ..utils.io import read_pairs, load_cool


@ti.data_oriented
class Grid:
    def __init__(self, max_radius, range_scale, bin_length, capacity):
        """3D grid for fast neighbor search."""
        self.capacity = capacity
        self.bin_length = bin_length
        s = max_radius * range_scale
        self.range = r = (-s, s)
        self.bin_num = int((r[1] - r[0]) // bin_length)
        self.data = ti.field(ti.i32)

    def init_data(self, fb):
        fb.dense(ti.ijk, self.bin_num).dynamic(ti.l, self.capacity).place(self.data)

    @ti.kernel
    def from_pos(self, pos: ti.template()):
        start, d_lim, capacity, bin_num = ti.static(
            self.range[0], self.bin_length, self.capacity, self.bin_num)
        for i in pos:
            I = [0, 0, 0]
            for d in ti.static(range(3)):
                p = pos[i][d]
                if p < start:
                    print("[Warning] position exceed grid range(<). please increase grid_range_scale.")
                ix = int((p - start) // d_lim)
                if ix >= bin_num:
                    print("[Warning] position exceed grid range(>). please increase grid_range_scale.")
                I[d] = ix
            if ti.length(self.data.parent(), I) == capacity:
                print("[Warning] cell capacity is not engough! please increase cell_capacity.")
            ti.append(self.data.parent(), I, i)

    @ti.kernel
    def print_cells_length(self):
        for i, j, k in self.data.parent().parent():
            len_ = ti.length(self.data.parent(), [i, j, k])
            if len_ != 0:
                print(i, j, k, len_)

    def clear(self):
        self.data.parent().deactivate_all()  # clear grid



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
