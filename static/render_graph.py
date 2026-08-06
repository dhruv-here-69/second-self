"""
render_graph.py — Helper to inject graph JSON into graph.html for Streamlit embedding.

Usage (from app.py):
    from static.render_graph import render_graph_html
    html = render_graph_html(graph_path=Path("graph.json"), height=600)
    st.components.v1.html(html, height=600)
"""

import json
from pathlib import Path
from typing import Optional

STATIC_DIR = Path(__file__).parent
GRAPH_HTML_PATH = STATIC_DIR / "graph.html"


def render_graph_html(graph_path: Optional[Path] = None, height: int = 600) -> str:
    """
    Read graph.json and graph.html, inject graph data into the HTML
    via a <script> tag setting window.graphData, and return the
    complete HTML string ready for Streamlit st.components.v1.html().
    """
    graph_path = graph_path or Path("graph.json")

    # Load graph data
    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            graph_data = json.load(f)
    except FileNotFoundError:
        graph_data = {"nodes": [], "edges": []}
    except json.JSONDecodeError:
        graph_data = {"nodes": [], "edges": []}

    graph_json = json.dumps(graph_data, ensure_ascii=False)

    # Load HTML template
    with open(GRAPH_HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject window.graphData BEFORE the main <script> block so the IIFE
    # can read it synchronously when it checks `if (window.graphData)`.
    # Injecting after </body> is too late — the IIFE has already run.
    inject_script = (
        f'<script type="text/javascript">window.graphData = {graph_json};</script>\n'
    )
    html = html.replace('<script type="text/javascript">\n(function ()', inject_script + '<script type="text/javascript">\n(function ()')

    return html
