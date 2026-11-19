"""規程Bot: 規程だけを根拠に回答し、引用は原文との照合をコードで強制する。

status: answered | no_record | refused
LLM 出力は提案に過ぎず、引用検証に失敗した回答は破棄して「記載なし」にする。
"""
import json
import re

from . import config, db, guard, llm, pii, regs

SYSTEM = """あなたは社内規程の問い合わせアシスタントです。
【役割】社員の質問に、与えられた社内規程だけを根拠に答える。
【前提】回答は規程に記載された内容に限り、法令や一般論で補わない。
【禁止】規程にないことを推測しない。個人の給与・評価・懲戒・健康情報には答えない。法的判断をしない。
【出力】JSONのみ:
{"answerable": true/false, "conclusion": "結論を1文", "citations": [{"doc": "規程名", "article": "第N条", "quote": "条文本文からの原文そのままの引用"}], "notes": "注意点(例外・手続)"}
規程に答えが無い場合は {"answerable": false} とする。引用は一字一句変えないこと。"""

_STOP = ["について", "でしょうか", "ですか", "ますか", "教えて", "ください", "どのくらい", "いくら",
         "ありますか", "あります", "できますか", "です", "ます", "される", "され", "する", "できる", "取れ", "行われ", "必要", "まで", "から", "何", "いつ", "どこ", "誰", "は", "が", "を", "に", "の", "で", "と", "も", "か"]


def _bigrams(s):
    s = regs.norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1) if "|" not in s[i:i + 2]}


_SYNONYMS = [("残業", "時間外労働"), ("年次有給休暇", "有給"), ("有給休暇", "有給"), ("有給", "年次有給休暇")]


def _query_bigrams(q):
    for a, b in _SYNONYMS:
        q = q.replace(a, b)
    q = re.sub(r"[？?。、,.!！「」（）()]", "|", q)
    for w in sorted(_STOP, key=len, reverse=True):
        q = q.replace(w, "|")
    return _bigrams(q)


def mock_answer(question, docs):
    """キー無しでも動く簡易検索。希少な2文字列の一致で条文を選び、その1文を引用する。"""
    qb = _query_bigrams(question)
    arts = [(d, a, _bigrams(a["title"] + a["body"])) for d in docs for a in d["articles"]]
    df = {}
    for _, _, bg in arts:
        for b in bg:
            df[b] = df.get(b, 0) + 1
    best = None
    for d, a, bg in arts:
        hit = qb & bg
        score = sum(1 / df[b] for b in hit)
        if not best or score > best[0]:
            best = (score, d, a, hit)
    hit_n = len(best[3]) if best else 0
    enough = hit_n == len(qb) if len(qb) <= 2 else (hit_n >= 2 and hit_n / len(qb) >= 0.4)
    if not best or not qb or hit_n < 1 or not enough:
        return {"answerable": False}
    _, d, a, hit = best
    sents = [s.strip() for s in re.split(r"[。\n]", a["body"]) if s.strip()]
    sent = max(sents, key=lambda s: len(_bigrams(s) & qb))
    return {"answerable": True, "conclusion": sent + "。",
            "citations": [{"doc": d["name"], "article": a["no"], "quote": sent}],
            "notes": "例外や手続の詳細は規程全文でご確認ください。"}


def claude_answer(question, docs):
    user = f"【社内規程】\n{regs.as_context(docs)}\n\n【質問】\n{question}"
    return llm.complete_json(SYSTEM, user)


def _default_llm(question, docs):
    if llm.available():
        try:
            return claude_answer(question, docs), "claude"
        except Exception:
            return mock_answer(question, docs), "mock(fallback)"
    return mock_answer(question, docs), "mock"


def _verify(raw, docs):
    cites = raw.get("citations") or []
    if not raw.get("answerable") or not cites or not raw.get("conclusion"):
        return None, "規程に該当する記載が見つかりません"
    for c in cites:
        if not regs.verify_quote(docs, c.get("doc", ""), c.get("article", ""), c.get("quote", "")):
            return None, "引用が規程原文と一致しないため回答を破棄"
    return raw, ""


def _render(raw, docs, contact):
    lines = [f"結論: {raw['conclusion']}", "", "根拠:"]
    for c in raw["citations"]:
        lines.append(f"  {c['doc']} {c['article']}「{c['quote']}」")
    if raw.get("notes"):
        lines += ["", f"注意点: {raw['notes']}"]
    lines += ["", f"確認先: {contact}", "規程版: " + " / ".join(f"{d['name']} {d['version']}" for d in docs)]
    return "\n".join(lines)


def answer(question, docs=None, llm_fn=None, con=None):
    docs = docs or regs.load()
    cfg = config.settings()
    contact = cfg["contact"]
    masked, found = pii.mask(question)
    versions = {d["name"]: d["version"] for d in docs}
    engine, reason, cites = "-", "", []

    refuse = guard.check(question)
    if refuse:
        status, reason = "refused", refuse
        text = f"この内容にはお答えできません（{refuse}）。{contact}へご相談ください。"
    else:
        raw, engine = (llm_fn(masked, docs), "custom") if llm_fn else _default_llm(masked, docs)
        ok, reason = _verify(raw, docs)
        if ok:
            status, cites = "answered", ok["citations"]
            text = _render(ok, docs, contact)
        else:
            status = "no_record"
            text = f"規程に記載がありません。{contact}へご確認ください。"
    if found:
        text += f"\n\n※質問に個人情報（{'・'.join(found)}）が含まれていました。入力を控えてください（ログにはマスクして保存）。"

    own = con is None
    con = con or db.connect()
    con.execute("INSERT INTO qa_log(question,status,reason,answer,citations,versions,engine,pii) VALUES(?,?,?,?,?,?,?,?)",
                (masked, status, reason, text, json.dumps(cites, ensure_ascii=False),
                 json.dumps(versions, ensure_ascii=False), engine, ",".join(found)))
    con.commit()
    if own:
        con.close()
    return {"status": status, "reason": reason, "text": text, "citations": cites, "engine": engine, "pii": found}
