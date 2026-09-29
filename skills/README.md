# U-Chrom agent skills

Skills in the [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills) format
(`<name>/SKILL.md`, optional `scripts/`). They teach a coding agent (Claude Code, Codex,
`uchrom_discovery`, …) *how* to use U-Chrom well: which API calls, in which order, and which checks an
answer must pass. They add no new API — analysis is the `uchrom` Python API, visualization the web
browser (`uchrom.browser.connect()` / WebMCP).

| skill | for | script |
|---|---|---|
| `load-data` | open / inspect a dataset: counts, columns, units, embeddings, linked contact maps; QC (traces per chromosome per cell, duplicate loci, spots per trace by group, detection) and what to do about each | `scripts/inspect_data.py` |
| `call-structures` | distance vs separation, Rg, P(s) slopes from contact maps (depth-normalised, pseudo-bulk), TADs / compartments / loops with the right caller and bin size | `scripts/structures.py` |
| `compare-groups` | a statistic between groups of cells, cell as the unit, effect size, FDR scan over many features, equal-loci subsampling, confounder checks | `scripts/compare_groups.py` |
| `associate-modalities` | feature ↔ structure or modality ↔ modality at the spot / bin / cell / cell-type level, Spearman + partial on confounders, within vs between cell types, embedding kNN purity | `scripts/associate.py` |
| `show-in-browser` | read the researcher's selection; open, arrange and capture views | — |

Scripts print one JSON object whose `checks` list what a report must mention; tests are in
`tests/skills/`. Use with Claude Code: copy or symlink a skill folder into `.claude/skills/` (project) or
`~/.claude/skills/` (user).
