"""全ての AI 判断を追記専用 JSONL に記録する（監査・ROI 集計の元データ）。"""
import json
import time
from pathlib import Path

from .config import ROOT

LOG = ROOT / "out" / "audit.jsonl"


def record(event, **data):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **data}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read(path=None):
    p = Path(path) if path else LOG
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
