# Inter-chromosomal whole-genome 3D reconstruction
#
# Algorithm:
#   1. Load whole-genome contact matrix (intra + inter) at low resolution
#   2. Global MDS on combined matrix -> scaffold coordinates
#   3. Per-chromosome high-resolution MDS (independent)
#   4. Procrustes alignment of each chromosome to its scaffold position
#   5. Global scaling correction

import os
import time
import numpy as np
import pandas as pd
import torch


def inter_mds(input_path, resolution_inter=1000000, resolution_intra=100000,
              chroms=None, alpha=4.0, weight=0.05, n_iter=1000,
              device='auto', output_dir=None, verbose=True):
    """Whole-genome 3D reconstruction with inter-chromosomal contacts.

    Args:
        input_path: Path to .hic or .mcool file
        resolution_inter: Resolution for inter-chromosomal scaffold (default 1Mb)
        resolution_intra: Resolution for intra-chromosomal structures (default 100kb)
        chroms: List of chromosomes (default: autosomes + X)
        alpha: Contact-to-distance exponent
        weight: Distance decay prior weight
        n_iter: MDS iterations
        device: 'auto', 'cpu', 'cuda', 'mps'
        output_dir: Output directory (None = don't save)
        verbose: Print progress

    Returns:
        genome_df: DataFrame with chrom, start, end, x, y, z for all bins
    """
    from uchrom.io import load_hic, load_hic_genome
    from .__main__ import load_contacts_from_mcool
    from .torch_mds import run_mds, get_device
    from .transforms import (
        procrustes_alignment, apply_transform, downsample_coords,
    )

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    dev = get_device(device)
    if verbose:
        print("=" * 60)
        print("  U-Chrom Inter-Chromosomal MDS")
        print(f"  Input: {os.path.basename(input_path)}")
        print(f"  Device: {dev}")
        print(f"  Inter resolution: {resolution_inter // 1000}kb")
        print(f"  Intra resolution: {resolution_intra // 1000}kb")
        print("=" * 60)

    # ── Step 1: Load whole-genome contact matrix at inter resolution ──
    if verbose:
        print(f"\n[1/4] Loading whole-genome contacts ({resolution_inter//1000}kb)...")
    t0 = time.time()
    genome_bins, genome_mat, offsets, chrom_sizes = load_hic_genome(
        input_path, resolution_inter, chroms, norm='KR'
    )
    chrom_list = list(offsets.keys())
    n_total = genome_mat.shape[0]
    if verbose:
        print(f"  Genome matrix: {n_total}x{n_total}, "
              f"{len(chrom_list)} chromosomes, {time.time()-t0:.1f}s")

    # ── Step 2: Global low-resolution MDS (scaffold) ──────────────────
    if verbose:
        print(f"\n[2/4] Global MDS (scaffold)...")
    t0 = time.time()
    genome_tensor = torch.from_numpy(genome_mat.astype(np.float64))
    scaffold_coords = run_mds(
        genome_tensor, alpha=alpha, device=device,
        weight=weight, n_iter=n_iter, verbose=False,
    )
    if verbose:
        print(f"  Scaffold MDS: {time.time()-t0:.1f}s")

    # extract per-chromosome scaffold coordinates
    scaffold_per_chrom = {}
    for c in chrom_list:
        o = offsets[c]
        n = chrom_sizes[c]
        scaffold_per_chrom[c] = scaffold_coords[o:o+n]

    # ── Step 3: Per-chromosome high-resolution MDS ────────────────────
    if verbose:
        print(f"\n[3/4] Per-chromosome MDS ({resolution_intra//1000}kb)...")

    res_ratio = resolution_inter // resolution_intra
    high_res_results = {}

    for c in chrom_list:
        t0 = time.time()
        try:
            if input_path.endswith('.hic'):
                bins_df, contact_mat = load_hic(input_path, resolution_intra, c)
            else:
                bins_df, contact_mat = load_contacts_from_mcool(
                    input_path, resolution_intra, c)
        except Exception as e:
            if verbose:
                print(f"  {c}: SKIP (load failed: {e})")
            continue

        contact_tensor = torch.from_numpy(contact_mat.astype(np.float64))
        coords = run_mds(
            contact_tensor, alpha=alpha, device=device,
            weight=weight, n_iter=n_iter, verbose=False,
        )
        high_res_results[c] = {
            'coords': coords,
            'bins_df': bins_df,
            'n_bins': len(coords),
        }
        if verbose:
            print(f"  {c}: {len(coords)} bins, {time.time()-t0:.1f}s")

    # ── Step 4: Align high-res structures to scaffold ─────────────────
    if verbose:
        print(f"\n[4/4] Aligning to scaffold...")

    aligned_results = {}

    for c in chrom_list:
        if c not in high_res_results:
            continue

        high_coords = high_res_results[c]['coords']
        scaffold_c = scaffold_per_chrom[c]

        # downsample high-res to match scaffold resolution
        low_from_high = downsample_coords(high_coords, res_ratio, method='mean')

        # trim to same length (may differ by 1 due to rounding)
        n_match = min(len(low_from_high), len(scaffold_c))
        if n_match < 3:
            if verbose:
                print(f"  {c}: SKIP (too few points to align)")
            continue

        low_from_high = low_from_high[:n_match]
        scaffold_section = scaffold_c[:n_match]

        # Procrustes alignment
        R, t, scale = procrustes_alignment(low_from_high, scaffold_section)

        # apply transform to high-res coords
        aligned = apply_transform(high_coords, R, t, scale)
        aligned_results[c] = aligned

        if verbose:
            print(f"  {c}: aligned (scale={scale:.3f})")

    # ── Build output DataFrame ────────────────────────────────────────
    all_dfs = []
    for c in chrom_list:
        if c not in aligned_results:
            continue
        coords = aligned_results[c]
        bins_df = high_res_results[c]['bins_df']
        n = len(coords)
        display_name = c if c.startswith('chr') else f'chr{c}'
        df = pd.DataFrame({
            'chrom': display_name,
            'start': bins_df['start'].values[:n],
            'end': bins_df['end'].values[:n],
            'x': coords[:, 0],
            'y': coords[:, 1],
            'z': coords[:, 2],
        })
        all_dfs.append(df)

        if output_dir:
            out_path = os.path.join(output_dir, f"{display_name}.csv")
            df.to_csv(out_path, index=True)

    genome_df = pd.concat(all_dfs, ignore_index=True)

    if output_dir:
        genome_df.to_csv(os.path.join(output_dir, "genome.csv"), index=True)

    if verbose:
        print(f"\n  Total: {len(genome_df)} bins across "
              f"{len(aligned_results)} chromosomes")
        if output_dir:
            print(f"  Output: {output_dir}/")

    return genome_df
