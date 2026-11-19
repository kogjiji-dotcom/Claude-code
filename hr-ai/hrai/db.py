"""質問・回答・引用・承認者の記録（SQLite）。HRAI_DB で保存先を切り替え可能。"""
import os
import sqlite3
from pathlib import Path

from .config import ROOT

SCHEMA = """
CREATE TABLE IF NOT EXISTS qa_log(
  id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP, question TEXT, status TEXT,
  reason TEXT, answer TEXT, citations TEXT, versions TEXT, engine TEXT, pii TEXT);
CREATE TABLE IF NOT EXISTS eval_access(
  id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP, evaluator TEXT, employee TEXT, period TEXT, draft_id INTEGER);
CREATE TABLE IF NOT EXISTS onboarding(
  id INTEGER PRIMARY KEY, emp TEXT, email TEXT, item TEXT, owner TEXT, due TEXT, human_only INTEGER DEFAULT 0, note TEXT, done_ts TEXT, done_by TEXT);
CREATE TABLE IF NOT EXISTS drafts(
  id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP, kind TEXT, params TEXT, body TEXT,
  flags TEXT, status TEXT DEFAULT 'pending', approver TEXT, decided_ts TEXT, note TEXT, engine TEXT,
  body_hash TEXT, sent_ts TEXT, sent_via TEXT, sent_to TEXT);
"""


def connect(path=None):
    p = Path(path or os.environ.get("HRAI_DB") or ROOT / "logs" / "hr_ai.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    cols = {r["name"] for r in con.execute("PRAGMA table_info(drafts)")}
    for c in ("body_hash", "sent_ts", "sent_via", "sent_to"):  # 旧DBの移行
        if c not in cols:
            con.execute(f"ALTER TABLE drafts ADD COLUMN {c} TEXT")
    return con
