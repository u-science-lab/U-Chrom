# Iterative Auto-discovery Design

This page records the proposed next architecture for U-Chrom
auto-discovery. The goal is to move from one-shot idea generation toward a
graph-guided discovery loop that uses dataset metadata, user annotations,
external literature, prior notebook results, and explicit evidence
classification.

## Motivation

The current auto-discovery workflow already supports:

- store-backed discovery schemas
- agent-generated structured ideas
- schema review before execution
- notebook-first exploration with free-form code
- runner re-execution and verification
- evidence classification separate from notebook verification

The next step is to make the system iterative. New ideas should not be
independent samples from a prompt. They should be linked to what is already
known, what was already tested, what was supported, what was contradicted,
and which regions of the dataset remain underexplored.

The central design principle is:

```text
schema tells what is measurable
references tell what is known
annotations tell what the user cares about
graph tells what has already been tried
evidence tells what held up
follow-up directions tell what to ask next
notebooks verify each claim
```

## Current Implementation

The first implementation pass now covers the local graph/follow-up-direction loop:

- `uchrom_discovery.graph.IdeaGraph` builds a discovery graph from
  `ideas.jsonl`, `reviews.jsonl`, and `results.jsonl`.
- `uchrom_discovery.direction.plan_discovery_directions` reads that graph
  plus the store-backed schema and produces diverse next-iteration follow-up
  directions.
- `run_auto_discovery` writes `graph/idea_graph.json`,
  `graph/graph_summary.md`, `graph/idea_graph.html`,
  `directions/next_directions.json`, and `directions/next_directions.md` after
  each run.
- `uchrom_discovery.iterative.run_iterative_auto_discovery` can run
  multiple graph-guided iterations. Iteration 2 and later receive the prior
  idea graph and follow-up-direction Markdown as explicit Pantheon idea-agent
  context.
- `uchrom_discovery.graph.ingest_literature_claims` ingests browser-agent
  `claims.jsonl` artifacts into the graph as `LiteratureClaim` and
  `Reference` nodes.
- `uchrom_discovery.visualization.write_idea_graph_html` writes a static
  interactive graph viewer for ideas, evidence, notebooks, references, and
  literature claims.
- The CLI can regenerate these artifacts from an existing run:

```bash
python -m uchrom_discovery directions RUN_DIR DATA.chromdata.zarr
python -m uchrom_discovery view RUN_DIR/graph/idea_graph.json graph.html
python -m uchrom_discovery claims RUN_DIR/graph/idea_graph.json RUN_DIR/browser/claims.jsonl
python -m uchrom_discovery iterate DATA.chromdata.zarr ITERATIVE_OUT \
  --iterations 3 \
  --ideas-per-iteration 20
```

Iterative mode asks the Pantheon notebook agent to generate a graphical
abstract during each notebook run by default. The image is requested after the
notebook's statistical analysis and verification inside the same agent task,
so the schematic reflects the actual evidence result rather than a later
separate pass. Use `--no-generate-schematic-image` for a faster evidence-only
run:

```bash
python -m uchrom_discovery iterate DATA.chromdata.zarr ITERATIVE_OUT \
  --iterations 3 \
  --ideas-per-iteration 20 \
  --schematic-image-model openai
```

The generated notebook agent prompt includes a `file_manager.observe_images`
QA step for the schematic and embeds the accepted image as a
`schematic_image` notebook cell.

See the real-data tutorial
{doc}`../tutorials/takei2025_iterative_auto_discovery` for a Takei
cerebellum example built from a completed 20-idea Pantheon notebook-agent
batch.

## High-level Architecture

The proposed system is organized around an `IdeaGraph` plus an orchestrator.
Agents do not call each other directly. Instead, each agent reads a graph
slice and writes structured artifacts that are ingested back into the graph.

```text
cdata / store
  -> discovery schema
  -> dataset references
  -> user annotations
  -> graph pointer / run summaries

Browser agent
  -> external sources, papers, dataset pages, claims, citations

Idea agent
  -> graph-guided computable hypotheses

Notebook agent
  -> notebook-first quantitative validation

Runner
  -> deterministic re-execution and evidence classification

IdeaGraph
  -> shared memory, provenance, coverage, and next follow-up directions
```

This keeps responsibilities clear:

- `ChromData` is the authority for data and data-level context.
- `IdeaGraph` is the authority for discovery history and scientific
  relationships.
- Browser agents collect knowledge.
- Idea agents propose hypotheses.
- Notebook agents test hypotheses.
- The orchestrator schedules work based on graph state and budget.

## Relationship to ChromData

`ChromData` should remain the entry point for the dataset. It should not
store large notebooks, browser logs, or full graph artifacts. Instead, it
should store lightweight context and pointers.

Recommended store metadata keys:

```python
cdata.uns["dataset_references"] = [...]
cdata.uns["user_annotations"] = [...]
cdata.uns["auto_discovery_schema"] = {...}
cdata.uns["auto_discovery_graph"] = {...}
cdata.uns["auto_discovery_runs"] = [...]
```

`dataset_references` records source material associated with the dataset.
These may include primary papers, data repositories, supplementary tables,
method papers, related biology priors, or user-provided references.

Example:

```json
[
  {
    "reference_id": "takei2025_primary",
    "role": "primary_dataset_paper",
    "title": "Primary dataset paper title",
    "doi": "10.xxxx/xxxxx",
    "pmid": null,
    "url": "https://example.org/paper",
    "year": 2025,
    "notes": "Primary dataset paper for linked chromatin tracing and RNA data."
  },
  {
    "reference_id": "zenodo_7693825",
    "role": "data_repository",
    "url": "https://zenodo.org/records/7693825",
    "notes": "Raw data and annotation tables."
  }
]
```

`user_annotations` records user-provided knowledge, constraints, or seeds.
These should be treated as high-priority context but not as validated
evidence.

Example:

```json
[
  {
    "annotation_id": "purkinje_marker_note",
    "scope": "cell_type",
    "target": "Purkinje",
    "text": "Pcp2 should be treated as a Purkinje marker in this dataset.",
    "tags": ["marker", "cell_type_prior"],
    "confidence": "user_asserted"
  },
  {
    "annotation_id": "rna_geometry_constraint",
    "scope": "analysis_constraint",
    "target": "linked_adata",
    "text": "RNA and chromatin tracing are linked at cell_id level; do not assume RNA spot geometry.",
    "tags": ["constraint", "multiomics_alignment"]
  }
]
```

The discovery schema should include these as first-class fields:

```python
schema["references"] = cdata.uns.get("dataset_references", [])
schema["user_annotations"] = cdata.uns.get("user_annotations", [])
schema["knowledge_seed_context"] = ...
```

This lets the first iteration start from dataset-specific knowledge rather
than from schema fields alone.

## IdeaGraph

The graph provides shared scientific memory. It should support both
machine-readable scheduling and human-readable audit trails.

Suggested node types:

```text
Dataset
SchemaSnapshot
Reference
LiteratureSource
LiteratureClaim
UserAnnotation
CellType
Gene
IFMarker
Modality
ParameterFamily
Follow-upDirection
Idea
NotebookRun
EvidenceResult
```

Suggested edge types:

```text
Idea -> uses_cell_type -> CellType
Idea -> uses_gene -> Gene
Idea -> uses_marker -> IFMarker
Idea -> uses_modality -> Modality
Idea -> has_parameter_family -> ParameterFamily
Idea -> motivated_by -> LiteratureClaim
Idea -> motivated_by -> UserAnnotation
Idea -> derived_from -> Idea
Idea -> refines -> Idea
Idea -> generalizes -> Idea
Idea -> specializes -> Idea
Idea -> alternative_definition_of -> Idea
Idea -> negative_control_for -> Idea
Idea -> tested_by -> NotebookRun
NotebookRun -> produced -> EvidenceResult
EvidenceResult -> supports -> Idea
EvidenceResult -> contradicts -> Idea
EvidenceResult -> not_supports -> Idea
LiteratureClaim -> sourced_from -> Reference
LiteratureClaim -> mentions_gene -> Gene
LiteratureClaim -> mentions_cell_type -> CellType
LiteratureClaim -> mentions_marker -> IFMarker
```

Each idea should be graph-linked. A generated idea should be able to answer:

- Which prior idea or result motivated it?
- Which literature claim or user annotation motivated it?
- Which fields, genes, markers, and cell types does it use?
- Which previous ideas are near duplicates?
- What would count as support, contradiction, or non-support?

## External Knowledge Layer

External knowledge should be handled by a dedicated browser or literature
agent, not by the notebook agent during analysis.

The browser agent is a knowledge ingestion worker:

```text
input:
  schema references
  user annotations
  graph gaps
  follow-up direction query plan

output:
  papers.jsonl
  claims.jsonl
  sources.bib
  retrieval_log.jsonl
  browser_records.jsonl
```

The browser agent should extract source-backed claims, not free-floating
summaries.

Example claim:

```json
{
  "claim_id": "claim_pcp2_purkinje_marker",
  "source": {
    "reference_id": "some_paper",
    "doi": "10.xxxx/xxxxx",
    "pmid": "12345678",
    "title": "Paper title",
    "year": 2024,
    "url": "https://example.org/paper"
  },
  "claim_text": "Pcp2 is used as a Purkinje-cell marker.",
  "entities": {
    "genes": ["Pcp2"],
    "cell_types": ["Purkinje"],
    "markers": [],
    "modalities": ["RNA"]
  },
  "relationship": "supports_marker_identity",
  "direction": "positive",
  "evidence_type": "paper_text",
  "confidence": 0.8,
  "quoted_evidence": "Short source-backed quote or excerpt."
}
```

External knowledge is a prior. It can motivate ideas, but it does not replace
data validation. Notebook results remain the evidence for whether an idea is
supported in the loaded dataset.

Suggested operation modes:

```text
closed_world
  Use only dataset schema and previous discovery results.

knowledge_guided
  Use cached literature claims and user annotations, but do not browse.

browser_refresh
  Refresh external knowledge first, then generate new ideas.
```

## Agent Scheduling

The orchestrator should run discovery in iterations. Each iteration updates
the graph before planning the next step.

```text
1. Sync graph from cdata and discovery schema.
2. Optionally refresh external knowledge with browser agents.
3. Plan dynamic follow-up directions from graph state.
4. Dispatch idea agents over selected directions.
5. Run schema review and graph novelty review.
6. Select a diverse idea portfolio.
7. Dispatch notebook agents over selected ideas.
8. Re-execute notebooks with the U-Chrom runner.
9. Classify evidence and update the graph.
10. Write graph summaries and dataset pointers.
```

Pseudo-code:

```python
while budget.remaining():
    graph.sync_from_cdata(cdata)

    if planner.needs_knowledge_refresh(graph):
        claims = browser_pool.run(graph.knowledge_queries())
        graph.ingest_literature_claims(claims)

    directions = planner.plan_directions(graph)
    candidates = idea_pool.run(directions)

    reviewed = [
        review_idea_against_schema(idea, schema)
        + review_idea_against_graph(idea, graph)
        for idea in candidates
    ]
    selected = portfolio_select(reviewed, graph, budget)

    notebooks = notebook_pool.run(selected)
    results = runner.verify(notebooks)
    graph.ingest_results(results)

    cdata.uns["auto_discovery_graph"] = graph.lightweight_summary()
```

## Dynamic Follow-up Directions

The current framework uses fixed idea direction buckets. This is useful for a
first pass, but it is too rigid for iterative discovery. The next design
should replace static buckets with graph-derived follow-up direction cards.

Follow-up direction examples:

```text
Follow up a supported rDNA inter-chromosomal hub result.
Explain a contradicted H3K27ac radial-enrichment result.
Refine a borderline Aldoc lamina-associated signal.
Fill an underexplored Bergmann RNA-linked region.
Add negative controls for active chromatin assortativity.
Generate literature-guided Pcp2/Purkinje spatial coupling ideas.
```

Example follow-up direction:

```json
{
  "direction_id": "contradicted_h3k27ac_radial_followup",
  "goal": "Explain why H3K27ac radial enrichment was contradicted.",
  "strategy": "alternative_definition",
  "preferred_facets": {
    "markers": ["H3K27ac"],
    "cell_types": ["Purkinje", "Granule"],
    "parameter_families": ["radial_position", "local_distance"]
  },
  "avoid_idea_ids": ["previous_near_duplicate_id"],
  "required_novelty": 0.65,
  "required_relation": "alternative_definition_of"
}
```

Follow-up directions can be generated from:

- supported findings that need replication, refinement, or controls
- contradicted findings that need alternative definitions or confounder tests
- borderline findings that need more power or less noisy parameters
- not-supported findings that should not be repeated exactly
- coverage gaps in cell types, markers, genes, modalities, or parameter
  families
- literature claims that have not yet been tested in this dataset
- user annotations that encode hypotheses or analysis constraints

## Diversity and Novelty

Static prompt instructions are not enough to avoid repetition. The graph
should provide a structured novelty review.

Each idea should get an `idea_signature`:

```json
{
  "modalities": ["chromatin_tracing", "rna_expression"],
  "cell_types": ["Purkinje"],
  "genes": ["Pcp2"],
  "markers": ["H3K27ac"],
  "parameter_family": "local_distance",
  "null_model": "cell_label_permutation",
  "expected_direction": "negative",
  "parent_idea_id": "previous_idea",
  "source_claim_ids": ["claim_pcp2_purkinje_marker"]
}
```

Graph review should compute:

```text
schema_feasibility
history_novelty
coverage_gain
literature_relevance
control_value
redundancy_penalty
```

The final set of ideas should be selected as a portfolio, not accepted in the
order returned by agents.

Example scoring:

```text
final_score =
  0.30 * novelty
+ 0.25 * evidence_relevance
+ 0.20 * coverage_gain
+ 0.15 * feasibility
+ 0.10 * control_value
- redundancy_penalty
```

Example portfolio constraints:

```text
No more than K ideas per marker.
No more than K ideas per cell type.
No more than K ideas per parameter family.
At least N RNA-linked ideas.
At least N literature-guided ideas.
At least N negative-control or robustness ideas.
At least N follow-ups to supported or contradicted findings.
```

## Evidence-driven Follow-up

New ideas should be derived from previous evidence states.

Suggested follow-up policies:

```text
Supported
  Generate replication, refinement, mechanism, cross-cell-type, and negative
  control ideas.

Contradicted
  Generate inverted-direction ideas, alternative operational definitions, and
  confounder checks.

Borderline
  Improve power, reduce noise, change aggregation, or test an adjacent marker.

Not supported
  Avoid exact repeats. Generate orthogonal formulations or explanatory null
  checks.

Verification failed
  Repair data access, simplify the parameter, or add missing data checks before
  biological interpretation.
```

This turns each run into a source of new questions.

## Notebook Agent Contract

The notebook agent should receive one accepted idea plus a focused graph
slice. It should not browse the web and should not decide the next global
direction.

Required notebook outputs:

```text
idea brief
data/schema checks
inspection code cell
main analysis code cell
explicit hypothesis test
result_table
analysis_summary
statistical matplotlib figure
verification output
final interpretation
```

The runner then re-executes the notebook and writes an `EvidenceResult` node:

```json
{
  "idea_id": "...",
  "notebook_status": "pass",
  "hypothesis_status": "Supported",
  "test_method": "...",
  "p_value": 0.01,
  "effect_size": 0.42,
  "observed_statistic": 0.42,
  "figure_path": "...",
  "result_table_path": "..."
}
```

The graph then connects this result back to the idea with `supports`,
`contradicts`, `not_supports`, or `inconclusive` edges.

## Storage Layout

The store should stay lightweight. Full graph and agent artifacts should live
in the run directory.

Recommended layout:

```text
runs/iterative_001/
  graph/
    idea_graph.json
    idea_graph.graphml
    graph_summary.md
  knowledge/
    papers.jsonl
    claims.jsonl
    sources.bib
    retrieval_log.jsonl
    browser_records.jsonl
  directions.jsonl
  ideas.jsonl
  reviews.jsonl
  graph_reviews.jsonl
  selected_ideas.jsonl
  results.jsonl
  agent_records.jsonl
  report.md
  notebooks/
```

The dataset pointer can remain small:

```json
{
  "schema_hash": "...",
  "latest_graph_path": "runs/iterative_001/graph/idea_graph.json",
  "n_ideas": 80,
  "n_verified": 62,
  "coverage_summary": {
    "cell_types": {},
    "markers": {},
    "genes": {},
    "parameter_families": {}
  }
}
```

## Proposed Implementation Phases

### Phase 1: Schema context

Add dataset references and user annotations to `ChromData` and to the
discovery schema.

Deliverables:

- `cdata.add_reference(...)`
- `cdata.add_user_annotation(...)`
- `schema["references"]`
- `schema["user_annotations"]`
- validation and round-trip tests

### Phase 2: IdeaGraph MVP

Build a graph from existing run artifacts.

Deliverables:

- `uchrom_discovery.graph`
- graph import from `ideas.jsonl`, `reviews.jsonl`, `results.jsonl`
- evidence nodes from `classify_hypothesis_evidence`
- graph export as JSON and GraphML
- graph summary Markdown

### Phase 3: Novelty and coverage review

Add structured idea signatures and graph-aware review.

Deliverables:

- `idea_signature(idea)`
- `review_idea_against_graph(idea, graph)`
- nearest-neighbor duplicate detection
- coverage gain scores
- portfolio selector

### Phase 4: Dynamic follow-up direction planner

Replace fixed direction buckets with graph-derived follow-up directions.

Deliverables:

- `plan_discovery_directions(schema, graph, ...)`
- follow-up direction JSON schema
- Pantheon idea-agent prompts that consume follow-up directions
- CLI flags for iterative mode and history runs

### Phase 5: External knowledge layer

Add browser/literature ingestion as a separate step.

Deliverables:

- `literature-refresh` CLI
- source and claim schemas
- browser agent records
- claim-to-graph ingestion
- citation/provenance checks

### Phase 6: Iterative orchestrator

Run complete graph-guided discovery loops.

Deliverables:

- `iterative-run` or `run --iterative`
- budgeted multi-iteration scheduling
- graph snapshots per iteration
- cdata graph pointer updates
- documentation and Takei example update

## Open Questions

- Should the graph use `networkx` internally, a lightweight custom JSON graph,
  or both?
- How much of the graph summary should be written back into the store versus kept
  only in run directories?
- What should be the default portfolio constraints for small datasets?
- How should literature claim confidence be represented when sources disagree?
- Should browser refresh be opt-in only to keep runs reproducible by default?
- How should multiple users' annotations be namespaced and versioned?

## Summary

The proposed system turns auto-discovery into an evidence-guided loop:

```text
Browser agents enrich the graph.
Idea agents propose graph-linked hypotheses.
Notebook agents validate graph-linked hypotheses.
The runner classifies evidence.
The graph plans the next round.
ChromData anchors everything to real data.
```

This provides a path from automated notebook generation toward a persistent,
auditable, literature-aware discovery engine for spatial multi-omics and
chromatin tracing data.
