"""人事評価の「根拠整理」と「コメント下書き」。点数・ランク・順位・処遇の推奨は行わない。

評価の判断と最終コメントは評価者（人）が行う。システムは次の3つだけ行う:
  1. 事実の集計（件数・時間・指標の変化）= コードで計算。AIは数値を作らない
  2. 日報の引用つき整理 = 引用が日報原文に実在することをコードで検証
  3. 評価コメントの下書き = 点数等を含む場合・要配慮情報を含む場合は承認不可
入力データは社員IDで仮名化されたローカルファイルのみ（data/eval/、Git管理外）。
"""
import json
import re
from pathlib import Path

from . import config, db, drafts, llm, pii

SENSITIVE = re.compile(r"病|通院|体調|入院|手術|うつ|障害|妊娠|出産|育休|産休|介護|家族|離婚|子供|子ども|宗教|国籍|年齢")
BAD_BODY = [
    ("点数・ランク・評価区分・順位", re.compile(r"\d+(?:\.\d+)?\s*点|[SABCDE]\s*評価|評価\s*[SABCDE](?![a-z])|[1-5１-５]\s*段階|ランク|順位|偏差値|ランキング|上位\d|下位\d")),
    ("処遇・人事措置の推奨", re.compile(r"(?:昇給|昇格|降格|降給|減給|賞与額|解雇|懲戒|雇止め|退職勧奨|異動).{0,6}(?:すべき|させる|が妥当|を推奨|に値|相当|適当)")),
    ("他の社員との比較", re.compile(r"他の社員|他社員|同僚より|同期より|平均より|比べて|他者と比較")),
]
CATS = [
    ("成果", re.compile(r"完了|達成|リリース|納品|解決|受注|削減|成功")),
    ("改善・提案", re.compile(r"改善|提案|効率化|自動化|見直し|テンプレート")),
    ("育成・共有", re.compile(r"教え|指導|説明|共有|レビューし|サポート|同行|勉強会|研修|フィードバック|OJT")),
    ("課題対応", re.compile(r"課題|不具合|トラブル|遅延")),
]


def _scan_text(body):
    """検査対象 = AI生成部分と評価者の記入。システムの固定注意書き（先頭の引用行・第4章・記入例）は除く。"""
    body = re.sub(r"## 4\..*?(?=## 5\.|\Z)", "", body, flags=re.S)
    body = body.replace("（評価者が記入。点数・ランクは記載しない）", "")
    return "\n".join(l for l in body.splitlines() if not l.startswith("> "))


def flags(body):
    """評価文書の承認前チェック（drafts.check_flags から呼ばれる）。"""
    text = _scan_text(body)
    out = [f"評価文書に使えない表現: {label}" for label, rx in BAD_BODY if rx.search(text)]
    if SENSITIVE.search(text):
        out.append("要配慮情報・属性に関する語が含まれています（評価に使えません）")
    return out


def _jsonl(p):
    p = Path(p)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def data_dir():
    real = config.DATA / "eval"
    return real if (real / "daily_reports.jsonl").exists() else config.DATA / "sample_eval"


def load(dir_=None):
    d = Path(dir_) if dir_ else data_dir()
    return {k: _jsonl(d / f"{k}.jsonl") for k in ("daily_reports", "mentoring", "outcomes", "oneonone")}


def criteria():
    return json.loads((config.DATA / "eval_criteria.json").read_text(encoding="utf-8"))


def _in(date, period):
    a, b = period
    return a <= date[:7] <= b


def parse_period(s):
    a, _, b = s.partition(":")
    if not re.fullmatch(r"\d{4}-\d{2}", a) or not re.fullmatch(r"\d{4}-\d{2}", b or a):
        raise ValueError("期間は 2026-04:2026-09 の形式で指定してください")
    return a, b or a


def _delta(o):
    d = o["end"] - o["start"]
    pct = f"{d / o['start'] * 100:+.1f}%" if o["start"] else "算出不可"
    return {**o, "delta": d, "pct": pct}


def facts(emp, period, data):
    reports = [r for r in data["daily_reports"] if r["employee"] == emp and _in(r["date"], period)]
    sess = [m for m in data["mentoring"] if m["mentor"] == emp and _in(m["date"], period)]
    mentees = sorted({m["mentee"] for m in sess})
    per_mentee = []
    for me in mentees:
        ms = [m for m in sess if m["mentee"] == me]
        outs = [_delta(o) for o in data["outcomes"] if o["employee"] == me and _in(o["to"], period)]
        per_mentee.append({"mentee": me, "sessions": len(ms), "hours": sum(m["hours"] for m in ms), "outcomes": outs})
    months = {}
    for r in reports:
        months[r["date"][:7]] = months.get(r["date"][:7], 0) + 1
    return {
        "reports": len(reports), "months": dict(sorted(months.items())), "sessions": len(sess),
        "hours": sum(m["hours"] for m in sess), "mentees": per_mentee,
        "own": [_delta(o) for o in data["outcomes"] if o["employee"] == emp and _in(o["to"], period)],
    }


def clean_reports(emp, period, data):
    """要配慮情報を含む文を除外し、個人情報をマスクする。AIへ渡す前の必須処理。"""
    out, removed = [], 0
    for r in data["daily_reports"]:
        if r["employee"] != emp or not _in(r["date"], period):
            continue
        keep = []
        for sent in [x for x in re.split(r"(?<=。)", r["text"]) if x.strip()]:
            if SENSITIVE.search(sent):
                removed += 1
            else:
                keep.append(pii.mask(sent)[0])
        out.append({"date": r["date"], "text": "".join(keep)})
    return out, removed


def _mock_highlights(reports):
    found = {c: [] for c, _ in CATS}
    for r in reports:
        for sent in [x.strip() for x in re.split(r"(?<=。)", r["text"]) if x.strip()]:
            for cat, rx in CATS:
                if rx.search(sent):
                    found[cat].append({"date": r["date"], "category": cat, "quote": sent.rstrip("。")})
                    break
    out = []
    for items in found.values():
        out += items[:1] + items[len(items) // 2:len(items) // 2 + 1] + items[-1:] if len(items) > 2 else items
    seen, uniq = set(), []
    for h in out:
        k = (h["date"], h["quote"])
        if k not in seen:
            seen.add(k); uniq.append(h)
    return sorted(uniq, key=lambda h: h["date"])


SYSTEM = """あなたは人事評価者を補助するアシスタントです。評価の判断はしません。
入力は、仮名化・要配慮情報の除外済みの日報です。次のJSONのみ返してください:
{"highlights":[{"date":"YYYY-MM-DD","category":"成果|改善・提案|育成・共有|課題対応","quote":"日報原文からそのまま引用"}]}
- 引用は日報の原文を一字一句変えずに抜き出す（最大8件、期間全体から偏りなく）
- 点数・ランク・順位・処遇の提案・他者との比較・要配慮情報への言及はしない"""


def highlights(reports):
    """(ハイライト, 検証で捨てた件数, engine)。引用が日報原文に実在しなければ破棄する。"""
    if llm.available():
        try:
            raw = llm.complete_json(SYSTEM, json.dumps(reports, ensure_ascii=False))["highlights"]
            by = {r["date"]: r["text"] for r in reports}
            ok = [h for h in raw if h.get("quote") and h["quote"] in by.get(h.get("date"), "")]
            return ok, len(raw) - len(ok), "claude"
        except Exception:
            pass
    return _mock_highlights(reports), 0, "mock"


def _yen(o):
    return f"{o['metric']}: {o['start']}→{o['end']}{o['unit']}（{o['delta']:+g}{o['unit']}／{o['pct']}）"


def render(emp, period, f, hl, removed, dropped, crit):
    a, b = period
    L = [f"# 評価根拠シート（下書き）: {emp} / {a}〜{b}", "",
         "> 点数・ランク・評価区分・順位は付けません。評価の判断と最終コメントは評価者が行います。",
         "> このシートは本人への説明時に開示できる内容のみで構成します。", ""]
    L += ["## 1. 事実（システムが集計。AIは数値を作っていません）", "",
          f"- 日報: {f['reports']}件（月別: " + "、".join(f"{m} {n}件" for m, n in f["months"].items()) + "）",
          "  ※日報の件数・文量の多少は評価に使わないでください",
          f"- 育成: {f['sessions']}回／合計{f['hours']:g}時間／育成相手{len(f['mentees'])}名", ""]
    if f["own"]:
        L += ["本人の成果指標:"] + [f"- {_yen(o)}" for o in f["own"]] + [""]
    if f["mentees"]:
        L += ["育成相手の成果指標の変化:"]
        for m in f["mentees"]:
            head = f"- {m['mentee']}（育成{m['sessions']}回／{m['hours']:g}時間）"
            L += [head] + [f"  - {_yen(o)}" for o in m["outcomes"]] if m["outcomes"] else [head + "：指標の記録なし"]
        L += ["  ※指標の良し悪しの方向（増加が良いか等）と、育成との関係は評価者が判断してください。成果の伸びには本人の努力や他の要因も含まれ、因果とはみなせません", ""]
    L += ["## 2. 日報から見える取り組み（原文引用）", ""]
    L += [f"- [{h['date']}]【{h['category']}】「{h['quote']}」" for h in hl] or ["- 該当する記載がありません"]
    L += ["", "## 3. 評価コメント案（下書き）", ""]
    ax = {a_["name"]: a_["desc"] for a_ in crit["axes"]}
    own = "；".join(_yen(o) for o in f["own"]) or "指標の記録なし"
    L += [f"**{'成果'}**（{ax['成果']}）", f"- 本人の成果指標は {own}。日報では成果・達成に関する記載が{sum(h['category'] == '成果' for h in hl)}件あります。内容と難易度を評価者が確認してください。", ""]
    ment = "、".join(f"{m['mentee']}（{'・'.join(_yen(o) for o in m['outcomes']) or '指標なし'}）" for m in f["mentees"]) or "育成相手なし"
    L += [f"**育成・貢献**（{ax['育成・貢献']}）",
          f"- 期間中に育成{f['sessions']}回（合計{f['hours']:g}時間）、育成相手は{len(f['mentees'])}名です。相手の指標の変化: {ment}。",
          "- 件数が少ない場合、傾向は判断できません。育成の質は1on1の内容等も踏まえて評価者が判断してください。", ""]
    n = lambda c: sum(h["category"] == c for h in hl)
    L += [f"**日々の取り組み**（{ax['日々の取り組み']}）",
          f"- 日報には、改善・提案{n('改善・提案')}件、育成・共有{n('育成・共有')}件、課題対応{n('課題対応')}件の記載があります（引用は第2章）。", "",
          "## 4. 評価者への確認事項（システムからの注意）", ""]
    L += [f"- 要配慮情報（健康・家庭・休職等）に関わる記載 {removed}件を、評価に使わないよう除外しました" if removed else "- 要配慮情報の除外対象: なし"]
    if dropped:
        L += [f"- AIの引用のうち、日報原文と一致しない{dropped}件を破棄しました"]
    if f["reports"] < 6:
        L += ["- 日報が少ないため、記載のない期間を低く評価しないでください（評価不能な部分は人が別の根拠で確認）"]
    L += ["- 直近の出来事に偏っていないか、月別の日報件数と引用の日付を確認してください",
          "- 本シートは他の社員との比較に使わないでください", "",
          "## 5. 評価者の最終コメント", "", "【要入力】（評価者が記入。点数・ランクは記載しない）", ""]
    return "\n".join(L)


def build(emp, period_str, evaluator, con, data=None):
    if not evaluator.strip():
        raise ValueError("評価者名が必要です（閲覧記録に残ります）")
    period = parse_period(period_str)
    data = data or load()
    f = facts(emp, period, data)
    if f["reports"] == 0 and f["sessions"] == 0 and not f["own"]:
        raise ValueError(f"{emp} の {period_str} のデータがありません")
    reports, removed = clean_reports(emp, period, data)
    hl, dropped, engine = highlights(reports)
    body = render(emp, period, f, hl, removed, dropped, criteria())
    did = drafts.insert("evaluation_evidence", {"employee": emp, "period": period_str}, body, engine, con)
    con.execute("INSERT INTO eval_access(evaluator,employee,period,draft_id) VALUES(?,?,?,?)", (evaluator, emp, period_str, did))
    con.commit()
    return did


def build_prep(emp, period_str, by, con, data=None):
    """1on1の準備シート。評価の場ではなく対話のための材料。点数・評価は含まない。"""
    if not by.strip():
        raise ValueError("作成者名が必要です（閲覧記録に残ります）")
    period = parse_period(period_str)
    data = data or load()
    reports, removed = clean_reports(emp, period, data)
    if not reports:
        raise ValueError(f"{emp} の {period_str} の日報がありません")
    hl, dropped, engine = highlights(reports)
    prev = sorted((o for o in data.get("oneonone", []) if o["employee"] == emp), key=lambda o: o["date"])
    open_actions = [(o["date"], a["text"]) for o in prev for a in o["actions"] if not a["done"]]
    n = lambda c: sum(h["category"] == c for h in hl)
    L = [f"# 1on1 準備シート（下書き）: {emp} / {period[0]}〜{period[1]}", "",
         "> 評価の場ではなく、本人の話を聞く対話のための材料です。点数・評価は含みません。", ""]
    L += ["## 1. 前回までの約束事（未完了）", ""]
    L += [f"- [{d}] {t}" for d, t in open_actions] or ["- 未完了の約束事はありません"]
    L += ["", "## 2. 最近の取り組み（日報の原文引用）", ""]
    L += [f"- [{h['date']}]【{h['category']}】「{h['quote']}」" for h in hl[-6:]] or ["- 該当する記載がありません"]
    L += ["", "## 3. 話題の候補（下書き）", ""]
    topics = ["困っていること、支援してほしいことはありますか", "今後取り組みたいこと、伸ばしたいことは何ですか"]
    if n("課題対応"):
        topics.insert(0, "課題対応（日報の引用を参照）の状況と、進めにくい点を聞く")
    if n("育成・共有"):
        topics.insert(0, "人を教える・共有する取り組みの手応えと負担を聞く")
    if n("改善・提案"):
        topics.insert(0, "改善提案の進め方と、次に必要な支援を聞く")
    L += [f"- {t}" for t in topics]
    L += ["", "## 4. 面談者への確認事項（システムからの注意）", "",
          f"- 要配慮情報（健康・家庭・休職等）に関わる記載 {removed}件を除外しています。本人が自ら話す場合は、受け止めたうえで評価には使わないでください" if removed else "- 要配慮情報の除外対象: なし",
          "- 約束事は、期限と担当を面談の最後に本人と確認してください"]
    if dropped:
        L += [f"- AIの引用のうち、日報原文と一致しない{dropped}件を破棄しました"]
    L += ["", "## 5. 面談メモ", "", "【要入力】（面談後に記入。なければ「なし」）", ""]
    body = "\n".join(L)
    did = drafts.insert("evaluation_oneonone", {"employee": emp, "period": period_str}, body, engine, con)
    con.execute("INSERT INTO eval_access(evaluator,employee,period,draft_id) VALUES(?,?,?,?)", (by, emp, period_str, did))
    con.commit()
    return did
