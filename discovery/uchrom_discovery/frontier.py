"""Backward-compatible aliases for the renamed direction planner."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .direction import (
    DiscoveryDirection,
    directions_to_agent_context,
    plan_discovery_directions,
    write_direction_artifacts,
)
from .graph import IdeaGraph

DiscoveryFrontier = DiscoveryDirection


def plan_discovery_frontiers(
    graph: IdeaGraph,
    schema: Mapping[str, Any],
    *,
    max_frontiers: int = 8,
    min_priority: float = 0.0,
) -> list[DiscoveryDirection]:
    """Legacy alias for :func:`plan_discovery_directions`."""
    return plan_discovery_directions(
        graph,
        schema,
        max_directions=max_frontiers,
        min_priority=min_priority,
    )


def frontiers_to_agent_context(frontiers: list[DiscoveryDirection]) -> str:
    """Legacy alias for :func:`directions_to_agent_context`."""
    return directions_to_agent_context(frontiers)


def write_frontier_artifacts(
    frontiers: list[DiscoveryDirection],
    output_dir: str | Path,
    *,
    json_name: str = "next_frontiers.json",
    markdown_name: str = "next_frontiers.md",
) -> dict[str, str]:
    """Legacy writer that preserves the historical artifact keys and path."""
    paths = write_direction_artifacts(
        frontiers,
        output_dir,
        json_name=json_name,
        markdown_name=markdown_name,
        directory_name="frontiers",
    )
    return {
        "frontiers_json": paths["directions_json"],
        "frontiers_markdown": paths["directions_markdown"],
    }
