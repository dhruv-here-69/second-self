from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

@dataclass
class GraphNode:
    id: str
    label: str
    category: str
    tags: List[str]
    summary: str
    content_preview: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class GraphEdge:
    source: str
    target: str
    weight: float
    type: str  # "explicit_link" | "semantic_similarity"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class GraphExport:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges]
        }
