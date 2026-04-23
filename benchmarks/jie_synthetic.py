"""Synthetic benchmark for uchrom.im.trace.jie.

Generates Gaussian-chain polymer walks with known ground-truth fiber
assignments, contaminates them with per-locus dropout, decoy spots, and
optional sister pairing, then reports:

- **Ploidy recall**: fraction of (cell, chrom) where the called fiber
  count matches the true count.
- **Spot-assignment accuracy**: per-fiber fraction of output spots
  whose ground-truth fiber matches the majority of the called fiber's
  spots, macro-averaged over fibers.
- **Sister recall / precision**: for cells with sister pairs, whether
  the two fibers end up in the same sister_group.

Usage::

    python benchmarks/jie_synthetic.py --n-cells 30 --seed 0
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from uchrom.im.trace import align_spots, SpotAlignerParams


@dataclass
class SynthConfig:
    n_cells: int = 30
    n_loci: int = 15
    bin_size_bp: int = 25_000
    tau_true: float = 0.012
    l_p_bp: float = 150.0
    dropout_rate: float = 0.15
    n_decoys_per_cell: int = 8
    decoy_pos_sigma_nm: float = 3000.0
    locus_sigma_nm: float = 30.0
    ploidy_probs: tuple = (0.2, 0.5, 0.2, 0.1)  # P(ploidy = 1, 2, 3, 4)
    sister_prob: float = 0.2
    sister_offset_sigma_nm: float = 80.0
    chrom: str = "chr1"


def _gen_walk(rng, n_loci, step_sigma_axis, offset=None):
    steps = rng.normal(0, step_sigma_axis, (n_loci, 3))
    w = np.cumsum(steps, axis=0)
    if offset is not None:
        w = w + offset
    return w


def make_synthetic_dataset(cfg: SynthConfig, seed: int = 0):
    """Return (spots_df, truth_df).

    ``truth_df`` has columns ``spot_id, true_fiber_id, cell_id, chrom,
    is_decoy``.  Decoys carry ``true_fiber_id = -1``.
    """
    rng = np.random.default_rng(seed)
    step_sigma = np.sqrt(2 * cfg.l_p_bp * cfg.tau_true * cfg.bin_size_bp / 3)
    bin_bp = np.arange(cfg.n_loci) * cfg.bin_size_bp

    spot_rows = []
    truth_rows = []
    next_spot = 0
    next_fiber = 0
    per_cell_truth = {}

    for ci in range(cfg.n_cells):
        cell_id = f"cell_{ci:02d}"
        ploidy = int(rng.choice([1, 2, 3, 4], p=list(cfg.ploidy_probs)))
        # Optionally replace one fiber with a sister pair
        has_sister = ploidy >= 2 and rng.random() < cfg.sister_prob

        fibers = []
        fiber_types = []
        if has_sister:
            base = _gen_walk(rng, cfg.n_loci, step_sigma)
            jitter = rng.normal(0, cfg.sister_offset_sigma_nm, base.shape)
            fibers.append(base)
            fibers.append(base + jitter)
            fiber_types.append("sister0")
            fiber_types.append("sister1")
            extra = ploidy - 2
        else:
            extra = ploidy

        for _ in range(extra):
            off = rng.normal(0, 3000, 3)  # well separated centres
            fibers.append(_gen_walk(rng, cfg.n_loci, step_sigma, off))
            fiber_types.append("solo")

        fiber_ids_for_cell = []
        for fi, walk in enumerate(fibers):
            fid = next_fiber
            next_fiber += 1
            fiber_ids_for_cell.append(fid)
            keep_mask = rng.random(cfg.n_loci) > cfg.dropout_rate
            for li in np.where(keep_mask)[0]:
                pos = walk[li] + rng.normal(0, cfg.locus_sigma_nm, 3)
                spot_rows.append(dict(
                    spot_id=next_spot,
                    cell_id=cell_id,
                    chrom=cfg.chrom,
                    start=int(bin_bp[li]),
                    end=int(bin_bp[li] + cfg.bin_size_bp),
                    x=float(pos[0]), y=float(pos[1]), z=float(pos[2]),
                ))
                truth_rows.append(dict(
                    spot_id=next_spot, true_fiber_id=fid,
                    cell_id=cell_id, chrom=cfg.chrom,
                    is_decoy=False,
                ))
                next_spot += 1

        # Decoys: random positions at random loci
        for _ in range(cfg.n_decoys_per_cell):
            li = int(rng.integers(0, cfg.n_loci))
            pos = rng.normal(0, cfg.decoy_pos_sigma_nm, 3)
            spot_rows.append(dict(
                spot_id=next_spot, cell_id=cell_id, chrom=cfg.chrom,
                start=int(bin_bp[li]),
                end=int(bin_bp[li] + cfg.bin_size_bp),
                x=float(pos[0]), y=float(pos[1]), z=float(pos[2]),
            ))
            truth_rows.append(dict(
                spot_id=next_spot, true_fiber_id=-1,
                cell_id=cell_id, chrom=cfg.chrom, is_decoy=True,
            ))
            next_spot += 1

        per_cell_truth[cell_id] = {
            "ploidy": ploidy,
            "fiber_ids": fiber_ids_for_cell,
            "fiber_types": fiber_types,
            "has_sister": has_sister,
        }

    spots_df = pd.DataFrame(spot_rows)
    truth_df = pd.DataFrame(truth_rows)
    return spots_df, truth_df, per_cell_truth


def evaluate(cd, truth_df, per_cell_truth, cfg: SynthConfig):
    """Compute accuracy metrics for a jie run."""
    # Join called trace_id back onto truth
    got = cd.spots[["spot_id", "cell_id", "trace_id"]].copy()
    got["trace_id"] = got["trace_id"].astype(int)
    merged = truth_df.merge(got, on=["spot_id", "cell_id"], how="left")

    # --- Ploidy (sister-aware: compare n_sister_groups to true distinct fibers)
    ploidy_df = cd.results["ploidy"]
    correct_ploidy = 0
    correct_sister = 0
    n_with_sister = 0
    total_cells = 0
    for _, row in ploidy_df.iterrows():
        cell_id = row["cell_id"]
        t = per_cell_truth[cell_id]
        # For sister cells, ground truth distinct-entity count = ploidy - 1 if sister pair exists
        true_entities = t["ploidy"] - (1 if t["has_sister"] else 0)
        n_sg = int(row["n_sister_groups"])
        if n_sg == true_entities:
            correct_ploidy += 1
        if t["has_sister"]:
            n_with_sister += 1
            # Check sister fibers grouped: both called fibers for this cell
            # should share a sister_group.
            cell_traces = cd.traces[cd.traces["cell_id"] == cell_id]
            # Count pairs sharing sister_group
            sg_counts = Counter(cell_traces["sister_group"].tolist())
            if any(v >= 2 for v in sg_counts.values()):
                correct_sister += 1
        total_cells += 1

    # --- Spot-assignment accuracy: per called trace, dominant true_fiber_id
    #     must be the "correct" one (not -1 / decoy).
    trace_purity = []
    decoy_in_trace = 0
    total_called_spots = 0
    for tid, g in merged.dropna(subset=["trace_id"]).groupby("trace_id"):
        total_called_spots += len(g)
        counts = g["true_fiber_id"].value_counts()
        top_fiber = counts.idxmax()
        purity = counts.iloc[0] / len(g)
        trace_purity.append(purity)
        decoy_in_trace += (g["true_fiber_id"] == -1).sum()

    # --- Coverage: fraction of true (non-decoy) spots that got assigned
    n_true = (~truth_df["is_decoy"]).sum()
    n_true_assigned = merged[~merged["is_decoy"]]["trace_id"].notna().sum()

    return {
        "ploidy_accuracy": correct_ploidy / total_cells,
        "sister_recall": (correct_sister / n_with_sister
                          if n_with_sister else float("nan")),
        "cells_with_sister": n_with_sister,
        "mean_trace_purity": float(np.mean(trace_purity)),
        "decoy_contamination_rate": decoy_in_trace / total_called_spots,
        "true_spot_recall": n_true_assigned / n_true,
        "n_cells": total_cells,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-cells", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dropout", type=float, default=0.15)
    ap.add_argument("--n-decoys", type=int, default=8)
    ap.add_argument("--n-loci", type=int, default=15)
    args = ap.parse_args()

    cfg = SynthConfig(
        n_cells=args.n_cells,
        dropout_rate=args.dropout,
        n_decoys_per_cell=args.n_decoys,
        n_loci=args.n_loci,
    )
    spots_df, truth_df, truth = make_synthetic_dataset(cfg, seed=args.seed)
    print(f"Synthetic: {len(spots_df)} spots across {cfg.n_cells} cells, "
          f"{cfg.n_loci} loci, dropout={cfg.dropout_rate}, "
          f"{cfg.n_decoys_per_cell} decoys/cell")

    cd = align_spots(
        spots_df,
        params=SpotAlignerParams(
            min_spots_per_fiber=max(5, int(cfg.n_loci * 0.4)),
            max_skip=3,
            gap_penalty=3.0,
            verbose=False,
        ),
    )
    metrics = evaluate(cd, truth_df, truth, cfg)
    print("\nMetrics:")
    for k, v in metrics.items():
        print(f"  {k:28s} {v:.3f}" if isinstance(v, float) else f"  {k:28s} {v}")


if __name__ == "__main__":
    main()
