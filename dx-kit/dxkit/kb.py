"""ナレッジベース検索。見出し単位に分割し、文字 bigram の重なりでスコアリング。"""
from pathlib import Path

from .config import ROOT


def _bigrams(s):
    s = "".join(s.split())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def load(dir_=None):
    d = Path(dir_) if dir_ else ROOT / "knowledge"
    entries = []
    for f in sorted(d.glob("*.md")):
        for block in f.read_text(encoding="utf-8").split("\n# "):
            block = block.lstrip("# ").strip()
            if block:
                title, _, body = block.partition("\n")
                entries.append({"title": title.strip(), "body": body.strip(), "src": f.name})
    return entries


def search(query, entries, k=2, min_score=0.15):
    q = _bigrams(query)
    scored = []
    for e in entries:
        t = _bigrams(e["title"] + e["body"])
        if q and t:
            scored.append((len(q & t) / len(q), e))
    scored.sort(key=lambda x: -x[0])
    return [dict(e, score=round(s, 2)) for s, e in scored[:k] if s >= min_score]
