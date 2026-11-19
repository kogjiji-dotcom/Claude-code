import argparse
import json
import sys
from pathlib import Path

from . import config, intake, kb, roi, triage
from .config import ROOT


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dxkit")
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("triage", help="問い合わせ JSONL を処理")
    t.add_argument("file")
    i = sub.add_parser("intake", help="請求書テキストを CSV 化")
    i.add_argument("files", nargs="+")
    i.add_argument("--out", default=str(ROOT / "out" / "documents.csv"))
    sub.add_parser("roi", help="削減効果レポート")
    a = ap.parse_args(argv)
    cfg = config.load(a.config)

    if a.cmd == "triage":
        entries = kb.load()
        outdir = ROOT / "out"
        outdir.mkdir(exist_ok=True)
        queues = {"auto": [], "review": [], "escalate": []}
        for line in Path(a.file).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = triage.triage(cfg, json.loads(line), entries)
                queues[r["action"]].append(r)
                print(f"[{r['action']:8}] {r['id']} {r['category']:9} → {r['route']:13} ({r['reason']})")
        for name, items in queues.items():  # 送信はせず、キューへ書き出すのみ
            (outdir / f"queue_{name}.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    elif a.cmd == "intake":
        for r in intake.run(a.files, a.out):
            print(r)
    else:
        print(json.dumps(roi.report(cfg), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
