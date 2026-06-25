"""Multi-omics auto-discovery helpers for ChromData."""

from .ideas import DiscoveryIdea, IdeaReview, review_idea_against_schema
from .claims import (
    CLAIM_KNOWLEDGE_MODES,
    ClaimRefreshResult,
    refresh_literature_claims_for_iteration,
)
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
from .direction import (
    DiscoveryDirection,
    directions_to_agent_context,
    plan_discovery_directions,
    write_direction_artifacts,
)
from .enrichment import DiscoveryEnrichmentConfig, enrich_for_discovery
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
from .backends import (
    AnalysisCodeResult,
    BackendAgentRecord,
    BackendCapabilities,
    BackendDetection,
    BackendError,
    CLISpec,
    get_backend,
    list_backends,
    register_backend,
    unregister_backend,
)
from .llm import (
    allowed_required_fields,
    analysis_output_schema,
    build_analysis_prompt,
    build_idea_prompt,
    build_required_fields_prompt_block,
    idea_output_schema,
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
    "CLAIM_KNOWLEDGE_MODES",
    "ClaimRefreshResult",
    "DiscoveryDirection",
    "DiscoveryEnrichmentConfig",
    "DiscoveryFrontier",
    "DiscoveryIdea",
    "EvidenceConclusion",
    "IdeaGraph",
    "IterativeDiscoveryConfig",
    "IterativeDiscoveryResult",
    "DiscoveryRunConfig",
    "DiscoveryRunResult",
    "IdeaReview",
    "AnalysisCodeResult",
    "BackendAgentRecord",
    "BackendCapabilities",
    "BackendDetection",
    "BackendError",
    "CLISpec",
    "allowed_required_fields",
    "analysis_output_schema",
    "build_analysis_prompt",
    "build_discovery_schema",
    "build_idea_prompt",
    "build_idea_graph_from_run",
    "build_idea_graph_from_runs",
    "build_required_fields_prompt_block",
    "classify_hypothesis_evidence",
    "create_exploration_notebook",
    "directions_to_agent_context",
    "enrich_for_discovery",
    "execute_notebook_python",
    "frontiers_to_agent_context",
    "generate_pantheon_ideas",
    "get_backend",
    "graph_summary_markdown",
    "idea_signature",
    "idea_output_schema",
    "ingest_literature_claims",
    "idea_to_markdown",
    "infer_parameter_family",
    "list_backends",
    "load_idea_graph",
    "pack_schema",
    "plan_discovery_directions",
    "plan_discovery_frontiers",
    "review_idea_against_schema",
    "refresh_literature_claims_for_iteration",
    "register_backend",
    "run_auto_discovery",
    "run_iterative_auto_discovery",
    "run_pantheon_notebook_agents",
    "schematic_coverage_for_run",
    "schema_to_agent_context",
    "structured_conclusion_markdown",
    "unpack_schema",
    "upsert_structured_conclusion",
    "validate_discovery_schema",
    "write_direction_artifacts",
    "write_frontier_artifacts",
    "write_idea_graph_html",
    "write_idea_graph_artifacts",
    "unregister_backend",
]
