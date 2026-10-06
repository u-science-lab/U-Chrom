#!/bin/bash
# ORIGINAL IGM (edbb331 + lammpgen serial) on its own demo (WTC11 Hi-C 2 Mb, male, demo
# configuration) with S structures, one seed per array task: the reference populations
# for igm_demo_compare.py.  One node, ipyparallel with one engine per core (IGM's own
# parallel mode; the M-step is one LAMMPS task per structure, the A-step one task per
# 1,000 pairs).
#
# Budget: IGM README "250 cores x 10-15 h" for 1,000 structures at 200 kb; the demo has
# ~10x fewer beads -> estimated 150-400 CPU-h per seed at S = 1,000 (32 cores x 5-12 h).
# S <= 16 uses IGM's serial controller (installation smoke test, ~1-2 h).
#
#   sbatch --export=ALL,S=8 benchmarks/bulk/sherlock/orig_demo.sbatch          # smoke test
#   sbatch --array=1-2 benchmarks/bulk/sherlock/orig_demo.sbatch                # S = 1000, 2 seeds
#SBATCH --job-name=bulk-igm-orig
#SBATCH --partition=xiaojie,owners,normal
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --output=%x-%A_%a.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"
ENV=$IGMO/env
export PATH=$ENV/bin:$PATH LD_LIBRARY_PATH=$ENV/lib:${LD_LIBRARY_PATH:-}
S=${S:-1000}
SEED=${SLURM_ARRAY_TASK_ID:-1}
RD=$RUNS/igm_demo/orig_S${S}_s${SEED}
mkdir -p "$RD"
cp "$HCS" "$RD/"
CONTROLLER=ipyparallel
[ "$S" -le 16 ] && CONTROLLER=serial
python - "$IGMO/igm/demo/config_file.json" "$RD/config.json" "$S" "$SEED" "$CONTROLLER" "$IGMO/lammpgen/src/lmp_serial" <<'EOF'
import json, sys
src, dst, S, seed, controller, lmp = sys.argv[1:]
c = json.load(open(src))
c["model"]["population_size"] = int(S)
c["optimization"]["kernel_opts"]["lammps"]["lammps_executable"] = lmp
c["optimization"]["kernel_opts"]["lammps"]["seed"] = 6535 + 1000 * (int(seed) - 1)
c["parallel"]["controller"] = controller
json.dump(c, open(dst, "w"), indent=1)
print(json.dumps({"population_size": S, "seed": c["optimization"]["kernel_opts"]["lammps"]["seed"], "controller": controller}))
EOF
cd "$RD"
if [ "$CONTROLLER" = ipyparallel ]; then
  # ipyparallel 6.3 (IGM's era; 8.x fails to start its controller on Python 3.6).
  # Wait for every engine to register and give up after 10 min instead of hanging.
  timeout 120 ipcluster start -n "$SLURM_CPUS_PER_TASK" --daemonize=True
  python - "$SLURM_CPUS_PER_TASK" <<'EOF2' || { echo "ipcluster did not come up"; ipcluster stop; exit 1; }
import sys, time, ipyparallel as ipp
n = int(sys.argv[1])
for _ in range(120):
    try:
        if len(ipp.Client().ids) >= n:
            print("ipcluster engines:", n); sys.exit(0)
    except Exception:
        pass
    time.sleep(5)
sys.exit(1)
EOF2
fi
START=$(date +%s)
/usr/bin/time -v igm-run config.json > igm_stdout.txt 2> igm_time.txt || echo "igm-run failed: see $RD/igm_stdout.txt, err_igm"
END=$(date +%s)
[ "$CONTROLLER" = ipyparallel ] && ipcluster stop || true
python - "$RD" "$START" "$END" "$SLURM_CPUS_PER_TASK" <<'EOF'
import json, sys
rd, a, b, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
json.dump({"seconds_wall": b - a, "cores": n, "cpu_hours_allocated": (b - a) * n / 3600}, open(f"{rd}/timing.json", "w"))
print(open(f"{rd}/timing.json").read())
EOF
ls -la "$RD"
