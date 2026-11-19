"""Claude API アダプタ（標準ライブラリのみ）。キー未設定なら available() が False。"""
import json
import os
import urllib.request

from . import config

API = "https://api.anthropic.com/v1/messages"


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _call(system, user, max_tokens):
    body = json.dumps({"model": config.model(), "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(API, body, {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["content"][0]["text"]


def complete_text(system, user, max_tokens=1500):
    return _call(system, user, max_tokens)


def complete_json(system, user, max_tokens=1200):
    text = _call(system, user, max_tokens)
    return json.loads(text[text.index("{"): text.rindex("}") + 1])
