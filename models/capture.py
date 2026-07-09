from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any

@dataclass
class RawCapture:
    id: str
    captured_at: str
    type: str  # "note" | "link" | "file"
    content: str
    status: str  # "pending" | "classified" | "linked" | "error"
    source_url: Optional[str] = None
    file_path: Optional[str] = None
    mime_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass instance to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RawCapture":
        """Create dataclass instance from dictionary."""
        # Ensure we only pass valid fields to constructor
        valid_fields = {
            f for f in cls.__dataclass_fields__
        }
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
