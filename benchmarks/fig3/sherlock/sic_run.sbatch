#!/bin/bash
# Si-C (Meng et al. 2021, Nat Commun 12:4369) as released: github.com/TheMengLab/Si-C HEAD 2a4d445
# (= Zenodo 10.5281/zenodo.4889467), modeling/get3Dstructure.sh on its bundled Stevens 2017 Cell 1
# contacts, 100 kb, REPNUM replicas (paper: 20).  Uses the precompiled x86-64 binaries shipped in
# the repo (the C sources cannot be compiled: they include files that are not in the repo).
# The script starts every replica with nohup in the background; this job waits for them.
#
#   sbatch --export=ALL,REPNUM=20 benchmarks/fig3/sherlock/sic_run.sbatch
#SBATCH --job-name=sic-run
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=20
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out

set -uo pipefail
W=$SCRATCH/uchrom-nd; R=${REPNUM:-20}
RUN=$W/runs/sic_100kb_${R}rep
rm -rf "$RUN"; cp -r "$W/sic/modeling" "$RUN"; cd "$RUN"
echo "host=$(hostname) job=$SLURM_JOB_ID cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2) start=$(date +%s)"
sed -i "s/^repnum=.*/repnum=${R}	#Number of structure replicas to generate/" get3Dstructure.sh
t0=$(date +%s)
bash get3Dstructure.sh > get3Dstructure.log 2>&1
t1=$(date +%s); echo "contact preparation + launch: $((t1 - t0)) s"
# wait for the background replicas (own processes on this node only)
while pgrep -u "$USER" -f "doall.sh ${SLURM_JOB_ID:+}" > /dev/null; do sleep 300; done
t2=$(date +%s); echo "structure calculation: $((t2 - t1)) s; total $((t2 - t0)) s"
ls MD_simulation/100kb_${R}replica/*/genome.pdb 2>/dev/null | wc -l
for d in MD_simulation/100kb_${R}replica/*/; do echo "$d $(stat -c %Y $d/genome.pdb 2>/dev/null)"; done
echo done
