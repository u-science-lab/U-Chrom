from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class Viewport:
    chrom: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None


@dataclass
class Session:
    session_id: str
    chromdata: Any = None  # uchrom.core.ChromData, loaded later
    viewport: Viewport = field(default_factory=Viewport)
    cell_selection: list = field(default_factory=list)
    pending_artifacts: list[dict] = field(default_factory=list)
