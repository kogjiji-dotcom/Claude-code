"""下書き → 人が承認 → 保存。AI は下書きまで。送信・提出は行わない。"""
import hashlib
import json
import re
import time
from pathlib import Path

from . import config, db, llm, pii

KINDS = {
    "job_posting": ("求人票", ["title", "duties", "requirements", "conditions"]),
    "interview_questions": ("面接質問案", ["title", "skills"]),
    "notice": ("社内通達", ["subject", "body_points"]),
    "offboarding_checklist": ("退職手続チェックリスト", ["role"]),
    # 以下は専用コマンドでのみ作成（汎用の draft new では作れない）
    "evaluation_evidence": ("評価根拠シート", ["employee", "period"]),
    "evaluation_oneonone": ("1on1準備シート", ["employee", "period"]),
    "attendance_alert": ("勤怠アラート", ["employee", "to"]),
    "onboarding_notice": ("入社のご案内", ["employee", "to"]),
    "onboarding_checklist": ("入社手続きチェックリスト", ["employee", "to"]),
    "onboarding_reminder": ("入社手続きのリマインド", ["employee", "to"]),
    "recruit_reply": ("応募者への返信", ["app_id", "to"]),
}
GENERIC = ["job_posting", "interview_questions", "notice", "offboarding_checklist"]
SYSTEM = """あなたは中小企業の人事担当の文書作成アシスタントです。下書きのみを作成します。
- 性別・年齢・国籍・婚姻状況・容姿など、採用差別につながる属性を条件にしない
- 個人名・個人情報を書かない。不明な項目は「【要入力】」と書く
- 法令の数値や要件を断定して書かない。給与・保険料の計算や届出の代行はしない
- Markdown で簡潔に出力する"""

BANNED = ["男性", "女性", "男子", "女子", "若手","歳以下", "歳まで", "独身", "既婚", "日本人", "国籍", "容姿", "美人", "主婦"]


def _mock(kind, p):
    g = lambda k: p.get(k) or "【要入力】"
    if kind == "job_posting":
        return f"# 求人票（下書き）: {g('title')}\n\n## 仕事内容\n{g('duties')}\n\n## 応募資格\n{g('requirements')}\n\n## 勤務条件\n{g('conditions')}\n\n## 選考フロー\n【要入力】\n"
    if kind == "interview_questions":
        return (f"# 面接質問案（下書き）: {g('title')}\n\n対象スキル: {g('skills')}\n\n"
                "1. これまでの業務で最も成果を出した経験を、役割と工夫を含めて教えてください。\n"
                "2. 対象スキルをどのように身につけ、直近でどう活用しましたか。\n"
                "3. チームで意見が分かれた際、どう進めましたか。\n"
                "4. 入社後に最初の3か月で取り組みたいことは何ですか。\n\n"
                "※全候補者に同じ質問をし、評価は職務に関連する基準のみで行う。\n")
    if kind == "notice":
        return f"# 社内通達（下書き）\n\n件名: {g('subject')}\n\n各位\n\n以下の件についてお知らせします。\n\n{g('body_points')}\n\n問い合わせ先: {config.settings()['contact']}\n"
    items = ["社員証・貸与PC・鍵の返却", "各種アカウントの停止（退職日付）", "業務の引継ぎ資料の作成", "秘密保持の確認（第17条）",
             "【人が専用ソフト/e-Govで実施】社会保険・雇用保険の資格喪失手続", "【人が専用ソフトで実施】最終給与・退職金の計算", "【人が実施】離職票等の交付可否の確認"]
    return f"# 退職手続チェックリスト（下書き）: {g('role')}\n\n" + "\n".join(f"- [ ] {i}" for i in items) + "\n"


def body_hash(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def check_flags(body, kind=None):
    flags = [f"差別につながる可能性のある表現: {w}" for w in BANNED if w in body]
    scrubbed = body.replace(config.settings()["contact"], "")  # 設定済みの社内問い合わせ先は個人情報扱いしない
    if kind and kind.startswith("evaluation"):
        scrubbed = re.sub(r"\[\d{4}-\d{2}-\d{2}\]", "", scrubbed)  # システムが付ける日報の日付引用は生年月日扱いしない
    flags += [f"個人情報パターン: {x}" for x in pii.find(scrubbed) if x != "氏名"]
    if "【要入力】" in body:
        flags.append("未入力項目（【要入力】）が残っています")
    if kind and kind.startswith("evaluation"):
        from . import evaluation  # 評価文書は点数・順位・処遇推奨・要配慮情報を禁止
        flags += evaluation.flags(body)
    return flags


def create(kind, params, con=None):
    if kind not in KINDS:
        raise ValueError(f"kind は {', '.join(KINDS)} のいずれか")
    if kind not in GENERIC:
        raise ValueError("この種別は専用コマンド（review / attendance / onboarding / recruit）で作成してください")
    engine = "mock"
    if llm.available():
        try:
            body = llm.complete_text(SYSTEM, f"種別: {KINDS[kind][0]}\n入力: {json.dumps(params, ensure_ascii=False)}")
            engine = "claude"
        except Exception:
            body = _mock(kind, params)
    else:
        body = _mock(kind, params)
    return insert(kind, params, body, engine, con)


def insert(kind, params, body, engine, con=None):
    own = con is None
    con = con or db.connect()
    cur = con.execute("INSERT INTO drafts(kind,params,body,flags,engine) VALUES(?,?,?,?,?)",
                      (kind, json.dumps(params, ensure_ascii=False), body, json.dumps(check_flags(body, kind), ensure_ascii=False), engine))
    con.commit()
    did = cur.lastrowid
    if own:
        con.close()
    return did


def get(did, con):
    r = con.execute("SELECT * FROM drafts WHERE id=?", (did,)).fetchone()
    if not r:
        raise KeyError(f"下書き {did} が見つかりません")
    return r


def edit(did, body, con):
    r = get(did, con)
    con.execute("UPDATE drafts SET body=?, flags=?, status='pending', body_hash=NULL WHERE id=?",
                (body, json.dumps(check_flags(body, r["kind"]), ensure_ascii=False), did))
    con.commit()


def approve(did, approver, con, out_dir=None):
    """フラグが残っている下書きは承認できない。承認時のみ out/approved/ へ書き出す。"""
    r = get(did, con)
    if not approver.strip():
        raise ValueError("承認者名が必要です")
    if r["status"] != "pending":
        raise ValueError(f"状態が {r['status']} のため承認できません")
    flags = check_flags(r["body"], r["kind"])
    if flags:
        raise ValueError("承認不可: " + " / ".join(flags))
    sub = "evaluations" if r["kind"].startswith("evaluation") else "approved"
    out = Path(out_dir or config.ROOT / "out" / sub)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{did:04d}_{r['kind']}.md"
    path.write_text(r["body"] + f"\n\n---\n承認者: {approver} / 承認日時: {time.strftime('%Y-%m-%d %H:%M')}\n", encoding="utf-8")
    con.execute("UPDATE drafts SET status='approved', approver=?, decided_ts=CURRENT_TIMESTAMP, body_hash=? WHERE id=?",
                (approver, body_hash(r["body"]), did))
    con.commit()
    return path


def reject(did, approver, reason, con):
    get(did, con)
    con.execute("UPDATE drafts SET status='rejected', approver=?, note=?, decided_ts=CURRENT_TIMESTAMP WHERE id=?", (approver, reason, did))
    con.commit()
