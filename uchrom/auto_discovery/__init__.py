"""Multi-omics auto-discovery helpers for ChromData."""

from .ideas import DiscoveryIdea, IdeaReview, review_idea_against_schema
from .evidence import (
    EvidenceConclusion,
    classify_hypothesis_evidence,
    structured_conclusion_markdown,
)
from .llm import generate_openai_analysis_code, generate_openai_ideas
from .notebooks import (
    create_exploration_notebook,
    execute_notebook_python,
    idea_to_markdown,
    upsert_structured_conclusion,
)
from .pantheon import generate_pantheon_ideas, run_pantheon_notebook_agents
from .runner import DiscoveryRunConfig, DiscoveryRunResult, run_auto_discovery
from .schema import (
    DISCOVERY_SCHEMA_KEY,
    build_discovery_schema,
    pack_schema,
    schema_to_agent_context,
    unpack_schema,
    validate_discovery_schema,
)

__all__ = [
    "DISCOVERY_SCHEMA_KEY",
    "DiscoveryIdea",
    "EvidenceConclusion",
    "DiscoveryRunConfig",
    "DiscoveryRunResult",
    "IdeaReview",
    "build_discovery_schema",
    "classify_hypothesis_evidence",
    "create_exploration_notebook",
    "execute_notebook_python",
    "generate_openai_analysis_code",
    "generate_openai_ideas",
    "generate_pantheon_ideas",
    "idea_to_markdown",
    "pack_schema",
    "review_idea_against_schema",
    "run_auto_discovery",
    "run_pantheon_notebook_agents",
    "schema_to_agent_context",
    "structured_conclusion_markdown",
    "unpack_schema",
    "upsert_structured_conclusion",
    "validate_discovery_schema",
]
