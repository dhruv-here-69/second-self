# SecondSelf — Edge Cases & Corner Scenarios

This document catalogs edge cases, corner scenarios, and failure modes for SecondSelf. Use it during implementation ([implementation-plan.md](./implementation-plan.md)), testing (Phases 6–7), and deployment (Phases 8–9).

Each entry follows this format:

| Field | Meaning |
|-------|---------|
| **ID** | Unique reference (e.g. `CAP-01`) |
| **Severity** | `Critical` / `High` / `Medium` / `Low` |
| **Scenario** | What can go wrong |
| **Expected behavior** | What the system should do |
| **Mitigation** | How to handle it in code |
| **Test hint** | How to verify |

---

## Summary by Severity

| Severity | Count focus | Action |
|----------|-------------|--------|
| Critical | Data loss, secrets leak, crash on happy path | Must handle before deploy |
| High | Wrong output, broken pipeline step | Must handle in phase implementation |
| Medium | Degraded UX, partial failure | Handle with fallbacks |
| Low | Cosmetic, rare, post-MVP | Document and defer if needed |

---

## Phase 0 — Project Setup

### SETUP-01: Missing or invalid `.env` file
| | |
|---|---|
| **Severity** | High |
| **Scenario** | User runs `classify.py` or `ask.py` without creating `.env` or with empty `GROQ_API_KEY`. |
| **Expected behavior** | Clear error: `"GROQ_API_KEY not set. Copy .env.example to .env and add your key."` — exit code 1. |
| **Mitigation** | Validate env vars at import time in `config.py`; fail fast with actionable message. |
| **Test hint** | Run classify with no `.env`; assert readable error, no stack trace dump. |

### SETUP-02: Required directories deleted at runtime
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | `raw/`, `wiki/`, or `data/` folder manually deleted while app is running. |
| **Expected behavior** | Auto-create missing directories on next write (mkdir -p pattern). |
| **Mitigation** | `ensure_dirs()` in `config.py` called before any file I/O. |
| **Test hint** | Delete `data/` mid-session; run `link.py --all`; folder recreated. |

### SETUP-03: Python version below 3.11
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User runs on Python 3.9; type hints or stdlib features may break. |
| **Expected behavior** | Document minimum version in README; optional runtime check in `config.py`. |
| **Mitigation** | `sys.version_info >= (3, 11)` check with clear message at startup. |
| **Test hint** | Manual check on target Python version. |

### SETUP-04: `sentence-transformers` model download fails (offline / firewall)
| | |
|---|---|
| **Severity** | High |
| **Scenario** | First run of `link.py` cannot download `all-MiniLM-L6-v2` from Hugging Face. |
| **Expected behavior** | Error explaining network required for first-time model download; suggest pre-download step in README. |
| **Mitigation** | Catch `OSError` / `ConnectionError` during model load; document `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` as setup step. |
| **Test hint** | Simulate offline (block network) on fresh install. |

### SETUP-05: Path resolution on Windows vs Unix
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Hardcoded `/` paths break on Windows; backslashes in file paths break JSON. |
| **Expected behavior** | All paths use `pathlib.Path`; JSON stores forward-slash or escaped paths consistently. |
| **Mitigation** | Never string-concatenate paths; use `Path.resolve()`. |
| **Test hint** | Run capture + file on Windows; verify `file_path` in raw JSON is readable. |

---

## Phase 1 — Capture Pipeline

### CAP-01: Empty note text
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | `python capture.py ""` or whitespace-only input. |
| **Expected behavior** | Reject with message: `"Capture content cannot be empty."` — no file written. |
| **Mitigation** | Strip and validate `len(content.strip()) > 0` before save. |
| **Test hint** | `capture.py ""` → exit 1, no new JSON in `raw/`. |

### CAP-02: Extremely long note (100K+ characters)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User pastes entire book or log dump as a note. |
| **Expected behavior** | Capture succeeds; warn if content exceeds configurable max (e.g. 500K chars). Later classify may truncate for LLM. |
| **Mitigation** | Optional `MAX_CAPTURE_LENGTH` in config; log warning, don't silently truncate at capture. |
| **Test hint** | Capture 200K char string; verify full content in raw JSON. |

### CAP-03: Duplicate content, different captures
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Same note captured twice intentionally. |
| **Expected behavior** | Two separate raw files with different IDs and timestamps (captures are immutable events). |
| **Mitigation** | Never dedupe at capture layer; linking/classify may later connect them. |
| **Test hint** | Capture same text twice; assert two distinct IDs. |

### CAP-04: Invalid URL format
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | `python capture.py --url "not-a-url"` or `--url ""`. |
| **Expected behavior** | Validation error before network call; no partial raw file. |
| **Mitigation** | Regex or `urllib.parse` validation; require `http://` or `https://`. |
| **Test hint** | `--url "foo"` → clear error. |

### CAP-05: URL fetch timeout or DNS failure
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Link capture to slow/dead domain; request hangs or 404. |
| **Expected behavior** | Save raw capture with `type=link`, `content=url string`, `metadata.error="fetch_failed"`. Status still `pending`. |
| **Mitigation** | 10s timeout; on failure store URL as content so nothing is lost. |
| **Test hint** | `--url "https://httpstat.us/504?sleep=15000"` or invalid domain. |

### CAP-06: URL returns non-HTML (PDF, JSON API)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User captures direct PDF or API endpoint URL. |
| **Expected behavior** | Store URL + whatever text can be extracted; don't crash on non-HTML content-type. |
| **Mitigation** | Check `Content-Type`; for PDF URLs optionally download and run pypdf; else store URL + content-type in metadata. |
| **Test hint** | Capture URL pointing to `.pdf` file. |

### CAP-07: Login-walled or paywalled page
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | BeautifulSoup extracts login form HTML, not article content. |
| **Expected behavior** | Capture saves thin/boilerplate content; classify may produce poor summary — acceptable. |
| **Mitigation** | Store `metadata.content_length` and `metadata.fetch_status`; user can re-capture as note manually. |
| **Test hint** | Capture a known paywalled URL; verify no crash. |

### CAP-08: File does not exist
| | |
|---|---|
| **Severity** | High |
| **Scenario** | `python capture.py --file "./missing.pdf"`. |
| **Expected behavior** | Error: `"File not found: ..."` — exit 1, no raw JSON. |
| **Mitigation** | `Path.exists()` check before copy. |
| **Test hint** | Nonexistent path → error. |

### CAP-09: Unsupported file type (.docx, .png, .zip)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User captures image or Word doc; no text extractor available. |
| **Expected behavior** | Copy file to `raw/files/`; store filename + mime type; `content` = empty or filename placeholder; status `pending`. |
| **Mitigation** | Allowlist text extractors (PDF, `.txt`, `.md`); for others store metadata only with warning. |
| **Test hint** | Capture `.png`; raw JSON has file_path, empty/minimal content. |

### CAP-10: PDF with no extractable text (scanned image PDF)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | pypdf returns empty string for OCR-only PDF. |
| **Expected behavior** | Save file; `content=""` or `"[No extractable text]"`; metadata notes `extraction=empty`. |
| **Mitigation** | Check `len(extracted.strip()) == 0`; set placeholder message. |
| **Test hint** | Use scanned PDF fixture. |

### CAP-11: PDF password-protected or corrupted
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | pypdf raises exception on read. |
| **Expected behavior** | Still copy file; raw JSON with `metadata.error="pdf_read_failed"`; content empty. |
| **Mitigation** | try/except around pypdf; never lose the file bytes. |
| **Test hint** | Corrupted PDF bytes file. |

### CAP-12: File exceeds size limit
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | 500MB video file passed to `--file`. |
| **Expected behavior** | Reject or warn above `MAX_FILE_SIZE_MB` (e.g. 50MB); don't freeze disk. |
| **Mitigation** | Check `Path.stat().st_size` before copy. |
| **Test hint** | Mock large file or lower limit in config for test. |

### CAP-13: Special characters and Unicode in note content
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Note contains emoji, Hindi/Devanagari, quotes, newlines, null bytes. |
| **Expected behavior** | JSON written as UTF-8; all characters preserved round-trip. |
| **Mitigation** | `open(..., encoding="utf-8")`; `json.dump(..., ensure_ascii=False)`. |
| **Test hint** | Capture `"Hello 世界 🧠 \"quotes\""`; reload JSON identically. |

### CAP-14: Concurrent captures (race on ID collision)
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Two capture commands in same second generate same hex ID (extremely rare). |
| **Expected behavior** | Second write detects existing file; regenerate ID and retry. |
| **Mitigation** | Loop: generate ID → if path exists, regenerate (max 5 attempts). |
| **Test hint** | Mock UUID to force collision once. |

### CAP-15: `--stdin` with empty pipe
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | `echo. \| python capture.py --stdin` (Windows empty stdin). |
| **Expected behavior** | Same as CAP-01 — reject empty content. |
| **Mitigation** | Read stdin fully; validate before save. |
| **Test hint** | Empty stdin pipe. |

### CAP-16: Simultaneous flags (`--url` and `--file`)
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | `python capture.py --url X --file Y "note"`. |
| **Expected behavior** | Clear precedence rule (e.g. positional note wins, or error on conflicting flags). |
| **Mitigation** | Typer mutual exclusion or documented priority order. |
| **Test hint** | Conflicting CLI args → deterministic behavior. |

---

## Phase 2 — Auto-Classification

### CLS-01: LLM returns invalid JSON
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Groq returns markdown-wrapped JSON, trailing commas, or prose instead of JSON. |
| **Expected behavior** | Strip code fences; parse with fallback → `para_category=Resources`, `tags=[]`, title=first 80 chars of content. Mark success but log warning. |
| **Mitigation** | Regex extract `{...}`; `json.loads` in try/except; architecture §11 fallback. |
| **Test hint** | Mock LLM returning `"Here is the result:\n```json\n{...}\n```"`. |

### CLS-02: LLM returns invalid PARA category
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Model returns `"Project"` or `"Misc"` instead of exact PARA enum. |
| **Expected behavior** | Normalize: map fuzzy matches; default to `Resources` if unrecognizable. |
| **Mitigation** | Allowlist `{"Projects","Areas","Resources","Archives"}`; case-insensitive match. |
| **Test hint** | Mock response with `"para_category": "project"`. |

### CLS-03: Groq API rate limit (429)
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Batch classify of 20 notes hits rate limit mid-run. |
| **Expected behavior** | Retry with exponential backoff (3 attempts); if still failing, mark that capture `error`, continue batch. |
| **Mitigation** | Per-item try/except; optional `time.sleep(1)` between batch items. |
| **Test hint** | Mock 429 on 3rd call; assert retry then error status. |

### CLS-04: Groq API key invalid (401)
| | |
|---|---|
| **Severity** | Critical |
| **Scenario** | Wrong or revoked API key. |
| **Expected behavior** | Fail immediately with clear auth error; don't mark all items as `error` silently. |
| **Mitigation** | Detect 401 on first call; abort batch with message. |
| **Test hint** | Mock 401 response. |

### CLS-05: Empty or minimal content capture classified
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Raw capture has `content=""` (failed PDF/link). |
| **Expected behavior** | Still create wiki note with title from filename/URL; category likely Archives or Resources. |
| **Mitigation** | Pass available metadata to LLM prompt when content empty. |
| **Test hint** | Classify link capture with fetch_failed metadata. |

### CLS-06: Re-classifying already classified capture
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User runs `classify.py --id X` when wiki note already exists. |
| **Expected behavior** | Overwrite wiki note OR skip with `--force` flag to re-classify. Default: skip if wiki exists unless `--force`. |
| **Mitigation** | Check `wiki/{id}.md` existence; document behavior in README. |
| **Test hint** | Classify same ID twice; second run skips without duplicate files. |

### CLS-07: Content exceeds LLM context window
| | |
|---|---|
| **Severity** | High |
| **Scenario** | 50-page PDF text sent to Groq. |
| **Expected behavior** | Truncate content to first N chars (e.g. 8000) for classification prompt; store full content in wiki body. |
| **Mitigation** | `content[:MAX_CLASSIFY_CHARS]` in prompt only. |
| **Test hint** | 100K char capture → classify succeeds; wiki body retains full text. |

### CLS-08: LLM hallucinates tags unrelated to content
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Tags don't match note topic. |
| **Expected behavior** | Accept imperfect tags (personal system); user can edit wiki manually later. |
| **Mitigation** | Cap tags at 10; strip empty strings. |
| **Test hint** | Manual review during Phase 7. |

### CLS-09: YAML frontmatter special characters in title/summary
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Title contains `:`, `#`, or `"` breaking YAML parsing. |
| **Expected behavior** | Quote strings properly in frontmatter; wiki note parses back correctly. |
| **Mitigation** | Use `python-frontmatter` or `yaml.dump` with `default_style='"'` for safety. |
| **Test hint** | Title `"Project: RAG #1"` → round-trip parse. |

### CLS-10: Network interruption mid-batch
| | |
|---|---|
| **Severity** | High |
| **Scenario** | WiFi drops during `classify.py --all`. |
| **Expected behavior** | Completed items stay `classified`; pending items remain `pending`; no partial wiki files without status update. |
| **Mitigation** | Update raw status only after wiki write succeeds (atomic order). |
| **Test hint** | Kill network after 2 of 5 items; rerun `--all` completes remainder. |

---

## Phase 3 — Auto-Linking

### LNK-01: Fewer than 2 notes in wiki
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Only one wiki note exists; nothing to link to. |
| **Expected behavior** | Embed note; save to index; no links created; no error. |
| **Mitigation** | Early return if `len(existing_notes) < 1` for comparison. |
| **Test hint** | Single note through link pipeline. |

### LNK-02: No notes above similarity threshold
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | All notes on unrelated topics; max similarity 0.4. |
| **Expected behavior** | Note embedded and saved; zero links; status `linked`. |
| **Mitigation** | Expected behavior — architecture §11. |
| **Test hint** | Capture "cat food" and "quantum physics"; no auto-link. |

### LNK-03: Near-duplicate notes (similarity > 0.95)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User captured same meeting notes twice with slight edits. |
| **Expected behavior** | Link them (likely above threshold); both notes get bidirectional links. |
| **Mitigation** | Accept as feature; future dedup is post-MVP. |
| **Test hint** | Two nearly identical notes → linked. |

### LNK-04: Link to deleted wiki note (dangling reference)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Note A links to `[[20260701_deadbeef]]` but that wiki file was manually deleted. |
| **Expected behavior** | `build_graph.py` skips missing target or creates orphan edge warning; don't crash. |
| **Mitigation** | Validate link targets exist before writing; prune from frontmatter on rebuild. |
| **Test hint** | Delete linked note file; run `build_graph.py`. |

### LNK-05: Bidirectional link update race
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Linking note A updates note B's file while B is also being linked. |
| **Expected behavior** | File writes are sequential per pipeline run; no concurrent writes in MVP. |
| **Mitigation** | Single-threaded `link.py --all`; document no parallel pipeline runs. |
| **Test hint** | Run single pipeline thread only in MVP. |

### LNK-06: Note content below MIN_CONTENT_LENGTH (50 chars)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Stub note: `"TODO"`. |
| **Expected behavior** | Skip embedding/linking; mark `linked` with metadata skip reason. |
| **Mitigation** | Check length before embed; architecture §5 threshold. |
| **Test hint** | 10-char note → no embedding in index. |

### LNK-07: MAX_LINKS_PER_NOTE exceeded
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Note similar to 20 others above 0.75. |
| **Expected behavior** | Link only top 5 by similarity score. |
| **Mitigation** | Sort matches descending; slice `[:MAX_LINKS_PER_NOTE]`. |
| **Test hint** | Mock 10 high-similarity matches; assert 5 links max. |

### LNK-08: Embeddings index out of sync with wiki
| | |
|---|---|
| **Severity** | High |
| **Scenario** | User manually edits wiki note; embedding stale. |
| **Expected behavior** | `link.py --rebuild` re-embeds all notes; document command. |
| **Mitigation** | Store `updated_at` in frontmatter; future incremental re-embed post-MVP. |
| **Test hint** | Edit wiki body; rebuild; retrieval reflects new content. |

### LNK-09: Corrupt embeddings.index file
| | |
|---|---|
| **Severity** | High |
| **Scenario** | `data/embeddings.index` truncated or wrong shape. |
| **Expected behavior** | Detect on load; offer rebuild from wiki: `"Index corrupt. Run link.py --rebuild"`. |
| **Mitigation** | Validate array shape vs `embeddings.meta.json` length. |
| **Test hint** | Truncate index file; assert graceful error + rebuild path. |

### LNK-10: Self-link (note matches itself)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Similarity search includes the query note itself. |
| **Expected behavior** | Exclude same ID from match results. |
| **Mitigation** | Filter `candidate_id != query_id`. |
| **Test hint** | Single note rebuild doesn't self-link. |

### LNK-11: Circular links (A→B→C→A)
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Transitive linking creates cycle in graph. |
| **Expected behavior** | Valid graph structure; force-directed layout handles cycles. |
| **Mitigation** | No special handling needed. |
| **Test hint** | Visual graph renders without infinite loop. |

### LNK-12: Non-English content embedding quality
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Notes in Hindi, mixed language; similarity scores lower than expected. |
| **Expected behavior** | Still embed and link if above threshold; may miss cross-language links. |
| **Mitigation** | Document model limitation; post-MVP: multilingual embedding model. |
| **Test hint** | Two related Hindi notes — may or may not link; no crash. |

---

## Phase 4 — Graph Visualization

### GRPH-01: Empty wiki folder (zero notes)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | `build_graph.py` run before any classification. |
| **Expected behavior** | Export `{"nodes": [], "edges": []}`; UI shows empty state message. |
| **Mitigation** | Valid empty JSON; graph.html displays "No notes yet. Capture something!" |
| **Test hint** | Fresh repo → build_graph → empty JSON valid. |

### GRPH-02: Orphan nodes (no edges)
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Note with no links and no matches. |
| **Expected behavior** | Node appears isolated in graph; architecture §11. |
| **Mitigation** | Include all wiki files as nodes regardless of edge count. |
| **Test hint** | Single orphan in 10-node graph visible. |

### GRPH-03: Broken `[[link]]` syntax in markdown
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Manual edit introduces `[[ invalid id ]]` or `[[not_an_id]]`. |
| **Expected behavior** | Skip malformed links; log warning; don't crash parser. |
| **Mitigation** | Regex: `^\[\[(\d{8}_[a-f0-9]{6})\]\]$` for valid IDs. |
| **Test hint** | Wiki with bad link syntax → graph builds. |

### GRPH-04: Duplicate edges (A→B and B→A both in frontmatter)
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Bidirectional linking creates two edge records. |
| **Expected behavior** | Deduplicate edges in export OR render as undirected; one visual edge. |
| **Mitigation** | Normalize edge key `tuple(sorted([source, target]))`. |
| **Test hint** | Assert unique edge count in graph.json. |

### GRPH-05: Very large graph (500+ nodes)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Browser slows; hover lag; physics unstable. |
| **Expected behavior** | Still renders; may need physics tuning or node clustering (post-MVP). |
| **Mitigation** | Disable physics after stabilization; limit label length; document personal scale ~100–1000 notes. |
| **Test hint** | Generate 200 fixture nodes; measure render time. |

### GRPH-06: Missing or invalid graph.json at UI load
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Streamlit loads before pipeline run; graph.json absent. |
| **Expected behavior** | Show placeholder UI; don't white-screen. |
| **Mitigation** | `if not Path(GRAPH_PATH).exists(): show st.info(...)`. |
| **Test hint** | Delete graph.json; open app. |

### GRPH-07: Malformed graph.json (invalid JSON)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Partial write during crash mid-export. |
| **Expected behavior** | Catch JSON parse error; show error in UI; suggest rerun build_graph. |
| **Mitigation** | Write to temp file then atomic rename. |
| **Test hint** | Truncated graph.json → graceful error. |

### GRPH-08: Node with missing required fields
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Old wiki note missing `para_category` in frontmatter. |
| **Expected behavior** | Default category `Resources`; default label to note ID. |
| **Mitigation** | Defensive `.get()` on all node fields in build_graph. |
| **Test hint** | Minimal frontmatter wiki file → node still created. |

### GRPH-09: vis-network CDN unavailable
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Offline or CDN blocked in corporate network. |
| **Expected behavior** | Graph panel shows fallback message; ask/search still works. |
| **Mitigation** | Optional: vendor vis-network into `static/` for offline (post-MVP). |
| **Test hint** | Block CDN domain; verify app doesn't crash entirely. |

### GRPH-10: Special characters in hover tooltip (XSS)
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Note content contains `<script>` or HTML in body displayed in tooltip. |
| **Expected behavior** | Escape HTML in tooltip content (personal data, but safe rendering). |
| **Mitigation** | Use textContent or escape `<`, `>`, `&` before injecting into DOM. |
| **Test hint** | Note with `<script>alert(1)</script>` → escaped in hover. |

---

## Phase 5 — RAG Q&A + Streamlit UI

### ASK-01: Question with no relevant notes (low retrieval score)
| | |
|---|---|
| **Severity** | High |
| **Scenario** | User asks "What's the weather?" — nothing in personal notes. |
| **Expected behavior** | Return: `"I don't have notes about that."` — no hallucinated answer. |
| **Mitigation** | Minimum similarity threshold (e.g. 0.3) below which retrieval returns empty. |
| **Test hint** | Off-topic question → no fabricated answer. |

### ASK-02: LLM ignores context and hallucinates
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Model adds general knowledge not in retrieved notes. |
| **Expected behavior** | Prompt instructs "ONLY provided notes"; cite sources; Phase 7 manual review. |
| **Mitigation** | Strong system prompt; include "If insufficient, say so"; show sources so user can verify. |
| **Test hint** | Ask obscure question with thin retrieval; check answer vs sources. |

### ASK-03: Retrieved context exceeds token limit
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Top-5 notes are each 10K chars; exceeds ~4K token budget. |
| **Expected behavior** | Truncate each note excerpt; prioritize highest similarity first; fit within budget. |
| **Mitigation** | `MAX_CONTEXT_CHARS = 12000`; trim notes in retrieval order. |
| **Test hint** | Mock 5 large notes; ask succeeds without API error. |

### ASK-04: Empty question submitted
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User clicks Go with blank search bar. |
| **Expected behavior** | No API call; optional hint "Enter a question." |
| **Mitigation** | `if not question.strip(): return`. |
| **Test hint** | Empty submit in Streamlit → no Groq call. |

### ASK-05: Embeddings index empty (ask before link.py)
| | |
|---|---|
| **Severity** | High |
| **Scenario** | User asks question but pipeline never ran linking step. |
| **Expected behavior** | Clear message: `"Knowledge base not indexed. Run pipeline first."` |
| **Mitigation** | Check index exists and non-empty before retrieve. |
| **Test hint** | Fresh wiki, no embeddings → helpful error. |

### ASK-06: Question in different language than notes
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | English question, Hindi notes (or vice versa). |
| **Expected behavior** | Retrieval may fail or score low; graceful "no notes" or partial answer. |
| **Mitigation** | Document limitation; same multilingual model helps slightly. |
| **Test hint** | Cross-language Q&A manual test. |

### ASK-07: Source citation IDs don't match retrieved notes
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | LLM cites `[20260709_fakeid]` not in context. |
| **Expected behavior** | Post-process: filter `sources` to only IDs actually retrieved. |
| **Mitigation** | Validate citations against retrieval set before returning AskResponse. |
| **Test hint** | Mock LLM with fake citation → stripped from output. |

### UI-01: Streamlit rerun on every keystroke
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | `st.text_input` triggers ask on each character if wired wrong. |
| **Expected behavior** | Ask only on button click or Enter submit. |
| **Mitigation** | Use form: `with st.form("ask_form"): ... st.form_submit_button`. |
| **Test hint** | Type question slowly; single API call on submit. |

### UI-02: Sidebar capture while pipeline running
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User clicks Capture + Run Pipeline twice rapidly. |
| **Expected behavior** | Disable buttons during pipeline; show spinner; queue or ignore duplicate. |
| **Mitigation** | `st.session_state.pipeline_running` flag. |
| **Test hint** | Double-click Run Pipeline → single execution. |

### UI-03: Graph iframe height too small on mobile
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Streamlit on phone; graph unusable. |
| **Expected behavior** | Acceptable for MVP (desktop-first); graph scrollable. |
| **Mitigation** | `layout="wide"`; min height 500px; document desktop recommended. |
| **Test hint** | Manual mobile viewport check. |

### PIPE-01: Pipeline partial failure mid-orchestration
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Classify succeeds; link fails on note 3 of 5. |
| **Expected behavior** | Notes 1–2 fully processed; note 3 marked error; 4–5 still attempted; graph rebuilt from successful notes. |
| **Mitigation** | Per-item error handling in pipeline; continue on failure. |
| **Test hint** | Mock link failure on one ID; pipeline completes others. |

### PIPE-02: `--rebuild` with no raw captures
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | `pipeline.py --rebuild` on empty repo. |
| **Expected behavior** | No-op with message; empty graph.json. |
| **Mitigation** | Early exit if no raw files. |
| **Test hint** | Empty raw/ rebuild. |

### PIPE-03: Processing single ID that doesn't exist
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | `pipeline.py --id nonexistent`. |
| **Expected behavior** | Error: `"Capture not found: nonexistent"`. |
| **Mitigation** | Validate raw JSON exists before processing. |
| **Test hint** | Bad ID → exit 1. |

---

## Phase 6–7 — Testing Edge Cases

### TEST-01: Tests depend on live Groq API
| | |
|---|---|
| **Severity** | High |
| **Scenario** | CI or offline test run calls real API. |
| **Expected behavior** | All unit tests mock LLM; integration tests optional with `@pytest.mark.integration`. |
| **Mitigation** | `unittest.mock` / `pytest-mock` for Groq client. |
| **Test hint** | `pytest -m "not integration"` passes without API key. |

### TEST-02: Tests write to production raw/wiki folders
| | |
|---|---|
| **Severity** | Critical |
| **Scenario** | Test fixtures pollute user's real captures. |
| **Expected behavior** | Tests use `tmp_path` pytest fixture for all I/O. |
| **Mitigation** | Inject paths via config override in conftest.py. |
| **Test hint** | Run tests; user's `raw/` count unchanged. |

### TEST-03: Embedding model loaded on every unit test
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Test suite takes 5+ minutes downloading/loading model. |
| **Expected behavior** | Mock embedding functions in unit tests; one integration test loads real model. |
| **Mitigation** | `@pytest.fixture` with mock embedder for test_link.py. |
| **Test hint** | Unit test suite completes < 30s. |

---

## Phase 8–9 — Deployment Edge Cases

### DEP-01: Personal data committed to public GitHub
| | |
|---|---|
| **Severity** | Critical |
| **Scenario** | `raw/` or `wiki/` accidentally pushed with private notes. |
| **Expected behavior** | `.gitignore` prevents; pre-push checklist in Phase 8. |
| **Mitigation** | Verify `git status` before push; use `demo/` only in repo. |
| **Test hint** | `git ls-files` contains no `raw/` paths. |

### DEP-02: GROQ_API_KEY in Streamlit secrets missing
| | |
|---|---|
| **Severity** | Critical |
| **Scenario** | Deployed app loads but ask/classify fails. |
| **Expected behavior** | UI shows config error in demo mode for ask; graph still renders from demo data. |
| **Mitigation** | Graceful degradation: graph from static demo; ask shows setup instructions. |
| **Test hint** | Deploy without secret; graph works, ask shows error. |

### DEP-03: Streamlit Cloud build timeout (sentence-transformers install)
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Cold build exceeds platform time limit. |
| **Expected behavior** | Pin versions; use demo mode without loading embedding model on cloud if needed. |
| **Mitigation** | Cloud deploy: pre-built demo graph; ask uses pre-computed demo index OR lazy load with cache. |
| **Test hint** | Monitor first deploy build logs. |

### DEP-04: USE_DEMO_DATA=true but demo/ folder empty
| | |
|---|---|
| **Severity** | High |
| **Scenario** | Cloud env set but demo assets not committed. |
| **Expected behavior** | Fallback empty state with README link. |
| **Mitigation** | Phase 5.8 requires demo/ with sample notes + graph.json. |
| **Test hint** | Run locally with USE_DEMO_DATA=true. |

### DEP-05: Concurrent users on public demo URL
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | Multiple visitors use ask simultaneously on Streamlit Cloud free tier. |
| **Expected behavior** | Read-only demo works; sidebar capture disabled in demo mode OR writes to ephemeral session only. |
| **Mitigation** | `USE_DEMO_DATA=true` disables capture/pipeline writes. |
| **Test hint** | Demo mode: capture button hidden or no-op. |

### DEP-06: Groq quota exhausted on public demo
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Viral traffic burns free API quota. |
| **Expected behavior** | Rate limit message to user; graph still viewable. |
| **Mitigation** | Optional daily ask limit in demo; cache common demo questions. |
| **Test hint** | Mock 429 in deployed ask path. |

---

## Cross-Cutting: Data Integrity

### DATA-01: Raw capture manually edited (breaks immutability assumption)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | User edits raw JSON by hand; wiki out of sync. |
| **Expected behavior** | `--force` re-classify from raw; document raw as source of truth. |
| **Mitigation** | `classify.py --force` reprocesses from raw content. |

### DATA-02: Wiki note manually deleted but raw remains
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | raw status=`linked` but wiki file gone. |
| **Expected behavior** | `classify.py --all` skips non-pending; add `pipeline.py --repair` to reset status to pending (optional). |
| **Mitigation** | Orphan detection: raw without wiki → re-classify. |

### DATA-03: Clock skew / timezone in timestamps
| | |
|---|---|
| **Severity** | Low |
| **Scenario** | `captured_at` in local TZ vs UTC. |
| **Expected behavior** | Consistent ISO 8601 with offset; sortable IDs use local date. |
| **Mitigation** | `datetime.now(timezone.utc).isoformat()` or explicit local offset. |

### DATA-04: Disk full during write
| | |
|---|---|
| **Severity** | Critical |
| **Scenario** | JSON write fails mid-serialize. |
| **Expected behavior** | Temp file + atomic rename; on failure, no corrupt partial file. |
| **Mitigation** | Write to `{path}.tmp` then `os.replace()`. |

---

## Cross-Cutting: Security & Privacy

### SEC-01: API key logged in error stack trace
| | |
|---|---|
| **Severity** | Critical |
| **Scenario** | Exception message includes request headers with API key. |
| **Expected behavior** | Never log secrets; redact in error handlers. |
| **Mitigation** | Custom exception handler; don't print full HTTP response. |

### SEC-02: SSRF via URL capture
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | `--url http://169.254.169.254/` (cloud metadata). |
| **Expected behavior** | Block private IP ranges in URL fetcher (optional for personal local tool). |
| **Mitigation** | Resolve hostname; reject RFC1918/link-local if `SSRF_PROTECTION=true`. |

### SEC-03: Malicious PDF (zip bomb / huge page count)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | PDF with millions of pages or decompression bomb. |
| **Expected behavior** | Limit pages extracted (e.g. first 100); max file size check. |
| **Mitigation** | `MAX_PDF_PAGES = 100` in pypdf loop. |

### SEC-04: Personal notes visible on public deployment
| | |
|---|---|
| **Severity** | Critical |
| **Scenario** | Deployed app reads local `wiki/` instead of `demo/`. |
| **Expected behavior** | `USE_DEMO_DATA=true` strictly switches data paths. |
| **Mitigation** | Assert in app startup: if cloud env detected, force demo paths. |

---

## Cross-Cutting: Performance

### PERF-01: First ask() loads embedding model (30s delay)
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Cold start on Streamlit Cloud. |
| **Expected behavior** | `@st.cache_resource` on model loader; show loading spinner. |
| **Mitigation** | Singleton model in session; preload on app start. |

### PERF-02: O(n) similarity search slows with 10K notes
| | |
|---|---|
| **Severity** | Low (post-MVP) |
| **Scenario** | Personal scale exceeded. |
| **Expected behavior** | Acceptable up to ~2000 notes with numpy; FAISS for larger. |
| **Mitigation** | Document scale limits; optional FAISS index in architecture §7. |

### PERF-03: Batch classify of 100 notes sequential
| | |
|---|---|
| **Severity** | Medium |
| **Scenario** | Full rebuild takes 5+ minutes. |
| **Expected behavior** | Progress bar; resumable batch (skip already classified). |
| **Mitigation** | `tqdm` progress; status field enables resume. |

---

## Edge Case Priority Matrix (Implement First)

| Priority | IDs | When to implement |
|----------|-----|-------------------|
| P0 — Blockers | SETUP-01, CLS-04, CAP-08, ASK-01, DEP-01, SEC-01, SEC-04, TEST-02 | Phase 0–2 and before deploy |
| P1 — Core reliability | CAP-05, CAP-13, CLS-01, CLS-03, CLS-07, LNK-08, LNK-10, GRPH-06, ASK-03, ASK-05, PIPE-01 | Same phase as component |
| P2 — UX polish | CAP-01, CAP-09, CLS-06, LNK-02, GRPH-01, ASK-04, UI-01, UI-02 | During phase implementation |
| P3 — Defer | CAP-14, GRPH-05, DEP-05, PERF-02, LNK-12 | Post-MVP or document only |

---

## Quick Test Checklist (Phase 7)

Use this checklist to validate the highest-risk edge cases before deployment:

- [ ] Empty note rejected (CAP-01)
- [ ] Invalid URL handled (CAP-04, CAP-05)
- [ ] Missing file handled (CAP-08)
- [ ] Unicode round-trip (CAP-13)
- [ ] LLM bad JSON fallback (CLS-01)
- [ ] API rate limit retry (CLS-03)
- [ ] Single note, no links (LNK-01)
- [ ] No false links across unrelated topics (LNK-02)
- [ ] Self-link excluded (LNK-10)
- [ ] Empty graph valid (GRPH-01)
- [ ] Orphan nodes visible (GRPH-02)
- [ ] Off-topic question → no hallucination (ASK-01)
- [ ] Empty question no-op (ASK-04)
- [ ] Pipeline partial failure continues (PIPE-01)
- [ ] Demo mode uses demo/ only (DEP-04, SEC-04)
- [ ] Tests don't touch real raw/ (TEST-02)

---

## References

- [architecture.md](./architecture.md) — system design, data models, error handling §11
- [implementation-plan.md](./implementation-plan.md) — phase tasks, risk register, acceptance criteria
