import sys
from pathlib import Path
import pytest

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from ask import ask, retrieve, AskResponse, NoteRef
from models.note import WikiNote

def test_ask_empty_question():
    response = ask("")
    assert response.answer == "Enter a question."
    assert len(response.sources) == 0

def test_ask_mocked_llm(monkeypatch):
    # Mock retrieve to return a test note
    def mock_retrieve(question, top_k=5):
        note = WikiNote(
            id="20260709_112233",
            title="Sentence Embeddings Guide",
            para_category="Resources",
            tags=["nlp", "embeddings"],
            summary="A note about sentence-transformers",
            links=[],
            embedding_id="20260709_112233",
            created_at="2026-07-24T00:00:00Z",
            updated_at="2026-07-24T00:00:00Z",
            content="Sentence embeddings map text to high-dimensional vectors to find similarity."
        )
        return [(note, 0.85)]

    # Mock the Groq Client completions
    class MockMessage:
        content = "You can compute similarities using sentence embeddings [20260709_112233]."

    class MockChoice:
        message = MockMessage()

    class MockCompletion:
        choices = [MockChoice()]

    class MockCompletions:
        def create(self, **kwargs):
            return MockCompletion()

    class MockChat:
        completions = MockCompletions()

    class MockGroq:
        def __init__(self, api_key):
            pass
        chat = MockChat()

    # Apply patches
    import ask as ask_module
    monkeypatch.setattr(ask_module, "retrieve", mock_retrieve)
    monkeypatch.setattr(ask_module, "Groq", MockGroq)
    monkeypatch.setattr(ask_module, "GROQ_API_KEY", "mock_key")

    response = ask("How do sentence embeddings work?")
    
    assert "Sentence Embeddings Guide" in response.sources[0].title
    assert response.sources[0].id == "20260709_112233"
    assert "sentence embeddings" in response.answer
    assert "[20260709_112233]" in response.answer

def test_ask_citation_validation(monkeypatch):
    # Test that invalid citations not present in the retrieved notes are filtered out (ASK-07)
    def mock_retrieve(question, top_k=5):
        note = WikiNote(
            id="20260709_112233",
            title="Real Note",
            para_category="Resources",
            tags=["test"],
            summary="Real",
            links=[],
            embedding_id="20260709_112233",
            created_at="2026-07-24T00:00:00Z",
            updated_at="2026-07-24T00:00:00Z",
            content="This is the real note content."
        )
        return [(note, 0.85)]

    class MockMessage:
        # LLM outputs both a valid citation [20260709_112233] and an invalid hallucinated one [20260709_999999]
        content = "This uses real note [20260709_112233] and hallucinated [20260709_999999]."

    class MockChoice:
        message = MockMessage()

    class MockCompletion:
        choices = [MockChoice()]

    class MockCompletions:
        def create(self, **kwargs):
            return MockCompletion()

    class MockChat:
        completions = MockCompletions()

    class MockGroq:
        def __init__(self, api_key):
            pass
        chat = MockChat()

    import ask as ask_module
    monkeypatch.setattr(ask_module, "retrieve", mock_retrieve)
    monkeypatch.setattr(ask_module, "Groq", MockGroq)
    monkeypatch.setattr(ask_module, "GROQ_API_KEY", "mock_key")

    response = ask("Test query")

    # Valid citation should remain
    assert "[20260709_112233]" in response.answer
    # Hallucinated citation should be post-processed and stripped
    assert "[20260709_999999]" not in response.answer
    # Only valid note should be in sources
    assert len(response.sources) == 1
    assert response.sources[0].id == "20260709_112233"
