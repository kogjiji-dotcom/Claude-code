"""入社手続きの案内・進捗管理・催促。届出（社会保険・雇用保険等）は人が実施し、システムは期限の管理だけ行う。"""
import datetime as dt
import json

from . import config, drafts


def template():
    return json.loads((config.DATA / "onboarding_template.json").read_text(encoding="utf-8"))["items"]


def _md(s):
    d = dt.date.fromisoformat(s)
    return f"{d.month}/{d.day}"


def start(emp, start_date, email, con):
    if con.execute("SELECT 1 FROM onboarding WHERE emp=?", (emp,)).fetchone():
        raise ValueError(f"{emp} は登録済みです")
    sd = dt.date.fromisoformat(start_date)
    items = []
    for it in template():
        due = (sd + dt.timedelta(days=it["due_offset"])).isoformat()
        con.execute("INSERT INTO onboarding(emp,email,item,owner,due,human_only,note) VALUES(?,?,?,?,?,?,?)",
                    (emp, email, it["item"], it["owner"], due, int(bool(it.get("human_only"))), it.get("note", "")))
        items.append({**it, "due": due})
    con.commit()
    mine = [f"- {i['item']}（期限 {_md(i['due'])}）" for i in items if i["owner"] == "本人"]
    notice = (f"# 入社のご案内（{emp}）\n\nご入社を楽しみにしています。入社日は {_md(start_date)} です。\n"
              "入社前に、次の書類のご提出をお願いします。\n\n" + "\n".join(mine) +
              f"\n\nご不明点は {config.settings()['contact']} までお問い合わせください。\n")
    check = [f"- [ ] {i['item']}（{i['owner']}／期限 {_md(i['due'])}）" + (f" ※{i['note']}" if i.get("note") else "") for i in items]
    sheet = f"# 入社手続きチェックリスト（{emp}／入社日 {_md(start_date)}）\n\n" + "\n".join(check) + "\n\n※届出は人が専用ソフト／e-Govで実施します。完了したら `onboarding done` で記録してください。\n"
    return [drafts.insert("onboarding_notice", {"employee": emp, "to": email, "key": f"onb:{emp}:notice"}, notice, "template", con),
            drafts.insert("onboarding_checklist", {"employee": emp, "to": config.settings()["contact_email"], "key": f"onb:{emp}:list"}, sheet, "template", con)]


def status(emp, con):
    return con.execute("SELECT item, owner, due, human_only, done_ts, done_by FROM onboarding WHERE emp=? ORDER BY due", (emp,)).fetchall()


def done(emp, item, by, con):
    if not by.strip():
        raise ValueError("記録者名が必要です")
    cur = con.execute("UPDATE onboarding SET done_ts=CURRENT_TIMESTAMP, done_by=? WHERE emp=? AND item=? AND done_ts IS NULL", (by, emp, item))
    con.commit()
    if cur.rowcount == 0:
        raise ValueError("該当する未完了の項目がありません（項目名は完全一致で指定）")


def remind(today, con):
    """期限超過の未完了項目の催促下書きを作る（本人宛と総務宛）。同日の重複は作らない。"""
    rows = con.execute("SELECT emp, email, item, owner, due, human_only FROM onboarding WHERE done_ts IS NULL AND due < ? ORDER BY emp, due", (today,)).fetchall()
    groups = {}
    for r in rows:
        groups.setdefault((r["emp"], r["owner"], r["email"]), []).append(r)
    made = []
    for (emp, owner, email), items in groups.items():
        to = email if owner == "本人" else config.settings()["contact_email"]
        key = f"onbrem:{emp}:{owner}:{today}"
        if con.execute("SELECT 1 FROM drafts WHERE params LIKE ?", (f'%"key": "{key}"%',)).fetchone():
            continue
        lines = [f"- {i['item']}（期限 {_md(i['due'])}）" + ("※人が専用ソフト／e-Govで実施" if i["human_only"] else "") for i in items]
        head = "提出期限を過ぎている書類があります。" if owner == "本人" else f"{emp} の入社手続きで、期限を過ぎている項目があります。"
        body = f"# 入社手続きのリマインド（{emp}）\n\n{head}\n\n" + "\n".join(lines) + f"\n\nお問い合わせ: {config.settings()['contact']}\n"
        made.append(drafts.insert("onboarding_reminder", {"employee": emp, "to": to, "key": key}, body, "template", con))
    return made
