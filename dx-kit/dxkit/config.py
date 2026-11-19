import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path=None):
    p = Path(path) if path else ROOT / "config" / "company.json"
    return json.loads(p.read_text(encoding="utf-8"))
