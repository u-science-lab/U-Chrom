# Shared settings of the spatial ATAC-Hi-C (GSE307620) contact reprocessing (sourced by the other scripts).
# map.sbatch, finish.sbatch, pairs_to_cool.py and barcodes.py are shared with ../../spatial_hic_chen2026/slurm
# (symlinks here; rsync -L copies them).  A "run" of those steps is a section here (its SRA runs merged).
HERE="${SLURM_SUBMIT_DIR:-$HOME/uchrom_atachic}"            # these scripts; jobs are submitted from this folder
ENV="$HOME/envs/uchrom-hicmap"                  # bwa, samtools, pairtools, pigz, cooler (Chen setup_env.sbatch)
UCHROM_ARCHIVE="${UCHROM_ARCHIVE:?set UCHROM_ARCHIVE: where reference files and results are kept}"
REF="$UCHROM_ARCHIVE/ref/mm10"                                  # mm10 main chromosomes + bwa index (Chen setup_env.sbatch)
RAW="$SCRATCH/atachic/raw"                                  # fastq per section (re-downloadable from SRA; removed when done)
WORK="$SCRATCH/atachic/work"                                # chunks, per-chunk pairs (disposable)
DEST="$UCHROM_ARCHIVE/spatial_atac_hic"                         # kept: dedup pairs, .scool, .mcool, stats
col() { awk -F'\t' -v r="$1" -v c="$2" 'NR==1{for(i=1;i<=NF;i++) h[$i]=i; next} $1==r {print $h[c]}' "$HERE/sections.tsv"; }
READID_TRANSFORM='readID[-16:]'                             # pairtools parse: read name -> the 16-base spot barcode
whitelist_args() { echo "--a $HERE/barcodes_A.tsv --b $HERE/barcodes_B.tsv --sep="; }
