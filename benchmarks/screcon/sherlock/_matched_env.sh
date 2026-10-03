# Settings of the matched-modality jobs (sourced by matched_*.sbatch after _env.sh).
#   repo copy      $SCRATCH/uchrom-nd/repo-matched   (separate from repo/, which running jobs use)
#   outputs        $SCRATCH/uchrom-nd/runs/screcon/matched/{sets,nagano,models,rows,tables}
source "$SCRATCH/uchrom-nd/repo-matched/benchmarks/screcon/sherlock/_env.sh"
REPO=$W/repo-matched
SC=$REPO/benchmarks/screcon
M=$W/runs/screcon/matched
NAG=$DATA/nagano2017_hap
TAN=$DATA/tan2021_cortex
TKB=$DATA/takei2021_brain
mkdir -p "$M"/{sets,nagano,models,rows,tables}
# Nagano 2017 haploid cell selection (stated rules on the GEO feature table columns)
NAGANO_SERUM_RULE='cond == "Serum_G1/S" and passed_qc == 1 and group in ["G1", "early-S", "late-S/G2"] and total_contacts >= 100000'
NAGANO_2I_RULE='cond in ["2i_all", "2i_G1"] and passed_qc == 1 and group in ["G1", "early-S", "late-S/G2"] and total_contacts >= 50000'
NAGANO_2I_MAX=200

# "cell<TAB>table" lines of the Nagano manifests (serum first)
nagano_cells() {
  local cond
  for cond in serum 2i; do
    awk -F'\t' 'NR==1{for(i=1;i<=NF;i++) h[$i]=i; next} {print $h["cell"] "\t" $h["table"]}' "$M/nagano/$cond/manifest.tsv"
  done
}
