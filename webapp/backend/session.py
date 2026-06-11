from dataclasses import dataclass, field
from typing import Optional, Any
import json
from datetime import datetime


@dataclass
class Viewport:
    chrom: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None


@dataclass
class Session:
    h5cd_path: Optional[str] = None
    viewport: Optional[dict] = None
    cell_selection: list = field(default_factory=list)
    conversation_history: list[dict] = field(default_factory=list)

    # Legacy attributes for backward compatibility
    session_id: Optional[str] = None
    chromdata: Any = None  # uchrom.core.ChromData, loaded later
    pending_artifacts: list[dict] = field(default_factory=list)

    # Extended state for persistence
    analysis_results: dict = field(default_factory=dict)  # TADs, compartments, loops
    annotations: list[dict] = field(default_factory=list)  # Custom annotations
    highlight_regions: list[dict] = field(default_factory=list)  # Highlighted regions
    colormap_config: Optional[dict] = None  # Colormap configuration
    panels: list[dict] = field(default_factory=list)  # Panel configurations

    def to_dict(self) -> dict:
        """Serialize session to dictionary for .uchromfig format."""
        # Handle viewport as dict or Viewport object
        if isinstance(self.viewport, dict):
            viewport_dict = self.viewport
        elif self.viewport is None:
            viewport_dict = {"chrom": None, "start": None, "end": None}
        else:
            viewport_dict = {
                "chrom": self.viewport.chrom,
                "start": self.viewport.start,
                "end": self.viewport.end,
            }

        return {
            "version": "2.0",
            "session_id": self.session_id,
            "h5cd_path": self.h5cd_path,
            "viewport": viewport_dict,
            "cell_selection": self.cell_selection,
            "conversation_history": self.conversation_history,
            "analysis_results": self.analysis_results,
            "annotations": self.annotations,
            "highlight_regions": self.highlight_regions,
            "colormap_config": self.colormap_config,
            "panels": self.panels,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @classmethod
    def from_dict(cls, data: dict, session_id: Optional[str] = None) -> "Session":
        """Deserialize session from dictionary."""
        session = cls(session_id=session_id or data.get("session_id"))

        # Load h5cd_path
        session.h5cd_path = data.get("h5cd_path")

        # Load viewport - handle both dict and Viewport object
        if "viewport" in data:
            vp = data["viewport"]
            if isinstance(vp, dict):
                session.viewport = vp
            else:
                session.viewport = {
                    "chrom": vp.get("chrom") if hasattr(vp, "get") else getattr(vp, "chrom", None),
                    "start": vp.get("start") if hasattr(vp, "get") else getattr(vp, "start", None),
                    "end": vp.get("end") if hasattr(vp, "get") else getattr(vp, "end", None),
                }

        # Load other state
        session.cell_selection = data.get("cell_selection", [])
        session.conversation_history = data.get("conversation_history", [])
        session.analysis_results = data.get("analysis_results", {})
        session.annotations = data.get("annotations", [])
        session.highlight_regions = data.get("highlight_regions", [])
        session.colormap_config = data.get("colormap_config")
        session.panels = data.get("panels", [])

        return session

    def save(self, path: str):
        """Save session to .uchromfig file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str, session_id: str) -> "Session":
        """Load session from .uchromfig file."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data, session_id)
