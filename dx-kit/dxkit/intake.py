"""請求書・領収書テキストから日付・金額・取引先を抽出して CSV 化。"""
import csv
import re
from pathlib import Path

from . import audit

FIELDS = ["file", "date", "amount", "vendor", "needs_review"]


def parse(text):
    date = re.search(r"(20\d{2})[/\-年.](\d{1,2})[/\-月.](\d{1,2})", text)
    amt = re.search(r"(?:合計|総額|請求金額)[^\d¥￥]*[¥￥]?\s*([\d,]+)", text)
    vendor = re.search(r"(?:請求元|発行元|店名|取引先)\s*[:：]\s*(.+)", text)
    row = {
        "date": f"{int(date[1]):04d}-{int(date[2]):02d}-{int(date[3]):02d}" if date else "",
        "amount": int(amt[1].replace(",", "")) if amt else "",
        "vendor": vendor[1].strip() if vendor else "",
    }
    row["needs_review"] = "" if all(row.values()) else "yes"  # 欠損は人間が確認
    return row


def run(paths, out_csv):
    rows = []
    for p in paths:
        row = {"file": Path(p).name, **parse(Path(p).read_text(encoding="utf-8"))}
        rows.append(row)
        audit.record("intake", file=row["file"], needs_review=row["needs_review"])
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return rows
