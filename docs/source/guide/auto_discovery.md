# Multi-omics Auto-discovery

```{note}
Auto-discovery ships as the separate **`uchrom-discovery`** package
(`packages/uchrom-discovery` in this repository) so the core `u-chrom` toolkit does not
depend on LLM backends.  Install it next to `u-chrom`:

    pip install -e packages/chromdata -e packages/uchrom   # u-chrom
    pip install -e packages/uchrom-discovery/   # uchrom-discovery  (import uchrom_discovery)

The old `uchrom.auto_discovery` import path and the
`ChromData.build_discovery_schema` / `describe_for_agent` methods still work
for one release but emit `DeprecationWarning`.
```

U-Chrom can expose an agent-readable schema directly from a ChromData store.
The schema is stored in `cdata.uns["auto_discovery_schema"]`, so discovery
agents can reason from the same object that downstream analyses load.

## Schema

```python
from uchrom import ChromData
from uchrom_discovery import build_discovery_schema, describe_for_agent

cdata = ChromData.read("takei2025_cerebellum_rep1.chromdata.zarr")
cdata.add_reference(
    role="primary_dataset_paper",
    title="Primary paper or dataset manuscript",
    doi="10.xxxx/example",
    url="https://example.org/paper",
)
cdata.add_user_annotation(
    scope="analysis_constraint",
    target="linked_adata",
    text="RNA and chromatin tracing are linked at cell_id level; do not assume RNA spot geometry.",
    tags=["constraint", "multiomics_alignment"],
)
schema = build_discovery_schema(cdata, store=True)
print(describe_for_agent(cdata))
cdata.write("takei2025_cerebellum_rep1.chromdata.zarr")
```

The schema records:

- axes: spot, trace, cell, marker, gene
- modalities: chromatin tracing, IF tracks, cell metadata, linked RNA
- field catalogs: `spots`, `tracks`, `cells`, `cellm`, `linked_adata`
- dataset references from `cdata.uns["dataset_references"]`
- user annotations from `cdata.uns["user_annotations"]`
- a compact `knowledge_seed_context` for browser/idea agents
- known missing data, such as raw RNA spot geometry or scRNA reference
- recommended verification checks for generated parameters

References and annotations are treated as priors and constraints for
discovery agents. They do not replace notebook-based validation.

## Runner

The local runner performs:

```text
dataset schema -> idea generation -> schema review -> notebook creation
-> notebook execution -> verification -> report
```

Run the default PantheonOS-agent backend:

```bash
MPLBACKEND=Agg python -m uchrom_discovery run data.chromdata.zarr runs/pantheon \
  --model openai/gpt-5.5 \
  --idea-agent-count 3 \
  --notebook-agent-concurrency 3 \
  --max-ideas 4
```

The PantheonOS backend creates two agent stages. Idea agents receive only
file access to the serialized dataset discovery schema. Accepted ideas are
converted into scaffold notebooks, then notebook agents receive file access
plus live notebook tools. They can read the notebook, insert Markdown notes,
insert or update code cells, execute cells, inspect outputs, and refine the
analysis inside the notebook. The runner then re-executes the final notebook
from top to bottom and verifies the outputs for reproducibility.

Notebook agents are instructed to produce a quantitative matplotlib figure
for each verified idea. The scaffold and lightweight runner executor force
matplotlib to the non-interactive `Agg` backend so batch/doc runs do not open
local GUI windows. For large batches, keep graphical abstract generation
decoupled from notebook verification. Generated schematics should be added as
a separate post-processing pass so image-generation latency cannot block
statistical exploration. Use retries plus strict coverage checking before
publishing exported notebooks:

```bash
python -m uchrom_discovery schematics runs/pantheon \
  --model openai \
  --concurrency 3 \
  --retries 2 \
  --strict
```

The command writes `pantheon/schematic_images/schematics.jsonl` and
`pantheon/schematic_images/schematic_coverage.json`. In strict mode, the
command fails if any target notebook still lacks the `schematic_image` cell,
so missing graphical abstracts cannot silently enter the docs snapshot.
`--visual-qa` is available for runtimes that provide a Pantheon sub-agent
callback context; the default CLI path keeps QA separate from the coverage
gate.

For direct backend debugging, the runner can use any registered structured
backend. Claude and Codex CLI backends return structured idea/code payloads;
the U-Chrom runner still writes, executes, and verifies the final notebooks:

The shared prompt contracts live in `uchrom_discovery.llm`; backend
adapters call those prompt builders but do not own provider-specific prompt
rules or the notebook lifecycle.

```bash
python -m uchrom_discovery run data.chromdata.zarr runs/claude \
  --idea-source claude \
  --code-source claude \
  --reasoning-effort low \
  --max-ideas 4
```

Use `--idea-source codex --code-source codex` to exercise the Codex CLI
backend with the same runner-owned notebook lifecycle.

Each run writes:

- `ideas.jsonl`
- `reviews.jsonl`
- `results.jsonl`
- `agent_records.jsonl`
- `report.md`
- `graph/idea_graph.json`
- `graph/graph_summary.md`
- one notebook per accepted idea under `notebooks/`

When `--store-schema` is used, the runner also stores a lightweight graph
pointer and run summary in `cdata.uns["auto_discovery_graph"]` and
`cdata.uns["auto_discovery_runs"]`. Full notebooks and graph artifacts stay
in the run directory.

Existing runs can be converted into graph artifacts without re-running the
agents:

```bash
python -m uchrom_discovery graph runs/pantheon
```

## Verified Notebook Exports

The Takei 2025 tutorial build includes standalone HTML exports from a completed 20-idea Pantheon notebook-agent batch. The batch generated 20 ideas, accepted 20 after dataset schema review, executed 20 notebooks, and U-Chrom re-executed/verified all 20 with explicit hypothesis tests and saved statistical figures.

The exported notebooks intentionally separate quantitative verification from schematic generation. Main exploration notebooks include statistical matplotlib figures; generated graphical abstracts are added by a separate post-processing pass with strict coverage checking before the docs snapshot is published.

- <a href="../_auto_discovery_notebooks/purkinje-specific-h3k27ac-decompaction-along-tra-8f00bdb00f.html">Purkinje-specific H3K27ac decompaction along traced chromosomes</a>: one-sided label permutation test on trace/chromosome deltas, 500 permutations..., p = 1.
- <a href="../_auto_discovery_notebooks/bergmann-specific-laminb1-peripheral-anchoring-s-509bbf93ca.html">Bergmann-specific LaminB1 peripheral anchoring signature</a>: one-sided exact cell-label permutation test, p = 0.9881.
- <a href="../_auto_discovery_notebooks/granule-cell-hp1alpha-heterochromatin-clustering-3401a4f59b.html">Granule-cell HP1alpha heterochromatin clustering in 3D traces</a>: one-sided matched randomization test (500 permutations; grouped by Granule tr..., p = 0.001996.
- <a href="../_auto_discovery_notebooks/pcp2-linked-active-chromatin-hub-proximity-acros-f62e7efc46.html">Pcp2-linked active chromatin hub proximity across cell types</a>: one-sided Spearman permutation test (1000 label shuffles), p = 0.999.
- <a href="../_auto_discovery_notebooks/pcp2-expression-predicts-h3k27ac-marked-chromati-667c6ee250.html">Pcp2 expression predicts H3K27ac-marked chromatin spatial clustering</a>: Spearman correlation, one-sided negative; 1000 deterministic label-shuffle pe..., p = 0.9989.
- <a href="../_auto_discovery_notebooks/aldoc-expression-tracks-lamina-associated-chroma-4c06d0d43e.html">Aldoc expression tracks lamina-associated chromatin signal</a>: Spearman correlation with fixed-seed one-sided permutation test (1000 Aldoc-l..., p = 0.07093.
- <a href="../_auto_discovery_notebooks/gabra6-expression-links-to-elongating-rna-polyme-eef7dd1223.html">Gabra6 expression links to elongating RNA polymerase chromatin signal</a>: one-sided Spearman rank correlation with fixed-seed label permutation control, p = 0.783.
- <a href="../_auto_discovery_notebooks/reln-expression-predicts-spatial-coupling-of-h3k-ec2890df4e.html">Reln expression predicts spatial coupling of H3K4me1 and CBP chromatin spots</a>: Spearman correlation with 1000 fixed-seed Reln-label permutations (one-sided..., p = 0.4156.
- <a href="../_auto_discovery_notebooks/lamina-proximal-local-compaction-across-chromoso-ee45672874.html">Lamina-proximal local compaction across chromosome traces</a>: Spearman rank correlation; one-sided permutation test with 500 shuffles of n_..., p = 0.001996.
- <a href="../_auto_discovery_notebooks/radial-enrichment-of-active-h3k27ac-chromatin-65ea38bd9b.html">Radial enrichment of active H3K27ac chromatin</a>: Within-cell H3K27ac-rank permutation test (500 permutations, two-sided), p = 0.001996.
- <a href="../_auto_discovery_notebooks/purkinje-marker-expression-predicts-chromosome-w-ed79327c32.html">Purkinje marker expression predicts chromosome-wide radial positioning</a>: Spearman rank correlation with 1000 reproducible cell-label permutations, p = 0.001998.
- <a href="../_auto_discovery_notebooks/lamina-association-of-repetitive-satellite-rich--6f2c6827ff.html">Lamina association of repetitive satellite-rich chromatin</a>: within-cell satellite-score permutation test (500 permutations, one-sided neg..., p = 1.
- <a href="../_auto_discovery_notebooks/xist-marked-chrx-inter-chromosomal-isolation-3bd44d703c.html">Xist-marked chrX inter-chromosomal isolation</a>: within-cell Xist-label randomization test, one-sided greater, 500 permutations, p = 0.01198.
- <a href="../_auto_discovery_notebooks/active-chromatin-assortativity-between-chromosom-6fcdb55564.html">Active chromatin assortativity between chromosomes</a>: one-sided chromosome-label permutation test (500 permutations), p = 0.001996.
- <a href="../_auto_discovery_notebooks/rdna-marked-inter-chromosomal-hub-compaction-41a5f6a09d.html">rDNA-marked inter-chromosomal hub compaction</a>: one-sided within-cell rDNA-label permutation test (300 permutations) on mean..., p = 0.003322.
- <a href="../_auto_discovery_notebooks/chromosome-specific-peripheral-positioning-by-la-8abdde15dc.html">Chromosome-specific peripheral positioning by LaminB1</a>: within-cell chromosome-label permutation test (500 permutations, two-sided me..., p = 0.005988.
- <a href="../_auto_discovery_notebooks/h3k27ac-high-loci-resist-spurious-compaction-cal-b54d7cca89.html">H3K27ac-high loci resist spurious compaction calls after marker permutation</a>: within-trace H3K27ac marker permutation test (500 permutations); supplementar..., p = 0.8743.
- <a href="../_auto_discovery_notebooks/rnapiiser2-p-neighborhoods-around-polya-rna-spot-6bd867a3af.html">RNAPIISer2-P neighborhoods around polyA_RNA spots should survive cell-label negative controls</a>: one-sided cell-label permutation test (500 permutations), p = 0.001996.
- <a href="../_auto_discovery_notebooks/h3k9me3-radial-enrichment-should-be-stronger-tha-b9769d3c8c.html">H3K9me3 radial enrichment should be stronger than shuffled radial assignments</a>: within-cell n_rad_score permutation test (500 permutations, one-sided), p = 1.
- <a href="../_auto_discovery_notebooks/pcp2-expression-should-align-with-per-cell-h3k27-b0193ea9a5.html">Pcp2 expression should align with per-cell H3K27ac only beyond shuffled-cell controls</a>: seeded one-sided shuffled-cell permutation test of Spearman rho (n_permutatio..., p = 0.004995.

## Notebook-first Code Agent

The code agent is not limited to a fixed tool registry. It can generate
free-form Python, but the exploration is auditable because every accepted
idea gets a notebook with:

- a readable Markdown idea brief generated by the idea agent
- data/schema checks
- agent-authored Markdown notes and executable analysis cells
- an explicit hypothesis test with null/alternative hypotheses, test method,
  p-value, effect size, and sample-size/context notes
- a statistical matplotlib figure explaining the observed parameter
- an optional post-processed scientific schematic / graphical abstract
- result table output
- verification summary

Successful notebook code can later be promoted into stable modules such as
`uchrom.fea` or `uchrom.strc`.

## PantheonOS

`uchrom_discovery.pantheon` implements the default agent orchestration
used by `run_auto_discovery`. PantheonOS is kept as an optional runtime
dependency of U-Chrom itself, but the Pantheon backend requires
`pantheon-agents` to be installed in the environment that runs the agents.

The backend is model-provider agnostic at the Pantheon layer. The example
above uses `openai/gpt-5.5`, but any Pantheon-supported model string can be
passed with `--model`.
