import sys
import json
import random
import shutil
import mimetypes
import urllib.parse
from datetime import datetime as dt
from pathlib import Path
from typing import Optional

import requests
import typer
from bs4 import BeautifulSoup
from pypdf import PdfReader

# Add project root to sys.path if not present (for running capture.py directly)
sys.path.append(str(Path(__file__).parent.resolve()))

from config import RAW_DIR, RAW_FILES_DIR, MAX_CAPTURE_LENGTH, MAX_FILE_SIZE_MB
from models.capture import RawCapture

app = typer.Typer(help="SecondSelf Capture Command Line Interface")

def generate_id() -> str:
    """Generate an ID matching {YYYYMMDD}_{6-char-hex} format."""
    date_str = dt.now().strftime("%Y%m%d")
    hex_str = f"{random.randint(0, 0xffffff):06x}"
    return f"{date_str}_{hex_str}"

def generate_unique_id() -> str:
    """Generate a unique ID, retrying up to 5 times in case of collision (CAP-14)."""
    for _ in range(5):
        cap_id = generate_id()
        if not (RAW_DIR / f"{cap_id}.json").exists():
            return cap_id
    raise RuntimeError("Failed to generate a unique ID after 5 attempts due to collisions.")

def save_capture(capture: RawCapture) -> Path:
    """Save the RawCapture object as a JSON file in raw/ directory using UTF-8 (CAP-13)."""
    file_path = RAW_DIR / f"{capture.id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(capture.to_dict(), f, ensure_ascii=False, indent=2)
    return file_path

def capture_note(text: str) -> RawCapture:
    """Capture a plain text note and save it to raw/."""
    text_stripped = text.strip()
    if not text_stripped:
        print("Error: Capture content cannot be empty. (CAP-01)", file=sys.stderr)
        sys.exit(1)
        
    if len(text_stripped) > MAX_CAPTURE_LENGTH:
        print(f"Warning: Capture content length ({len(text_stripped)} chars) exceeds warning threshold ({MAX_CAPTURE_LENGTH} chars). (CAP-02)", file=sys.stderr)

    cap_id = generate_unique_id()
    captured_at = dt.now().astimezone().isoformat()
    
    capture = RawCapture(
        id=cap_id,
        captured_at=captured_at,
        type="note",
        content=text_stripped,
        status="pending"
    )
    
    save_capture(capture)
    return capture

def is_valid_url(url: str) -> bool:
    """Validate that the URL starts with http:// or https:// (CAP-04)."""
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)

def capture_link(url: str) -> RawCapture:
    """Capture a URL link, fetch its content, extract text/metadata, and save to raw/."""
    url = url.strip()
    if not is_valid_url(url):
        print(f"Error: Invalid URL format '{url}'. Must start with http:// or https://. (CAP-04)", file=sys.stderr)
        sys.exit(1)

    cap_id = generate_unique_id()
    captured_at = dt.now().astimezone().isoformat()
    
    metadata = {}
    content = url  # Fallback content is the URL itself (CAP-05)
    
    try:
        # Fetch with 10s timeout (CAP-05)
        response = requests.get(url, timeout=10)
        metadata["fetch_status"] = response.status_code
        
        # Check Content-Type (CAP-06)
        content_type = response.headers.get("Content-Type", "")
        metadata["content_type"] = content_type
        
        if "text/html" in content_type:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extract title
            title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled Link"
            metadata["title"] = title
            
            # Extract paragraphs / article text
            text_blocks = []
            for tag in soup.find_all(['p', 'h1', 'h2', 'h3']):
                t = tag.get_text().strip()
                if t:
                    text_blocks.append(t)
            
            extracted_text = "\n\n".join(text_blocks)
            metadata["content_length"] = len(extracted_text)
            
            if extracted_text:
                content = f"Title: {title}\n\nContent:\n{extracted_text}"
            else:
                content = f"Title: {title}\n\n[No visible article text extracted]"
                metadata["extraction"] = "empty"
        else:
            # Non-HTML content (CAP-06)
            if "text/" in content_type or "application/json" in content_type:
                extracted_text = response.text
                metadata["content_length"] = len(extracted_text)
                content = extracted_text
            else:
                content = f"[Non-HTML link of type {content_type}]"
                metadata["content_length"] = 0
                metadata["extraction"] = "unsupported_mime"
                
    except requests.exceptions.RequestException as e:
        # Fetch failed (CAP-05)
        metadata["error"] = "fetch_failed"
        metadata["error_detail"] = str(e)
        content = f"Failed to fetch content from URL: {url}\nError: {e}"
        print(f"Warning: Failed to fetch URL content. Capturing URL as text. (CAP-05)", file=sys.stderr)

    capture = RawCapture(
        id=cap_id,
        captured_at=captured_at,
        type="link",
        content=content,
        source_url=url,
        status="pending",
        metadata=metadata
    )
    
    save_capture(capture)
    return capture

def capture_file(file_path_str: str) -> RawCapture:
    """Capture a local file, copy it to raw/files/, extract content if supported, and save metadata to raw/."""
    file_path = Path(file_path_str)
    
    # Validate file existence (CAP-08)
    if not file_path.exists() or not file_path.is_file():
        print(f"Error: File not found: '{file_path_str}'. (CAP-08)", file=sys.stderr)
        sys.exit(1)
        
    # Enforce size limit (CAP-12)
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        print(f"Error: File size ({file_size_mb:.2f} MB) exceeds maximum allowed limit ({MAX_FILE_SIZE_MB} MB). (CAP-12)", file=sys.stderr)
        sys.exit(1)
        
    cap_id = generate_unique_id()
    captured_at = dt.now().astimezone().isoformat()
    ext = file_path.suffix
    
    # Destination path
    dest_path = RAW_FILES_DIR / f"{cap_id}{ext}"
    
    # Copy file to raw/files/ (keep bytes safe - CAP-11)
    shutil.copy2(file_path, dest_path)
    
    # Detect mime type
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        if ext == ".md":
            mime_type = "text/markdown"
        else:
            mime_type = "application/octet-stream"
            
    metadata = {
        "original_filename": file_path.name,
        "file_size_bytes": file_path.stat().st_size
    }
    
    content = ""
    
    # Extract content if supported (CAP-09)
    if mime_type == "application/pdf":
        try:
            reader = PdfReader(dest_path)
            if reader.is_encrypted:
                metadata["error"] = "pdf_read_failed"
                metadata["error_detail"] = "PDF is password-protected"
                content = ""
                print("Warning: PDF is password-protected. Copied file without text extraction. (CAP-11)", file=sys.stderr)
            else:
                extracted_pages = []
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        extracted_pages.append(text)
                
                extracted_text = "\n\n".join(extracted_pages).strip()
                if extracted_text:
                    content = extracted_text
                else:
                    content = "[No extractable text]"
                    metadata["extraction"] = "empty"
                    print("Warning: PDF contains no extractable text (possibly scanned image). (CAP-10)", file=sys.stderr)
        except Exception as e:
            metadata["error"] = "pdf_read_failed"
            metadata["error_detail"] = str(e)
            content = ""
            print(f"Warning: Failed to read PDF. Copied file without text extraction. Error: {e} (CAP-11)", file=sys.stderr)
            
    elif mime_type in ("text/plain", "text/markdown") or ext in (".txt", ".md"):
        try:
            with open(dest_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(dest_path, "r", encoding="latin-1") as f:
                    content = f.read()
                metadata["encoding_warning"] = "read_as_latin1"
            except Exception as e:
                metadata["error"] = "file_read_failed"
                metadata["error_detail"] = str(e)
                content = ""
                print(f"Warning: Failed to read text file. Copied file without text extraction. (CAP-09)", file=sys.stderr)
    else:
        content = f"[Captured non-text file: {file_path.name}]"
        metadata["extraction"] = "unsupported_mime"
        print(f"Warning: Unsupported file type '{mime_type}'. Copied file without text extraction. (CAP-09)", file=sys.stderr)
        
    capture = RawCapture(
        id=cap_id,
        captured_at=captured_at,
        type="file",
        content=content,
        file_path=f"raw/files/{cap_id}{ext}",
        mime_type=mime_type,
        status="pending",
        metadata=metadata
    )
    
    save_capture(capture)
    return capture

@app.command()
def main(
    content: Optional[str] = typer.Argument(None, help="Text note to capture"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL link to capture"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Local file path to capture"),
    stdin: bool = typer.Option(False, "--stdin", "-s", help="Pipe note content from stdin")
):
    """Capture a new item (note, URL link, or local file) and save it to the raw captures folder."""
    # Count provided inputs (CAP-16)
    provided_inputs = []
    if content is not None:
        provided_inputs.append("positional content")
    if url is not None:
        provided_inputs.append("--url")
    if file is not None:
        provided_inputs.append("--file")
    if stdin:
        provided_inputs.append("--stdin")
        
    if len(provided_inputs) == 0:
        print("Error: No capture source provided. Provide note text, or use --url, --file, or --stdin. (CAP-16)", file=sys.stderr)
        sys.exit(1)
    elif len(provided_inputs) > 1:
        print(f"Error: Conflicting capture sources: {', '.join(provided_inputs)}. Provide only one capture source. (CAP-16)", file=sys.stderr)
        sys.exit(1)

    capture = None

    if content is not None:
        capture = capture_note(content)
        
    elif url is not None:
        capture = capture_link(url)
        
    elif file is not None:
        capture = capture_file(file)
        
    elif stdin:
        stdin_content = sys.stdin.read()
        if not stdin_content.strip():
            print("Error: Capture content from stdin cannot be empty. (CAP-15)", file=sys.stderr)
            sys.exit(1)
        capture = capture_note(stdin_content)

    if capture:
        # Confirm capture details (1.6)
        print(f"Capture successful!")
        print(f"ID: {capture.id}")
        print(f"Type: {capture.type}")
        if capture.file_path:
            print(f"Saved file to: {capture.file_path}")

if __name__ == "__main__":
    app()
