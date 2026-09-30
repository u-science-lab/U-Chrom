#!/bin/bash
# Install the ORIGINAL IGM (reference for benchmarks/bulk/design.md §7(d)) in
# $GROUP_HOME/$USER/uchrom-nd/igm-orig (run once):
#
#   env/       conda env, Python 3.6 + the IGM README dependencies (cgal 4.14, hdf5, swig, ...)
#   alabtools/ github.com/alberlab/alabtools @ $ALAB_REF (pip-installed into env)
#   igm/       github.com/alberlab/igm       @ edbb331 (pip-installed into env)
#   lammpgen/  github.com/alberlab/lammpgen  @ 8a1a4cb, `make yes-user-genome yes-molecule serial`
#   ~/.igm/user_defaults.cfg  -> the lmp_serial path
#
# All three codes are GPL; they are installed here only to run them — nothing of them
# enters U-Chrom.  The commits are the ones read for benchmarks/bulk/pgs_spec.md.  If
# alabtools HEAD no longer builds with Python 3.6, set ALAB_REF to an older commit
# (e.g. the last one of 2022) and record it in the job output.
#
#   sbatch benchmarks/bulk/sherlock/setup_igm_orig.sbatch
#SBATCH --job-name=bulk-igm-setup
#SBATCH --partition=xiaojie,owners,normal
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"
IGM_REF=edbb33135260443b8b41eb09d7ca4c37b19e330d
LMP_SHORT=8a1a4cbb4d0bffda516c7f51cd3cf2f706ec3cb9   # lammpgen commit read for the spec
ALAB_REF=${ALAB_REF:-2daab4710845674a224f524e0b50e893bf030e35}
MAMBA=${MAMBA:-$HOME/miniconda3/bin/mamba}
mkdir -p "$IGMO"
ENV=$IGMO/env
if [ ! -d "$ENV" ]; then
  "$MAMBA" create -q -y -p "$ENV" -c conda-forge -c defaults python=3.6 pandas swig cython "cgal=4.14" hdf5 h5py \
    numpy scipy matplotlib tornado ipyparallel cloudpickle gxx_linux-64 gcc_linux-64 make git
fi
export PATH=$ENV/bin:$PATH CPATH=$ENV/include LIBRARY_PATH=$ENV/lib LD_LIBRARY_PATH=$ENV/lib:${LD_LIBRARY_PATH:-}
python --version

clone() {  # repo dir ref
  [ -d "$2" ] || git clone -q "$1" "$2"
  (cd "$2" && git fetch -q origin && git checkout -q "$3" && echo "$2 at $(git rev-parse HEAD)")
}
clone https://github.com/alberlab/alabtools "$IGMO/alabtools" "$ALAB_REF"
clone https://github.com/alberlab/igm "$IGMO/igm" "$IGM_REF"
clone https://github.com/alberlab/lammpgen "$IGMO/lammpgen" "$LMP_SHORT"
pip install -q "$IGMO/alabtools"
pip install -q "$IGMO/igm"
python -c "import alabtools, igm; print('alabtools', alabtools.__file__); print('igm', igm.__file__)"

cd "$IGMO/lammpgen/src"
make -s yes-user-genome
make -s yes-molecule
make -s -j "$SLURM_CPUS_PER_TASK" serial CC="$ENV/bin/x86_64-conda-linux-gnu-g++" LINK="$ENV/bin/x86_64-conda-linux-gnu-g++" > "$IGMO/lammpgen-build.log" 2>&1 \
  || make -s -j "$SLURM_CPUS_PER_TASK" serial >> "$IGMO/lammpgen-build.log" 2>&1
ls -la lmp_serial
mkdir -p "$HOME/.igm"
printf '[DEFAULT]\noptimization/kernel_opts/lammps/lammps_executable = %s\n' "$IGMO/lammpgen/src/lmp_serial" > "$HOME/.igm/user_defaults.cfg"
cat "$HOME/.igm/user_defaults.cfg"
echo done
