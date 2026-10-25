# Shared settings of the SpaceA reprocessing (Ma et al. 2026, Dev Cell; GSA CRA038845), sourced by the other scripts.
# The authors' pipeline (github.com/YuetongXU/SpaceA-Paper, 1_Pre-processing/Snakefile) as Slurm jobs: cutadapt, the
# Guttman lab's BarcodeIdentification, STAR on mm10, Picard duplicates, MAPQ 255, get_clusters -> SPRITE clusters,
# then the clusters as ChromData.clusters per spot (build_store.py).  Set SPACEA_ROOT and SPACEA_REF before submitting
# (sbatch passes the environment); every other path can be set too (SPACEA_<NAME>).
HERE="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"   # these scripts (jobs are submitted here)
ROOT="${SPACEA_ROOT:?set SPACEA_ROOT: the folder of the data, work files and outputs}"
REF="${SPACEA_REF:?set SPACEA_REF: a folder with mm10.fa (UCSC chr1-19, X, Y, M)}"
ENV="${SPACEA_ENV:-$HOME/envs/uchrom-spacea}"               # STAR, cutadapt, samtools, Picard, pysam (setup_env.sbatch)
STARIDX="${SPACEA_STARIDX:-$ROOT/ref/mm10_star_2.7.10b_refGene}"  # derived from REF + UCSC refGene (rebuildable)
RAW="${SPACEA_RAW:-$ROOT/raw}"                              # fastq: re-downloadable from GSA, removed after a run is done
WORK="${SPACEA_WORK:-$ROOT/work}"                           # parts, BAMs (disposable)
DEST="${SPACEA_DEST:-$ROOT/out}"                            # kept: clusters files, stats, stores
SRC="${SPACEA_SRC:-$ROOT/src}"                              # code of others, cloned at the commits below
SPACEA_COMMIT=c1e1753                                       # YuetongXU/SpaceA-Paper: barcode configs
SPRITE_COMMIT=5e11a58                                       # GuttmanLab/sprite-pipeline: BarcodeIdentification, scripts
FTP="https://download.cncb.ac.cn/gsa6/CRA038845"
col() { awk -F'\t' -v r="$1" -v c="$2" 'NR==1{for(i=1;i<=NF;i++) h[$i]=i; next} $1==r {print $h[c]}' "$HERE/runs.tsv"; }
