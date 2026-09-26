# U-Chrom agent skills

Skills in the [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills) format
(`<name>/SKILL.md`, optional `scripts/`). They teach a coding agent (Claude Code, Codex,
`uchrom_discovery`, …) *how* to use U-Chrom well: which API calls, in which order, and which checks an
answer must pass. They add no new API — analysis is the `uchrom` Python API, visualization the web
browser (`uchrom.browser.connect()` / WebMCP).

| skill | for |
|---|---|
| `compare-groups` | a statistic between two groups of cells, cell as the unit, effect size, confounder checks |
| `show-in-browser` | read the researcher's selection; open, arrange and capture views |

Use with Claude Code: copy or symlink a skill folder into `.claude/skills/` (project) or
`~/.claude/skills/` (user).
