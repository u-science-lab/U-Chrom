# benchmarks/schicluster_parity/results

| File | What | Run |
|---|---|---|
| `parity.json` | U-Chrom's scHiCluster imputation (`uchrom.emb.hic.schicluster_impute`) against the authors' code (`impute_cpu` of `schicluster` 1.3.2 from PyPI, github.com/zhoujt1994/scHiCluster) on every cell of the scHiCAR mouse cortex `.scool` (5,313 cells, 1 Mb, chr1-19; `run.py`): per chromosome the share of identical entries of the binarised features (`hicluster_cpu`'s top 20 % per cell), the share of cells whose binarised features are identical, the largest difference of the imputed maps of three cells, the times of both. `{"results", "provenance"}` | 2026-10-14, Sherlock job 47753795 (node sh04-05n13, 8 CPUs) |

## Result

Every binarised entry of every cell and chromosome is identical (5,313 cells x 19 chromosomes), and the imputed maps
of the sampled cells are equal bit for bit (largest difference 0.0): U-Chrom runs the authors' operations
(`log2(A + Aᵀ + 1)`, their cumulative-sum mean filter rounded to 8 decimals, `np.dot` / the Frobenius norm of the
random walk) with single-threaded BLAS, as the authors' process pool does.  A 500-cell trial with the earlier
batched implementation (job 47750855) differed in the last bits (1e-15) and in one binarised entry at a percentile tie.

Downstream, the agent benchmark's R4 (all 5,313 cells: features with 20 PCs per chromosome, PCA to 20, kNN purity
of the 22 published cell types at k = 30; `benchmarks/fig6/agent_bench/v3/truth/schic.py`) gives 0.24019072714724887
with U-Chrom's `embed_contacts` and with the authors' code (job 47754119; U-Chrom before the fix: 0.2433).

## Times

`parity.json`'s times include reading each cell's chromosome with cooler, in the authors' 8-process pool for theirs
and one cell after the other in `run.py` for U-Chrom's, so they measure this script's I/O more than the library
(authors 378 s, U-Chrom 1,120 s).  The library's own path reads each cell once (`scool_cell_features`): the R4
computation above takes 325 s on 16 threads (job 47754119), the authors' 289 / 304 s on 8 processes; U-Chrom before
the fix took 827 / 864 s.
