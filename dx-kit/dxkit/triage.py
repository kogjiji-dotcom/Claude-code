"""問い合わせの分類 → ナレッジ根拠付き返信案 → 自動送信可否 or 人間承認キュー。

安全設計: LLM の出力は「提案」に過ぎない。最終的な自動/人間の判定は
config の決定論的ルール（キーワード・カテゴリ・信頼度・根拠有無）が行う。
"""
from . import audit, kb, llm

CATS = ["faq", "billing", "refund", "bug", "complaint", "legal", "sales", "general"]

SYSTEM = (
    "あなたは企業のカスタマーサポート担当です。問い合わせを分類し、"
    "【ナレッジ】に書かれた内容だけを根拠に丁寧な日本語の返信案を作ります。"
    "ナレッジに無い事は約束・推測しないこと。"
    f'JSONのみで返答: {{"category": one of {CATS}, "confidence": 0-1, "draft": "返信案"}}'
)

_RULES = [  # モック用の簡易分類（キー無しでも動作確認できるように）
    ("legal", ["弁護士", "訴訟", "個人情報", "漏洩"]),
    ("complaint", ["不満", "最悪", "クレーム", "対応が"]),
    ("refund", ["返金", "解約"]),
    ("bug", ["バグ", "エラー", "真っ白", "動かない"]),
    ("sales", ["見積", "導入", "デモ"]),
]


def _mock(text, hits):
    for cat, kws in _RULES:
        if any(k in text for k in kws):
            return {"category": cat, "confidence": 0.9, "draft": "お問い合わせありがとうございます。担当部署より改めてご連絡いたします。"}
    if hits:
        return {"category": "faq", "confidence": min(0.95, 0.5 + hits[0]["score"]),
                "draft": f"お問い合わせありがとうございます。\n{hits[0]['body']}\n他にご不明点があればお知らせください。"}
    return {"category": "general", "confidence": 0.3, "draft": ""}


def decide(cfg, text, result, hits):
    """決定論的ゲート。戻り値: (action, reason)"""
    cat = result["category"]
    ar = cfg["auto_reply"]
    if cat in cfg["always_escalate_categories"]:
        return "escalate", f"カテゴリ {cat} は常に人間対応"
    if any(k in text for k in cfg["escalation_keywords"]):
        return "escalate", "エスカレーションキーワード検出"
    if not ar["enabled"] or cat not in ar["auto_categories"]:
        return "review", "自動返信対象外カテゴリ"
    if ar["require_kb_grounding"] and not hits:
        return "review", "ナレッジ根拠なし"
    if result["confidence"] < ar["min_confidence"]:
        return "review", f"信頼度 {result['confidence']:.2f} < {ar['min_confidence']}"
    return "auto", "低リスク・根拠あり・高信頼度"


def triage(cfg, inquiry, entries):
    text = f"{inquiry['subject']}\n{inquiry['body']}"
    hits = kb.search(text, entries)
    try:
        if not llm.available():
            raise RuntimeError("no key")
        ctx = "\n".join(f"- {h['title']}: {h['body']}" for h in hits) or "（該当なし）"
        result = llm.complete_json(SYSTEM, f"【ナレッジ】\n{ctx}\n\n【問い合わせ】\n{text}", cfg["model"])
        if result.get("category") not in CATS:
            raise ValueError("bad category")
        engine = "claude"
    except Exception:
        result, engine = _mock(text, hits), "mock"
    action, reason = decide(cfg, text, result, hits)
    out = {
        "id": inquiry["id"], "to": inquiry["from"], "category": result["category"],
        "confidence": result["confidence"], "action": action, "reason": reason,
        "route": cfg["routes"].get(result["category"], "support"),
        "draft": result.get("draft", ""), "kb": [h["title"] for h in hits], "engine": engine,
    }
    audit.record("triage", **{k: out[k] for k in ("id", "category", "action", "reason", "engine")})
    return out
