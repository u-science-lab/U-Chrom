import fire
import numpy as np
import pandas as pd


def load_contacts_from_mcool(path, resolution, chrom=None):
    """Load contact matrix from mcool/cool file."""
    from cooler import Cooler

    if '::' in path:
        uri = path
    else:
        uri = f"{path}::resolutions/{resolution}"

    try:
        clr = Cooler(uri)
    except Exception:
        clr = Cooler(path)

    bins = clr.bins()[:]

    if chrom is not None:
        chrom_bins = bins[bins['chrom'] == chrom].copy()
        chrom_bins['idx'] = range(len(chrom_bins))
        matrix = clr.matrix(balance=True).fetch(chrom)
        matrix = np.nan_to_num(matrix, nan=0.0)
        return chrom_bins, matrix
    else:
        matrix = clr.matrix(balance=True)[:]
        matrix = np.nan_to_num(matrix, nan=0.0)
        bins['idx'] = range(len(bins))
        return bins, matrix


def save_structure(coords, bins_df, output_path):
    """Save 3D structure to CSV."""
    result = pd.DataFrame({
        'chrom': bins_df['chrom'].values,
        'start': bins_df['start'].values,
        'end': bins_df['end'].values,
        'x': coords[:, 0],
        'y': coords[:, 1],
        'z': coords[:, 2],
    })
    result.to_csv(output_path, index=True)
    print(f"Structure saved to {output_path}")


def main(input, output, resolution=100000, chrom=None,
         device='auto', alpha=4.0, alpha2=2.5, weight=0.05,
         n_iter=1000, lr=0.01, res_ratio=10,
         partitioned=False, tad_bed=None, n_workers=1,
         verbose=False):
    """Reconstruct 3D chromatin structure from Hi-C data using MDS."""
    import torch
    from .torch_mds import run_mds, get_device
    from .partitioned import partitioned_mds

    print(f"Loading contacts from {input}...")

    if input.endswith(('.mcool', '.cool')):
        bins_df, contact_mat = load_contacts_from_mcool(
            input, resolution, chrom
        )
    else:
        print("Error: Currently only .mcool/.cool files are supported")
        return

    print(f"Contact matrix shape: {contact_mat.shape}")
    print(f"Using device: {get_device(device)}")

    contact_tensor = torch.from_numpy(contact_mat.astype(np.float64))

    tad_regions = None
    if tad_bed:
        from uchrom.strc.tad.utils import load_tad_from_bed, tad_regions_to_bin_indices
        regions = load_tad_from_bed(tad_bed)
        tad_regions = tad_regions_to_bin_indices(regions, bins_df, chrom)
        print(f"Loaded {len(tad_regions)} TAD regions from {tad_bed}")

    print("Running MDS...")
    if partitioned:
        coords = partitioned_mds(
            contact_tensor,
            tad_regions=tad_regions,
            device=device,
            res_ratio=res_ratio,
            alpha=alpha,
            alpha2=alpha2,
            weight=weight,
            n_iter=n_iter,
            verbose=verbose,
            n_workers=n_workers
        )
    else:
        coords = run_mds(
            contact_tensor,
            alpha=alpha,
            device=device,
            weight=weight,
            n_iter=n_iter,
            lr=lr,
            verbose=verbose
        )

    save_structure(coords, bins_df, output)
    print("Done!")


if __name__ == "__main__":
    fire.Fire(main)
