"""Slack 連携（標準ライブラリのみ）。

  /hr 質問   … 規程Botに質問（回答は質問者だけに見える ephemeral）
  承認ボタン … 承認待ちの下書きを、許可された承認者だけが承認/却下（送信は別操作）
セキュリティ: Slack署名の検証（HMAC-SHA256・5分以内）。承認者は data/settings.json の slack.approvers に登録した
Slackユーザーのみ。評価関連の下書きはSlackに出さず、ボタンでも操作できない。
必要な環境変数: 受信の検証用（ENV_VERIFY）、承認依頼の投稿用（ENV_POST）。値はコードに書かない。
"""
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import bot, config, db, drafts, llm

ENV_VERIFY = "SLACK_SIGNING_SECRET"  # 環境変数の名前（値ではない）
ENV_POST = "SLACK_BOT_TOKEN"  # 環境変数の名前（値ではない）


def verify_signature(signing_key, timestamp, body, signature, now=None):
    try:
        if abs((now or time.time()) - int(timestamp)) > 300:  # リプレイ攻撃対策
            return False
    except (TypeError, ValueError):
        return False
    base = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(signing_key.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def handle_command(form, con=None):
    text = (form.get("text") or "").strip()
    if not text:
        return {"response_type": "ephemeral", "text": "使い方: `/hr 有給休暇は半日で取れますか？`（個人情報は入力しないでください）"}
    return {"response_type": "ephemeral", "text": bot.answer(text, con=con)["text"]}


def approvers():
    return config.settings().get("slack", {}).get("approvers", {})


def handle_interaction(payload, con):
    """承認/却下ボタン。承認者として登録されたユーザーだけが操作できる。"""
    name = approvers().get(payload["user"]["id"])
    if not name:
        return {"response_type": "ephemeral", "replace_original": False, "text": "承認権限がありません。"}
    act = payload["actions"][0]
    did = int(act["value"])
    try:
        row = drafts.get(did, con)
        if row["kind"].startswith("evaluation"):
            return {"response_type": "ephemeral", "replace_original": False, "text": "評価関連の文書はSlackから操作できません。"}
        if act["action_id"] == "approve":
            drafts.approve(did, name, con)
            msg = f"✅ 下書き #{did} を {name} が承認しました（送信は別途 `draft send` で行います）"
        else:
            drafts.reject(did, name, "Slackから却下", con)
            msg = f"🚫 下書き #{did} を {name} が却下しました"
    except (ValueError, KeyError) as ex:
        return {"response_type": "ephemeral", "replace_original": False, "text": f"できませんでした: {ex}"}
    return {"replace_original": True, "text": msg}


def pending_blocks(con, limit=10):
    out = []
    for r in con.execute("SELECT id, kind, body, flags FROM drafts WHERE status='pending' ORDER BY id LIMIT 200"):
        if r["kind"].startswith("evaluation"):
            continue
        flags = json.loads(r["flags"] or "[]")
        text = f"*#{r['id']} {drafts.KINDS[r['kind']][0]}*\n```{r['body'][:900]}```" + (f"\n⚠️ 承認不可: {' / '.join(flags)}" if flags else "")
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
        if not flags:
            blocks.append({"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "承認"}, "style": "primary", "action_id": "approve", "value": str(r["id"])},
                {"type": "button", "text": {"type": "plain_text", "text": "却下"}, "style": "danger", "action_id": "reject", "value": str(r["id"])}]})
        out.append(blocks)
        if len(out) >= limit:
            break
    return out


def notify(channel, con, post=None):
    """承認待ちの下書きを承認チャンネルへ投稿する。"""
    def _post(payload):
        req = urllib.request.Request("https://slack.com/api/chat.postMessage", json.dumps(payload).encode(),
                                     {"content-type": "application/json", "authorization": "Bearer " + os.environ[ENV_POST]})
        return json.load(urllib.request.urlopen(req, timeout=30))
    n = 0
    for blocks in pending_blocks(con):
        (post or _post)({"channel": channel, "blocks": blocks, "text": "承認待ちの下書き"})
        n += 1
    return n


def _respond_later(url, payload):
    if not url.startswith("https://hooks.slack.com/"):  # 投稿先はSlackのみ
        return
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"content-type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 質問文をログへ出さない
        pass

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        verifier = os.environ.get(ENV_VERIFY, "")
        if not verifier or not verify_signature(verifier, self.headers.get("x-slack-request-timestamp"), body, self.headers.get("x-slack-signature")):
            return self._send(401, {"error": "invalid signature"})
        form = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode()).items()}
        con = db.connect()
        try:
            if self.path == "/slack/command":
                if llm.available() and form.get("response_url"):  # Slackの3秒制限: 先に受付を返し、回答は後から投稿
                    threading.Thread(target=lambda: _respond_later(form["response_url"], handle_command(form)), daemon=True).start()
                    return self._send(200, {"response_type": "ephemeral", "text": "確認しています…"})
                return self._send(200, handle_command(form, con))
            if self.path == "/slack/interact":
                return self._send(200, handle_interaction(json.loads(form["payload"]), con))
            return self._send(404, {"error": "not found"})
        finally:
            con.close()


def serve(port=3000):
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
