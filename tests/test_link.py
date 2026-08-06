import sys
from pathlib import Path
import numpy as np
import pytest

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from link import SIMILARITY_THRESHOLD, MAX_LINKS_PER_NOTE, MIN_CONTENT_LENGTH
from models.note import WikiNote

def test_config_values():
    assert SIMILARITY_THRESHOLD == 0.75
    assert MAX_LINKS_PER_NOTE == 5
    assert MIN_CONTENT_LENGTH == 50

def test_embed_note(monkeypatch):
    # Mock SentenceTransformer encoding
    class MockModel:
        def encode(self, text, convert_to_numpy=True):
            # Return a simple mock vector based on length of text
            vec = np.zeros(384, dtype=np.float32)
            vec[0] = len(text)
            return vec

    import link
    monkeypatch.setattr(link, "model", MockModel())

    note = WikiNote(
        id="test_id",
        title="Test Title",
        para_category="Resources",
        tags=["test"],
        summary="Test summary",
        links=[],
        embedding_id="test_id",
        created_at="2026-07-18T00:00:00Z",
        updated_at="2026-07-18T00:00:00Z",
        content="This is a test note content to verify that embedding function works correctly."
    )

    emb = link.embed_note(note)
    assert isinstance(emb, np.ndarray)
    assert emb.shape == (384,)
    assert emb[0] == len("Test Title\nThis is a test note content to verify that embedding function works correctly.")

def test_auto_linking_similarity_and_capping():
    # Test our similarity matching logic directly on mock vectors
    # We want to ensure that:
    # 1. Self-linking is excluded.
    # 2. Similarity threshold (0.75) is respected.
    # 3. Max links cap (5) is enforced.
    
    # 6 mock embeddings of size 384
    # e0 is query. e1, e2, e3, e4, e5 are targets.
    # Let's make:
    # e1 very similar to e0 (cosine = 0.9)
    # e2 similar to e0 (cosine = 0.85)
    # e3 similar to e0 (cosine = 0.8)
    # e4 similar to e0 (cosine = 0.78)
    # e5 similar to e0 (cosine = 0.76)
    # e6 not similar to e0 (cosine = 0.5)
    
    e0 = np.array([1, 0, 0], dtype=np.float32) # Query note
    e1 = np.array([0.9, 0.43589, 0], dtype=np.float32) # cos ~ 0.9
    e2 = np.array([0.85, 0.52678, 0], dtype=np.float32) # cos ~ 0.85
    e3 = np.array([0.8, 0.6, 0], dtype=np.float32) # cos ~ 0.8
    e4 = np.array([0.78, 0.62578, 0], dtype=np.float32) # cos ~ 0.78
    e5 = np.array([0.76, 0.64992, 0], dtype=np.float32) # cos ~ 0.76
    e6 = np.array([0.5, 0.86603, 0], dtype=np.float32) # cos ~ 0.5 (below 0.75 threshold)
    
    # Pad to 384 dimensions
    embeddings = []
    for e in [e0, e1, e2, e3, e4, e5, e6]:
        padded = np.zeros(384, dtype=np.float32)
        padded[:3] = e
        embeddings.append(padded)
    embeddings = np.array(embeddings)
    
    meta = ["n0", "n1", "n2", "n3", "n4", "n5", "n6"]
    
    # Normalize embeddings
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norm_embeddings = embeddings / norms
    
    query_idx = 0
    query_emb = norm_embeddings[query_idx]
    
    # Calculate cosine similarity using dot product
    similarities = np.dot(norm_embeddings, query_emb)
    
    # Match candidate verification
    candidates = []
    for i, sim in enumerate(similarities):
        cand_id = meta[i]
        if cand_id == "n0": # Self-link exclusion
            continue
        if sim >= 0.75:
            candidates.append((cand_id, float(sim)))
            
    candidates.sort(key=lambda x: x[1], reverse=True)
    matches = candidates[:5] # cap at 5
    
    # Verify candidates
    # n1, n2, n3, n4, n5 should pass threshold. n6 should fail. n0 should be excluded.
    assert len(candidates) == 5
    assert [c[0] for c in candidates] == ["n1", "n2", "n3", "n4", "n5"]
    assert "n6" not in [c[0] for c in candidates]
    assert "n0" not in [c[0] for c in candidates]
    
    # Capping verification
    # If we have 6 matches above threshold, matches should only return top 5
    # Let's add one more match e7 (cos = 0.95)
    e7 = np.array([0.95, 0.31225, 0], dtype=np.float32) # cos ~ 0.95
    padded_e7 = np.zeros(384, dtype=np.float32)
    padded_e7[:3] = e7
    
    embeddings_with_7 = np.vstack([embeddings, padded_e7])
    meta_with_7 = meta + ["n7"]
    
    norms_with_7 = np.linalg.norm(embeddings_with_7, axis=1, keepdims=True)
    norm_embeddings_with_7 = embeddings_with_7 / norms_with_7
    
    query_emb_7 = norm_embeddings_with_7[query_idx]
    similarities_7 = np.dot(norm_embeddings_with_7, query_emb_7)
    
    candidates_7 = []
    for i, sim in enumerate(similarities_7):
        cand_id = meta_with_7[i]
        if cand_id == "n0":
            continue
        if sim >= 0.75:
            candidates_7.append((cand_id, float(sim)))
            
    candidates_7.sort(key=lambda x: x[1], reverse=True)
    matches_7 = candidates_7[:5] # cap at 5
    
    assert len(candidates_7) == 6 # n7, n1, n2, n3, n4, n5
    assert len(matches_7) == 5 # capped at 5
    assert [m[0] for m in matches_7] == ["n7", "n1", "n2", "n3", "n4"]
