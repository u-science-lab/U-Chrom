# TAD utilities: BED file I/O and substructure operations



def load_tad_from_bed(bed_path):
    """Load TAD regions from BED file."""
    regions = []
    with open(bed_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 3:
                chrom = parts[0]
                start = int(parts[1])
                end = int(parts[2])
                regions.append((chrom, start, end))
    return regions


def tad_regions_to_bin_indices(regions, bins_df, chrom=None):
    """Convert TAD genomic regions to bin indices."""
    bin_indices = []
    for rgn_chrom, rgn_start, rgn_end in regions:
        if chrom is not None and rgn_chrom != chrom:
            continue
        mask = (
            (bins_df['chrom'] == rgn_chrom) &
            (bins_df['start'] >= rgn_start) &
            (bins_df['end'] <= rgn_end)
        )
        matching_bins = bins_df[mask]
        if len(matching_bins) > 0:
            start_idx = matching_bins.index[0]
            end_idx = matching_bins.index[-1]
            bin_indices.append((start_idx, end_idx))
    return bin_indices
