import sys
import json
from pathlib import Path
import pytest

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from build_graph import build_graph, extract_inline_links, escape_html
from models.graph import GraphNode, GraphEdge

def test_extract_inline_links():
    content = "Here is a link to [[20260709_540350]] and another [[20260709_54a36b]]."
    links = extract_inline_links(content)
    assert links == ["20260709_540350", "20260709_54a36b"]

    # Invalid ID formats should be ignored
    content_invalid = "Bad links: [[12345_abc]] or [[20260709_54035]] or [[20260709_540350a]]."
    links_invalid = extract_inline_links(content_invalid)
    assert len(links_invalid) == 0

def test_escape_html():
    text = "Hello <script>alert(1)</script> & welcome!"
    escaped = escape_html(text)
    assert escaped == "Hello &lt;script&gt;alert(1)&lt;/script&gt; &amp; welcome!"

def test_build_graph_basic():
    # Mock some notes
    notes = {
        "20260709_000001": {
            "id": "20260709_000001",
            "title": "Note One",
            "para_category": "Projects",
            "tags": ["test"],
            "summary": "This is note one",
            "links": ["20260709_000002"],
            "content": "# Note One\n\nBody content of note one linking to [[20260709_000002]]."
        },
        "20260709_000002": {
            "id": "20260709_000002",
            "title": "Note Two",
            "para_category": "Resources",
            "tags": ["test"],
            "summary": "This is note two",
            "links": ["20260709_000001"], # Bidirectional link
            "content": "# Note Two\n\nBody content of note two linking back to [[20260709_000001]]."
        },
        "20260709_000003": {
            "id": "20260709_000003",
            "title": "Orphan Note",
            "para_category": "Areas",
            "tags": ["orphan"],
            "summary": "No links",
            "links": [],
            "content": "# Orphan Note\n\nThis note is not connected to anything else."
        }
    }

    graph = build_graph(notes)

    # 3 nodes should exist
    assert len(graph.nodes) == 3
    node_ids = {n.id for n in graph.nodes}
    assert node_ids == {"20260709_000001", "20260709_000002", "20260709_000003"}

    # Orphan note should still appear as a node (GRPH-02)
    orphan_node = next(n for n in graph.nodes if n.id == "20260709_000003")
    assert orphan_node.label == "Orphan Note"
    assert orphan_node.category == "Areas"

    # Edge checks:
    # A->B and B->A should be deduplicated to a single edge (GRPH-04)
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    # Source/target order should be sorted alphabetically by build_graph deduplication
    assert edge.source == "20260709_000001"
    assert edge.target == "20260709_000002"
    assert edge.type == "explicit_link"
