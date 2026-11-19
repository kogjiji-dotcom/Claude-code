"""監査ログから削減工数・コストを試算。"""
from . import audit


def report(cfg, log=None):
    r = cfg["roi"]
    rows = audit.read(log)
    tri = [x for x in rows if x["event"] == "triage"]
    docs = [x for x in rows if x["event"] == "intake"]
    auto = sum(x["action"] == "auto" for x in tri)
    assisted = len(tri) - auto  # 下書き支援で短縮される分
    saved_min = (
        auto * r["minutes_per_inquiry_manual"]
        + assisted * (r["minutes_per_inquiry_manual"] - r["minutes_per_inquiry_with_ai"])
        + len(docs) * (r["minutes_per_document_manual"] - r["minutes_per_document_with_ai"])
    )
    return {
        "inquiries": len(tri), "auto_resolved": auto, "documents": len(docs),
        "saved_hours": round(saved_min / 60, 1),
        "saved_jpy": round(saved_min / 60 * r["hourly_cost_jpy"]),
    }
