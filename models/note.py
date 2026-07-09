from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

@dataclass
class WikiNote:
    id: str
    title: str
    para_category: str  # "Projects" | "Areas" | "Resources" | "Archives"
    tags: List[str]
    summary: str
    links: List[str]  # IDs of linked notes
    embedding_id: str
    created_at: str
    updated_at: str
    content: str  # The markdown body content (excluding frontmatter)

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass instance to dictionary (excluding body content)."""
        d = asdict(self)
        d.pop("content", None)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any], content: str = "") -> "WikiNote":
        """Create dataclass instance from a dictionary of metadata and a body content string."""
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        if "content" not in filtered_data:
            filtered_data["content"] = content
        return cls(**filtered_data)
