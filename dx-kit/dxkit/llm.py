"""LLM アダプタ。ANTHROPIC_API_KEY があれば Claude、無ければ規則ベースのモックで動作。"""
import json
import os
import urllib.request

API = "https://api.anthropic.com/v1/messages"


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete_json(system, user, model, max_tokens=800):
    """JSON オブジェクトを返す。失敗時は例外（呼び出し側が人間へフォールバック）。"""
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(API, body, {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        text = json.load(r)["content"][0]["text"]
    return json.loads(text[text.index("{"): text.rindex("}") + 1])
