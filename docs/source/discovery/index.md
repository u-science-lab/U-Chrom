# Auto-discovery

`uchrom-discovery` (`import uchrom_discovery`) lets LLM agents explore a `ChromData`: it describes
the data to the agent (a schema of what is measured), collects candidate hypotheses, has each one
analysed in a notebook, checks the claims against the evidence, and grows an idea graph over
iterations.  Backends: Claude Code, Codex CLI, PantheonOS.

```bash
pip install -e packages/uchrom-discovery
uchrom-discovery run data.chromdata.zarr runs/example --backend claude
```

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/takei2025_auto_discovery
/tutorials/takei2025_iterative_auto_discovery
```

## Guides

```{toctree}
:maxdepth: 1

auto_discovery
iterative
enrichment
```

API: [uchrom_discovery](../reference/api/auto_discovery).
