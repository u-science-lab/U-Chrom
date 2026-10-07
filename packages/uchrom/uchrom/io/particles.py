"""Contacts counted between the particles (bins) of a structure: ``count_contacts``."""

import numpy as np
import pandas as pd


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
        if not "count" in df.columns:  # pairs
            # sort each (i, j) pair, not each column (axis=0 scrambled the pairing)
            idx_pair = np.sort(np.c_[idxs[0], idxs[1]], axis=1)
            pair, cnt = np.unique(idx_pair, axis=0, return_counts=True)
        else:  # cool
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
