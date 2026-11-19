from . import config, db


def report(con=None):
    r = config.settings()["roi"]
    con = con or db.connect()
    q = {row["status"]: row["n"] for row in con.execute("SELECT status, COUNT(*) n FROM qa_log GROUP BY status")}
    approved = con.execute("SELECT COUNT(*) FROM drafts WHERE status='approved'").fetchone()[0]
    answered = q.get("answered", 0)
    saved_min = (answered * (r["minutes_per_question_manual"] - r["minutes_per_question_bot"])
                 + approved * (r["minutes_per_draft_manual"] - r["minutes_per_draft_with_ai"]))
    return {"questions": q, "approved_drafts": approved, "saved_hours": round(saved_min / 60, 1),
            "saved_jpy": round(saved_min / 60 * r["hourly_cost_jpy"])}
