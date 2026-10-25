# Shared settings of the Chen 2026 spatial Hi-C reprocessing (sourced by the other scripts).
HERE="${SLURM_SUBMIT_DIR:-$HOME/uchrom_chen2026}"          # these scripts (rsync'ed from the repo; jobs are submitted here)
ENV="$HOME/envs/uchrom-hicmap"                  # bwa, samtools, pairtools, pigz, cooler (setup_env.sbatch)
UCHROM_ARCHIVE="${UCHROM_ARCHIVE:?set UCHROM_ARCHIVE: where reference files and results are kept}"
REF="$UCHROM_ARCHIVE/ref/mm10"                                  # mm10.fa (chr1-19, X, Y, M), bwa index, chrom sizes
RAW="$SCRATCH/chen2026/raw"                                 # fastq: re-downloadable from GSA, removed after a run is done
WORK="$SCRATCH/chen2026/work"                               # chunks, per-chunk pairs (disposable)
DEST="$UCHROM_ARCHIVE/spatial_hic_chen2026"                     # kept: dedup pairs, .scool, .mcool, stats
FTP="ftp://download.big.ac.cn/gsa5/CRA016676"
col() { awk -F'\t' -v r="$1" -v c="$2" 'NR==1{for(i=1;i<=NF;i++) h[$i]=i; next} $1==r {print $h[c]}' "$HERE/runs.tsv"; }
READID_TRANSFORM='readID[-17:]'                            # pairtools parse: read name -> "<bcB>_<bcA>"
# whitelists of a run for pairs_to_cool.py (50: authors' A / B lists; 96: one list for both)
whitelist_args() { if [ "$(col "$1" grid)" = 50 ]; then echo "--a $HERE/barcodes_50_A.tsv --b $HERE/barcodes_50_B.tsv --sep=_";
                   else echo "--a $HERE/barcodes_96.tsv --b $HERE/barcodes_96.tsv --sep=_"; fi; }
