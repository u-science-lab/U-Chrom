#!/bin/bash
# One-off: the references the spatial statistics are checked against —
#   * SPARK (xzhoulab/SPARK @a8b4bf2, GPL-3; SPARK-X) and its CRAN dependencies into $BASE/ref/Rlib (R/4.4.2);
#   * esda + libpysal (PySAL; Moran's I, Geary's C) into venv-sc, binary wheels only, numpy / pandas / scipy pinned
#     at the versions already there (pip installs and compiling belong in a job, not on a login node).
#   sbatch benchmarks/spatial_variable/sherlock/setup.sbatch
#SBATCH --job-name=sv-setup
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-sv/benchmarks/spatial_variable/sherlock/_env.sh"
mkdir -p "$R_LIBS_USER"
Rscript -e 'want <- c("Rcpp", "RcppArmadillo", "foreach", "doParallel", "CompQuadForm", "matlab", "pracma");
             need <- setdiff(want, rownames(installed.packages(lib.loc = Sys.getenv("R_LIBS_USER"))));
             if (length(need)) install.packages(need, repos = "https://cloud.r-project.org",
                                                lib = Sys.getenv("R_LIBS_USER"), Ncpus = 4)'
SHA=a8b4bf27b804604dfda53da42992f100b8e4e727
curl -sSL -o "$L_SCRATCH/SPARK.tar.gz" "https://github.com/xzhoulab/SPARK/archive/$SHA.tar.gz"
tar -xzf "$L_SCRATCH/SPARK.tar.gz" -C "$L_SCRATCH"
# the repository ships object files built elsewhere (SPARK.so linked to a system liblapack): build from source
rm -f "$L_SCRATCH/SPARK-$SHA"/src/*.o "$L_SCRATCH/SPARK-$SHA"/src/*.so
R CMD INSTALL -l "$R_LIBS_USER" "$L_SCRATCH/SPARK-$SHA"
Rscript -e 'library(SPARK); cat("SPARK", as.character(packageVersion("SPARK")), "\n")'
$PY -m pip freeze | grep -iE "^(numpy|pandas|scipy|scikit-learn)==" > "$L_SCRATCH/pins.txt"
cat "$L_SCRATCH/pins.txt"
$PY -m pip install --only-binary=:all: -c "$L_SCRATCH/pins.txt" "esda==2.10.0" "libpysal==4.15.0"
$PY -c "import esda, libpysal; print('esda', esda.__version__, 'libpysal', libpysal.__version__)"
du -sh "$BASE/ref"
