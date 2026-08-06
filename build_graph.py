"""
build_graph.py — Phase 4: Graph Visualization

Scans all wiki/*.md files, parses frontmatter and inline [[id]] links,
builds GraphNode and GraphEdge lists, and exports graph.json.

Usage:
    python build_graph.py
    python build_graph.py --output graph.json
"""

import sys
import io
import json
import re
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Set, Tuple

import typer
import frontmatter

# Ensure project root is in sys.path when running directly
sys.path.append(str(Path(__file__).parent.resolve()))

# Fix Windows console encoding
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import WIKI_DIR, GRAPH_PATH
from models.graph import GraphNode, GraphEdge, GraphExport

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex for valid [[id]] links (GRPH-03)
LINK_PATTERN = re.compile(r"\[\[(\d{8}_[a-f0-9]{6})\]\]")

# PARA category color mapping (for reference — used in graph.html)
PARA_COLORS = {
    "Projects": "#4A90D9",
    "Areas": "#27AE60",
    "Resources": "#E67E22",
    "Archives": "#95A5A6",
}

CONTENT_PREVIEW_LENGTH = 200


# ---------------------------------------------------------------------------
# Core graph building logic
# ---------------------------------------------------------------------------


def load_wiki_notes() -> dict:
    """
    Load all wiki/*.md files and return a dict of {note_id: metadata+content}.
    GRPH-08: Uses defensive .get() on all fields with defaults.
    """
    notes = {}
    for md_path in sorted(WIKI_DIR.glob("*.md")):
        note_id = md_path.stem
        try:
            post = frontmatter.load(md_path)
            metadata = post.metadata
            content = post.content or ""

            notes[note_id] = {
                "id": note_id,
                "title": str(metadata.get("title", note_id)),
                "para_category": str(metadata.get("para_category", "Resources")),
                "tags": metadata.get("tags", []),
                "summary": str(metadata.get("summary", "")),
                "links": metadata.get("links", []),
                "content": content,
            }
        except Exception as e:
            print(f"Warning: Failed to load wiki note {md_path.name}: {e}", file=sys.stderr)

    return notes


def extract_inline_links(content: str) -> List[str]:
    """
    Extract [[id]] links from markdown body text.
    GRPH-03: Only matches valid {YYYYMMDD}_{6-char-hex} IDs.
    """
    return LINK_PATTERN.findall(content)


def escape_html(text: str) -> str:
    """GRPH-10: Escape HTML special characters for safe tooltip rendering."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_graph(notes: dict) -> GraphExport:
    """
    Build GraphExport from loaded wiki notes.
    GRPH-01: Returns empty graph if no notes.
    GRPH-02: Orphan nodes (no edges) still included.
    GRPH-04: Deduplicates edges using sorted tuple key.
    """
    nodes = []
    seen_edges: Set[Tuple[str, str]] = set()
    edges = []

    valid_ids = set(notes.keys())

    for note_id, note_data in notes.items():
        # Build content preview (first N chars, HTML-escaped)
        raw_content = note_data["content"]
        # Strip the markdown heading line for a cleaner preview
        preview_text = raw_content.strip()
        if preview_text.startswith("#"):
            # Skip the first heading line
            lines = preview_text.split("\n", 1)
            preview_text = lines[1].strip() if len(lines) > 1 else ""
        content_preview = escape_html(preview_text[:CONTENT_PREVIEW_LENGTH])
        if len(preview_text) > CONTENT_PREVIEW_LENGTH:
            content_preview += "..."

        # Build node
        node = GraphNode(
            id=note_id,
            label=escape_html(note_data["title"]),
            category=note_data["para_category"],
            tags=note_data["tags"],
            summary=escape_html(note_data["summary"]),
            content_preview=content_preview,
        )
        nodes.append(node)

        # Collect links from frontmatter + inline [[id]] references
        frontmatter_links = note_data.get("links", [])
        if not isinstance(frontmatter_links, list):
            frontmatter_links = []
        inline_links = extract_inline_links(raw_content)
        all_link_targets = set(frontmatter_links) | set(inline_links)

        for target_id in all_link_targets:
            # Skip links to non-existent notes (dangling references)
            if target_id not in valid_ids:
                continue
            # Skip self-links
            if target_id == note_id:
                continue

            # GRPH-04: Deduplicate — normalize edge key
            edge_key = tuple(sorted([note_id, target_id]))
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            edge = GraphEdge(
                source=note_id,
                target=target_id,
                weight=1.0,  # default weight for frontmatter/inline links
                type="explicit_link",
            )
            edges.append(edge)

    return GraphExport(nodes=nodes, edges=edges)


def export_graph(graph: GraphExport, output_path: Path) -> None:
    """
    Export graph to JSON file.
    GRPH-07: Writes to temp file first then does atomic rename.
    """
    graph_dict = graph.to_dict()

    # Write to temp file first for atomicity (GRPH-07)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".json", dir=str(output_path.parent)
    )
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(graph_dict, f, ensure_ascii=False, indent=2)
        # Atomic rename
        shutil.move(tmp_path, str(output_path))
    except Exception:
        # Clean up temp file on failure
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        raise


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="SecondSelf Phase 4 — Build knowledge graph from wiki notes")


@app.command()
def main(
    output: Optional[str] = typer.Option(
        None, "--output", "-o",
        help="Output path for graph JSON (default: graph.json in project root)"
    ),
):
    """
    Scan wiki notes, build nodes + edges, and export graph.json.
    """
    output_path = Path(output) if output else GRAPH_PATH

    print("Scanning wiki notes...")
    notes = load_wiki_notes()

    if not notes:
        print("No wiki notes found. Exporting empty graph (GRPH-01).")
    else:
        print(f"Found {len(notes)} wiki note(s).")

    print("Building graph...")
    graph = build_graph(notes)

    print(f"Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    export_graph(graph, output_path)
    print(f"Exported to {output_path}")

    # Summary
    if graph.nodes:
        categories = {}
        for node in graph.nodes:
            cat = node.category
            categories[cat] = categories.get(cat, 0) + 1
        print("\nPARA distribution:")
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count}")

        orphans = set(n.id for n in graph.nodes)
        for edge in graph.edges:
            orphans.discard(edge.source)
            orphans.discard(edge.target)
        if orphans:
            print(f"\nOrphan nodes (no edges): {len(orphans)}")


if __name__ == "__main__":
    app()
