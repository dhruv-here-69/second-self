"""
pipeline.py — Phase 5B: Pipeline Orchestrator

Ties together all pipeline modules (classify.py, link.py, build_graph.py)
into a single executable script.

Usage:
    python pipeline.py
    python pipeline.py --id 20260709_a3f9c2
    python pipeline.py --rebuild
"""

import sys
import subprocess
from pathlib import Path
from typing import Optional

import typer

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).parent.resolve()))

app = typer.Typer(help="SecondSelf Phase 5B — End-to-End Pipeline Orchestrator")


def run_command(args: list[str]) -> bool:
    """Helper to run python commands via subprocess."""
    cmd = [sys.executable] + args
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed with exit code {e.returncode}", file=sys.stderr)
        return False


@app.command()
def main(
    capture_id: Optional[str] = typer.Option(
        None, "--id", help="Process a single capture by ID"
    ),
    rebuild: bool = typer.Option(
        False, "--rebuild", "-r", help="Full rebuild from raw captures and wiki notes"
    ),
):
    """
    Runs classification, auto-linking, and graph building in sequence.
    """
    print("=" * 60)
    print("STARTING SECONDSELF PIPELINE RUN")
    print("=" * 60)

    # 1. Classification Step
    print("\n--- STAGE 1: Classification (classify.py) ---")
    classify_args = ["classify.py"]
    if capture_id:
        classify_args += ["--id", capture_id]
    elif rebuild:
        classify_args += ["--all", "--force"]
    else:
        classify_args += ["--all"]

    classify_success = run_command(classify_args)
    if not classify_success:
        print("Warning: Classification stage reported errors. Continuing to next stage...", file=sys.stderr)

    # 2. Linking Step
    print("\n--- STAGE 2: Auto-Linking (link.py) ---")
    link_args = ["link.py"]
    if capture_id:
        link_args += ["--id", capture_id]
    elif rebuild:
        link_args += ["--rebuild"]
    else:
        link_args += ["--all"]

    link_success = run_command(link_args)
    if not link_success:
        print("Warning: Auto-linking stage reported errors. Continuing to next stage...", file=sys.stderr)

    # 3. Graph Building Step
    print("\n--- STAGE 3: Graph Building (build_graph.py) ---")
    graph_args = ["build_graph.py"]
    graph_success = run_command(graph_args)
    if not graph_success:
        print("Error: Graph building failed.", file=sys.stderr)

    print("\n" + "=" * 60)
    if classify_success and link_success and graph_success:
        print("PIPELINE COMPLETED SUCCESSFULLY!")
    else:
        print("PIPELINE COMPLETED WITH WARNINGS/ERRORS.")
    print("=" * 60)


if __name__ == "__main__":
    app()
