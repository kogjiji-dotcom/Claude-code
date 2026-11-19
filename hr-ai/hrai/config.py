import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def model():
    return os.environ.get("LLM_MODEL", "claude-sonnet-5-5")


def settings():
    return json.loads((DATA / "settings.json").read_text(encoding="utf-8"))


def reg_dir():
    """本番規程があればそれを、無ければ架空のサンプルを使う。"""
    real = DATA / "regulations"
    if any(p for p in real.glob("*.md") if p.name.lower() != "readme.md"):
        return real
    return DATA / "sample_regulations"
