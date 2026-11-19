"""求人応募の一次対応。受付返信・FAQ回答・面接日程の候補提示まで。選考（合否・評価・条件交渉）は行わない。

返信は承認待ちの下書き。FAQの回答は規程Botと同じ「原文引用の検証」を通ったものだけを使う。
"""
import json
import re
from pathlib import Path

from . import bot, config, db, drafts, regs

HANDOFF = re.compile(r"合否|合格|不合格|内定|結果|年収|給与|給料|条件交渉|オファー|落ち|採用されますか")
EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def recruit_dir():
    real = config.DATA / "recruit"
    return real if any(real.glob("*.md")) else config.DATA / "sample_recruit"


def reply_body(app, docs, con):
    text = f"{app['subject']}\n{app['body']}"
    lines = [f"# 応募者への返信（下書き）: {app['id']}", "",
             f"{app.get('position', '')}へのご応募ありがとうございます。応募を受け付けました。", ""]
    if HANDOFF.search(text):
        lines += ["選考結果・条件に関するお問い合わせは、担当者より改めてご連絡します。", ""]
    else:
        r = bot.answer(text, docs, None, con)
        if r["status"] == "answered":
            c = r["citations"][0]
            lines += [f"お問い合わせの件: {c['quote']}。（{c['doc'].split('（')[0]} {c['article']}）", ""]
        else:
            lines += ["お問い合わせの内容は、担当者より改めてご連絡します。", ""]
    slots = config.settings().get("interview_slots", [])
    if slots and not HANDOFF.search(text):  # 結果・条件の問い合わせには日程候補を出さない
        lines += ["面接日程の候補: " + " ／ ".join(slots), "ご都合のよい日時をご返信ください。", ""]
    lines += ["※このメールは応募の受付確認です。選考結果をお知らせするものではありません。", f"採用担当: {config.settings()['contact']}"]
    return "\n".join(lines) + "\n"


def reply_all(file, con, docs_dir=None):
    docs = regs.load(docs_dir or recruit_dir())
    made = []
    for line in Path(file).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        app = json.loads(line)
        if not EMAIL.match(app.get("email", "")):
            continue  # 宛先が不正な応募は作成しない
        key = f"recruit:{app['id']}"
        if con.execute("SELECT 1 FROM drafts WHERE params LIKE ?", (f'%"key": "{key}"%',)).fetchone():
            continue
        made.append(drafts.insert("recruit_reply", {"app_id": app["id"], "to": app["email"], "key": key}, reply_body(app, docs, con), "template", con))
    return made
