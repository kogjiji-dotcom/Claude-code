"""規程ファイル（条番号つき Markdown）の読み込みと原文照合。"""
import re
from pathlib import Path

from . import config

_ART = re.compile(r"^## (第\d+条|Q\d+)（(.+?)）\n(.*?)(?=^## |\Z)", re.M | re.S)


def norm(s):
    return re.sub(r"\s+", "", s)


def load(dir_=None):
    docs = []
    for f in sorted(Path(dir_ or config.reg_dir()).glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        text = f.read_text(encoding="utf-8")
        name = re.search(r"^規程名:\s*(.+)$", text, re.M)
        ver = re.search(r"^改訂日:\s*(.+)$", text, re.M)
        docs.append({
            "file": f.name,
            "name": name[1].strip() if name else f.stem,
            "version": ver[1].strip() if ver else "不明",
            "articles": [{"no": m[1], "title": m[2], "body": m[3].strip()} for m in _ART.finditer(text)],
        })
    return docs


def find_article(docs, doc_name, art_no):
    for d in docs:
        if d["name"] == doc_name or d["file"].rsplit(".", 1)[0] == doc_name:
            for a in d["articles"]:
                if a["no"] == art_no:
                    return d, a
    return None, None


def verify_quote(docs, doc_name, art_no, quote):
    """引用が、指定の規程・条の本文の部分文字列として実在するか（コードによる強制検証）。"""
    _, art = find_article(docs, doc_name, art_no)
    q = norm(quote)
    return bool(art and len(q) >= 4 and q in norm(art["body"]))


def as_context(docs):
    out = []
    for d in docs:
        out.append(f"【{d['name']}｜改訂日 {d['version']}】")
        for a in d["articles"]:
            out.append(f"{a['no']}（{a['title']}）\n{a['body']}")
    return "\n\n".join(out)
