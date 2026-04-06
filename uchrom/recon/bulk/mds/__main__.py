"""
CLI entry point for MDS-based 3D structure reconstruction.

Usage:
    python -m uchrom.recon.bulk.mds input.mcool output.csv --resolution 100000 --device cuda
"""

import argparse
import sys

import numpy as np
import pandas as pd


def load_contacts_from_mcool(path: str, resolution: int, chrom: str = None):
    """
    Load contact data from mcool file.

    Args:
        path: Path to .mcool file
        resolution: Resolution to use (bp)
        chrom: Chromosome to extract (optional, for intra-chromosomal)

    Returns:
        Tuple of (bin_info_df, contact_matrix)
    """
    from cooler import Cooler

    # Open cooler at specified resolution
    if '::' in path:
        uri = path
    else:
        uri = f"{path}::resolutions/{resolution}"

    try:
        clr = Cooler(uri)
    except Exception:
        # Try without resolution suffix for .cool files
        clr = Cooler(path)

    # Get bins and pixels
    bins = clr.bins()[:]

    if chrom is not None:
        # Get single chromosome
        chrom_bins = bins[bins['chrom'] == chrom].copy()
        chrom_bins['idx'] = range(len(chrom_bins))

        matrix = clr.matrix(balance=True).fetch(chrom)
        # Replace NaN with 0
        matrix = np.nan_to_num(matrix, nan=0.0)

        return chrom_bins, matrix
    else:
        # Get all chromosomes
        matrix = clr.matrix(balance=True)[:]
        matrix = np.nan_to_num(matrix, nan=0.0)

        bins['idx'] = range(len(bins))
        return bins, matrix


def save_structure(coords: np.ndarray, bins_df: pd.DataFrame, output_path: str):
    """
    Save 3D structure to CSV file.

    Args:
        coords: N x 3 coordinate array
        bins_df: DataFrame with bin information
        output_path: Output file path
    """
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


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct 3D chromatin structure from Hi-C data using MDS."
    )
    parser.add_argument(
        "input",
        help="Input file path (.mcool, .cool, or Hi-C BED)"
    )
    parser.add_argument(
        "output",
        help="Output CSV file path"
    )
    parser.add_argument(
        "--resolution", "-r",
        type=int,
        default=100000,
        help="Resolution in base pairs (default: 100000)"
    )
    parser.add_argument(
        "--chrom", "-c",
        type=str,
        default=None,
        help="Chromosome to process (default: all)"
    )
    parser.add_argument(
        "--device", "-d",
        type=str,
        default="auto",
        choices=["auto", "cuda", "mps", "cpu"],
        help="Compute device (default: auto)"
    )
    parser.add_argument(
        "--alpha", "-a",
        type=float,
        default=4.0,
        help="Alpha exponent for contact-to-distance conversion (default: 4.0)"
    )
    parser.add_argument(
        "--alpha2",
        type=float,
        default=2.5,
        help="Short-range alpha for partitioned mode (default: 2.5)"
    )
    parser.add_argument(
        "--weight", "-w",
        type=float,
        default=0.05,
        help="Distance decay prior weight (default: 0.05)"
    )
    parser.add_argument(
        "--n-iter",
        type=int,
        default=1000,
        help="Maximum number of MDS iterations (default: 1000)"
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=0.01,
        help="Learning rate for optimization (default: 0.01)"
    )
    parser.add_argument(
        "--res-ratio", "-l",
        type=int,
        default=10,
        help="Resolution ratio for partitioned mode (default: 10)"
    )
    parser.add_argument(
        "--partitioned",
        action="store_true",
        help="Use partitioned MDS for high-resolution data"
    )
    parser.add_argument(
        "--tad-bed",
        type=str,
        default=None,
        help="Path to TAD regions BED file (for partitioned mode)"
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=1,
        help="Number of parallel workers for partitioned mode (default: 1)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress information"
    )

    args = parser.parse_args()

    # Import here to avoid slow imports for --help
    import torch
    from .torch_mds import run_mds, get_device
    from .partitioned import partitioned_mds

    print(f"Loading contacts from {args.input}...")

    # Load contact data
    if args.input.endswith(('.mcool', '.cool')):
        bins_df, contact_mat = load_contacts_from_mcool(
            args.input, args.resolution, args.chrom
        )
    else:
        # TODO: Support Hi-C BED format
        print("Error: Currently only .mcool/.cool files are supported")
        sys.exit(1)

    print(f"Contact matrix shape: {contact_mat.shape}")
    print(f"Using device: {get_device(args.device)}")

    # Convert to torch tensor
    contact_tensor = torch.from_numpy(contact_mat.astype(np.float64))

    # Load external TAD regions if provided
    tad_regions = None
    if args.tad_bed:
        from uchrom.strc.tad.utils import load_tad_from_bed, tad_regions_to_bin_indices
        regions = load_tad_from_bed(args.tad_bed)
        tad_regions = tad_regions_to_bin_indices(regions, bins_df, args.chrom)
        print(f"Loaded {len(tad_regions)} TAD regions from {args.tad_bed}")

    # Run MDS
    print("Running MDS...")
    if args.partitioned:
        coords = partitioned_mds(
            contact_tensor,
            tad_regions=tad_regions,
            device=args.device,
            res_ratio=args.res_ratio,
            alpha=args.alpha,
            alpha2=args.alpha2,
            weight=args.weight,
            n_iter=args.n_iter,
            verbose=args.verbose,
            n_workers=args.n_workers
        )
    else:
        coords = run_mds(
            contact_tensor,
            alpha=args.alpha,
            device=args.device,
            weight=args.weight,
            n_iter=args.n_iter,
            lr=args.lr,
            verbose=args.verbose
        )

    # Save result
    save_structure(coords, bins_df, args.output)
    print("Done!")


if __name__ == "__main__":
    main()
