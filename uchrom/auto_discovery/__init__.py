"""Multi-omics auto-discovery helpers for ChromData."""

from .ideas import DiscoveryIdea, IdeaReview, review_idea_against_schema
from .iterative import (
    IterativeDiscoveryConfig,
    IterativeDiscoveryResult,
    run_iterative_auto_discovery,
)
from .evidence import (
    EvidenceConclusion,
    classify_hypothesis_evidence,
    structured_conclusion_markdown,
)
from .frontier import (
    DiscoveryFrontier,
    frontiers_to_agent_context,
    plan_discovery_frontiers,
    write_frontier_artifacts,
)
from .graph import (
    IdeaGraph,
    build_idea_graph_from_run,
    build_idea_graph_from_runs,
    graph_summary_markdown,
    idea_signature,
    ingest_literature_claims,
    infer_parameter_family,
    load_idea_graph,
    write_idea_graph_artifacts,
)
from .llm import generate_openai_analysis_code, generate_openai_ideas
from .notebooks import (
    create_exploration_notebook,
    execute_notebook_python,
    idea_to_markdown,
    upsert_structured_conclusion,
)
from .pantheon import (
    generate_pantheon_ideas,
    run_pantheon_notebook_agents,
    schematic_coverage_for_run,
)
from .runner import DiscoveryRunConfig, DiscoveryRunResult, run_auto_discovery
from .schema import (
    DISCOVERY_SCHEMA_KEY,
    build_discovery_schema,
    pack_schema,
    schema_to_agent_context,
    unpack_schema,
    validate_discovery_schema,
)
from .visualization import write_idea_graph_html

__all__ = [
    "DISCOVERY_SCHEMA_KEY",
    "DiscoveryFrontier",
    "DiscoveryIdea",
    "EvidenceConclusion",
    "IdeaGraph",
    "IterativeDiscoveryConfig",
    "IterativeDiscoveryResult",
    "DiscoveryRunConfig",
    "DiscoveryRunResult",
    "IdeaReview",
    "build_discovery_schema",
    "build_idea_graph_from_run",
    "build_idea_graph_from_runs",
    "classify_hypothesis_evidence",
    "create_exploration_notebook",
    "execute_notebook_python",
    "frontiers_to_agent_context",
    "generate_openai_analysis_code",
    "generate_openai_ideas",
    "generate_pantheon_ideas",
    "graph_summary_markdown",
    "idea_signature",
    "ingest_literature_claims",
    "idea_to_markdown",
    "infer_parameter_family",
    "load_idea_graph",
    "pack_schema",
    "plan_discovery_frontiers",
    "review_idea_against_schema",
    "run_auto_discovery",
    "run_iterative_auto_discovery",
    "run_pantheon_notebook_agents",
    "schematic_coverage_for_run",
    "schema_to_agent_context",
    "structured_conclusion_markdown",
    "unpack_schema",
    "upsert_structured_conclusion",
    "validate_discovery_schema",
    "write_frontier_artifacts",
    "write_idea_graph_html",
    "write_idea_graph_artifacts",
]
