import argparse
import json
import sys
from pathlib import Path

from . import attendance, bot, db, drafts, evaluate, evaluation, onboarding, recruit, roi, sender, slack_app


def _params(items):
    return dict(i.split("=", 1) for i in items or [])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hrai")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ask").add_argument("question")
    d = sub.add_parser("draft").add_subparsers(dest="dcmd", required=True)
    n = d.add_parser("new")
    n.add_argument("kind", choices=drafts.GENERIC)
    n.add_argument("--param", "-p", action="append", help="key=value（例: title=経理担当）")
    d.add_parser("list")
    s = d.add_parser("show"); s.add_argument("id", type=int)
    e = d.add_parser("edit"); e.add_argument("id", type=int); e.add_argument("file")
    a = d.add_parser("approve"); a.add_argument("id", type=int); a.add_argument("--by", required=True)
    kinds = [k for k in drafts.KINDS if not k.startswith("evaluation")]
    aa = d.add_parser("approve-all", help="種別を指定して、承認待ちを一括承認（内容を確認したうえで。フラグ付きは承認されない）")
    aa.add_argument("--kind", required=True, choices=["attendance_alert", "onboarding_notice", "onboarding_checklist", "onboarding_reminder"], help="固定テンプレートの社内通知のみ。応募者宛などは1件ずつ承認")
    aa.add_argument("--by", required=True)
    sa = d.add_parser("send-all", help="種別を指定して、承認済みを一括送信（宛先は各下書きの宛先）")
    sa.add_argument("--kind", required=True, choices=kinds); sa.add_argument("--via", default="email", choices=list(sender.TRANSPORTS)); sa.add_argument("--dry-run", action="store_true")
    t = d.add_parser("send", help="承認済みの下書きを送信")
    t.add_argument("id", type=int); t.add_argument("--via", required=True, choices=list(sender.TRANSPORTS))
    t.add_argument("--to", default=""); t.add_argument("--dry-run", action="store_true")
    r = d.add_parser("reject"); r.add_argument("id", type=int); r.add_argument("--by", required=True); r.add_argument("--reason", default="")
    rv = sub.add_parser("review", help="人事評価の根拠シート（点数なし・下書き）").add_subparsers(dest="rcmd", required=True)
    rb = rv.add_parser("build"); rb.add_argument("employee"); rb.add_argument("--period", required=True, help="例: 2026-04:2026-09"); rb.add_argument("--by", required=True, help="評価者名")
    rp = rv.add_parser("prep", help="1on1の準備シート"); rp.add_argument("employee"); rp.add_argument("--period", required=True); rp.add_argument("--by", required=True)
    at = sub.add_parser("attendance").add_subparsers(dest="acmd", required=True).add_parser("check", help="勤怠・有給アラートの下書きを作成")
    at.add_argument("--month", required=True, help="例: 2026-10"); at.add_argument("--today", required=True, help="例: 2026-10-27")
    ob = sub.add_parser("onboarding").add_subparsers(dest="ocmd", required=True)
    o1 = ob.add_parser("start"); o1.add_argument("employee"); o1.add_argument("--start-date", required=True); o1.add_argument("--email", required=True)
    o2 = ob.add_parser("status"); o2.add_argument("employee")
    o3 = ob.add_parser("done"); o3.add_argument("employee"); o3.add_argument("item"); o3.add_argument("--by", required=True)
    o4 = ob.add_parser("remind"); o4.add_argument("--today", required=True)
    rc = sub.add_parser("recruit").add_subparsers(dest="rccmd", required=True).add_parser("reply", help="応募への返信下書きを作成"); rc.add_argument("file")
    sl = sub.add_parser("slack").add_subparsers(dest="scmd", required=True)
    s1 = sl.add_parser("serve"); s1.add_argument("--port", type=int, default=3000)
    s2 = sl.add_parser("notify"); s2.add_argument("--channel", required=True)
    sub.add_parser("eval")
    sub.add_parser("report")
    args = ap.parse_args(argv)

    if args.cmd == "ask":
        print(bot.answer(args.question)["text"])
    elif args.cmd == "review":
        con = db.connect()
        try:
            did = (evaluation.build if args.rcmd == "build" else evaluation.build_prep)(args.employee, args.period, args.by, con)
            print(f"{drafts.KINDS[drafts.get(did, con)['kind']][0]} #{did} を作成（承認待ち）。`draft show {did}` で確認、`draft edit` で最終コメントを記入\n")
            print(drafts.get(did, con)["body"])
        except ValueError as ex:
            print(f"エラー: {ex}", file=sys.stderr)
            return 1
    elif args.cmd in ("attendance", "onboarding", "recruit", "slack"):
        if args.cmd == "slack" and args.scmd == "serve":
            print(f"Slack受信を開始します（ポート {args.port}）。Request URL: /slack/command と /slack/interact")
            slack_app.serve(args.port)
            return 0
        con = db.connect()
        try:
            if args.cmd == "attendance":
                made = attendance.check(args.month, args.today, con)
                print(f"アラート下書きを{len(made)}件作成（承認待ち）")
                for m in made:
                    print(f"  #{m['id']} {m['employee']} → {m['role']}")
            elif args.cmd == "onboarding":
                if args.ocmd == "start":
                    print("作成した下書き:", onboarding.start(args.employee, args.start_date, args.email, con))
                elif args.ocmd == "status":
                    for r in onboarding.status(args.employee, con):
                        print(f"{'済' if r['done_ts'] else '未'} {r['due']} [{r['owner']}] {r['item']}" + (" ※人が実施" if r["human_only"] else ""))
                elif args.ocmd == "done":
                    onboarding.done(args.employee, args.item, args.by, con)
                    print("完了を記録しました")
                else:
                    print("リマインド下書き:", onboarding.remind(args.today, con))
            elif args.cmd == "recruit":
                print("返信下書き:", recruit.reply_all(args.file, con))
            else:
                print(f"承認待ち {slack_app.notify(args.channel, con)}件を投稿しました")
        except (ValueError, KeyError, OSError) as ex:
            print(f"エラー: {ex}", file=sys.stderr)
            return 1
    elif args.cmd == "eval":
        return 0 if evaluate.run()[0] else 1
    elif args.cmd == "report":
        print(json.dumps(roi.report(), ensure_ascii=False, indent=2))
    else:
        con = db.connect()
        try:
            if args.dcmd == "new":
                did = drafts.create(args.kind, _params(args.param), con)
                row = drafts.get(did, con)
                print(f"下書き #{did} を作成（承認待ち）\n{row['body']}\nフラグ: {json.loads(row['flags']) or 'なし'}")
            elif args.dcmd == "list":
                for row in con.execute("SELECT id,kind,status,flags FROM drafts ORDER BY id"):
                    print(f"#{row['id']} {row['kind']:22} {row['status']:9} フラグ{len(json.loads(row['flags']))}件")
            elif args.dcmd == "show":
                row = drafts.get(args.id, con)
                print(row["body"], "\nフラグ:", json.loads(row["flags"]) or "なし")
            elif args.dcmd == "edit":
                drafts.edit(args.id, Path(args.file).read_text(encoding="utf-8"), con)
                print("更新しました（再チェック済み・承認待ち）")
            elif args.dcmd == "approve":
                print("承認・保存:", drafts.approve(args.id, args.by, con))
            elif args.dcmd == "approve-all":
                ok = bad = 0
                for r in con.execute("SELECT id FROM drafts WHERE kind=? AND status='pending' ORDER BY id", (args.kind,)).fetchall():
                    try:
                        drafts.approve(r["id"], args.by, con)
                        ok += 1
                    except ValueError as ex:
                        bad += 1
                        print(f"  #{r['id']} 承認不可: {ex}")
                print(f"承認 {ok}件／承認不可 {bad}件")
            elif args.dcmd == "send-all":
                ok = bad = 0
                for r in con.execute("SELECT id FROM drafts WHERE kind=? AND status='approved' ORDER BY id", (args.kind,)).fetchall():
                    try:
                        res = sender.send(r["id"], args.via, "", con, args.dry_run)
                        ok += 1
                        print(f"  #{r['id']} {'[dry-run] ' if res['dry_run'] else ''}→ {res['to'] or res['via']}")
                    except (ValueError, KeyError, OSError) as ex:
                        bad += 1
                        print(f"  #{r['id']} 送信不可: {ex}")
                print(f"{'送信予定' if args.dry_run else '送信'} {ok}件／不可 {bad}件")
            elif args.dcmd == "send":
                res = sender.send(args.id, args.via, args.to, con, args.dry_run)
                print(("[dry-run] 送信しません: " if res["dry_run"] else "送信しました: ") + f"{res['via']} {res['to']} {res['subject']}")
            else:
                drafts.reject(args.id, args.by, args.reason, con)
                print("却下しました")
        except (ValueError, KeyError) as ex:
            print(f"エラー: {ex}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
