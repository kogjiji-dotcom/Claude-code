"""勤怠・有給アラート。判定は全て数値計算（コード）。文面は固定テンプレートで、AIは使わない。

勤怠CSV（employee,date,clock_in,clock_out,break_min,leave）と社員ディレクトリ（社員ID→連絡先・上長・付与日数）を入力する。
しきい値（残業時間の目安・有給の最低取得日数など）は data/settings.json の自社設定。法令値はコードに埋め込まない。
アラートは承認待ちの下書きになり、人が承認してから送信される（本人と上長のみ宛先）。
"""
import csv
import datetime as dt
import json
from pathlib import Path

from . import config, drafts


def hr_dir():
    real = config.DATA / "hr"
    return real if (real / "attendance.csv").exists() else config.DATA / "sample_hr"


def load(dir_=None):
    d = Path(dir_) if dir_ else hr_dir()
    with (d / "attendance.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads((d / "directory.json").read_text(encoding="utf-8"))


def _min(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _workdays(first, last, holidays):
    d, out = first, []
    while d <= last:
        if d.weekday() < 5 and d.isoformat() not in holidays:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _fy_start(today, mmdd):
    m, d = map(int, mmdd.split("-"))
    start = dt.date(today.year, m, d)
    return start if today >= start else dt.date(today.year - 1, m, d)


def analyze(emp, month, today, rows, info, cfg):
    y, m = map(int, month.split("-"))
    first = dt.date(y, m, 1)
    last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
    hol = set(cfg["holidays"])
    workdays = _workdays(first, last, hol)
    passed = [d for d in workdays if d < today]
    mine = [r for r in rows if r["employee"] == emp]
    have = {r["date"] for r in mine}
    out = {"missing": [d for d in passed if d.isoformat() not in have]}

    std = cfg["standard_hours_per_day"] * 60
    ot = 0
    for r in mine:
        if r["date"][:7] == month and r["clock_in"] and r["clock_out"]:
            ot += max(0, _min(r["clock_out"]) - _min(r["clock_in"]) - int(r["break_min"] or 0) - std)
    out["ot_so_far"] = ot / 60
    out["ot_projected"] = ot / 60 / len(passed) * len(workdays) if passed else 0.0
    out["ot_warn"] = out["ot_projected"] > cfg["overtime_warn_hours"]

    fy = _fy_start(today, cfg["fiscal_year_start"])
    taken = info.get("leave_taken_before", 0) + sum(
        (1.0 if r["leave"] == "有給" else 0.5 if r["leave"] == "半休" else 0.0) for r in mine if r["date"] >= fy.isoformat())
    fy_end = dt.date(fy.year + 1, fy.month, fy.day) - dt.timedelta(days=1)
    months_left = (fy_end.year - today.year) * 12 + fy_end.month - today.month
    out.update(leave_taken=taken, months_left=months_left, leave_needed=max(0.0, cfg["paid_leave_min_days"] - taken))
    out["leave_warn"] = (info.get("paid_leave_granted", 0) >= cfg["paid_leave_obligation_min_grant"]
                         and taken < cfg["paid_leave_min_days"] and months_left <= cfg["alert_months_before_year_end"])
    return out


def _md(d):
    return f"{d.month}/{d.day}"


def _body(emp, month, a, cfg, for_manager):
    y, m = month.split("-")
    lines = [f"# [勤怠] ご確認のお願い（{emp}／{y}年{int(m)}月）", ""]
    if for_manager:
        lines += [f"チームの {emp} について、次の点をご確認のうえ、必要に応じて声かけをお願いします。", ""]
    else:
        lines += ["次の点をご確認ください。", ""]
    if a["missing"] and not for_manager:
        lines.append("- 勤怠の未入力: " + "、".join(_md(d) for d in a["missing"]))
    if a["ot_warn"]:
        lines.append(f"- 残業時間が月末に向けて増える見込みです（現在 {a['ot_so_far']:.1f}時間／月末見込み {a['ot_projected']:.1f}時間、社内の目安 {cfg['overtime_warn_hours']}時間）")
    if a["leave_warn"]:
        lines.append(f"- 年次有給休暇の取得が目安に達していません（取得 {a['leave_taken']:g}日／目安 {cfg['paid_leave_min_days']}日、年度末まであと{a['months_left']}か月、あと{a['leave_needed']:g}日）")
    lines += ["", "※数値は勤怠データからの自動集計です。詳細は勤怠システムでご確認ください。", "※この通知は評価に使われるものではありません。", f"お問い合わせ: {config.settings()['contact']}"]
    return "\n".join(lines) + "\n"


def _exists(con, key):
    return con.execute("SELECT 1 FROM drafts WHERE params LIKE ?", (f'%"key": "{key}"%',)).fetchone() is not None


def check(month, today, con, dir_=None):
    """アラート下書きを作成して返す。同じ日付・宛先・対象の重複は作らない。"""
    cfg = config.settings()["attendance"]
    rows, directory = load(dir_)
    today = dt.date.fromisoformat(today) if isinstance(today, str) else today
    created = []
    for emp, info in directory.items():
        if not info.get("track"):
            continue
        a = analyze(emp, month, today, rows, info, cfg)
        if not (a["missing"] or a["ot_warn"] or a["leave_warn"]):
            continue
        targets = [("employee", info["email"])]
        if (a["ot_warn"] or a["leave_warn"]) and info.get("manager") in directory:
            targets.append(("manager", directory[info["manager"]]["email"]))
        for role, to in targets:
            key = f"attendance:{emp}:{role}:{today.isoformat()}"
            if _exists(con, key):
                continue
            body = _body(emp, month, a, cfg, role == "manager")
            did = drafts.insert("attendance_alert", {"employee": emp, "to": to, "role": role, "key": key}, body, "template", con)
            created.append({"id": did, "employee": emp, "role": role, "to": to})
    return created
