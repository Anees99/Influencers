import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
for p in ["", "config", "database", "schemas", "ingestion", "matching",
          "reconciliation", "reporting", "ai", "ui"]:
    d = str(ROOT / p)
    if d not in sys.path:
        sys.path.insert(0, d)
