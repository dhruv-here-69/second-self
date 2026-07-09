import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Python Version Check (SETUP-03)
if sys.version_info < (3, 11):
    print(f"Error: Python 3.11+ is required. Current version is {sys.version_info.major}.{sys.version_info.minor}.", file=sys.stderr)
    sys.exit(1)

# Resolve base directory (absolute path to secondself folder - SETUP-05)
BASE_DIR = Path(__file__).parent.resolve()

# Load env file from the base directory
load_dotenv(BASE_DIR / ".env")

# Check GROQ_API_KEY (SETUP-01)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Allow missing key during pytest tests to allow mocking/running test suite
is_testing = "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST") is not None or os.getenv("TESTING") == "true"
if not GROQ_API_KEY and not is_testing:
    print("Error: GROQ_API_KEY not set. Copy .env.example to .env and add your key.", file=sys.stderr)
    sys.exit(1)

# Path Configurations (absolute paths using pathlib)
RAW_DIR = BASE_DIR / "raw"
RAW_FILES_DIR = RAW_DIR / "files"
WIKI_DIR = BASE_DIR / "wiki"
DATA_DIR = BASE_DIR / "data"
GRAPH_PATH = BASE_DIR / "graph.json"

# Threshold and Config Constants
SIMILARITY_THRESHOLD = 0.75
MAX_LINKS_PER_NOTE = 5
TOP_K = 5
MAX_FILE_SIZE_MB = 50
MAX_CAPTURE_LENGTH = 500000

# Demo mode config
USE_DEMO_DATA = os.getenv("USE_DEMO_DATA", "false").lower() == "true"

def ensure_dirs():
    """Ensure all required directories exist (SETUP-02)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RAW_FILES_DIR.mkdir(parents=True, exist_ok=True)
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

# Run ensure_dirs at import time to guarantee folders exist (SETUP-02)
ensure_dirs()
