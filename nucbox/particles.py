import pandas as pd
import numpy as np

from .lib.cooler import Cooler
import h5py


def random_pos(n_particle, max_radius):
    """Random 3D points inside a sphere"""
    radius = np.random.randn(n_particle) * max_radius
    theta, phi = [np.random.randn(n_particle) * (2 * np.pi) for _ in range(2)]
    x = radius * np.cos(theta) * np.sin(phi)
    y = radius * np.sin(theta) * np.cos(phi)
    z = radius * np.cos(phi)
    return x, y, z


def create_particles_from_pairs(df, particle_size, prev_particles=None, random_seed=0, max_radius=10):
    np.random.seed(random_seed)
    chroms = sorted(set(df['chr1'].unique()) | \
                    set(df['chr2'].unique()))
    particles = {}
    for chr in chroms:
        min_ = df[df['chr1'] == chr]['pos1'].min()
        max_ = df[df['chr2'] == chr]['pos2'].max()
        if any([np.isnan(i) for i in (min_, max_)]):
            continue
        n_particle = (max_ - min_) // particle_size
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


def count_contacts(pairs_df, particles, min_skip=2):
    """Count contacts between all particles."""
    contacts = {}
    chroms = set(particles['chrom'].unique())
    for (chr1, chr2), sub_df in pairs_df.groupby(by=['chr1', 'chr2']):
        if any([c not in chroms for c in (chr1, chr2)]):
            continue
        idxs = []
        for (c, p) in [(chr1, 'pos1'), (chr2, 'pos2')]:
            sub_prat = particles[particles['chrom'] == c]
            ix = np.searchsorted(sub_prat['start'], sub_df[p], side='right') - 1
            idxs.append(sub_prat.iloc[ix,:].index)
        idx_pair = np.sort(np.c_[idxs[0], idxs[1]], axis=0)
        pair, cnt = np.unique(idx_pair, axis=0, return_counts=True)
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


def load_cool(path):
    """Load bins and pixels from cooler."""
    c = Cooler(path)
    with h5py.File(c.store) as f:
        c_root = f['resolutions'][str(c.binsize)]
        c_bins = c_root['bins']
        bin_df = pd.DataFrame({
            'chrom': c.chromsizes.index[c_bins['chrom'][:]],
            'start': c_bins['start'][:],
            'end': c_bins['end'][:],
        })
        c_pixels = c_root['pixels']
        pixel_df = pd.DataFrame({
            'bin1_id': c_pixels['bin1_id'][:],
            'bin2_id': c_pixels['bin2_id'][:],
            'count': c_pixels['count'][:],
        })
    return bin_df, pixel_df, c


def create_particles_from_cool(bin_df, max_radius=10):
    x, y, z = random_pos(bin_df.shape[0], max_radius)
    particles = pd.DataFrame({
        'chrom': bin_df['chrom'],
        'start': bin_df['start'],
        'end': bin_df['end'],
        'x': x,
        'y': y,
        'z': z,
    })
    return particles


def create_contacts_from_cool(pixel_df, min_count=10, min_skip=2):
    pixel_df = pixel_df[pixel_df['count'] >= min_count]
    pixel_df = pixel_df[(pixel_df['bin2_id'] - pixel_df['bin1_id']) >= min_skip]
    contacts = pd.DataFrame({
        "particle_1": pixel_df['bin1_id'],
        "particle_2": pixel_df['bin2_id'],
        "count": pixel_df['count']
    })
    return contacts
