# uchrom-discovery

LLM-driven multi-omics auto-discovery on top of
[U-Chrom](../README.md) `ChromData`.

It turns an `.h5cd` file into an agent-readable schema, asks an agent
backend (Pantheon, Claude Code or Codex CLI) for structured hypotheses,
reviews them against the schema, writes and executes one exploration
notebook per idea, verifies the numbers, classifies the evidence, and
keeps an iterative idea graph across runs.

This package depends only on the public `uchrom` API; the core toolkit
does not depend on it.

## Install

```bash
pip install -e .              # from the repo root: u-chrom
pip install -e discovery/     # this package (import uchrom_discovery)
pip install -e "discovery/[pantheon]"   # optional Pantheon backend
```

## Usage

```python
from uchrom import ChromData
from uchrom_discovery import build_discovery_schema, describe_for_agent

cdata = ChromData.read("data.h5cd")
build_discovery_schema(cdata, store=True)   # -> cdata.uns["auto_discovery_schema"]
print(describe_for_agent(cdata))
```

```bash
uchrom-discovery run data.h5cd runs/example --backend claude
python -m uchrom_discovery iterate data.h5cd runs/iterative
```

Guides: `docs/source/guide/auto_discovery.md`,
`iterative_auto_discovery.md`, `data_enrichment_for_discovery.md`.

## Layout

```
discovery/
├── pyproject.toml
├── uchrom_discovery/   schema, ideas, llm prompts, backends, runner,
│                       notebooks, evidence, graph, directions, claims,
│                       enrichment, iterative loop, visualization
│   └── ui/             Vue idea-graph viewer (npm run build -> ui/dist)
└── tests/              run with `cd discovery && pytest tests`
```

## Migrating from `uchrom.auto_discovery`

| Before | After |
|---|---|
| `from uchrom.auto_discovery import X` | `from uchrom_discovery import X` |
| `python -m uchrom.auto_discovery ...` | `python -m uchrom_discovery ...` / `uchrom-discovery ...` |
| `cd.build_discovery_schema(store=True)` | `build_discovery_schema(cd, store=True)` |
| `cd.discovery_schema` | `get_discovery_schema(cd)` |
| `cd.update_discovery_schema(schema)` | `store_discovery_schema(cd, schema)` |
| `cd.validate_discovery_schema()` | `validate_discovery_schema(cdata=cd)` |
| `cd.describe_for_agent()` | `describe_for_agent(cd)` |

The old spellings still work for one release with a `DeprecationWarning`.
The on-disk keys (`uns["auto_discovery_schema"]`, `auto_discovery_graph`,
`auto_discovery_runs`) are unchanged.
