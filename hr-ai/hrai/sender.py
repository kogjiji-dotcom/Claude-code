"""承認済みの下書きの送信。文面の確認は人、送信はシステム。

送信できる条件（すべて満たすこと）:
  承認済み / 未送信 / 承認時から本文が不変（ハッシュ一致）/ フラグ無し / 宛先が許可リスト内
届出（社会保険・雇用保険・労基署など）の提出機能は存在しない。届出は人が行う。
"""
import hashlib
import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage

from . import config, drafts


def _slack(to, subject, body):
    url = os.environ["HRAI_SLACK_WEBHOOK"]
    req = urllib.request.Request(url, json.dumps({"text": f"*{subject}*\n{body}"}).encode(),
                                 {"content-type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def _email(to, subject, body):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.environ["HRAI_MAIL_FROM"], to, subject
    msg.set_content(body)
    with smtplib.SMTP(os.environ["HRAI_SMTP_HOST"], int(os.environ.get("HRAI_SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(os.environ["HRAI_SMTP_USER"], os.environ["HRAI_SMTP_PASSWORD"])
        s.send_message(msg)


TRANSPORTS = {"slack": _slack, "email": _email}


def _check(r, via, to):
    if r["kind"].startswith("evaluation"):
        raise ValueError("評価関連の文書は個人情報のため送信できません（人が直接取り扱う）")
    if r["status"] == "sent":
        raise ValueError("送信済みです（二重送信は不可）")
    if r["status"] != "approved":
        raise ValueError(f"状態が {r['status']} のため送信できません。人の承認が必要です")
    if not r["body_hash"] or drafts.body_hash(r["body"]) != r["body_hash"]:
        raise ValueError("承認後に本文が変更されています。再承認してください")
    flags = drafts.check_flags(r["body"], r["kind"])
    if flags:
        raise ValueError("送信不可: " + " / ".join(flags))
    if via not in TRANSPORTS:
        raise ValueError(f"送信手段は {', '.join(TRANSPORTS)} のいずれか")
    params = json.loads(r["params"] or "{}")
    if r["kind"] == "recruit_reply":  # 応募者宛: 応募メールの送信元アドレス以外には送らない（ドメイン許可リストの対象外）
        if via != "email" or not to or to != params.get("to"):
            raise ValueError("応募者への返信は、応募者のアドレス宛にメールでのみ送信できます")
    elif via == "email":
        domains = config.settings().get("allowed_email_domains", [])
        if not to or "@" not in to or to.rsplit("@", 1)[1].lower() not in [d.lower() for d in domains]:
            raise ValueError(f"宛先は data/settings.json の allowed_email_domains {domains} 内のアドレスのみ")


def send(did, via, to, con, dry_run=False, transport=None):
    r = drafts.get(did, con)
    to = to or json.loads(r["params"] or "{}").get("to", "")  # 宛先省略時は下書き作成時の宛先
    _check(r, via, to)
    subject = f"[{drafts.KINDS[r['kind']][0]}] {r['body'].splitlines()[0].lstrip('# ').strip()}"
    if dry_run:
        return {"dry_run": True, "via": via, "to": to, "subject": subject}
    (transport or TRANSPORTS[via])(to, subject, r["body"])
    con.execute("UPDATE drafts SET status='sent', sent_ts=CURRENT_TIMESTAMP, sent_via=?, sent_to=? WHERE id=?", (via, to or "", did))
    con.commit()
    return {"dry_run": False, "via": via, "to": to, "subject": subject}
