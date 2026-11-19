import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dxkit import audit, config, intake, kb, triage

audit.LOG = Path(tempfile.mkdtemp()) / "audit.jsonl"  # 本番ログを汚さない


class T(unittest.TestCase):
    cfg = config.load()
    entries = kb.load()

    def run_q(self, subject, body):
        return triage.triage(self.cfg, {"id": "x", "from": "a@b", "subject": subject, "body": body}, self.entries)

    def test_faq_auto(self):
        self.assertEqual(self.run_q("営業時間", "営業時間を教えてください。")["action"], "auto")

    def test_refund_escalates(self):
        self.assertEqual(self.run_q("返金", "返金してください")["action"], "escalate")

    def test_legal_keyword_escalates(self):
        self.assertEqual(self.run_q("営業時間", "営業時間について弁護士に相談します")["action"], "escalate")

    def test_no_kb_never_auto(self):
        self.assertNotEqual(self.run_q("天気", "明日の天気は？")["action"], "auto")

    def test_intake(self):
        r = intake.parse(Path(__file__).resolve().parent.parent.joinpath("samples/documents.txt").read_text(encoding="utf-8"))
        self.assertEqual((r["date"], r["amount"], r["vendor"]), ("2026-10-15", 33000, "山田商店"))
        self.assertEqual(intake.parse("何もない")["needs_review"], "yes")


if __name__ == "__main__":
    unittest.main()
