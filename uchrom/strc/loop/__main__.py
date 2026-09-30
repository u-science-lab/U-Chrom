"""CLI: ``python -m uchrom.strc.loop`` — run axis-wise F loop calling."""

from __future__ import annotations

import fire

from uchrom import ChromData
from uchrom.io import save_particles

from .axiswise_f import call_loops_axiswise_f, LoopCallerParams


def main(
    input,
    output,
    chrom,
    device: str = "auto",
    cut_lo: float = 1e5,
    cut_up: float = 1e6,
    inner_cut: float = 2.5e4,
    outer_cut: float = 5e4,
    fdr_cutoff: float = 0.1,
    pval_cutoff: float = 1e-5,
    gap: float = 5e4,
    k_sigma: float = 4.0,
    frac: float = 0.1,
    verbose: bool = True,
    format: str = "chromdata",
    key_added: str = "loops.axiswise_f",
):
    """Call loops on a single chromosome with the ArcFISH-style axis F-test.

    Parameters
    ----------
    input : path to a ChromData store (``.chromdata.zarr`` / ``.cdz``) or a
        FOF-CT ``.csv``
    output : path to save result.
        - ``.bedpe`` → write BEDPE TSV (six columns + score)
        - ``.csv`` → full CSV with all columns
        - ``.chromdata.zarr`` / ``.cdz`` → update
          the input ChromData with ``results[key_added]`` (default
          ``'loops.axiswise_f'``) and write it to ``output``.
    chrom : chromosome to process (required).
    device : ``'auto' | 'cpu' | 'cuda' | 'mps'``
    """
    from uchrom.core.zarrcd import container_kind

    input = str(input)
    if container_kind(input) is not None:
        cd = ChromData.read(input)
    else:
        cd = ChromData.from_fofct(input)

    params = LoopCallerParams(
        cut_lo=cut_lo, cut_up=cut_up,
        inner_cut=inner_cut, outer_cut=outer_cut,
        fdr_cutoff=fdr_cutoff, pval_cutoff=pval_cutoff,
        gap=gap, k_sigma=k_sigma, frac=frac,
    )
    loops = call_loops_axiswise_f(
        cd, chrom=chrom, params=params, device=device,
        key_added=key_added, verbose=verbose,
    )

    out = str(output)
    if out.endswith(".bedpe"):
        loops.to_csv(out, sep="\t", index=False,
                     columns=["chrom1", "start1", "end1",
                              "chrom2", "start2", "end2", "score"])
    elif out.endswith(".csv"):
        loops.to_csv(out, index=False)
    else:
        cd.write(out)

    if verbose:
        print(f"Called {len(loops)} loops on {chrom} → {output}")


if __name__ == "__main__":
    fire.Fire(main)
