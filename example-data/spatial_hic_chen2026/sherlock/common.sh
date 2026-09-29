# Shared settings of the Chen 2026 spatial Hi-C reprocessing (sourced by the other scripts).
HERE="$HOME/uchrom_chen2026"                              # these scripts (rsync'ed from the repo)
ENV="$GROUP_HOME/$USER/envs/uchrom-hicmap"                  # bwa, samtools, pairtools, pigz, cooler (setup_env.sbatch)
REF="$OAK/uchrom/ref/mm10"                                  # mm10.fa (chr1-19, X, Y, M), bwa index, chrom sizes
RAW="$SCRATCH/chen2026/raw"                                 # fastq: re-downloadable from GSA, removed after a run is done
WORK="$SCRATCH/chen2026/work"                               # chunks, per-chunk pairs (disposable)
DEST="$OAK/uchrom/spatial_hic_chen2026"                     # kept: dedup pairs, .scool, .mcool, stats
FTP="ftp://download.big.ac.cn/gsa5/CRA016676"
col() { awk -F'\t' -v r="$1" -v c="$2" 'NR==1{for(i=1;i<=NF;i++) h[$i]=i; next} $1==r {print $h[c]}' "$HERE/runs.tsv"; }
