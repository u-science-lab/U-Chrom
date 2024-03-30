from copy import copy

import fire
import pandas as pd
import taichi as ti
import numpy as np


from .base import SimulationBase, Grid, deal_input
from ..utils.particles import remove_violated_contacts


def get_restraints(particles, contacts, prams):
    chroms = set(particles['chrom'].unique())
    restraints = []
    # backbone
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
    # contact
    d_target = (contacts['count'] * prams['scale']) ** prams['pow']
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


@ti.func
def calc_repulsive(pos, i, j, k1, d_lim, force) -> ti.f32:
    diff = pos[j] - pos[i]
    dist = diff.norm()
    f = 0.0
    if dist <= d_lim:
        d = dist - d_lim
        f = k1*d**2
        for k in ti.static(range(3)):
            f_ = f * diff[k]
            force[i][k] += -f_
            force[j][k] += f_
    return f


@ti.func
def get_temp(vel):
    kin = 0.0
    BOLTZMANN_K = 0.0019872041
    n = vel.shape[0]
    for i in range(0, n):
        v = vel[i]
        kin += v.norm()
    return kin / (3 * n * BOLTZMANN_K)



@ti.data_oriented
class Simulation(SimulationBase):
    def __init__(
            self, particles, particle_size, restraints, d_lim, time_step,
            grid=None, shift_freq=1, step_callback=None):
        self.particles = particles
        self.particle_size = particle_size
        self.d_lim = d_lim
        self.time_step = time_step
        self.grid = grid
        self.shift_freq = shift_freq
        self.step_callback = step_callback
        self.schedule = []
        # init fields
        fb = ti.FieldsBuilder()
        self.pos = ti.Vector.field(3, ti.f32)
        self.vel = ti.Vector.field(3, ti.f32)
        self.force = ti.Vector.field(3, ti.f32)
        self.accel = ti.Vector.field(3, ti.f32)
        fb.dense(ti.i, particles.shape[0]).place(self.pos, self.force, self.vel, self.accel)
        self.rest_idx = ti.Vector.field(3, ti.i32) # restraint pair, index and type(0: backbone, 1: contact)
        self.rest_dist = ti.Vector.field(2, ti.f32) # min and max restraint distance
        fb.dense(ti.i, restraints.shape[0]).place(self.rest_idx, self.rest_dist)
        if self.grid is not None:
            self.grid.init_data(fb)
        self.fb_snode_tree = fb.finalize()
        # load data into fields
        self.pos.from_numpy(particles[['x', 'y', 'z']].values)
        self.rest_idx.from_numpy(restraints[['a', 'b', 'type']].values)
        self.rest_dist.from_numpy(restraints[['d_min', 'd_max']].values)
        # count value
        self.rmsd_backbone = ti.field(ti.f32, shape=())
        self.rmsd_contact = ti.field(ti.f32, shape=())

    @ti.kernel
    def get_repulsive_force(self, k1: ti.f32) -> ti.f32:
        total = 0.0
        d_lim = self.d_lim
        for i in range(0, self.pos.shape[0]-2):
            for j in range(i+2, self.pos.shape[0]):
                f = calc_repulsive(self.pos, i, j, k1, d_lim, self.force)
                total += f
        return total

    @ti.kernel
    def get_repulsive_force_with_grid(self, k1: ti.f32) -> ti.f32:
        total = 0.0
        start = self.grid.range[0]
        d_lim = self.d_lim
        grid = ti.static(self.grid.data)
        for i in self.pos:
            I = [0, 0, 0]
            for d in ti.static(range(3)):
                I[d] = int((self.pos[i][d] - start) // d_lim)
            for gi in range(max(0, I[0]-1), min(I[0]+2, grid.shape[0])):
                for gj in range(max(0, I[1]-1), min(I[1]+2, grid.shape[1])):
                    for gk in range(max(0, I[2]-1), min(I[2]+2, grid.shape[2])):
                        # iter over each element in cell
                        for gl in range(ti.length(grid.parent(), [gi, gj, gk])):
                            j = grid[gi, gj, gk, gl]
                            if j < i + 1:
                                continue
                            f = calc_repulsive(self.pos, i, j, k1, d_lim, self.force)
                            total += f
        return total

    @ti.kernel
    def get_restraint_force(self) -> ti.f32:
        total = 0.0
        k2 = 25.0
        dist_switch = 0.5
        asymptote = 1.0
        exponent = 2.0

        B = asymptote*(dist_switch**2) - exponent*(dist_switch**3)
        A = dist_switch**2 - asymptote*dist_switch - B/dist_switch

        for i in self.rest_idx:
            a, b, tp = self.rest_idx[i]
            d_min, d_max = self.rest_dist[i]
            pos_a = self.pos[a]
            pos_b = self.pos[b]
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
                self.force[a][j] += -f_
                self.force[b][j] += f_
        return total

    @ti.kernel
    def update_motion(self, temp_ref: ti.f32) -> ti.f32:
        time_step = self.time_step
        rt_step = 0.5 * time_step**2
        temp = get_temp(self.vel)
        temp = max(temp, 0.001)
        beta = 10.0 / 20.458
        r = beta * (temp_ref/temp - 1.0)
        for i in range(self.force.shape[0]):
            for j in ti.static(range(3)):
                a = self.force[i][j] + r * self.vel[i][j]
                self.pos[i][j] += time_step * self.vel[i][j] + rt_step * a
                self.vel[i][j] += time_step * a
                self.accel[i][j] = a
                self.force[i][j] = 0.0
        return temp

    @ti.kernel
    def update_vel(self, temp_ref: ti.f32) -> ti.f32:
        time_step = self.time_step
        temp = get_temp(self.vel)
        temp = max(temp, 0.001)
        beta = 10.0 / 20.458
        r = beta * (temp_ref/temp - 1.0)
        for i in range(self.force.shape[0]):
            for j in ti.static(range(3)):
                self.vel[i][j] += 0.5 + time_step * (self.force[i][j] + r * self.vel[i][j] - self.accel[i][j])
        return temp

    @ti.kernel
    def get_rmsd(self) -> ti.f32:
        total = 0.0
        backbone = 0.0
        contact = 0.0
        for i in self.rest_idx:
            a, b, tp = self.rest_idx[i]
            d_min, d_max = self.rest_dist[i]
            pos_a = self.pos[a]
            pos_b = self.pos[b]
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
        self.rmsd_backbone[None] = ti.sqrt(backbone/self.rest_idx.shape[0])
        self.rmsd_contact[None] = ti.sqrt(contact/self.rest_idx.shape[0])
        return ti.sqrt(total/self.rest_idx.shape[0])

    def setup_schedule(self, num_steps, temp_start, temp_end):
        schedule = []
        adj = 1.0 / np.arctan(10)
        decay = np.log(temp_start / temp_end)
        for step in range(num_steps):
            r = step / num_steps
            k1 = float(0.5 + adj * np.arctan(r * 20.0 - 10.0) / np.pi)
            temp = temp_start * np.exp(-decay * r)
            schedule.append((temp, k1))
        self.schedule = schedule

    def log_step(self, step, **kwargs):
        log_kw = {'total_force': kwargs.get("repulsive", 0) + kwargs.get("restraint", 0)}
        log_kw.update(kwargs)
        log_kw['rsmd_backbone'] = self.rmsd_backbone
        log_kw['rsmd_contact'] = self.rmsd_contact
        print(f"-------------------- step:{step}")
        print(" ".join([f"{k}:{v}" for k, v in log_kw.items()]))

    def run(self):
        for step, (temp, k1) in enumerate(self.schedule):
            c_temp = self.update_motion(temp)
            if self.grid:
                self.grid.from_pos(self.pos)
                t_rep = self.get_repulsive_force_with_grid(k1)
                self.grid.clear()
            else:
                t_rep = self.get_repulsive_force(k1)
            t_res = self.get_restraint_force()
            c_temp = self.update_vel(temp)
            rmsd = self.get_rmsd()
            self.log_step(step, temp=temp, c_temp=c_temp, k1=k1, repulsive=t_rep, restraint=t_res, rmsd=rmsd)
            self.rmsd_backbone[None] = 0.0
            self.rmsd_contact[None] = 0.0
            if ((step + 1) % self.shift_freq) == 0:
                self.shift_to_center()
            if self.step_callback:
                self.step_callback(self, step)

    def destroy_fields(self):
        self.fb_snode_tree.destroy()


default_params = {
    "genome_ranges": None,
    "pow": -0.33,
    "bb_lower": 0.1,
    "bb_upper": 1.1,
    "lower": 0.8,
    "upper": 1.2,
    "scale": 1.0,
    "repulsive_lim": 2.0,
    "hot": 5000.0,
    "cold": 10.0,
    "dyns": 500,
    "random_seed": 0,
    "time_step": 0.01,
    "size_steps": [8, 4, 2, 0.4, 0.2, 0.1],
    "max_radius": 10.0,
    "use_grid": False,
    "grid_range_scale": 5.0,
    "cell_capacity": 10000,
    "shift_freq": 10,
    "min_skip": 2,
    "violated_threshold": 5.0,
}


def run_once(particles, particle_size, contacts, prams, step_callback):
    counts = pd.concat([contacts['particle_1'], contacts['particle_2']]).value_counts()
    particles['contact_count'] = particles['index'].map(counts).fillna(0).astype(int)
    restraints = get_restraints(particles, contacts, prams)
    print("====================")
    print(f"particle_size:{particle_size} num_particles:{particles.shape[0]}")
    print(f"num_contact:{contacts.shape[0]} num_restraints:{restraints.shape[0]}")
    grid = None
    if prams['use_grid']:
        grid = Grid(prams['max_radius'], prams['grid_range_scale'], prams['repulsive_lim'], prams['cell_capacity'])
    simu = Simulation(particles, particle_size, restraints, prams['repulsive_lim'], prams['time_step'], grid, prams['shift_freq'], step_callback)
    simu.setup_schedule(prams['dyns'], prams['hot'], prams['cold'])
    simu.run()
    particles = simu.get_results()
    simu.destroy_fields()
    return particles


def main(in_file, out_file,
         arch="gpu", device_memory_fraction=0.9,
         **kwargs):
    prams = copy(default_params)
    prams.update(kwargs)
    print(in_file)
    df, create_particles, create_contacts = deal_input(in_file, prams)
    print(prams)
    ti.init(arch=getattr(ti, arch), device_memory_fraction=device_memory_fraction)
    particles = None
    Mb = 10**6
    for stage, size in enumerate(prams['size_steps']):
        particle_size = int(Mb * size)
        particles = create_particles(df, particle_size, prev_particles=particles, random_seed=prams['random_seed'], max_radius=prams['max_radius'])
        contacts = create_contacts(df, particles, min_skip=prams['min_skip'])
        if stage > 0:
            contacts = remove_violated_contacts(contacts, particles, prams['violated_threshold'])
        particles = run_once(particles, particle_size, contacts, prams, None)
    particles.to_csv(out_file)


if __name__ == "__main__":
    fire.Fire(main)
