#!/bin/bash
# Fig. 3 precision table of the frozen `robust` method: the ED Table 2 metrics of
# benchmarks/fig3/a_nucdyn_engine_score.py (precision with / without mirror images, violations, vs the
# GEO models) on the full Stevens 2017 tables of cells 1-8 (cells 1-4: $RB/real/models/frozen, cells 5-8:
# $RB/test/real/models; 100 kb, 10 models, seed 1, frozen build).
#
#   sbatch robust_fig3_score.sbatch
#SBATCH --job-name=rb-f3score
#SBATCH --partition=normal,owners
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-robust/benchmarks/screcon/sherlock/_env_robust.sh"
D=$RB/fig3/models
mkdir -p "$D"
for c in 1 2 3 4; do ln -sf "$RB/real/models/frozen/cell$c.npz" "$D/cell$c.npz"; done
for c in 5 6 7 8; do ln -sf "$RB/test/real/models/cell$c.npz" "$D/cell$c.npz"; done
$PY $REPO/benchmarks/fig3/a_nucdyn_engine_score.py --runs "$D" --labels robust --cells 1-8 --geo-dir "$GEO" \
  --out "$RB/fig3/a_robust_score_all.json"
echo done
