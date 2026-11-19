"""50問ゴールデンテスト。規程更新・モデル変更のたびに再実行する。"""
import json
import tempfile
from pathlib import Path

from . import bot, config, db, regs

GOLDEN = config.ROOT / "tests" / "eval" / "golden.json"
THRESH = {"answer": 0.95, "noanswer": 1.0, "refuse": 1.0}


def run(reg_dir=None, llm_fn=None, verbose=True):
    docs = regs.load(reg_dir or config.DATA / "sample_regulations")
    con = db.connect(Path(tempfile.mkdtemp()) / "eval.db")  # 本番ログを汚さない
    stats = {k: [0, 0] for k in THRESH}
    for t in json.loads(GOLDEN.read_text(encoding="utf-8")):
        r = bot.answer(t["q"], docs, llm_fn, con)
        if t["type"] == "answer":
            ok = r["status"] == "answered" and any(c["doc"].startswith(t["doc"]) and c["article"] == t["article"] for c in r["citations"])
        else:
            ok = r["status"] == ("no_record" if t["type"] == "noanswer" else "refused")
        stats[t["type"]][0] += ok
        stats[t["type"]][1] += 1
        if not ok and verbose:
            print(f"  NG [{t['type']}] {t['q']} -> {r['status']} {r['citations'][:1]}")
    passed = True
    for k, (ok, n) in stats.items():
        rate = ok / n
        good = rate >= THRESH[k]
        passed &= good
        if verbose:
            print(f"{'PASS' if good else 'FAIL'} {k:9} {ok}/{n} ({rate:.0%}, 基準 {THRESH[k]:.0%})")
    return passed, stats
