"""
link.py — Phase 3: Auto-Linking

Computes embeddings for each classified wiki note using SentenceTransformers,
calculates cosine similarity, and auto-links related notes bidirectionally.

Usage:
    python link.py --all
    python link.py --id 20260709_a3f9c2
    python link.py --rebuild
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Tuple, List, Set

import typer
import yaml
import numpy as np
import frontmatter
from sentence_transformers import SentenceTransformer

# Ensure project root is in sys.path when running directly
sys.path.append(str(Path(__file__).parent.resolve()))

from config import (
    RAW_DIR,
    WIKI_DIR,
    DATA_DIR,
    SIMILARITY_THRESHOLD,
    MAX_LINKS_PER_NOTE,
    MIN_CONTENT_LENGTH,
)
from models.note import WikiNote

# Initialize paths
INDEX_PATH = DATA_DIR / "embeddings.index"
META_PATH = DATA_DIR / "embeddings.meta.json"

# Load SentenceTransformer model once at module init
print("Loading sentence-transformers model 'all-MiniLM-L6-v2'...", flush=True)
model = SentenceTransformer("all-MiniLM-L6-v2")

# ---------------------------------------------------------------------------
# Embedding Store I/O and Validation
# ---------------------------------------------------------------------------

def load_embedding_store() -> Tuple[np.ndarray, List[str]]:
    """
    Loads data/embeddings.index and data/embeddings.meta.json.
    Returns (embeddings_array, list_of_ids).
    If they do not exist, returns an empty array and list.
    If corrupt (LNK-09), raises ValueError with a suggestion to rebuild.
    """
    if not INDEX_PATH.exists() and not META_PATH.exists():
        return np.empty((0, 384), dtype=np.float32), []

    if INDEX_PATH.exists() != META_PATH.exists():
        raise ValueError("Index corrupt. Run link.py --rebuild")

    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if not isinstance(meta, list):
            raise ValueError("Metadata is not a list")
    except Exception as e:
        raise ValueError("Index corrupt. Run link.py --rebuild") from e

    try:
        with open(INDEX_PATH, "rb") as f:
            embeddings = np.load(f)
    except Exception as e:
        raise ValueError("Index corrupt. Run link.py --rebuild") from e

    if not isinstance(embeddings, np.ndarray):
        raise ValueError("Index corrupt. Run link.py --rebuild")

    # Validate shape compatibility
    if len(meta) != len(embeddings):
        raise ValueError("Index corrupt. Run link.py --rebuild")

    if len(embeddings.shape) != 2 or (embeddings.shape[0] > 0 and embeddings.shape[1] != 384):
        raise ValueError("Index corrupt. Run link.py --rebuild")

    return embeddings.astype(np.float32), meta


def save_embedding_store(embeddings: np.ndarray, meta: List[str]) -> None:
    """Saves embeddings and metadata mapping to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX_PATH, "wb") as f:
        np.save(f, embeddings)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# Wiki Note I/O and Embedding
# ---------------------------------------------------------------------------

def load_wiki_note(path: Path) -> Tuple[WikiNote, bool]:
    """
    Loads a WikiNote from a markdown file with YAML frontmatter.
    Checks and prunes dangling references from the links list (LNK-04).
    Returns (wiki_note_object, was_pruned_flag).
    """
    post = frontmatter.load(path)
    metadata = post.metadata
    content = post.content

    links = metadata.get("links", [])
    if not isinstance(links, list):
        links = []

    valid_links = []
    pruned = False
    for link_id in links:
        if (WIKI_DIR / f"{link_id}.md").exists():
            valid_links.append(link_id)
        else:
            pruned = True

    metadata["links"] = valid_links
    return WikiNote.from_dict(metadata, content), pruned


def save_wiki_note(note: WikiNote) -> Path:
    """Saves a WikiNote back to disk preserving YAML formatting."""
    dest = WIKI_DIR / f"{note.id}.md"
    frontmatter_data = {
        "id": note.id,
        "title": note.title,
        "para_category": note.para_category,
        "tags": note.tags,
        "summary": note.summary,
        "links": note.links,
        "embedding_id": note.embedding_id,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }
    fm_str = yaml.dump(
        frontmatter_data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    with open(dest, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(fm_str)
        f.write("---\n")
        f.write(note.content)
        if not note.content.endswith("\n"):
            f.write("\n")
    return dest


def embed_note(note: WikiNote) -> np.ndarray:
    """
    Computes embedding for a WikiNote (3.3).
    Concatenates title + "\n" + content before embedding.
    """
    text_to_embed = f"{note.title}\n{note.content}"
    return model.encode(text_to_embed, convert_to_numpy=True).astype(np.float32)


def update_raw_capture_status(note_id: str, skip_reason: Optional[str] = None) -> None:
    """Updates the status of a raw capture to 'linked' and logs skip reason if any."""
    raw_path = RAW_DIR / f"{note_id}.json"
    if raw_path.exists():
        try:
            with open(raw_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["status"] = "linked"
            if skip_reason:
                if "metadata" not in data or not isinstance(data["metadata"], dict):
                    data["metadata"] = {}
                data["metadata"]["skip_reason"] = skip_reason
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  Updated status of raw capture {note_id} to 'linked'.")
        except Exception as e:
            print(f"  Warning: Failed to update status for raw capture {note_id}: {e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Linking Orchestration
# ---------------------------------------------------------------------------

def run_linking(target_ids: List[str], rebuild: bool = False) -> None:
    """
    Orchestrates embedding and auto-linking (3.5 - 3.7).
    Runs single-threaded to prevent write races (LNK-05).
    """
    # 1. Load the embedding store
    try:
        embeddings, meta = load_embedding_store()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Load all notes in the wiki/ directory
    all_notes = {}
    modified_notes = set()
    for md_path in WIKI_DIR.glob("*.md"):
        note_id = md_path.stem
        try:
            note, pruned = load_wiki_note(md_path)
            all_notes[note_id] = note
            if pruned:
                modified_notes.add(note_id)
        except Exception as e:
            print(f"Warning: Failed to load wiki note {md_path.name}: {e}", file=sys.stderr)

    # 3. Handle rebuild: clear existing store and reset note links
    if rebuild:
        embeddings = np.empty((0, 384), dtype=np.float32)
        meta = []
        for note in all_notes.values():
            note.links = []
            # We don't remove manual markdown links in body content to avoid data loss,
            # but we will rebuild frontmatter links and insert missing links.

    # 4. Filter target IDs that actually exist in the wiki
    target_ids = [tid for tid in target_ids if tid in all_notes]
    if not target_ids:
        print("No valid notes found to link.")
        return

    # 5. Determine which notes need embedding (LNK-06)
    new_embeddings = []
    new_meta = []
    skipped_notes = {}

    for note_id in target_ids:
        note = all_notes[note_id]
        body_len = len(note.content.strip())
        if body_len < MIN_CONTENT_LENGTH:
            skipped_notes[note_id] = f"content length {body_len} below threshold {MIN_CONTENT_LENGTH}"
            continue

        # If not rebuilding and already in store, skip embedding computation
        if not rebuild and note_id in meta:
            continue

        print(f"  Embedding note {note_id}...")
        try:
            emb = embed_note(note)
            new_embeddings.append(emb)
            new_meta.append(note_id)
        except Exception as e:
            print(f"  Error: Failed to embed note {note_id}: {e}", file=sys.stderr)

    # Update embedding store
    if new_embeddings:
        new_arr = np.array(new_embeddings, dtype=np.float32)
        if len(meta) == 0:
            embeddings = new_arr
            meta = new_meta
        else:
            # Overwrite or append
            if rebuild:
                embeddings = new_arr
                meta = new_meta
            else:
                # If we are incrementally adding, make sure we don't duplicate IDs in meta
                # (Remove old embeddings for these IDs if they exist)
                keep_indices = [i for i, mid in enumerate(meta) if mid not in new_meta]
                if len(keep_indices) < len(meta):
                    embeddings = embeddings[keep_indices]
                    meta = [meta[i] for i in keep_indices]
                embeddings = np.vstack([embeddings, new_arr])
                meta = meta + new_meta

        save_embedding_store(embeddings, meta)
        print(f"  Saved {len(new_meta)} embeddings to store.")

    # 6. Similarity computation and auto-linking
    if len(meta) < 2:
        print("  Fewer than 2 embedded notes in store. No auto-linking performed (LNK-01).")
        # Update raw capture status for target notes
        for note_id in target_ids:
            reason = skipped_notes.get(note_id)
            update_raw_capture_status(note_id, reason)
        # Save any notes that had dangling references pruned
        for note_id in modified_notes:
            save_wiki_note(all_notes[note_id])
        return

    # Normalize all embeddings for fast cosine similarity via dot product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    norm_embeddings = embeddings / norms

    # Determine which notes to query similarity for
    # If rebuilding, link all notes in store. Otherwise, link targeted newly embedded notes.
    notes_to_link = meta if rebuild else [tid for tid in target_ids if tid in meta]

    for query_id in notes_to_link:
        if query_id not in meta:
            continue

        idx = meta.index(query_id)
        query_emb = norm_embeddings[idx]

        # Calculate cosine similarity using dot product
        similarities = np.dot(norm_embeddings, query_emb)

        # Collect matches (LNK-10: exclude self-link)
        candidates = []
        for i, sim in enumerate(similarities):
            cand_id = meta[i]
            if cand_id == query_id:
                continue
            if cand_id not in all_notes:
                # Skip dangling reference in store
                continue
            if sim >= SIMILARITY_THRESHOLD:
                candidates.append((cand_id, float(sim)))

        # Sort candidates descending by score
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Cap matches to top N (LNK-07)
        matches = candidates[:MAX_LINKS_PER_NOTE]

        query_note = all_notes[query_id]

        if matches:
            print(f"  Note {query_id} matches: {[(m[0], round(m[1], 3)) for m in matches]}")
        else:
            print(f"  Note {query_id} has no semantic matches above threshold.")

        # Update link arrays and inject bidirectional references
        for match_id, score in matches:
            match_note = all_notes[match_id]

            # Query note links to match note
            if match_id not in query_note.links:
                query_note.links.append(match_id)
                modified_notes.add(query_id)
            if f"[[{match_id}]]" not in query_note.content:
                query_note.content = query_note.content.rstrip() + f"\n\nRelated: [[{match_id}]]"
                modified_notes.add(query_id)

            # Bidirectional link: match note links to query note
            if query_id not in match_note.links:
                match_note.links.append(query_id)
                modified_notes.add(match_id)
            if f"[[{query_id}]]" not in match_note.content:
                match_note.content = match_note.content.rstrip() + f"\n\nRelated: [[{query_id}]]"
                modified_notes.add(match_id)

    # Save all modified notes to disk
    for note_id in modified_notes:
        note = all_notes[note_id]
        print(f"  Saving updated note {note_id} (links: {note.links}).")
        save_wiki_note(note)

    # Update raw capture status for target notes
    for note_id in target_ids:
        reason = skipped_notes.get(note_id)
        update_raw_capture_status(note_id, reason)

# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="SecondSelf Phase 3 — Auto-Linking")

@app.command()
def main(
    all_notes: bool = typer.Option(
        False, "--all", "-a", help="Auto-link all pending/newly-classified notes"
    ),
    note_id: Optional[str] = typer.Option(
        None, "--id", help="Link a single note by ID"
    ),
    rebuild: bool = typer.Option(
        False, "--rebuild", "-r", help="Re-embed all wiki notes and rebuild index from scratch"
    ),
):
    """
    Computes note embeddings and builds/updates semantic connections between notes.
    """
    if not all_notes and not note_id and not rebuild:
        print("Error: Provide --all, --id <note_id>, or --rebuild.", file=sys.stderr)
        raise typer.Exit(1)

    if (all_notes and note_id) or (all_notes and rebuild) or (note_id and rebuild):
        print("Error: Use only one of --all, --id, or --rebuild.", file=sys.stderr)
        raise typer.Exit(1)

    # Gather wiki note IDs from disk
    wiki_ids = [p.stem for p in WIKI_DIR.glob("*.md")]

    if rebuild:
        target_ids = wiki_ids
        print(f"Starting complete rebuild for all {len(target_ids)} notes...")
        run_linking(target_ids, rebuild=True)
    elif note_id:
        if note_id not in wiki_ids:
            print(f"Error: Wiki note '{note_id}' does not exist.", file=sys.stderr)
            raise typer.Exit(1)
        target_ids = [note_id]
        print(f"Processing note: {note_id}")
        run_linking(target_ids, rebuild=False)
    else:
        # --all mode:
        # Find raw captures with status="classified"
        classified_raw_ids = []
        for raw_path in RAW_DIR.glob("*.json"):
            try:
                with open(raw_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") == "classified":
                    classified_raw_ids.append(raw_path.stem)
            except Exception:
                pass

        # Also find any wiki notes not in metadata
        try:
            _, meta = load_embedding_store()
        except ValueError:
            meta = []

        unembedded_wiki_ids = [wid for wid in wiki_ids if wid not in meta]

        # Union and sort
        target_ids = sorted(list(set(classified_raw_ids + unembedded_wiki_ids)))
        print(f"Processing {len(target_ids)} new/unlinked notes...")
        run_linking(target_ids, rebuild=False)

    print("\nLinking process complete.")

if __name__ == "__main__":
    app()
