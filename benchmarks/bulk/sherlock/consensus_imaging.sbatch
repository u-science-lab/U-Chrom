#!/bin/bash
# Imaging references (imaging.py): per locus pair the median / mean / count of the imaged distances + the
# mean-distance embedding, for Su 2020 genome-scale (1,787 cells x 2 homologs x 1,041 loci, cis + trans),
# Su 2020 chr21 (all traces, 651 x 50 kb) and Takei 2021 mESC 1 Mb (201 cells, 2,460 loci, cis + trans);
# then the imaging-calibrated alpha per cell type (calibrate.py; the "oracle" variant of tasks_real.tsv).
# Laptop: 300 Su cells in 47 s (all cells ~5 min); chr21 (~7,600 traces) and Takei similar.
#
#   sbatch benchmarks/bulk/sherlock/consensus_imaging.sbatch
#SBATCH --job-name=cons-img
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out

source "$SCRATCH/uchrom-nd/repo-consensus/benchmarks/bulk/sherlock/consensus_env.sh"
for ds in su2020_genome su2020_chr21 takei2021_1mb; do
  [ -f "$CS/imaging/$ds.npz" ] || $PY "$BC/imaging.py" --dataset "$ds" --out "$CS/imaging/$ds.npz"
done
$PY "$BC/calibrate.py" --imaging "$CS/imaging/su2020_genome.npz" --cell imr90 --resolution 250000 --out "$CS/calib/imr90.json"
$PY "$BC/calibrate.py" --imaging "$CS/imaging/takei2021_1mb.npz" --cell bonev --resolution 250000 --out "$CS/calib/bonev.json"
ls -la "$CS/imaging" "$CS/calib"
