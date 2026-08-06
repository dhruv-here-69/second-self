"""
classify.py — Phase 2: Auto-Classification

Reads raw captures (status=pending) and uses Groq/Llama 3 to assign
PARA categories, generate tags, a title, and a one-line summary.
Writes results as wiki notes: wiki/{id}.md with YAML frontmatter.

Usage:
    python classify.py --all              # Process all pending captures
    python classify.py --id 20260709_a3f9c2
    python classify.py --all --force      # Re-classify even if wiki note exists
"""

import sys
import io
import json
import time
from datetime import datetime as dt
from pathlib import Path
from typing import Optional

import typer
import yaml
from groq import Groq, APIStatusError, APIConnectionError

# Ensure project root is in sys.path when running directly
sys.path.append(str(Path(__file__).parent.resolve()))

# Fix Windows console encoding for Unicode output (→, etc.)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import (
    GROQ_API_KEY,
    RAW_DIR,
    WIKI_DIR,
    GROQ_MODEL,
    MAX_CLASSIFY_CHARS,
    MAX_TAGS,
)
from models.capture import RawCapture
from models.note import WikiNote

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARA_CATEGORIES = {"Projects", "Areas", "Resources", "Archives"}
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds (doubles on each retry)
BATCH_DELAY = 0.5       # polite delay between batch items

PARA_PROMPT_TEMPLATE = """\
You are a personal knowledge librarian using the PARA method.
Classify the following capture into exactly one PARA category:

- Projects: time-bound outcomes with a clear deadline or goal
- Areas: ongoing responsibilities (health, finance, career, habits)
- Resources: reference material, tutorials, articles, interests
- Archives: inactive, completed, or no-longer-relevant items

Return ONLY a valid JSON object with these exact keys:
{{
  "para_category": "Projects|Areas|Resources|Archives",
  "tags": ["tag1", "tag2"],
  "title": "One-line descriptive title (max 80 chars)",
  "summary": "One-sentence summary of the capture"
}}

Do not include any text outside the JSON object.

Capture type: {capture_type}
Capture content:
{content}
"""

# ---------------------------------------------------------------------------
# Groq client (lazy init)
# ---------------------------------------------------------------------------

_client: Optional[Groq] = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------


def build_prompt(raw: RawCapture) -> str:
    """Build the PARA classification prompt, truncating content for LLM safety."""
    content = raw.content or ""

    # CLS-05: empty content — pass metadata context instead
    if not content.strip():
        meta_hints = []
        if raw.source_url:
            meta_hints.append(f"Source URL: {raw.source_url}")
        if raw.file_path:
            meta_hints.append(f"File path: {raw.file_path}")
        if raw.mime_type:
            meta_hints.append(f"MIME type: {raw.mime_type}")
        if raw.metadata:
            title = raw.metadata.get("title")
            if title:
                meta_hints.append(f"Page title: {title}")
            err = raw.metadata.get("error_detail")
            if err:
                meta_hints.append(f"Fetch error: {err}")
        content = "\n".join(meta_hints) if meta_hints else "[No content available]"

    # CLS-07: truncate for LLM context window
    truncated = content[:MAX_CLASSIFY_CHARS]
    if len(content) > MAX_CLASSIFY_CHARS:
        truncated += "\n\n[...content truncated for classification...]"

    return PARA_PROMPT_TEMPLATE.format(
        capture_type=raw.type,
        content=truncated,
    )


def parse_llm_response(text: str) -> dict:
    """
    Extract and parse JSON from LLM response text.
    Returns a dict with keys: para_category, tags, title, summary.
    Raises ValueError on failure.
    """
    text = text.strip()

    # Try to isolate a JSON object in case the model adds surrounding text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")

    json_str = text[start:end]
    data = json.loads(json_str)
    return data


def validate_llm_data(data: dict) -> dict:
    """
    Validate/normalize the LLM output dict.
    Returns a cleaned dict ready for WikiNote construction.
    """
    # para_category — must be one of the four valid PARA categories
    category = str(data.get("para_category", "")).strip()
    if category not in PARA_CATEGORIES:
        category = "Resources"  # safe fallback per plan §2.3

    # tags — list of strings, capped at MAX_TAGS, strip empties (CLS-08)
    raw_tags = data.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = []
    tags = [str(t).strip().lower() for t in raw_tags if str(t).strip()][:MAX_TAGS]

    # title — string, max 80 chars
    title = str(data.get("title", "")).strip()[:80] or "Untitled"

    # summary — single sentence string
    summary = str(data.get("summary", "")).strip() or title

    return {
        "para_category": category,
        "tags": tags,
        "title": title,
        "summary": summary,
    }


def call_groq_with_retry(prompt: str) -> dict:
    """
    Call Groq API with retry logic (up to MAX_RETRIES).
    Returns validated LLM classification data.
    Raises on auth error (CLS-04) or after exhausting retries.
    """
    client = get_client()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=512,
            )
            text = response.choices[0].message.content or ""
            data = parse_llm_response(text)
            return validate_llm_data(data)

        except APIStatusError as e:
            if e.status_code == 401:
                # CLS-04: Auth error — fail immediately, don't retry
                raise RuntimeError(
                    f"Groq API authentication failed (401). "
                    f"Check your GROQ_API_KEY in .env."
                ) from e
            if e.status_code == 429:
                # CLS-03: Rate limit — exponential backoff
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(
                    f"  Rate limited (429). Waiting {delay:.1f}s before retry "
                    f"{attempt}/{MAX_RETRIES}...",
                    file=sys.stderr,
                )
                time.sleep(delay)
                last_error = e
            else:
                # Other API error — retry
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(
                    f"  API error {e.status_code} on attempt {attempt}/{MAX_RETRIES}: {e}. "
                    f"Retrying in {delay:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(delay)
                last_error = e

        except APIConnectionError as e:
            # CLS-10: Network error — retry
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            print(
                f"  Network error on attempt {attempt}/{MAX_RETRIES}: {e}. "
                f"Retrying in {delay:.1f}s...",
                file=sys.stderr,
            )
            time.sleep(delay)
            last_error = e

        except (ValueError, json.JSONDecodeError) as e:
            # LLM returned malformed JSON — retry once more then fallback
            delay = RETRY_BASE_DELAY
            print(
                f"  LLM response parse error on attempt {attempt}/{MAX_RETRIES}: {e}. "
                f"Retrying in {delay:.1f}s...",
                file=sys.stderr,
            )
            time.sleep(delay)
            last_error = e

    raise RuntimeError(
        f"Failed to get valid classification after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def classify_capture(raw: RawCapture) -> WikiNote:
    """
    Classify a single RawCapture using Groq/Llama 3.
    Returns a WikiNote ready to be written to disk.
    Falls back gracefully on LLM parse failure.
    """
    prompt = build_prompt(raw)

    # Attempt LLM classification
    try:
        llm_data = call_groq_with_retry(prompt)
    except RuntimeError as e:
        # Auth errors bubble up — don't silently swallow them
        raise

    now = dt.now().astimezone().isoformat()
    title = llm_data["title"]
    body_content = raw.content or ""

    # Compose the markdown body (full content, not truncated — CLS-07)
    body_lines = [f"# {title}", ""]
    if raw.source_url:
        body_lines += [f"> Source: {raw.source_url}", ""]
    if raw.file_path:
        body_lines += [f"> File: `{raw.file_path}`", ""]
    body_lines.append(body_content)

    return WikiNote(
        id=raw.id,
        title=title,
        para_category=llm_data["para_category"],
        tags=llm_data["tags"],
        summary=llm_data["summary"],
        links=[],           # populated in Phase 3
        embedding_id=raw.id,
        created_at=now,
        updated_at=now,
        content="\n".join(body_lines),
    )


# ---------------------------------------------------------------------------
# Wiki note file I/O
# ---------------------------------------------------------------------------


def write_wiki_note(note: WikiNote) -> Path:
    """
    Write wiki/{id}.md with YAML frontmatter + markdown body.
    CLS-09: Uses yaml.dump for safe quoting of special characters.
    """
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
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

    # CLS-09: yaml.dump handles quoting of :, #, " etc. automatically
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


def load_raw_capture(raw_path: Path) -> RawCapture:
    """Load a RawCapture from a JSON file."""
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return RawCapture.from_dict(data)


def update_raw_status(raw_path: Path, status: str) -> None:
    """
    Update the status field in a raw capture JSON file (CLS-10: atomic — 
    only called after wiki write succeeds).
    """
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["status"] = status
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Classify one capture
# ---------------------------------------------------------------------------


def process_one(raw_path: Path, force: bool = False) -> bool:
    """
    Classify a single raw capture file.
    Returns True on success, False on skip or error.
    """
    raw = load_raw_capture(raw_path)
    wiki_path = WIKI_DIR / f"{raw.id}.md"

    # CLS-06: skip if wiki already exists (unless --force)
    if wiki_path.exists() and not force:
        print(f"  [SKIP] {raw.id} — wiki note already exists (use --force to re-classify)")
        # Still mark as classified so --all doesn't keep trying
        if raw.status == "pending":
            update_raw_status(raw_path, "classified")
        return False

    print(f"  Classifying {raw.id} ({raw.type})...")

    try:
        note = classify_capture(raw)

        # CLS-10: write wiki FIRST, then update status (atomic order)
        dest = write_wiki_note(note)
        update_raw_status(raw_path, "classified")

        print(
            f"  [OK]   {raw.id} -> {note.para_category} | "
            f'"{note.title}" | tags: {note.tags}'
        )
        return True

    except RuntimeError as e:
        err_msg = str(e)
        # CLS-04: auth error — abort immediately
        if "authentication failed" in err_msg.lower():
            print(f"\nFATAL: {err_msg}", file=sys.stderr)
            sys.exit(1)
        # Other errors — mark as error, continue batch
        print(f"  [ERR]  {raw.id} — {err_msg}", file=sys.stderr)
        update_raw_status(raw_path, "error")
        return False

    except Exception as e:
        print(f"  [ERR]  {raw.id} — Unexpected error: {e}", file=sys.stderr)
        update_raw_status(raw_path, "error")
        return False


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="SecondSelf Phase 2 — Auto-Classification using Groq/Llama 3")


@app.command()
def main(
    all_captures: bool = typer.Option(
        False, "--all", "-a", help="Process all pending raw captures"
    ),
    capture_id: Optional[str] = typer.Option(
        None, "--id", help="Process a single capture by ID"
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Re-classify even if wiki note already exists (CLS-06)"
    ),
):
    """
    Classify raw captures with Groq/Llama 3 and write wiki notes to wiki/.
    """
    if not all_captures and not capture_id:
        print(
            "Error: Provide --all to process all pending captures, "
            "or --id <capture_id> to process one.",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    if all_captures and capture_id:
        print("Error: Use --all OR --id, not both.", file=sys.stderr)
        raise typer.Exit(1)

    # --id mode
    if capture_id:
        raw_path = RAW_DIR / f"{capture_id}.json"
        if not raw_path.exists():
            print(f"Error: No raw capture found for ID '{capture_id}'.", file=sys.stderr)
            raise typer.Exit(1)
        raw = load_raw_capture(raw_path)
        if raw.status not in ("pending", "error") and not force:
            print(
                f"Capture {capture_id} has status '{raw.status}'. "
                f"Use --force to re-classify.",
                file=sys.stderr,
            )
            raise typer.Exit(0)
        process_one(raw_path, force=force)
        return

    # --all mode: collect pending captures
    raw_files = sorted(RAW_DIR.glob("*.json"))
    pending = []
    skipped_non_pending = 0

    for raw_path in raw_files:
        raw = load_raw_capture(raw_path)
        if raw.status == "pending" or (force and raw.status in ("classified", "error")):
            pending.append(raw_path)
        else:
            skipped_non_pending += 1

    if not pending:
        print("No pending captures to classify.")
        if skipped_non_pending:
            print(f"({skipped_non_pending} captures already classified — use --force to re-run)")
        return

    print(f"Classifying {len(pending)} capture(s)...")
    if skipped_non_pending:
        print(f"  ({skipped_non_pending} already classified, skipped)")

    success = 0
    errors = 0
    skipped = 0

    for i, raw_path in enumerate(pending):
        ok = process_one(raw_path, force=force)
        if ok:
            success += 1
        else:
            # Distinguish skip vs error by re-checking status
            raw = load_raw_capture(raw_path)
            if raw.status == "error":
                errors += 1
            else:
                skipped += 1

        # CLS-03: polite delay between batch items to avoid rate limits
        if i < len(pending) - 1:
            time.sleep(BATCH_DELAY)

    print(f"\nDone. {success} classified, {skipped} skipped, {errors} error(s).")
    if errors:
        print("  Re-run with --all to retry errored captures.", file=sys.stderr)


if __name__ == "__main__":
    app()
