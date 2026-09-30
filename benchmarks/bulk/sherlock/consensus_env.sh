# Settings of the consensus-structure jobs (benchmarks/bulk/consensus), sourced by consensus_*.sbatch.
#
#   $SCRATCH/uchrom-nd/repo-consensus             repo copy of branch Nanguage/bulk-consensus (rsync from the laptop)
#   $GROUP_HOME/$USER/uchrom-nd/venv-consensus    Python 3.12 env of these jobs (consensus_setup.sbatch creates it the
#                                                 way setup_deconv.sbatch creates venv-deconv, and builds the engine wheel
#                                                 of this branch into it; the deconv jobs keep venv-deconv untouched)
#   $GROUP_HOME/$USER/uchrom-nd/minimds           clone of github.com/seqcode/miniMDS @ 9915d21 (baseline, full mode)
#   $SCRATCH/uchrom-nd/data                       example data shared with the bulk jobs (mcools, Su 2020, Takei 2021)
#   $SCRATCH/uchrom-nd/runs/consensus/            outputs: imaging/, calib/, models/, base/, scores/, scaling/, tables/
export VENV=${VENV:-$GROUP_HOME/$USER/uchrom-nd/venv-consensus}
export REPO=${REPO:-$SCRATCH/uchrom-nd/repo-consensus}
source "$REPO/benchmarks/bulk/sherlock/_env.sh"
BC=$REPO/benchmarks/bulk/consensus
MINIMDS=$BASE/minimds
CS=$W/runs/consensus
mkdir -p "$CS"/{imaging,calib,models,base,scores,scaling,tables}
export PYTHONUNBUFFERED=1

# line N of a task table (tab-separated, '#' comments and the header skipped)
task_line() {
  grep -v '^#' "$1" | sed -n "$(( $2 + 1 ))p"
}
