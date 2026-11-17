"""評分出來後：判定這次讀入的使用中經驗（G-22～G-26），再做寫入審核（audit.py）。判定訊號定義 A。

- 「有用到」看 Tool 呼叫紀錄，不看報告自稱（決策 #71）：
  只算 why 本身寫了這條經驗編號、Tool 在路線 Tool 清單上、正常回傳的那幾次呼叫（沒寫編號的呼叫不算）。
- 照走：有用到＋那些呼叫的 Evidence ID 至少 1 個被報告引用 → 累計歸零；有用到但沒新東西 → 累計 +1，連續 2 次 → 下架（no_value）。
  沒用到 → 不改狀態，只記次數，也不中斷累計。
- 別走（查不到）：輕試＝登記後用同一 Tool、同一目標的那 1 次呼叫（stop.py 標 light_test_of）。
  沒輕試＝沒用到；輕試回傳 Tool 錯誤＝這次不算（路徑列進被擋清單）；
  已經通了只認報告 experience.overturned 的推翻並附輕試的 Evidence ID → 下架（overturned，網站已變）；沒標推翻＝仍不通。
- 被推翻：報告 experience.overturned 標推翻＋Evidence ID（要非空且都在證據庫裡）→ 下架（overturned）。
- 判錯：這次帶出的 Evidence ID 撐起的結論被評分判錯 → 下架（judged_wrong）。
- 別走（會誤導）不重試；配對的照走經驗下架，它也跟著下架。
- 評分還沒出來 → 這次不算，什麼都不改。每個 run 只判一次。

用法：python -m seo_agent.lifecycle RUN_DIR [--store experience/candidates.jsonl]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .evaluation import judged_wrong_evidence
from .experience import (
    DEFAULT_PATH,
    ExperienceStore,
    _now,
    _read_jsonl,
    cascade_pairs,
    retire,
)
from .tools.context import Context

JUDGEMENT = "experience_judgement.json"
NO_VALUE_LIMIT = 2


def report_evidence(run_dir: Path) -> set[str]:
    data = json.loads((Path(run_dir) / "report.json").read_text(encoding="utf-8"))
    return set(re.findall(r"E-\d{4}", json.dumps(data.get("report") or {}, ensure_ascii=False)))


def _ids(c: dict) -> list[str]:
    return [e for e in (c.get("evidence_id"), c.get("derived_evidence_id")) if e]


def used_calls(calls: list[dict], entry: dict) -> list[dict]:
    """why 本身寫了這條經驗編號、用路線 Tool 清單上的 Tool、正常回傳的呼叫（只算寫了編號的那幾次）。"""
    from .coverage import why_ids
    tools = {t["tool"] for t in entry.get("route_tools") or []}
    return [c for c in calls if entry["id"] in why_ids(c.get("args") or {}) and c.get("tool") in tools
            and c.get("ok", True) and not c.get("error")]


def report_overturns(run_dir: Path, evidence_ids: set[str]) -> list[dict]:
    """報告 experience.overturned（決策 #71）：只採用附了 Evidence ID、而且全部在證據庫裡的項目。
    格式檢查只退回 1 次，之後照收，所以這裡再核一次；不附證據的推翻不能讓經驗下架。"""
    data = json.loads((Path(run_dir) / "report.json").read_text(encoding="utf-8"))
    items = ((data.get("report") or {}).get("experience") or {}).get("overturned") or []
    return [o for o in items if (ids := o.get("evidence_ids") or []) and set(ids) <= evidence_ids]


def judge_entry(entry: dict, *, calls: list[dict], cited: set[str], wrong: set[str], overturned: list[dict]) -> dict:
    eid, kind = entry["id"], (entry.get("result"), entry.get("avoid_reason") or "")
    out = {"id": eid, "result": entry.get("result"), "avoid_reason": entry.get("avoid_reason") or ""}
    overturns = [o for o in overturned if o.get("experience_id") == eid]
    if kind == ("別走", "查不到"):
        light = [c for c in calls if c.get("light_test_of") == eid]
        if not light:
            return {**out, "verdict": "沒用到", "detail": "沒做輕試"}
        test = light[0]
        if test.get("error"):
            return {**out, "verdict": "不算", "detail": f"輕試回傳 Tool 錯誤 {test['error']}", "blocked": test.get("target")}
        light_ids = set(_ids(test)) | {e for c in light for e in _ids(c)}
        if any(light_ids & set(o.get("evidence_ids") or []) for o in overturns):
            return {**out, "verdict": "下架", "reason": "overturned", "note": "網站已變", "evidence_ids": sorted(light_ids)}
        return {**out, "verdict": "仍不通", "detail": "有輕試、沒標推翻", "evidence_ids": sorted(light_ids)}
    if overturns:
        return {**out, "verdict": "下架", "reason": "overturned", "note": "被推翻",
                "evidence_ids": sorted({e for o in overturns for e in o.get("evidence_ids") or []})}
    if kind[0] != "照走":  # 別走（會誤導）：不重試，只跟著配對下架
        return {**out, "verdict": "不判定", "detail": "會誤導型不重試"}
    used = used_calls(calls, entry)
    if not used:
        return {**out, "verdict": "沒用到"}
    carried = {e for c in used for e in _ids(c)}
    if carried & wrong:
        return {**out, "verdict": "下架", "reason": "judged_wrong", "note": "帶出的證據撐起的結論被判錯",
                "evidence_ids": sorted(carried & wrong)}
    new = bool(carried & cited)
    return {**out, "verdict": "有用到＋有新東西" if new else "有用到但沒新東西", "evidence_ids": sorted(carried),
            "calls": [c.get("n") for c in used]}


def judge_run(run_dir: Path, store: ExperienceStore) -> dict:
    run_dir = Path(run_dir)
    path = run_dir / JUDGEMENT
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "skipped": "這個 run 已判定過"}
    wrong = judged_wrong_evidence(run_dir)
    if wrong is None:
        return {"status": "waiting_for_grade", "detail": "評分還沒出來，這次不算"}
    ctx = Context(run_dir)
    run_id = run_dir.name
    meta = json.loads((run_dir / "report.json").read_text(encoding="utf-8")).get("meta") or {}
    read_ids = (meta.get("experience_read") or {}).get("entry_ids")
    items = store.load()
    targets = [e for e in items if e["status"] == "active" and (read_ids is None or e["id"] in read_ids)]
    calls, cited, overturned = _read_jsonl(ctx.tool_calls_path), report_evidence(run_dir), report_overturns(run_dir, set(ctx.store.ids()))
    results = []
    for e in targets:
        r = judge_entry(e, calls=calls, cited=cited, wrong=wrong, overturned=overturned)
        if r["verdict"] == "有用到＋有新東西":
            e["no_value_streak"] = 0
        elif r["verdict"] == "有用到但沒新東西":
            e["no_value_streak"] = int(e.get("no_value_streak") or 0) + 1
            r["streak"] = e["no_value_streak"]
            if e["no_value_streak"] >= NO_VALUE_LIMIT:
                r.update(verdict="下架", reason="no_value", note=f"連續 {NO_VALUE_LIMIT} 次有用到但沒新東西")
        elif r["verdict"] == "沒用到":
            e["unused_runs"] = int(e.get("unused_runs") or 0) + 1
        if r["verdict"] == "下架":
            retire(items, e["id"], r["reason"], note=r.get("note", ""), run_id=run_id)
        e.setdefault("history", []).append({"run": run_id, "verdict": r["verdict"]})
        results.append(r)
    followed = cascade_pairs(items, run_id=run_id)
    store.save_all(items)
    record = {"at": _now(), "status": "done", "results": results, "followed_pairs": followed,
              "blocked": [r["blocked"] for r in results if r.get("blocked")]}
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def post_run(run_dir: Path, store: ExperienceStore | None = None) -> dict:
    """評分後的經驗處理：先判定使用中經驗，再審核這次寫下的新路線。"""
    from .audit import audit_run
    store = store or ExperienceStore(DEFAULT_PATH)
    res = Path(run_dir) / "result.json"
    untrusted = res.exists() and json.loads(res.read_text(encoding="utf-8")).get("untrusted_run")
    if untrusted:  # 決策 #57：模擬執行者用了專案以外的 Tool 或輸出格式不符，這輪不動經驗庫
        skip = {"status": "skipped_untrusted_run", "detail": untrusted}
        return {"judgement": skip, "audit": skip}
    return {"judgement": judge_run(run_dir, store), "audit": audit_run(run_dir, store)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--store", type=Path, default=DEFAULT_PATH)
    args = ap.parse_args(argv)
    print(json.dumps(post_run(args.run_dir, ExperienceStore(args.store)), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
