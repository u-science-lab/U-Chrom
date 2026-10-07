"""count_contacts must keep each read pair's two ends together."""
import numpy as np
import pandas as pd


def test_count_contacts_keeps_pairs():
    from uchrom.io import count_contacts

    size = 100
    particles = pd.DataFrame({"chrom": "chr1", "start": np.arange(10) * size,
                              "end": np.arange(1, 11) * size})
    # (particle a, particle b) for each read; unsorted within and across rows
    ab = [(0, 9), (9, 0), (5, 2), (1, 8), (0, 9)]
    df = pd.DataFrame({"chr1": "chr1", "chr2": "chr1",
                       "pos1": [a * size + 10 for a, _ in ab],
                       "pos2": [b * size + 10 for _, b in ab]})
    got = count_contacts(df, particles, min_skip=2)
    pairs = {(int(r.particle_1), int(r.particle_2)): int(r.count) for r in got.itertuples()}
    assert pairs == {(0, 9): 3, (2, 5): 1, (1, 8): 1}
