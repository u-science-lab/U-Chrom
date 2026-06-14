from dataclasses import dataclass, field
from typing import Optional, Any
import json
import time
from datetime import datetime


# Cap on per-view render diagnostics (FIFO). Keeps a misbehaving render that
# throws on every frame from growing the session unbounded.
MAX_VIEW_DIAGNOSTICS = 20


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge ``patch`` into ``base`` in place and return it.

    Mirrors the frontend ``deepMerge`` so an update means the same thing on
    both ends. Dict values merge key-by-key; everything else (lists, scalars)
    replaces wholesale.
    """
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


@dataclass
class ViewSession:
    """Backend-authoritative state for one agent-driven view.

    The agent mutates ``state`` (render_gosling creates it, patch_gosling
    deep-merges into it); the user's interactions are reported back and also
    land here (see ws_handler ``ui_event``). ``revision`` increments on every
    mutation so the frontend can detect a gap and request a fresh snapshot.
    """
    view_id: str
    view_type: str  # "gosling" | "component" | "embedding" | "structure" | ...
    state: dict = field(default_factory=dict)
    revision: int = 0
    title: str = ""
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    # Rendering diagnostics fed back from the frontend (React error-boundary
    # catches, Gosling spec failures). Capped FIFO so a render that keeps
    # throwing can't grow this unbounded; get_view_state surfaces it so the
    # agent can SEE that its output "画崩了" and self-correct.
    diagnostics: list = field(default_factory=list)

    def replace(self, state: dict) -> None:
        self.state = state
        self.revision += 1
        self.last_updated = time.time()

    def merge(self, patch: dict) -> None:
        _deep_merge(self.state, patch)
        self.revision += 1
        self.last_updated = time.time()

    def add_diagnostic(self, diag: dict, cap: int = MAX_VIEW_DIAGNOSTICS) -> None:
        """Append a render diagnostic, keeping only the most recent ``cap``."""
        self.diagnostics.append(diag)
        if len(self.diagnostics) > cap:
            self.diagnostics = self.diagnostics[-cap:]
        self.last_updated = time.time()

    def to_dict(self) -> dict:
        return {
            "view_id": self.view_id,
            "view_type": self.view_type,
            "state": self.state,
            "revision": self.revision,
            "title": self.title,
            "diagnostics": self.diagnostics,
        }


@dataclass
class Viewport:
    chrom: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None

    # Support both attribute access (vp.chrom) and dict-style access
    # (vp["chrom"]) so callers and tests written against either form work.
    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError as e:
            raise KeyError(key) from e

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __eq__(self, other):
        if isinstance(other, Viewport):
            return (self.chrom, self.start, self.end) == (other.chrom, other.start, other.end)
        if isinstance(other, dict):
            return {"chrom": self.chrom, "start": self.start, "end": self.end} == other
        return NotImplemented

    def __hash__(self):
        return hash((self.chrom, self.start, self.end))


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

    # Backend-authoritative view state (agent-driven UI). Keyed by view_id.
    # Not serialized to .uchromfig (live UI state, rebuilt per connection),
    # but survives WS reconnects because the Session outlives the socket.
    views: dict[str, "ViewSession"] = field(default_factory=dict)
    # When the WS disconnects we mark the time instead of dropping the session,
    # so a reconnect within the grace window restores history + views.
    detached_at: Optional[float] = None

    def get_or_create_view(
        self, view_id: str, view_type: str, title: str = ""
    ) -> "ViewSession":
        v = self.views.get(view_id)
        if v is None:
            v = ViewSession(view_id=view_id, view_type=view_type, title=title)
            self.views[view_id] = v
        return v

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

        # Load viewport — always reconstruct a Viewport object so callers can
        # use attribute access (session.viewport.chrom). Accept dict or object.
        if "viewport" in data and data["viewport"] is not None:
            vp = data["viewport"]
            if isinstance(vp, dict):
                session.viewport = Viewport(
                    chrom=vp.get("chrom"),
                    start=vp.get("start"),
                    end=vp.get("end"),
                )
            else:
                session.viewport = Viewport(
                    chrom=getattr(vp, "chrom", None),
                    start=getattr(vp, "start", None),
                    end=getattr(vp, "end", None),
                )

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
