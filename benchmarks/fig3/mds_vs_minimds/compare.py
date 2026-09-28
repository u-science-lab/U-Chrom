"""Compare miniMDS (seqcode/miniMDS) and uchrom.recon.bulk.mds on the same
balanced IMR90(?) chr21 matrices (30 / 90 / 150 kb).

Run with PYTHONPATH=<U-Chrom worktree> ~/micromamba/envs/pantheon/bin/python compare.py
Needs mm_{full,part}_*kb.tsv from run_minimds.py and mat_*kb.npy from make_bed.py.
"""
import json, os, time, warnings
import numpy as np, torch
from scipy.stats import pearsonr, spearmanr
from scipy.spatial.distance import pdist
from uchrom.recon.bulk.mds import run_mds, partitioned_mds
from uchrom.recon.bulk.mds.transforms import procrustes_alignment, apply_transform

warnings.filterwarnings('ignore')
D = os.path.dirname(os.path.abspath(__file__)); os.chdir(D)


def load_mm(path, n):
    with open(path) as fh:
        chrom = fh.readline(); res = float(fh.readline()); start = int(fh.readline())
        arr = np.loadtxt(fh)
    off = int(start // res)
    X = np.full((n, 3), np.nan)
    X[off + arr[:, 0].astype(int)] = arr[:, 1:]
    return X


def rg_norm(X):
    X = X - X.mean(0)
    return X / np.sqrt((X ** 2).sum(1).mean())


def compare(A, B):
    ok = np.isfinite(A).all(1) & np.isfinite(B).all(1) & (np.abs(A).sum(1) > 0) & (np.abs(B).sum(1) > 0)
    a, b = rg_norm(A[ok]), rg_norm(B[ok])
    da, db = pdist(a), pdist(b)
    R, t, s = procrustes_alignment(a, b, scale=True)
    a2 = apply_transform(a, R, t, s)
    # also mirror (MDS is reflection-invariant; procrustes_alignment forbids reflections)
    R2, t2, s2 = procrustes_alignment(a * np.array([1, 1, -1]), b, scale=True)
    a3 = apply_transform(a * np.array([1, 1, -1]), R2, t2, s2)
    rmsd = min(np.sqrt(((a2 - b) ** 2).sum(1).mean()), np.sqrt(((a3 - b) ** 2).sum(1).mean()))
    return dict(n=int(ok.sum()), pearson=round(pearsonr(da, db)[0], 4),
                spearman=round(spearmanr(da, db)[0], 4), rmsd_rg=round(float(rmsd), 4))


def fit_to_hic(X, M, alpha=4.0):
    """Spearman / Pearson of structure distance vs Hi-C-implied distance c^(-1/alpha) over nonzero pairs."""
    ok = np.isfinite(X).all(1) & (np.abs(X).sum(1) > 0)
    iu = np.triu_indices(len(M), 1)
    sel = ok[iu[0]] & ok[iu[1]] & (M[iu] > 0)
    d = np.linalg.norm(X[iu[0][sel]] - X[iu[1][sel]], axis=1)
    h = M[iu][sel] ** (-1 / alpha)
    return dict(spearman=round(spearmanr(d, h)[0], 4), pearson=round(pearsonr(d, h)[0], 4))


def main():
  out = {}
  for res in (150, 90, 30):
      M = np.load(f'mat_{res}kb.npy'); n = len(M)
      t = time.time()
      c, mask = run_mds(torch.from_numpy(M.copy()), alpha=4, device='cpu')
      t_u = time.time() - t
      U = np.full((n, 3), np.nan); U[mask] = c
      mm = load_mm(f'mm_full_{res}kb.tsv', n)
      r = dict(uchrom_run_mds_s=round(t_u, 2), n_bins=n, n_uchrom=int(mask.sum()),
               n_minimds=int(np.isfinite(mm).all(1).sum()),
               minimds_full_vs_uchrom=compare(mm, U),
               fit_hic_uchrom=fit_to_hic(U, M), fit_hic_minimds=fit_to_hic(mm, M))
      rep = f'mm_full_{res}kb_rep2.tsv'
      if os.path.exists(rep):
          r['minimds_full_rep1_vs_rep2'] = compare(mm, load_mm(rep, n))
      if res == 30:
          t = time.time()
          P = partitioned_mds(torch.from_numpy(M.copy()), device='cpu', res_ratio=10)
          r['uchrom_partitioned_s'] = round(time.time() - t, 2)
          mp = load_mm('mm_part_30kb.tsv', n)
          r['minimds_part_vs_uchrom_part'] = compare(mp, P)
          r['minimds_part_vs_minimds_full'] = compare(mp, mm)
          r['uchrom_part_vs_uchrom_full'] = compare(P, U)
          r['fit_hic_uchrom_part'] = fit_to_hic(P, M)
          r['fit_hic_minimds_part'] = fit_to_hic(mp, M)
          if os.path.exists('mm_part_30kb_rep2.tsv'):
              r['minimds_part_rep1_vs_rep2'] = compare(mp, load_mm('mm_part_30kb_rep2.tsv', n))
      np.save(f'uchrom_full_{res}kb.npy', U)
      out[f'{res}kb'] = r
      print(res, json.dumps(r, indent=1))
  json.dump(out, open('compare_results.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
