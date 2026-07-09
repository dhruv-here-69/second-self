# SecondSelf — AI-Powered Personal Second Brain

**SecondSelf** is a local-first, self-organizing personal knowledge base. It is designed to capture thoughts, web links, and documents instantly, classify them automatically using the PARA organization framework, build semantic connections (auto-links) via embeddings, visualize your knowledge space as an interactive force-directed graph, and answer natural-language questions grounded directly in your captured notes.

---

## Key Features

1. **Capture Pipeline (`capture.py`)**: Frictionless entry for text notes, web articles (automated title & content extraction), and PDF files.
2. **Auto-Classification (`classify.py`)**: Automated organization into PARA (Projects, Areas, Resources, Archives) categories and tag generation via Groq & Llama 3.
3. **Auto-Linking (`link.py`)**: Dense semantic connections generated using sentence embeddings (local `sentence-transformers` model).
4. **Knowledge Graph (`build_graph.py`)**: Interactive spatial representation of files, categories, and connections.
5. **RAG Q&A (`ask.py`)**: Retrieval-augmented generation answering questions grounded purely in your personal notes, with clear source note citations.

---

## Local Setup

### Prerequisites
- **Python 3.11+** is required.
- A **Groq API Key** (for fast, free-tier LLM inference).

### Installation

1. **Clone or Navigate to the Repository:**
   ```bash
   cd second-self
   ```

2. **Create a Virtual Environment:**
   ```bash
   python -m venv .venv
   ```

3. **Activate the Virtual Environment:**
   - **Windows (PowerShell):**
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     source .venv/bin/activate
     ```

4. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure Environment Variables:**
   Copy the example environment file and add your Groq API key:
   ```bash
   cp .env.example .env
   ```
   Open `.env` in a text editor and fill in your API key:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   USE_DEMO_DATA=false
   ```

---

## Project Structure

```
secondself/
├── raw/                          # Immutable raw captures (JSON)
├── raw/files/                    # Copied raw file uploads (PDFs, etc.)
├── wiki/                         # Organized markdown files with YAML metadata
├── data/                         # Embedding index and vector mapping metadata
├── models/                       # Dataclass schemas for captures, notes, and graph exports
├── static/                       # HTML/JS rendering files for graph visualization
├── tests/                        # Automated unit and integration tests
├── requirements.txt              # Project package requirements
└── config.py                     # Central paths, version controls, and settings
```
