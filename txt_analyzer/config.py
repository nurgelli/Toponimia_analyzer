from __future__ import annotations
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if getattr(sys, "frozen", False):
    default_data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Türkmen dili boýunça barlaýjy"
else:
    default_data_dir = BASE_DIR / "data"
DATA_DIR = Path(os.environ.get("TXT_ANALYZER_DATA_DIR", default_data_dir))
DB_PATH = DATA_DIR / "names.sqlite3"
OUTPUT_DIR = DATA_DIR / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)