"""寫入審核 7 項（G-16～G-20、G-57；判定訊號定義 A；第 7 項見決策 #59）。

研究結束、評分出來後（run 資料夾有 evaluation.json），程式逐條審核 ⑧ 寫下的路線（experience_proposals.jsonl）：
  1. 寫的是方法，不是結論：不收網站上的數字、網頁指令、擴權內容——不比對關鍵字，只做格式檢查（決策 #50）。
  2. Evidence ID 真的存在，而且不全是 Tool 錯誤回傳。
  3. 照走：路線上 Tool 產生的 Evidence ID，至少 1 個被報告引用。
  4. 照走：這些 Evidence ID 撐起的結論，評分沒有判錯（讀 evaluation.json 的判錯結論紀錄）。
  5. 別走（會誤導）：要有配對照走編號；配對的照走經驗已是使用中，或在同一次審核通過。
  6. 別走（查不到）＝否定型經驗：Evidence ID 來自 2 個不同 Tool，且都存在、都不是 Tool 錯誤回傳。
  7. 不記網址：situation、route 不能含目標網域，也不能含這個 run 的證據來源或 sitemap 出現過的站內路徑
     （字串比對，見 experience.site_problems）。route_tools 原始資料照存，只是不顯示給研究 Agent。
全部通過 → 寫進 candidates.jsonl，狀態 active；有一項不過 → 不收，只在 run 資料夾的 experience_audit.json 寫明沒過哪幾項。
評分還沒出來 → 不審核。同一個 run 只審一次。

第 1 項的格式規則（使用者確認的箭頭模板，定義在 experience.format_problems）：
  - situation：單段、≤300 字。
  - route：一步一行「編號. Tool：做什麼，因為 為什麼」，2–4 步；每步 ≤90 字、寫出 1 個研究 Tool、寫「因為」。
  - 去掉網址、網域、路徑與編號（E-0001、EXP-001、P1）後，不能有 2 位數以上的數字（網站上的數量、日期屬於結論）。
  - 目標網址、站內路徑本身不在第 1 項判斷：含了就由第 7 項直接不收。

用法：python -m seo_agent.audit RUN_DIR [--store experience/candidates.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluation import judged_wrong_evidence
from .experience import (  # noqa: F401
    DEFAULT_PATH,
    RESEARCH_TOOLS,
    ExperienceStore,
    _now,
    format_problems,
    proposals_for_audit,
    site_paths,
    site_problems,
)
from .hermes_bridge import error_evidence_ids
from .lifecycle import report_evidence
from .tools.context import Context

AUDIT = "experience_audit.json"
ITEMS = {1: "方法不是結論（格式）", 2: "Evidence ID 存在且不全是 Tool 錯誤", 3: "照走：至少 1 個 Evidence ID 被報告引用",
         4: "照走：結論沒被判錯", 5: "別走（會誤導）：配對照走通過", 6: "別走（查不到）：2 個不同 Tool、都不是錯誤回傳",
         7: "不記網址：不含目標網域與站內路徑"}


def _route_ids(p: dict) -> set[str]:
    """路線上 Tool 產生的 Evidence ID：Opus 列的，加上同一次呼叫的原檔／衍生證據。"""
    return set(p.get("evidence_ids") or []) | {e for t in p.get("route_tools") or [] for e in t.get("evidence_ids") or []}


def check(p: dict, *, existing: set[str], errors: set[str], cited: set[str], wrong: set[str],
          domain: str | None = None, paths: set[str] | None = None) -> dict[int, str]:
    """回傳沒過的項目 {編號: 原因}；第 5 項另由 audit_run 依配對結果補判。"""
    failed: dict[int, str] = {}
    fmt = format_problems(p)
    if fmt:
        failed[1] = "；".join(fmt)
    site = site_problems(p, domain, paths or set())
    if site:
        failed[7] = "；".join(site)
    ids = list(p.get("evidence_ids") or [])
    missing = [e for e in ids if e not in existing]
    if not ids:
        failed[2] = "沒附 Evidence ID"
    elif missing:
        failed[2] = f"Evidence ID 不存在：{missing}"
    elif all(e in errors for e in ids):
        failed[2] = "Evidence ID 全是 Tool 錯誤回傳"
    if p.get("result") == "照走":
        route = _route_ids(p)
        if not route & cited:
            failed[3] = "路線的 Evidence ID 沒有被報告引用"
        if route & wrong:
            failed[4] = f"路線的 Evidence ID 撐起的結論被判錯：{sorted(route & wrong)}"
    if p.get("result") == "別走" and p.get("avoid_reason") == "查不到":  # 只讀這兩個欄位，不看文字
        tools = {t["tool"] for t in p.get("route_tools") or []}
        bad = [e for e in ids if e not in existing or e in errors]
        if len(tools) < 2 or bad or not ids:
            failed[6] = (f"Evidence ID 來自 {len(tools)} 個 Tool" + (f"；錯誤回傳或不存在：{bad}" if bad else ""))
    return failed


def _site_domain(run_dir: Path) -> str | None:
    """目標網域：讀報告 meta.site（沒交報告時讀未完成報告）。"""
    from .baseline import domain_key
    for name in ("report.json", "report_incomplete.json"):
        path = run_dir / name
        if path.exists():
            site = (json.loads(path.read_text(encoding="utf-8")).get("meta") or {}).get("site")
            if site:
                return domain_key(site)
    return None


def audit_run(run_dir: Path, store: ExperienceStore | None = None) -> dict:
    run_dir = Path(run_dir)
    store = store or ExperienceStore(DEFAULT_PATH)
    out_path = run_dir / AUDIT
    if out_path.exists():
        return {**json.loads(out_path.read_text(encoding="utf-8")), "skipped": "這個 run 已審核過"}
    wrong = judged_wrong_evidence(run_dir)
    if wrong is None:
        return {"status": "waiting_for_grade", "detail": "評分還沒出來，先不審核"}
    ctx = Context(run_dir)
    ctx.site_domain = _site_domain(run_dir)
    proposals = proposals_for_audit(ctx)
    existing, errors, cited = set(ctx.store.ids()), error_evidence_ids(ctx), report_evidence(run_dir)
    paths = site_paths(ctx)
    results = {p["id"]: check(p, existing=existing, errors=errors, cited=cited, wrong=wrong, domain=ctx.site_domain,
                              paths=paths) for p in proposals}
    active = {e["id"] for e in store.active()}
    for p in proposals:  # 第 5 項：配對要已是使用中，或同一次審核通過（照走先判完，上面已算）
        if p.get("result") == "別走" and p.get("avoid_reason") == "會誤導":
            pid = p.get("paired_id") or ""
            pair = next((x for x in proposals if x["id"] == pid), None)
            if not pid:
                results[p["id"]][5] = "沒有配對照走編號"
            elif pair is not None:
                if pair.get("result") != "照走" or results[pid]:
                    results[p["id"]][5] = f"配對 {pid} 沒通過審核"
            elif pid not in active or (store.get(pid) or {}).get("result") != "照走":
                results[p["id"]][5] = f"配對 {pid} 不是使用中的照走經驗"
    items = store.load()
    new_ids: dict[str, str] = {}
    for p in proposals:
        if not results[p["id"]]:
            new_ids[p["id"]] = store.next_id(items + [{"id": v} for v in new_ids.values()])
    for p in proposals:
        if p["id"] in new_ids:
            items.append({"id": new_ids[p["id"]], "status": "active", "situation": p["situation"], "route": p["route"],
                          "result": p["result"], "avoid_reason": p.get("avoid_reason") or "",
                          "paired_id": new_ids.get(p.get("paired_id") or "", p.get("paired_id") or ""),
                          "evidence_ids": p.get("evidence_ids") or [], "route_tools": p.get("route_tools") or [],
                          "route_summary": p.get("route_summary") or [], "source_run": p.get("source_run"),
                          "proposal_id": p["id"], "added_at": _now()})
    if new_ids:
        store.save_all(items)
    record = {"at": _now(), "status": "done", "items": ITEMS,
              "results": [{"proposal_id": p["id"], "passed": not results[p["id"]], "experience_id": new_ids.get(p["id"]),
                           "failed": [{"item": k, "reason": v} for k, v in sorted(results[p["id"]].items())]}
                          for p in proposals]}
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--store", type=Path, default=DEFAULT_PATH)
    args = ap.parse_args(argv)
    r = audit_run(args.run_dir, ExperienceStore(args.store))
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
