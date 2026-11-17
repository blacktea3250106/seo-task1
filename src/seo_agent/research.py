"""研究 job：模型在 Hermes Loop 中用 7 個研究 Tool＋經驗 Tool＋交卷 Tool 研究競品，交出 5 段報告（決策 #71）。在 worker 子程序內執行。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .baseline import BASELINE_ROOT, domain_key, prepare
from .board import write_board
from .coverage import research_tools
from .experience import DEFAULT_PATH as EXPERIENCE_PATH
from .experience import ExperienceStore, experience_tool, write_route_summary
from .hermes_bridge import ToolLog, run_agent
from .metrics import run_metrics
from .model_env import ModelSettings
from .report import ReportFlow, report_tool, write_incomplete_report
from .review import default_reviewer
from .stop import StopGuard
from .tools.context import Context

SKILL_PATH = Path(__file__).parent / "skill" / "SKILL.md"

TASK = """請研究這個競爭者網站：{site}
指定關鍵字：{keywords}

任務：這個競爭者在 SEO／Organic Search 上採取了哪些值得關注的策略（包含 On-page／Off-page）？
如果我們希望與它競爭，有哪些值得優先採取的行動？

網站可能有數萬個網址，請考慮時間與抓取成本，決定下一步最值得研究什麼。最後用 submit_report 交報告。"""


def system_prompt(store: ExperienceStore) -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    return skill + "\n\n" + store.notes_markdown()


def run_research(model: ModelSettings, payload: dict, *, run_dir: Path, transport=None,
                 experience_path: Path | None = None, baseline_root: Path | None = None, reviewer=None) -> dict:
    if reviewer is None:
        reviewer = lambda c, inp: default_reviewer(c, inp, run_id=run_dir.name, model=model.model)  # noqa: E731
    s = open_session(model.model, payload, run_dir=run_dir, transport=transport, experience_path=experience_path,
                     baseline_root=baseline_root, reviewer=reviewer)
    out = run_agent(model, s["tools"], system_prompt=s["prompt"], message=s["message"], run_id=run_dir.name,
                    max_iterations=int(payload.get("max_iterations", 400)),
                    budget_seconds=float(payload.get("total_minutes", 120)) * 60, log=s["log"])
    return close_session(s, out)


def open_session(model_name: str, payload: dict, *, run_dir: Path, reviewer, transport=None,
                 experience_path: Path | None = None, baseline_root: Path | None = None) -> dict:
    """研究開始前的準備（底稿、資料卡、停止條件、Tool、提示）。Hermes 與模擬執行（sim.py）共用。"""
    run_id = run_dir.name
    # fetch_delay_s：多個 run 同時跑時放大每個 run 的請求間隔，讓對同一網站的合計速度仍溫和
    delay = float(payload.get("fetch_delay_s", 1.5))
    ctx = Context(run_dir, transport=transport, delay_s=delay)
    ctx.site_domain = domain_key(payload.get("site", "https://2030.tw"))
    store = ExperienceStore(experience_path or Path(payload.get("experience_path") or EXPERIENCE_PATH))
    before_exp = [dict(e) for e in store.load()]
    meta = {"run_id": run_id, "model": model_name, "at": time.strftime("%Y-%m-%d %H:%M"),
            "site": payload.get("site", "https://2030.tw"), "keywords": payload.get("keywords", ["娛樂城", "3A娛樂城"])}
    # ② 程式準備：網站底稿 → 匯入證據庫 → 資料卡（在停止條件開始計算前，不算研究時間、不算新證據；G-50、G-51）
    prep = prepare(ctx, meta["site"], meta["keywords"], refresh=bool(payload.get("refresh")),
                   root=Path(baseline_root or payload.get("baseline_root") or BASELINE_ROOT), transport=transport,
                   delay_s=delay)
    meta["baseline"] = {"hash": prep["baseline"]["baseline_hash"], "fetched_at": prep["fetched_at"]}  # 報告要標（G-54）
    guard = StopGuard(ctx, total_s=float(payload.get("total_minutes", 120)) * 60,
                      reserve_s=min(1200.0, float(payload.get("total_minutes", 120)) * 60 / 6))  # 120 分鐘時保留 20 分鐘（G-36）
    guard.seed_snapshot()
    log = ToolLog(guard=guard, ctx=ctx)
    accepted = {"v": False}
    flow = ReportFlow(ctx, experience_store=store, meta=meta, guard=guard, reviewer=reviewer,
                      on_accept=lambda: accepted.__setitem__("v", True))
    research, cov = research_tools(ctx, meta["site"])  # page_text＋sections_not_yet_read＋why（決策 #71）
    tools = research + [experience_tool(store, run_id, ctx), report_tool(flow)]
    # 別走（查不到）經驗的原路線：輕試判斷用（G-23、G-34）
    ctx.light_test_routes = {e["id"]: [{"tool": t["tool"], "target": {"domain": t.get("domain"), "path": t.get("path")}}
                                       for t in e.get("route_tools") or []]
                             for e in store.active() if e.get("result") == "別走" and e.get("avoid_reason") == "查不到"}
    notes = store.notes_snapshot()  # 這次讀了哪個版本、哪些條目（G-21）
    meta["experience_read"] = {"notes_sha256": notes["notes_sha256"], "entry_ids": notes["entry_ids"]}
    prompt = system_prompt(store)
    (run_dir / "system_prompt.md").write_text(prompt, encoding="utf-8")
    message = payload.get("message") or TASK.format(site=meta["site"], keywords="、".join(f"[{k}]" for k in meta["keywords"]))
    message += "\n\n" + prep["markdown"]
    return {"run_id": run_id, "model": model_name, "ctx": ctx, "store": store, "before_exp": before_exp, "meta": meta,
            "prep": prep, "guard": guard, "log": log, "accepted": accepted, "flow": flow, "tools": tools,
            "prompt": prompt, "message": message, "started": time.time(), "coverage": cov}


def close_session(s: dict, out: dict) -> dict:
    """研究結束後的收尾：存 HTTP 紀錄、收初稿、Board、路線摘要、run 摘要。out＝執行層（Hermes 或模擬）的結果。"""
    ctx, flow, guard, meta, store, prep = s["ctx"], s["flow"], s["guard"], s["meta"], s["store"], s["prep"]
    run_dir, before_exp, started = ctx.run_dir, s["before_exp"], s["started"]
    ctx.fetcher.close()
    with (run_dir / "http_requests.jsonl").open("w", encoding="utf-8") as fh:
        for r in ctx.fetcher.requests:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    flow.finalize_pending()  # 交了初稿、沒交修正稿就結束：初稿照收，待修清單列為未處理
    after_exp = store.load()
    calls = out.pop("tool_calls", None) or s["log"].calls
    board = write_board(ctx)
    coverage = s["coverage"].summary()
    write_route_summary(ctx)  # ⑧ 路線摘要，附在經驗旁一起送寫入審核（G-14）
    # G-38：Opus／API 中途錯誤 → 中斷（證據與紀錄保留、不續跑）；時間到或沒交報告 → 程式輸出「未完成」報告
    if s["accepted"]["v"]:
        status = "passed"
    else:
        status = "interrupted" if out.get("error") else "incomplete"
        write_incomplete_report(ctx, meta, reason="中斷：模型／API 錯誤" if out.get("error") else "時間到或沒交報告",
                                coverage=coverage)
    result = {
        "status": status, "status_label": {"passed": "完成", "interrupted": "中斷", "incomplete": "未完成"}[status],
        "run_id": s["run_id"], "model": s["model"], "started_at": round(started, 3),
        "elapsed_s": round(time.time() - started, 1),
        "tool_calls_total": len(calls),
        "tool_calls_by_name": _count(c["tool"] for c in calls),
        "tool_errors": _count(c["error"] for c in calls if c.get("error")),
        "evidence_total": len(ctx.store.ids()),
        "baseline": prep["baseline"],
        "http_requests": len(ctx.fetcher.requests),
        "coverage": coverage,
        "why_filled": board["why_filled"],
        "stop": guard.summary(),
        "experience_read": meta["experience_read"],
        "experience_proposals": len(ctx.read_jsonl(run_dir / "experience_proposals.jsonl")),
        "experience_changes": _exp_diff(before_exp, after_exp),
        "review": _review_summary(flow, out),
        "metrics": run_metrics(run_dir, [e for e in before_exp if e.get("id") in meta["experience_read"]["entry_ids"]]),
        "approvals_pending": ctx.read_jsonl(run_dir / "approvals_pending.jsonl"),
        **out,
    }
    return result


def _review_summary(flow, out: dict) -> dict:
    """⑥ 審查另列一筆（請求數、token、耗時），並算進總數（G-61、G-31）。"""
    review = flow.review or {}
    cost = review.get("cost") or {}
    tok_r, tok_m = cost.get("tokens") or {}, out.get("tokens") or {}
    return {"triggered": flow.reviews_triggered, "status": review.get("status"), "items": len(review.get("items") or []),
            "revised": flow.stage == "final" and flow.accepted, "cost": cost,
            "total_with_review": {"api_calls": (out.get("api_calls") or 0) + (cost.get("api_calls") or 0),
                                  "tokens": {k: (tok_m.get(k) or 0) + (tok_r.get(k) or 0) for k in ("input", "output", "total")}}}


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def _exp_diff(before: list[dict], after: list[dict]) -> list[dict]:
    old = {e["id"]: e["status"] for e in before}
    return [{"id": e["id"], "from": old.get(e["id"]), "to": e["status"], "retired_reason": e.get("retired_reason")}
            for e in after if old.get(e["id"]) != e["status"]]
