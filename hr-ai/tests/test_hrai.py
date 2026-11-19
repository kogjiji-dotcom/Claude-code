import hashlib
import hmac
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hrai import attendance, bot, cli, config, db, drafts, evaluate, evaluation, onboarding, pii, recruit, regs, roi, sender, slack_app  # noqa: E402

DOCS = regs.load(config.DATA / "sample_regulations")
DOC = DOCS[0]["name"]


def fake(raw):
    return lambda q, d: raw


class BotSafety(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(Path(tempfile.mkdtemp()) / "t.db")

    def ask(self, q, llm_fn=None):
        return bot.answer(q, DOCS, llm_fn, self.con)

    def test_fabricated_quote_is_discarded(self):
        r = self.ask("休日は？", fake({"answerable": True, "conclusion": "毎日休みです。",
                     "citations": [{"doc": DOC, "article": "第4条", "quote": "休日は毎日とする"}]}))
        self.assertEqual(r["status"], "no_record")
        self.assertIn("記載がありません", r["text"])

    def test_quote_from_wrong_article_is_discarded(self):
        r = self.ask("休日は？", fake({"answerable": True, "conclusion": "x。",
                     "citations": [{"doc": DOC, "article": "第5条", "quote": "休日は土曜日、日曜日"}]}))
        self.assertEqual(r["status"], "no_record")

    def test_valid_quote_is_accepted_and_shows_version(self):
        r = self.ask("休日は？", fake({"answerable": True, "conclusion": "土日祝です。",
                     "citations": [{"doc": DOC, "article": "第4条", "quote": "休日は土曜日、日曜日、国民の祝日"}]}))
        self.assertEqual(r["status"], "answered")
        self.assertIn("2026-04-01", r["text"])

    def test_personal_questions_refused_without_calling_llm(self):
        def boom(q, d):
            raise AssertionError("LLM must not be called")
        self.assertEqual(self.ask("私の給料はいくらですか", boom)["status"], "refused")

    def test_pii_masked_in_log_and_llm_input(self):
        seen = []
        self.ask("山田さん(taro@example.com, 090-1234-5678)の有給休暇は半日で取れますか？",
                 lambda q, d: (seen.append(q), {"answerable": False})[1])
        row = self.con.execute("SELECT question, pii FROM qa_log").fetchone()
        for leaked in ("taro@example.com", "090-1234-5678"):
            self.assertNotIn(leaked, row["question"])
            self.assertNotIn(leaked, seen[0])
        self.assertIn("メール", row["pii"])

    def test_pii_detect(self):
        self.assertEqual(pii.find("特になし"), [])
        self.assertIn("生年月日", pii.find("1990/04/01生まれ"))


class DraftFlow(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(Path(tempfile.mkdtemp()) / "t.db")
        self.out = Path(tempfile.mkdtemp())

    def test_cannot_approve_with_unfilled_fields(self):
        did = drafts.create("job_posting", {"title": "経理"}, self.con)
        with self.assertRaises(ValueError):
            drafts.approve(did, "総務 太郎", self.con, self.out)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_approve_after_edit_exports_with_approver(self):
        did = drafts.create("job_posting", {"title": "経理", "duties": "経理業務", "requirements": "経験者", "conditions": "週5日"}, self.con)
        drafts.edit(did, drafts.get(did, self.con)["body"].replace("【要入力】", "面接2回"), self.con)
        path = drafts.approve(did, "総務 太郎", self.con, self.out)
        self.assertIn("承認者: 総務 太郎", path.read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):  # 二重承認不可
            drafts.approve(did, "総務 太郎", self.con, self.out)

    def test_discriminatory_wording_blocks_approval(self):
        did = drafts.create("notice", {"subject": "募集", "body_points": "30歳まで・男性のみ"}, self.con)
        self.assertTrue(any("差別" in f for f in drafts.check_flags(drafts.get(did, self.con)["body"])))
        with self.assertRaises(ValueError):
            drafts.approve(did, "総務 太郎", self.con, self.out)

    def test_approver_required(self):
        did = drafts.create("offboarding_checklist", {"role": "営業"}, self.con)
        with self.assertRaises(ValueError):
            drafts.approve(did, "  ", self.con, self.out)

    def test_checklist_leaves_calculations_to_humans(self):
        body = drafts._mock("offboarding_checklist", {"role": "営業"})
        self.assertIn("人が専用ソフト", body)

    def test_roi_counts_only_answered_and_approved(self):
        bot.answer("休日は何曜日ですか", DOCS, None, self.con)
        bot.answer("私の給料はいくらですか", DOCS, None, self.con)
        r = roi.report(self.con)
        self.assertEqual(r["questions"], {"answered": 1, "refused": 1})
        self.assertEqual(r["approved_drafts"], 0)


class Sending(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(Path(tempfile.mkdtemp()) / "t.db")
        self.out = Path(tempfile.mkdtemp())
        self.sent = []
        self.tx = lambda to, subj, body: self.sent.append((to, subj))
        self.did = drafts.create("notice", {"subject": "休業日のお知らせ", "body_points": "12月29日から1月3日は休業です。"}, self.con)

    def approved(self):
        drafts.approve(self.did, "総務 太郎", self.con, self.out)

    def test_unapproved_cannot_be_sent(self):
        with self.assertRaises(ValueError):
            sender.send(self.did, "email", "a@example.com", self.con, transport=self.tx)
        self.assertEqual(self.sent, [])

    def test_approved_is_sent_once(self):
        self.approved()
        sender.send(self.did, "email", "a@example.com", self.con, transport=self.tx)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(drafts.get(self.did, self.con)["status"], "sent")
        with self.assertRaises(ValueError):
            sender.send(self.did, "email", "a@example.com", self.con, transport=self.tx)

    def test_edit_after_approval_blocks_send(self):
        self.approved()
        drafts.edit(self.did, "改ざん後の本文", self.con)
        with self.assertRaises(ValueError):
            sender.send(self.did, "email", "a@example.com", self.con, transport=self.tx)

    def test_hash_mismatch_blocks_send(self):
        self.approved()
        self.con.execute("UPDATE drafts SET body='差し替え' WHERE id=?", (self.did,))
        with self.assertRaises(ValueError):
            sender.send(self.did, "email", "a@example.com", self.con, transport=self.tx)

    def test_recipient_domain_allowlist(self):
        self.approved()
        with self.assertRaises(ValueError):
            sender.send(self.did, "email", "x@evil.test", self.con, transport=self.tx)
        self.assertEqual(self.sent, [])

    def test_dry_run_sends_nothing(self):
        self.approved()
        res = sender.send(self.did, "email", "a@example.com", self.con, dry_run=True, transport=self.tx)
        self.assertTrue(res["dry_run"])
        self.assertEqual(self.sent, [])
        self.assertEqual(drafts.get(self.did, self.con)["status"], "approved")

    def test_no_filing_capability(self):
        self.assertFalse(any(k for k in sender.TRANSPORTS if "e-gov" in k.lower() or "届出" in k))


class Review(unittest.TestCase):
    P = "2026-04:2026-09"

    def setUp(self):
        self.con = db.connect(Path(tempfile.mkdtemp()) / "t.db")
        self.out = Path(tempfile.mkdtemp())

    def sheet(self, emp="E01"):
        did = evaluation.build(emp, self.P, "評価者A", self.con)
        return did, drafts.get(did, self.con)["body"]

    def test_facts_are_computed_by_code(self):
        f = evaluation.facts("E01", evaluation.parse_period(self.P), evaluation.load())
        self.assertEqual((f["sessions"], f["hours"], len(f["mentees"])), (6, 8.0, 2))
        e02 = next(m for m in f["mentees"] if m["mentee"] == "E02")["outcomes"][0]
        self.assertEqual((e02["delta"], e02["pct"]), (18, "+45.0%"))

    def test_sheet_has_no_score_and_excludes_sensitive_and_other_people(self):
        _, body = self.sheet()
        self.assertNotIn("通院", body)          # 要配慮情報は除外
        self.assertNotIn("田中", body)          # 氏名はマスク
        self.assertNotIn("営業資料", body)      # 他の社員(E04)の日報は含まない
        self.assertEqual(evaluation.flags(body), [])

    def test_cannot_approve_until_final_comment_is_written(self):
        did, body = self.sheet()
        self.assertEqual(json.loads(drafts.get(did, self.con)["flags"]), ["未入力項目（【要入力】）が残っています"])
        with self.assertRaisesRegex(ValueError, "未入力"):
            drafts.approve(did, "評価者A", self.con, self.out)

    def test_score_or_ranking_or_sensitive_blocks_approval(self):
        did, body = self.sheet()
        for bad, why in (("総合85点", "点数"), ("S評価とする", "点数"), ("同僚より優秀で昇給すべき", "処遇"), ("育休明けのため配慮", "要配慮")):
            drafts.edit(did, body.replace("【要入力】", bad), self.con)
            with self.assertRaisesRegex(ValueError, why, msg=bad):
                drafts.approve(did, "評価者A", self.con, self.out)

    def test_approved_goes_to_local_dir_and_can_never_be_sent(self):
        did, body = self.sheet()
        drafts.edit(did, body.replace("【要入力】", "育成に力を入れ、相手が伸びた。引き続き期待する。"), self.con)
        path = drafts.approve(did, "評価者A", self.con)
        self.assertIn("evaluations", str(path))
        path.unlink()
        with self.assertRaises(ValueError):
            sender.send(did, "email", "a@example.com", self.con, transport=lambda *a: None)

    def test_access_is_logged_and_evaluator_required(self):
        did, _ = self.sheet()
        row = self.con.execute("SELECT evaluator, employee FROM eval_access WHERE draft_id=?", (did,)).fetchone()
        self.assertEqual((row["evaluator"], row["employee"]), ("評価者A", "E01"))
        with self.assertRaises(ValueError):
            evaluation.build("E01", self.P, " ", self.con)

    def test_fabricated_ai_quotes_are_discarded(self):
        orig = (evaluation.llm.available, evaluation.llm.complete_json)
        evaluation.llm.available = lambda: True
        evaluation.llm.complete_json = lambda sys, user: {"highlights": [
            {"date": "2026-04-08", "category": "成果", "quote": "売上を2倍にした"},
            {"date": "2026-04-08", "category": "改善・提案", "quote": "見積テンプレートを作成し、チームに共有した"}]}
        try:
            r, _ = evaluation.clean_reports("E01", evaluation.parse_period(self.P), evaluation.load())
            hl, dropped, engine = evaluation.highlights(r)
        finally:
            evaluation.llm.available, evaluation.llm.complete_json = orig
        self.assertEqual((len(hl), dropped, engine), (1, 1, "claude"))

    def test_generic_draft_cannot_create_evaluation_and_no_data_errors(self):
        with self.assertRaises(ValueError):
            drafts.create("evaluation_evidence", {}, self.con)
        with self.assertRaises(ValueError):
            evaluation.build("E99", self.P, "評価者A", self.con)


class Features(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(Path(tempfile.mkdtemp()) / "t.db")
        self.sent = []
        self.tx = lambda to, subj, body: self.sent.append(to)

    def approve_send(self, did, to=""):
        drafts.approve(did, "総務 太郎", self.con, Path(tempfile.mkdtemp()))
        return sender.send(did, "email", to, self.con, transport=self.tx)

    # --- 勤怠 ---
    def test_attendance_analysis(self):
        cfg = config.settings()["attendance"]
        rows, directory = attendance.load()
        import datetime as dt
        e02 = attendance.analyze("E02", "2026-10", dt.date(2026, 10, 27), rows, directory["E02"], cfg)
        self.assertEqual([d.isoformat() for d in e02["missing"]], ["2026-10-05", "2026-10-06"])
        self.assertTrue(e02["ot_warn"] and e02["leave_warn"])
        e01 = attendance.analyze("E01", "2026-10", dt.date(2026, 10, 27), rows, directory["E01"], cfg)
        self.assertFalse(e01["missing"] or e01["ot_warn"] or e01["leave_warn"])  # 休日・祝日は未入力扱いにしない
        small = dict(directory["E03"], paid_leave_granted=9)  # 付与日数が基準未満なら有給アラート対象外
        self.assertFalse(attendance.analyze("E03", "2026-10", dt.date(2026, 10, 27), rows, small, cfg)["leave_warn"])

    def test_attendance_alerts_are_drafts_deduped_and_scoped(self):
        made = attendance.check("2026-10", "2026-10-27", self.con)
        self.assertEqual(sorted((m["employee"], m["role"]) for m in made), [("E02", "employee"), ("E02", "manager"), ("E03", "employee"), ("E03", "manager")])
        self.assertEqual(attendance.check("2026-10", "2026-10-27", self.con), [])  # 重複作成しない
        mgr = next(m for m in made if m["employee"] == "E02" and m["role"] == "manager")
        self.assertNotIn("未入力", drafts.get(mgr["id"], self.con)["body"])  # 上長には未入力の通知は送らない
        self.assertTrue(all(drafts.get(m["id"], self.con)["status"] == "pending" for m in made))
        res = self.approve_send(made[0]["id"])
        self.assertEqual(self.sent, ["e02@example.com"])

    # --- 入社手続き ---
    def test_onboarding_flow(self):
        ids = onboarding.start("E10", "2026-11-01", "e10@example.com", self.con)
        self.assertEqual(len(ids), 2)
        with self.assertRaises(ValueError):
            onboarding.start("E10", "2026-11-01", "e10@example.com", self.con)
        rem = onboarding.remind("2026-11-03", self.con)
        self.assertEqual(len(rem), 2)
        self.assertEqual(onboarding.remind("2026-11-03", self.con), [])
        human = [r for r in onboarding.status("E10", self.con) if r["human_only"]]
        self.assertEqual(len(human), 1)
        self.assertIsNone(human[0]["done_ts"])  # 届出は自動で完了にならない
        with self.assertRaises(ValueError):
            onboarding.done("E10", "雇用契約書の返送", " ", self.con)
        onboarding.done("E10", "雇用契約書の返送", "総務 太郎", self.con)
        self.assertEqual(len(onboarding.remind("2026-11-04", self.con)), 2)

    # --- 応募対応 ---
    def test_recruit_replies(self):
        made = recruit.reply_all(config.DATA / "sample_recruit" / "applications.jsonl", self.con)
        self.assertEqual(len(made), 3)
        bodies = [drafts.get(i, self.con)["body"] for i in made]
        self.assertIn("オンライン", bodies[0])
        self.assertIn("11/10 10:00", bodies[0])
        self.assertNotIn("11/10", bodies[2])  # 合否・年収の問い合わせには日程を出さず担当者へ
        self.assertIn("担当者より改めてご連絡", bodies[2])
        self.assertTrue(all("合格" not in b for b in bodies))

    def test_recruit_send_only_to_the_applicant(self):
        did = recruit.reply_all(config.DATA / "sample_recruit" / "applications.jsonl", self.con)[0]
        drafts.approve(did, "総務 太郎", self.con, Path(tempfile.mkdtemp()))
        with self.assertRaises(ValueError):
            sender.send(did, "email", "other@evil.test", self.con, transport=self.tx)
        with self.assertRaises(ValueError):
            sender.send(did, "slack", "", self.con, transport=self.tx)
        sender.send(did, "email", "", self.con, transport=self.tx)  # 宛先省略=応募者のアドレス
        self.assertEqual(self.sent, ["applicant1@mail.test"])

    def test_recruit_skips_invalid_email_and_dupes(self):
        f = Path(tempfile.mkdtemp()) / "a.jsonl"
        f.write_text('{"id":"X","email":"not-an-email","position":"p","subject":"s","body":"b"}\n', encoding="utf-8")
        self.assertEqual(recruit.reply_all(f, self.con), [])

    def test_bulk_approve_excludes_external_and_evaluation(self):
        for kind in ("recruit_reply", "evaluation_evidence"):
            with self.assertRaises(SystemExit):
                cli.main(["draft", "approve-all", "--kind", kind, "--by", "x"])

    # --- 1on1 ---
    def test_oneonone_prep(self):
        did = evaluation.build_prep("E01", "2026-04:2026-09", "上長A", self.con)
        r = drafts.get(did, self.con)
        self.assertEqual(r["kind"], "evaluation_oneonone")
        self.assertEqual(json.loads(r["flags"]), ["未入力項目（【要入力】）が残っています"])
        self.assertIn("手順書の改訂版", r["body"])
        self.assertNotIn("通院", r["body"])
        with self.assertRaises(ValueError):
            sender.send(did, "email", "a@example.com", self.con, transport=self.tx)

    # --- Slack ---
    def test_slack_signature(self):
        body, ts, key = b"text=x", "1700000000", "k"
        sig = "v0=" + hmac.new(key.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
        self.assertTrue(slack_app.verify_signature(key, ts, body, sig, now=1700000100))
        self.assertFalse(slack_app.verify_signature(key, ts, b"text=y", sig, now=1700000100))   # 改ざん
        self.assertFalse(slack_app.verify_signature(key, ts, body, sig, now=1700001000))        # 期限切れ
        self.assertFalse(slack_app.verify_signature(key, ts, body, "", now=1700000100))

    def test_slack_command_is_ephemeral_and_refuses_personal(self):
        r = slack_app.handle_command({"text": "有給休暇は半日単位で取れますか"}, self.con)
        self.assertEqual(r["response_type"], "ephemeral")
        self.assertIn("第9条", r["text"])
        self.assertIn("お答えできません", slack_app.handle_command({"text": "私の給料はいくらですか"}, self.con)["text"])

    def test_slack_buttons_require_registered_approver_and_skip_evaluation(self):
        did = attendance.check("2026-10", "2026-10-27", self.con)[0]["id"]
        press = lambda uid, d, act="approve": slack_app.handle_interaction({"user": {"id": uid}, "actions": [{"action_id": act, "value": str(d)}]}, self.con)
        self.assertIn("権限がありません", press("U_RANDOM", did)["text"])
        self.assertEqual(drafts.get(did, self.con)["status"], "pending")
        self.assertIn("承認しました", press("U0APPROVER", did)["text"])
        self.assertEqual(drafts.get(did, self.con)["status"], "approved")
        ev = evaluation.build("E01", "2026-04:2026-09", "評価者A", self.con)
        self.assertIn("Slackから操作できません", press("U0APPROVER", ev)["text"])
        shown = json.dumps(slack_app.pending_blocks(self.con), ensure_ascii=False)
        self.assertNotIn("評価根拠シート", shown)
        self.assertNotIn(f'"value": "{ev}"', shown)

    def test_slack_notify_posts_only_pending_non_evaluation(self):
        attendance.check("2026-10", "2026-10-27", self.con)
        evaluation.build("E01", "2026-04:2026-09", "評価者A", self.con)
        posts = []
        self.assertEqual(slack_app.notify("C1", self.con, post=posts.append), 4)
        self.assertTrue(all(p["channel"] == "C1" for p in posts))


class Golden(unittest.TestCase):
    def test_golden_50(self):
        passed, stats = evaluate.run(verbose=False)
        self.assertTrue(passed, stats)


if __name__ == "__main__":
    unittest.main()
