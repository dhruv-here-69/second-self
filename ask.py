"""
ask.py — Phase 5A: Retrieval-Augmented Q&A

Answers natural-language questions using notes retrieved from the local wiki
and synthesized via Groq/Llama 3.

Usage:
    python ask.py "What did I capture about RAG?"
    python ask.py "Summarize my project ideas"
"""

import os
import sys
import re
import json
import io
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

import typer
import numpy as np
from groq import Groq

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).parent.resolve()))

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    WIKI_DIR,
    DATA_DIR,
    TOP_K,
    MIN_RETRIEVAL_SCORE,
)
from link import load_embedding_store, load_wiki_note, model, INDEX_PATH, META_PATH
from models.note import WikiNote

# Fix Windows console encoding
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

MAX_CONTEXT_CHARS = 12000

@dataclass
class NoteRef:
    id: str
    title: str
    excerpt: str

    def to_dict(self):
        return asdict(self)

@dataclass
class AskResponse:
    answer: str
    sources: List[NoteRef]
    confidence: Optional[float] = None

    def to_dict(self):
        return {
            "answer": self.answer,
            "sources": [s.to_dict() for s in self.sources],
            "confidence": self.confidence
        }

# ---------------------------------------------------------------------------
# Retrieval Layer
# ---------------------------------------------------------------------------

def retrieve(question: str, top_k: int = 5) -> List[Tuple[WikiNote, float]]:
    """
    Embed the question, compute cosine similarity, and return the top_k
    matching WikiNotes along with their similarity scores.
    """
    # ASK-05: Check if index exists and is non-empty
    if not INDEX_PATH.exists() or not META_PATH.exists():
        raise FileNotFoundError("Knowledge base not indexed. Run pipeline first.")

    try:
        embeddings, meta = load_embedding_store()
    except ValueError as e:
        raise ValueError("Index corrupt. Run link.py --rebuild") from e

    if len(meta) == 0:
        raise FileNotFoundError("Knowledge base not indexed. Run pipeline first.")

    # Embed query
    query_emb = model.encode(question, convert_to_numpy=True)
    query_norm = np.linalg.norm(query_emb)
    if query_norm == 0:
        query_norm = 1.0
    norm_query_emb = query_emb / query_norm

    # Normalize stored embeddings
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    norm_embeddings = embeddings / norms

    # Compute similarities (dot product since normalized)
    similarities = np.dot(norm_embeddings, norm_query_emb)

    # Filter and sort
    candidates = []
    for i, score in enumerate(similarities):
        note_id = meta[i]
        # ASK-01: Filter out scores below minimum threshold
        if score >= MIN_RETRIEVAL_SCORE:
            candidates.append((note_id, float(score)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    top_candidates = candidates[:top_k]

    # Load corresponding WikiNote objects
    retrieved = []
    for note_id, score in top_candidates:
        note_path = WIKI_DIR / f"{note_id}.md"
        if note_path.exists():
            try:
                note, _ = load_wiki_note(note_path)
                retrieved.append((note, score))
            except Exception as e:
                print(f"Warning: Failed to load retrieved note {note_id}: {e}", file=sys.stderr)

    return retrieved

# ---------------------------------------------------------------------------
# Synthesis Layer
# ---------------------------------------------------------------------------

def build_context(retrieved: List[Tuple[WikiNote, float]]) -> Tuple[str, List[WikiNote]]:
    """
    Build a context string from the retrieved notes, adhering to MAX_CONTEXT_CHARS.
    Returns (context_string, list_of_included_notes).
    """
    context_parts = []
    included_notes = []

    for note, score in retrieved:
        note_context = f"Note ID: {note.id}\nTitle: {note.title}\nContent:\n{note.content}\n---\n"
        current_len = sum(len(part) for part in context_parts)

        if current_len + len(note_context) > MAX_CONTEXT_CHARS:
            allowed_chars = MAX_CONTEXT_CHARS - current_len
            if allowed_chars > 100:
                context_parts.append(note_context[:allowed_chars] + "\n[Content truncated due to context limit]\n---\n")
                included_notes.append(note)
            break
        else:
            context_parts.append(note_context)
            included_notes.append(note)

    return "".join(context_parts), included_notes


def ask(question: str, top_k: int = 5) -> AskResponse:
    """
    Performs retrieval-augmented generation to answer the question using Groq/Llama 3.
    """
    # ASK-04: Gracefully handle empty questions
    if not question.strip():
        return AskResponse(answer="Enter a question.", sources=[])

    try:
        retrieved = retrieve(question, top_k=top_k)
    except (FileNotFoundError, ValueError) as e:
        return AskResponse(answer=str(e), sources=[])

    # ASK-01: Handle case where no notes pass the similarity threshold
    if not retrieved:
        return AskResponse(answer="I don't have notes about that.", sources=[])

    # Build prompt context
    retrieved_context, included_notes = build_context(retrieved)

    # Prepare Groq API call
    if not GROQ_API_KEY:
        return AskResponse(answer="Error: GROQ_API_KEY is not configured.", sources=[])

    client = Groq(api_key=GROQ_API_KEY)
    
    system_prompt = (
        "You are SecondSelf, a personal knowledge assistant.\n"
        "Answer the user's question using ONLY the provided notes.\n"
        "Cite the note IDs in brackets like [20260709_a3f9c2] whenever referencing their content.\n"
        "If the notes do not contain enough information to answer the question, state: "
        "'I don't have notes about that.'\n"
        "Do not invent information or use general knowledge not present in the notes."
    )

    user_prompt = f"Question: {question}\n\nRelevant notes:\n{retrieved_context}"

    try:
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,  # Minimize hallucination
            max_tokens=1024,
        )
        answer = completion.choices[0].message.content or ""
    except Exception as e:
        return AskResponse(answer=f"Error communicating with Groq API: {e}", sources=[])

    # Post-process citations (ASK-07)
    # Find all citation patterns like [20260709_abcdef] in LLM response
    citation_pattern = re.compile(r"\[(\d{8}_[a-f0-9]{6})\]")
    found_citations = set(citation_pattern.findall(answer))
    retrieved_ids = {note.id for note in included_notes}

    # Filter to only valid retrieved IDs
    valid_citations = found_citations.intersection(retrieved_ids)

    # Remove fake or non-retrieved citations from the text
    for cite_id in found_citations:
        if cite_id not in valid_citations:
            answer = answer.replace(f"[{cite_id}]", "")

    # Build sources list
    sources = []
    for note in included_notes:
        if note.id in valid_citations:
            sources.append(NoteRef(
                id=note.id,
                title=note.title,
                excerpt=note.summary or note.content[:200]
            ))

    # Calculate average confidence of retrieved set (as optional retrieval score)
    confidence = float(np.mean([score for _, score in retrieved[:len(included_notes)]])) if retrieved else 0.0

    return AskResponse(answer=answer, sources=sources, confidence=confidence)

# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="SecondSelf Phase 5A — Ask your second brain")

@app.command()
def main(
    question: str = typer.Argument(..., help="The natural-language question to ask"),
    top_k: int = typer.Option(TOP_K, "--top-k", "-k", help="Number of notes to retrieve"),
):
    """Ask a question to your knowledge base."""
    print(f"Querying brain: '{question}'...")
    response = ask(question, top_k=top_k)

    print("\n--- Answer ---")
    print(response.answer)
    print("--------------")

    if response.sources:
        print("\nSources cited:")
        for source in response.sources:
            print(f"- [{source.id}] {source.title}")
    else:
        print("\nNo sources cited.")

if __name__ == "__main__":
    app()
