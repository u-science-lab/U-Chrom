"""[Fig. 3a feasibility; copied from the data-check scratch dir.  Run from a working
directory holding a clone of github.com/seqcode/miniMDS (commit 9915d21) and a venv
`venv_minimds` with numpy 1.26 / scikit-learn 1.5 (miniMDS --partitioned fails under
NumPy 2); inputs come from remote_slice.py.  Results: u-chrom-paper/figures/fig3/feasibility/a_mds_vs_minimds_*.json]

miniMDS vs uchrom on genuine Rao 2014 IMR90 in situ Hi-C chr21 (4DN 4DNFIR1JDZH7,
GRCh38), sliced remotely by remote_slice.py at 100 kb and 25 kb, ICE-balanced (4DN weights).

Run: PYTHONPATH=<U-Chrom worktree>:<this dir> ~/micromamba/envs/pantheon/bin/python run_rao.py
miniMDS runs as a subprocess in venv_minimds (numpy 1.26 / sklearn 1.5.0)."""
import json, os, subprocess, time, warnings
import numpy as np, torch, cooler
warnings.filterwarnings('ignore')
D = os.path.dirname(os.path.abspath(__file__)); os.chdir(D)
from compare import load_mm, compare, fit_to_hic
from uchrom.recon.bulk.mds import run_mds, partitioned_mds
MM_PY = os.path.join(D, 'venv_minimds/bin/python')


def write_bed(M, res, path):
    iu = np.triu_indices(len(M), 1); v = M[iu]; k = v > 0
    with open(path, 'w') as fh:
        for i, j, x in zip(iu[0][k], iu[1][k], v[k]):
            fh.write(f'chr21\t{i*res}\t{(i+1)*res}\tchr21\t{j*res}\t{(j+1)*res}\t{x:.10g}\n')


def minimds(bed, out, part=False, extra=()):
    cmd = [MM_PY, 'miniMDS/minimds.py', '-o', out] + (['--partitioned'] if part else []) + list(extra) + [bed]
    t = time.time(); r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return round(time.time() - t, 2)


out = {}
for res_kb in (100, 25):
    res = res_kb * 1000
    M = np.nan_to_num(cooler.Cooler(f'IMR90_rao_chr21_{res_kb}kb.cool').matrix(balance=True)[:])
    np.fill_diagonal(M, 0); n = len(M)
    bed = f'RAO_IMR90_21_{res_kb}kb.bed'; write_bed(M, res, bed)
    r = {'n_bins': n}
    r['minimds_full_s'] = minimds(bed, f'rao_mm_full_{res_kb}kb.tsv')
    r['minimds_full_rep2_s'] = minimds(bed, f'rao_mm_full_{res_kb}kb_rep2.tsv')
    mm, mm2 = load_mm(f'rao_mm_full_{res_kb}kb.tsv', n), load_mm(f'rao_mm_full_{res_kb}kb_rep2.tsv', n)
    t = time.time(); c, mask = run_mds(torch.from_numpy(M.copy()), alpha=4, device='cpu'); r['uchrom_run_mds_s'] = round(time.time() - t, 2)
    U = np.full((n, 3), np.nan); U[mask] = c
    r.update(n_uchrom=int(mask.sum()), n_minimds=int(np.isfinite(mm).all(1).sum()),
             minimds_full_vs_uchrom=compare(mm, U), minimds_full_rep1_vs_rep2=compare(mm, mm2),
             fit_hic_uchrom=fit_to_hic(U, M), fit_hic_minimds=fit_to_hic(mm, M))
    if res_kb == 25:
        r['minimds_part_s'] = minimds(bed, f'rao_mm_part_{res_kb}kb.tsv', part=True)
        minimds(bed, f'rao_mm_part_{res_kb}kb_rep2.tsv', part=True)
        mp, mp2 = load_mm(f'rao_mm_part_{res_kb}kb.tsv', n), load_mm(f'rao_mm_part_{res_kb}kb_rep2.tsv', n)
        t = time.time(); P = partitioned_mds(torch.from_numpy(M.copy()), device='cpu', res_ratio=10); r['uchrom_partitioned_s'] = round(time.time() - t, 2)
        r.update(minimds_part_vs_uchrom_part=compare(mp, P), minimds_part_rep1_vs_rep2=compare(mp, mp2),
                 fit_hic_uchrom_part=fit_to_hic(P, M), fit_hic_minimds_part=fit_to_hic(mp, M))
    out[f'{res_kb}kb'] = r
    print(res_kb, json.dumps(r, indent=1, default=float))
json.dump(out, open('rao_results.json', 'w'), indent=1, default=float)
