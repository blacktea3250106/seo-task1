"""三個新評估數字＋run 摘要的附加欄位（G-30、G-31；判定訊號定義 D、A）。

- 白做工次數（run 中由程式算）：沒帶來新證據的 Tool 呼叫。不算：交卷動作、別走經驗的輕試、
  ④ 重抓到和底稿一樣的內容（決策 #50）、被停止條件擋下沒執行的呼叫。「新證據」沿用停止條件 ② 的判斷（同一份指紋）。
- 找到第一個關鍵發現的時間與呼叫次數（評估後回填）：關鍵發現＝單獨評分時命中評分表某一項（y 或 p）的結論；
  時間取該結論第一個證據的產生時間（從 run 開始算），呼叫次數＝從 run 開始數到產生該證據的那次 Tool 呼叫（含）。
  證據是匯入的底稿（不是這次 Tool 產生）→ 呼叫次數 0、時間 0。
- 新發現數（評估後回填）：這次命中、上一次沒命中的評分項數；沒有上一次就是 None。
- 被擋清單：Tool 錯誤回傳（robots 不准、連不上、被限速……）的路徑，給人看。
- 省下的呼叫：模型在 Tool 呼叫的 why 寫「別走（會誤導）」的經驗編號＝自稱因這條經驗避開某條路；不計分，只記錄（決策 #71）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .grader import grade, load_rubric
from .hermes_bridge import TOOL_ERROR_CODES

NOT_COUNTED = {"experience", "submit_report"}
HIT = {"y", "p"}


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def wasted_calls(calls: list[dict]) -> int:
    return sum(1 for c in calls
               if c["tool"] not in NOT_COUNTED and not c.get("blocked_by_guard") and not c.get("light_test_of")
               and not c.get("same_as_snapshot") and not c.get("new_evidence"))


def blocked_list(calls: list[dict]) -> list[dict]:
    out, seen = [], set()
    for c in calls:
        if c.get("error") in TOOL_ERROR_CODES:
            t = c.get("target") or {}
            key = (c["tool"], t.get("domain"), t.get("path"), c["error"])
            if key not in seen:
                seen.add(key)
                out.append({"tool": c["tool"], "domain": t.get("domain"), "path": t.get("path"), "error": c["error"],
                            "evidence_ids": c.get("error_evidence_ids") or []})
    return out


def saved_calls(calls: list[dict], entries: list[dict]) -> dict:
    from .coverage import why_ids
    misleading = {e["id"] for e in entries if e.get("result") == "別走" and e.get("avoid_reason") == "會誤導"}
    items, seen = [], set()
    for c in calls:
        for eid in sorted(why_ids(c.get("args") or {}) & misleading):
            if eid not in seen:
                seen.add(eid)
                items.append({"experience_id": eid, "call_n": c.get("n")})
    return {"count": len(items), "items": items, "note": "模型自稱避開，不計分"}


def run_metrics(run_dir: Path, entries_read: list[dict]) -> dict:
    run_dir = Path(run_dir)
    calls = _jsonl(run_dir / "tool_calls.jsonl")
    return {"wasted_calls": wasted_calls(calls), "blocked": blocked_list(calls),
            "saved_calls": saved_calls(calls, entries_read),
            "key_finding": None, "new_findings": None}  # 後兩個評估後回填


def key_finding(run_dir: Path, claims: list[dict], rubric: dict | None = None, *, started_at: float | None = None) -> dict | None:
    rubric = rubric or load_rubric()
    run_dir = Path(run_dir)
    calls = _jsonl(run_dir / "tool_calls.jsonl")
    made_by: dict[str, dict] = {}
    for c in calls:
        for eid in [c.get("evidence_id"), c.get("derived_evidence_id"), *(c.get("error_evidence_ids") or [])]:
            if eid and eid not in made_by:
                made_by[eid] = c
    start = started_at if started_at is not None else (calls[0]["at"] if calls else 0.0)
    best = None
    for c in claims:
        hits = [i["id"] for i in grade((c.get("text") or "").replace("\n", " "), rubric)["items"] if i["mark"] in HIT]
        if not hits:
            continue
        firsts = []
        for eid in c.get("evidence_ids") or []:
            call = made_by.get(eid)
            firsts.append((call["n"], call["at"], eid) if call else (0, start, eid))  # 底稿快照：開始時就有
        if not firsts:
            continue
        n, at, eid = min(firsts)
        cand = {"claim_id": c.get("id"), "rubric_items": hits, "evidence_id": eid, "calls": n,
                "elapsed_s": round(max(0.0, at - start), 1)}
        if best is None or (n, cand["elapsed_s"]) < (best["calls"], best["elapsed_s"]):
            best = cand
    return best


def new_findings(marks: str, prev_marks: str | None, item_ids: list[str]) -> dict | None:
    if prev_marks is None:
        return None
    ids = [i for i, now, before in zip(item_ids, marks, prev_marks, strict=False) if now in HIT and before not in HIT]
    return {"count": len(ids), "items": ids}
