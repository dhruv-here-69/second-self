"""
app.py — Phase 5C: Streamlit Web UI

A premium, interactive web interface for SecondSelf. Includes sidebar capture controls,
pipeline orchestration, an interactive force-directed vis-network graph, and a
Retrieval-Augmented Generation Q&A panel.
"""

import os
import sys
import re
import subprocess
import json
from pathlib import Path

import streamlit as st

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).parent.resolve()))

from config import (
    USE_DEMO_DATA,
    GRAPH_PATH,
    WIKI_DIR,
    RAW_DIR,
)
from ask import ask
from static.render_graph import render_graph_html

# ---------------------------------------------------------------------------
# Streamlit Page Config & Premium Aesthetics (CSS)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="SecondSelf — Your AI Second Brain",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling using Outfit/Inter fonts, glassmorphism, and neon gradients
PREMIUM_STYLE = """
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
    /* Global Styles */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        letter-spacing: -0.02em;
    }

    /* Gradient Header */
    .header-container {
        background: linear-gradient(135deg, #1a1d2e 0%, #0f1117 100%);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 30px;
        margin-bottom: 25px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }
    
    .header-title {
        font-size: 2.8rem;
        background: linear-gradient(135deg, #4A90D9 0%, #27AE60 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
    }
    
    .header-subtitle {
        color: #888899;
        font-size: 1.1rem;
        font-weight: 300;
    }

    /* Glassmorphic Cards */
    .glass-card {
        background: rgba(26, 29, 46, 0.6);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
    }

    .answer-card {
        border-left: 4px solid #4A90D9;
        background: rgba(74, 144, 217, 0.03);
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #0f111a !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }

    /* Styled Alerts */
    .demo-badge {
        display: inline-block;
        background: rgba(230, 126, 34, 0.15);
        color: #E67E22;
        border: 1px solid rgba(230, 126, 34, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 500;
        margin-top: 5px;
    }
</style>
"""
st.markdown(PREMIUM_STYLE, unsafe_allow_html=True)

# Initialize Session State
if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False

# Helper to run CLI tools via subprocesses
def run_cli_tool(command: list[str]) -> tuple[bool, str]:
    cmd = [sys.executable] + command
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, res.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr or e.stdout

# ---------------------------------------------------------------------------
# Sidebar UI: Capture & Pipeline Control
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://img.icons8.com/nolan/96/artificial-intelligence.png", width=64)
    st.markdown("### Brain Controls")
    
    if USE_DEMO_DATA:
        st.markdown('<div class="demo-badge">🔒 Cloud Demo Mode (Read-Only)</div>', unsafe_allow_html=True)
        st.caption("Capturing and reprocessing are disabled for the cloud demo.")
    
    st.markdown("---")
    st.markdown("#### 📥 Capture New Item")
    
    # Selection of Capture Source
    capture_type = st.selectbox(
        "Source Type",
        ["Plain Text Note", "URL Link", "Local File Path"],
        disabled=USE_DEMO_DATA
    )
    
    # Build Capture Inputs
    with st.form("capture_form"):
        note_content = ""
        url_input = ""
        file_input = ""
        
        if capture_type == "Plain Text Note":
            note_content = st.text_area("Note Content", placeholder="Type your ideas, snippets, or thoughts here...", height=120)
        elif capture_type == "URL Link":
            url_input = st.text_input("URL Link", placeholder="https://example.com/article")
        else:
            file_input = st.text_input("Local File Path", placeholder="C:/path/to/report.pdf")
            
        capture_btn = st.form_submit_button("Capture & Process", disabled=USE_DEMO_DATA)
        
        if capture_btn and not USE_DEMO_DATA:
            if st.session_state.pipeline_running:
                st.warning("Pipeline is already running! Please wait.")
            else:
                # Capture processing
                st.session_state.pipeline_running = True
                success = False
                capture_out = ""
                capture_id = ""
                
                with st.spinner("Capturing content..."):
                    # Assemble capture command
                    if capture_type == "Plain Text Note":
                        if not note_content.strip():
                            st.error("Capture content cannot be empty.")
                            st.session_state.pipeline_running = False
                        else:
                            ok, out = run_cli_tool(["capture.py", note_content.strip()])
                            success = ok
                            capture_out = out
                    elif capture_type == "URL Link":
                        if not url_input.strip():
                            st.error("URL input cannot be empty.")
                            st.session_state.pipeline_running = False
                        else:
                            ok, out = run_cli_tool(["capture.py", "--url", url_input.strip()])
                            success = ok
                            capture_out = out
                    else:
                        if not file_input.strip():
                            st.error("File path cannot be empty.")
                            st.session_state.pipeline_running = False
                        else:
                            ok, out = run_cli_tool(["capture.py", "--file", file_input.strip()])
                            success = ok
                            capture_out = out

                    if success:
                        # Extract capture ID from stdout (capture.py prints "ID: XXXXXXXX_xxxxxx")
                        match = re.search(r"ID:\s*(\d{8}_[a-f0-9]{6})", capture_out)
                        if match:
                            capture_id = match.group(1)
                            st.toast(f"Captured {capture_id} successfully!")
                            with st.spinner(f"Running pipeline for {capture_id}..."):
                                pipe_ok, pipe_out = run_cli_tool(["pipeline.py", "--id", capture_id])
                                if pipe_ok:
                                    st.success(f"✅ Processing complete for {capture_id}!")
                                    st.session_state.pipeline_running = False
                                    st.rerun()
                                else:
                                    st.error("Pipeline run encountered errors.")
                        else:
                            st.error(f"Could not parse capture ID from output: {capture_out}")
                    else:
                        st.error(f"Capture failed: {capture_out}")
                
                st.session_state.pipeline_running = False

    st.markdown("---")
    st.markdown("#### ⚙️ Pipeline Utilities")
    
    # Standard Pipeline Processing
    run_all_btn = st.button("Process Pending Captures", disabled=USE_DEMO_DATA)
    if run_all_btn and not USE_DEMO_DATA:
        if st.session_state.pipeline_running:
            st.warning("Pipeline is already running!")
        else:
            st.session_state.pipeline_running = True
            with st.spinner("Processing all pending captures..."):
                ok, out = run_cli_tool(["pipeline.py"])
                if ok:
                    st.success("All pending captures processed successfully!")
                else:
                    st.error(f"Pipeline processing failed: {out}")
            st.session_state.pipeline_running = False
            
    # Full Rebuild Control
    rebuild_btn = st.button("Full Rebuild (Classify + Link + Graph)", disabled=USE_DEMO_DATA)
    if rebuild_btn and not USE_DEMO_DATA:
        if st.session_state.pipeline_running:
            st.warning("Pipeline is already running!")
        else:
            st.session_state.pipeline_running = True
            with st.spinner("Rebuilding knowledge base from scratch..."):
                ok, out = run_cli_tool(["pipeline.py", "--rebuild"])
                if ok:
                    st.success("Rebuild completed successfully!")
                else:
                    st.error(f"Rebuild failed: {out}")
            st.session_state.pipeline_running = False

    st.markdown("---")
    # Quick Statistics
    try:
        raw_count = len(list(RAW_DIR.glob("*.json")))
        wiki_count = len(list(WIKI_DIR.glob("*.md")))
        st.markdown("#### 📊 Statistics")
        st.metric("Raw Captures", raw_count)
        st.metric("Wiki Notes", wiki_count)
    except Exception:
        pass



# ---------------------------------------------------------------------------
# Main UI Layout
# ---------------------------------------------------------------------------

# Gradient header card
st.markdown(
    """
    <div class="header-container">
        <h1 class="header-title">SecondSelf — Your AI Second Brain</h1>
        <div class="header-subtitle">A self-organizing knowledge base backed completely by your personal files and notes.</div>
    </div>
    """,
    unsafe_allow_html=True
)

# 🔍 Section 1: Ask Your Brain Form (UI-01: wrapped inside form)
with st.form("ask_form"):
    st.markdown("### 🔍 Ask Your Second Brain")
    question = st.text_input(
        "Query",
        placeholder="e.g. What is SecondSelf? / Summarize my project ideas / What did I learn about sentence embeddings?",
        label_visibility="collapsed"
    )
    submit_ask = st.form_submit_button("Search & Synthesize")

if submit_ask and question.strip():
    with st.spinner("Retrieving notes and synthesizing answer..."):
        response = ask(question.strip())
        
        # Display synthesized answer
        st.markdown(
            f"""
            <div class="glass-card answer-card">
                <h4>🧠 Synthesized Answer</h4>
                <p style="font-size: 1.05rem; line-height: 1.6; color: #f0f0f5;">{response.answer}</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Display cited sources as cards
        if response.sources:
            st.markdown("##### 📚 Sources Cited:")
            cols = st.columns(min(len(response.sources), 3))
            for idx, source in enumerate(response.sources):
                col_idx = idx % 3
                with cols[col_idx]:
                    st.markdown(
                        f"""
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">
                            <span style="font-size: 0.75rem; font-weight: 600; color: #4A90D9; background: rgba(74, 144, 217, 0.15); padding: 2px 6px; border-radius: 4px;">{source.id}</span>
                            <div style="font-weight: 600; font-size: 0.95rem; margin-top: 6px; margin-bottom: 4px; color: #fff;">{source.title}</div>
                            <div style="font-size: 0.8rem; color: #888; line-height: 1.4; height: 55px; overflow: hidden; text-overflow: ellipsis;">{source.excerpt}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
        else:
            st.caption("No sources were cited in the answer.")

# 🌐 Section 2: Interactive Knowledge Graph
st.markdown("### 🌐 Interactive Knowledge Graph")
if Path(GRAPH_PATH).exists():
    try:
        graph_html = render_graph_html(GRAPH_PATH, height=650)
        st.iframe(graph_html, height=650)
    except Exception as e:
        st.error(f"Failed to load graph visualization: {e}")
else:
    # GRPH-06: Missing graph.json at UI load placeholder
    st.info("Knowledge graph file (graph.json) not found. Run a rebuild from the sidebar to generate it.")
