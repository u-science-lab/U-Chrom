import fire
import pandas as pd
import numpy as np
from functools import partial


Mb = 1000000


def mark_empty_particles(particles, contacts, threshold=0):
    p1_cnt = contacts.groupby('particle_1')['count'].sum()
    p2_cnt = contacts.groupby('particle_2')['count'].sum()
    p_cnt = p1_cnt.add(p2_cnt, fill_value=0)
    particles['is_empty'] = True
    particles.loc[p_cnt[p_cnt > threshold].index, 'is_empty'] = False
    return particles


def mark_empty(particle_path, contacts_path, out_path, resolution=0.8, threshold=0, min_skip=2, min_count=0):
    from .utils.io import read_pairs, load_cool, read_particles
    from .utils.particles import (
        create_particles_from_pairs, create_contacts_from_pairs,
        create_particles_from_cool, create_contacts_from_cool,
    )
    particles = read_particles(particle_path)
    print(f"num_particles:{particles.shape[0]}")
    input_type = "cool" if any([s in contacts_path for s in [".scool", '.cool', '.mcool']]) else "pairs"
    if input_type == "cool":
        read_func = load_cool
        create_particles = create_particles_from_cool
        create_contacts = partial(create_contacts_from_cool, min_count=min_count)
    else:
        read_func = read_pairs
        create_particles = create_particles_from_pairs
        create_contacts = create_contacts_from_pairs
    print("Loading data")
    df = read_func(contacts_path)
    print(f"num_pixels:{df.shape[0]}")
    _part = create_particles(df, int(Mb * resolution))
    contacts = create_contacts(df, _part, min_skip=min_skip)
    _part = mark_empty_particles(_part, contacts, threshold)
    idx = np.searchsorted(_part['start'], (particles['start'] + particles['end']) / 2, side="right") - 1
    particles['is_empty'] = _part.loc[idx]['is_empty'].values
    print(f"num_empty:{particles[particles['is_empty']].shape[0]}")
    particles.to_csv(out_path)


if __name__ == "__main__":
    fire.Fire({
        'mark_empty': mark_empty,
    })
