import pandas as pd
import numpy as np
from functools import partial


def random_pos(n_particle, max_radius):
    """Random 3D points inside a sphere"""
    radius = np.random.randn(n_particle) * max_radius
    theta, phi = [np.random.randn(n_particle) * (2 * np.pi) for _ in range(2)]
    x = radius * np.cos(theta) * np.sin(phi)
    y = radius * np.sin(theta) * np.cos(phi)
    z = radius * np.cos(phi)
    return x, y, z


def _create_particles(df, particle_size, prev_particles=None, random_seed=0, max_radius=10, min_label='pos1', max_label='pos2'):
    np.random.seed(random_seed)
    chroms = sorted(set(df['chr1'].unique()) | \
                    set(df['chr2'].unique()))
    particles = {}
    for chr in chroms:
        min_ = df[df['chr1'] == chr][min_label].min()
        max_ = df[df['chr2'] == chr][max_label].max()
        if any([np.isnan(i) for i in (min_, max_)]):
            continue
        n_particle = (max_ - min_) // particle_size
        if n_particle <= 3:
            continue
        space = np.linspace(min_, max_, n_particle+1)
        starts, ends = [s.astype(np.int64) for s in [space[:-1], space[1:]]]
        pos = {}
        if prev_particles is None:
            # generate random positions
            pos['x'], pos['y'], pos['z'] = random_pos(n_particle, max_radius)
        else:
            # generate positions with interpolation
            prev = prev_particles[prev_particles['chrom'] == chr]
            xp = np.concatenate([
                [0], (prev['start'] + prev['end']) / 2, [prev['end'].iloc[-1] + particle_size / 2],
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
        particles[chr] = p_df
    particles = pd.concat(particles.values()).reset_index()
    return particles


create_particles_from_pairs = partial(_create_particles, min_label="pos1", max_label="pos2")
create_particles_from_cool = partial(_create_particles, min_label='start1', max_label='end2')


def count_contacts(df, particles, min_skip=2):
    """Count contacts between all particles."""
    contacts = {}
    chroms = set(particles['chrom'].unique())
    for (chr1, chr2), sub_df in df.groupby(by=['chr1', 'chr2']):
        if any([c not in chroms for c in (chr1, chr2)]):
            continue
        idxs = []
        for (c, p) in [(chr1, 'pos1'), (chr2, 'pos2')]:
            sub_prat = particles[particles['chrom'] == c]
            ix = np.searchsorted(sub_prat['start'], sub_df[p], side='right') - 1
            idxs.append(sub_prat.iloc[ix,:].index)
        if not "count" in df.columns:
            idx_pair = np.sort(np.c_[idxs[0], idxs[1]], axis=0)
            pair, cnt = np.unique(idx_pair, axis=0, return_counts=True)
        else:
            idx_df = pd.DataFrame({"ix1": idxs[0], "ix2": idxs[1], "count": sub_df['count']})
            gdf = idx_df.groupby(['ix1', 'ix2'], as_index=False).sum()
            pair, cnt = gdf[['ix1', 'ix2']].values, gdf['count'].values
        count = np.c_[pair, cnt]
        count = pd.DataFrame({
            "chr1": chr1,
            "chr2": chr2,
            "particle_1": pair[:, 0],
            "particle_2": pair[:, 1],
            "count": cnt,
        })
        if chr1 == chr2:
            count = count[(count['particle_2'] - count['particle_1']) >= min_skip]
        contacts[(chr1, chr2)] = count
    contacts = pd.concat(contacts.values()).reset_index(drop=True)
    return contacts


create_contacts_from_pairs = count_contacts


def create_contacts_from_cool(pixel_df, particles, min_count=0, min_skip=2):
    if min_count > 0:
        pixel_df = pixel_df[pixel_df['count'] >= min_count]
    df = pd.DataFrame({
        "chr1": pixel_df['chr1'],
        "pos1": (pixel_df['start1'] + pixel_df['end1']) / 2,
        "chr2": pixel_df['chr2'],
        "pos2": (pixel_df['start2'] + pixel_df['end2']) / 2,
        "count": pixel_df["count"],
    })
    contacts = count_contacts(df, particles, min_skip=min_skip)
    return contacts
