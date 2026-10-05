"""Central project paths. No API keys are stored in source code."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "br_performance.db"
SAMPLES_DIR = DATA_DIR / "samples"
REFERENCES_DIR = DATA_DIR / "references"
UPLOADS_DIR = DATA_DIR / "uploads"
