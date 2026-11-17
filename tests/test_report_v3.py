"""5 段報告（決策 #71）、⑥ 獨立審查與待修清單（G-61）、補查最多 1 輪與格式退回 1 次（G-37）、
引用內容核對（G-46）、外部說法（G-47）、底稿抓取時間（G-54）、經驗欄位。全部離線。"""
from __future__ import annotations

import json

import pytest
from fixture_site import FakeSite

from seo_agent.checks import citation_warnings
from seo_agent.experience import ExperienceStore
from seo_agent.hermes_bridge import ToolLog
from seo_agent.report import (
    ReportFlow,
    check_report,
    external_only,
    program_findings,
    report_tool,
)
from seo_agent.stop import StopGuard
from seo_agent.tools import build_tools
from seo_agent.tools.context import Context

HEADS = ("## 1. 摘要", "## 2. On-page", "## 3. Off-page", "## 4. 優先行動", "## 5. 未知與限制", "## 經驗")


@pytest.fixture
def env(tmp_path):
    site = FakeSite()
    site.search_ok = True
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=0, sleep=lambda s: None)
    ctx.site_domain = "2030.tw"
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard, ctx=ctx)
    tools = {t.name: (lambda h: (lambda a: json.loads(h(a))))(log.wrap(t)) for t in build_tools(ctx)}
    p1 = tools["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    p2 = tools["polite_fetch"]({"url": "https://2030.tw/news/a/"})["evidence_id"]
    return ctx, tools, guard, (p1, p2)


def good(p1, p2):
    return {
        "summary": "對方用體育新聞包裝娛樂城內容。",
        "onpage": [{"id": "C1", "text": "首頁有體育新聞區", "kind": "fact", "evidence_ids": [p1]}],
        "offpage": [{"id": "C2", "text": "新聞頁可能用來導流", "kind": "inference", "evidence_ids": [p2],
                     "limits": "只看 1 頁"}],
        "actions": [{"action": "先做賽事頁", "rationale": "影響大、成本低", "based_on": ["C1", "C2"]}],
        "unknowns": ["外鏈數：免費來源沒有"],
    }


def check(ctx, rep, experience_ids=()):
    return check_report(rep, evidence_ids=set(ctx.store.ids()), experience_ids=set(experience_ids))


# ---- 格式檢查（決策 #71） ----
def test_good_report_passes(env):
    ctx, _, _, (p1, p2) = env
    assert check(ctx, good(p1, p2)) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda r: r.pop("unknowns"), "缺少第 5. 未知與限制"),
    (lambda r: r.pop("summary"), "缺少第 1. 摘要"),
    (lambda r: r.update(onpage=[], offpage=[]), "onpage、offpage 不能都是空的"),
    (lambda r: r["onpage"][0].pop("kind"), "kind 要是 fact 或 inference"),
    (lambda r: r["onpage"][0].update(evidence_ids=["E-9999"]), "證據編號不存在"),
    (lambda r: r["onpage"][0].update(evidence_ids=[]), "fact 至少要 1 個 Evidence ID"),
    (lambda r: r["offpage"][0].update(limits=""), "inference 要寫 limits"),
    (lambda r: r["offpage"][0].update(id="C1"), "結論編號重複"),
    (lambda r: r.update(experience={"overturned": [{"experience_id": "EXP-001", "evidence_ids": []}]}),
     "要附存在的 Evidence ID"),
])
def test_report_rejections(env, mutate, expect):
    ctx, _, _, (p1, p2) = env
    rep = good(p1, p2)
    mutate(rep)
    assert any(expect in e for e in check(ctx, rep, ["EXP-001"])), check(ctx, rep, ["EXP-001"])


def test_experience_section_ok(env):
    ctx, _, _, (p1, p2) = env
    rep = {**good(p1, p2), "experience": {"used": ["EXP-001"],
                                          "overturned": [{"experience_id": "EXP-001", "evidence_ids": [p1], "why": "網站已變"}]}}
    assert check(ctx, rep, ["EXP-001"]) == []


# ---- G-47 ----
def test_search_marks_external_and_report_warns(env):
    ctx, tools, _, (p1, p2) = env
    res = tools["web_search"]({"query": "娛樂城"})["results"]
    labels = {r["url"]: r.get("label") for r in res}
    assert labels["https://2030.tw/wordcup/casino-1/"] is None
    assert [v for u, v in labels.items() if "other.example" in u] == ["外部說法"]
    ext = ctx.store.add(b"<p>blog</p>", source="https://other.example/post", tool="polite_fetch", kind="page")["id"]
    rep = good(p1, p2)
    rep["onpage"][0]["evidence_ids"] = [ext]
    assert check(ctx, rep) == []  # 只警告不擋（使用者 2026-11-16 決定）
    assert external_only(rep, ctx)["C1"] == ["只引用外部說法"]
    assert any("外部說法" in i["problem"] for i in program_findings(rep, ctx))


# ---- G-46 ----
def test_citation_check(env):
    ctx, *_ = env
    eid = ctx.store.add("<td>網址數 2273 個</td><td>AbC</td>".encode(), source="https://2030.tw/s", tool="polite_fetch",
                        kind="page")["id"]
    ok = [("C1", f'共〔{eid}:"2,273"〕個'), ("C2", f'〔{eid}：「２２７３」〕'), ("C3", f'〔{eid}:"abc"〕')]
    assert citation_warnings(ctx, ok) == []
    warns = citation_warnings(ctx, [("C4", f'〔{eid}:"3,000"〕'), ("C5", '〔E-9999:"x"〕'), ("C6", "沒有固定格式 2,273")])
    assert [w["where"] for w in warns] == ["C4", "C5"] and all(w["level"] == "警告" for w in warns)


# ---- G-61、G-37 ----
@pytest.fixture
def flow_env(env, tmp_path):
    ctx, tools, guard, (p1, p2) = env
    seen = []

    def reviewer(c, inp):
        seen.append(inp)
        return {"status": "passed", "api_calls": 2, "tokens": {"input": 100, "output": 20, "total": 120}, "elapsed_s": 3.0,
                "tools_offered": [],
                "items": [{"sentence": "C2 新聞頁可能用來導流", "problem": "只有 1 頁", "evidence_ids": [p2],
                           "needs_evidence": True, "stale": False}]}
    meta = {"run_id": "t", "model": "m", "at": "now", "site": "https://2030.tw",
            "baseline": {"hash": "abcdef1234567890", "fetched_at": {"sitemap": "2026-11-16T10:00:00+0800"}}}
    flow = ReportFlow(ctx, experience_store=ExperienceStore(tmp_path / "exp.json"), meta=meta, guard=guard,
                      reviewer=reviewer)
    return ctx, tools, guard, flow, seen, (p1, p2)


def test_review_triggered_once_and_saved(flow_env):
    ctx, tools, guard, flow, seen, (p1, p2) = flow_env
    tool = report_tool(flow)
    out = tool.func(good(p1, p2))
    assert out["status"] == "review" and len(seen) == 1 and guard.phase == "revise"
    review = json.loads((ctx.run_dir / "review.json").read_text(encoding="utf-8"))
    first = review["items"][0]
    assert first["source"] == "審查" and first["id"] == "R1" and first["evidence_ids"] == [p2]
    assert review["cost"] == {"api_calls": 2, "tokens": {"input": 100, "output": 20, "total": 120}, "elapsed_s": 3.0}
    # 審查只拿到報告＋引用證據原文，沒有研究過程
    inp = seen[0]
    assert set(inp) == {"report", "evidence"} and {e["id"] for e in inp["evidence"]} == {p1, p2}
    blob = json.dumps(inp, ensure_ascii=False)
    for word in ("board", "tool_calls", "why"):
        assert word not in blob
    assert all(e["text"] for e in inp["evidence"])
    # 修正稿：不再審查；交出後不能再回 ④
    assert tool.func(good(p1, p2))["status"] == "accepted" and len(seen) == 1
    assert tools["polite_fetch"]({"url": "https://2030.tw/x/"})["error"]["code"] == "stop_after_review"


def test_recheck_once_bypasses_reserve_and_streak(flow_env):
    ctx, tools, guard, flow, seen, (p1, p2) = flow_env
    guard.streak = 99
    guard.clock = lambda: guard.started + 110 * 60  # 已進保留的最後 20 分鐘
    assert tools["polite_fetch"]({"url": "https://2030.tw/a/"})["error"]["code"] == "stop_time_limit"
    report_tool(flow).func(good(p1, p2))  # 初稿 → 待修清單
    assert tools["polite_fetch"]({"url": "https://2030.tw/a/"})["ok"]  # 回 ④ 補查（抓即時資料）
    assert guard.recheck_calls == 1
    bad = good(p1, p2)
    bad["offpage"][0]["limits"] = ""
    out = report_tool(flow).func(bad)
    assert out["status"] == "rejected" and out["rejections"] == 1  # report.py 退回只改格式
    assert tools["polite_fetch"]({"url": "https://2030.tw/b/"})["error"]["code"] == "stop_after_review"  # 第二次回 ④ 被擋
    out = report_tool(flow).func(bad)
    assert out["status"] == "accepted_with_issues" and len(seen) == 1
    md = (ctx.run_dir / "report.md").read_text(encoding="utf-8")
    for head in HEADS + ("[檢查未通過]",):
        assert head in md
    assert "網站底稿：hash `abcdef123456`" in md and "sitemap 2026-11-16T10:00:00+0800" in md  # G-54
    saved = json.loads((ctx.run_dir / "report.json").read_text(encoding="utf-8"))
    assert saved["meta"]["revised"] is True and [c["id"] for c in saved["report"]["strategy"]] == ["C1", "C2"]


def test_draft_without_revision_is_kept(flow_env):
    ctx, _, _, flow, _, (p1, p2) = flow_env
    report_tool(flow).func(good(p1, p2))
    assert flow.finalize_pending() and not flow.finalize_pending()
    md = (ctx.run_dir / "report.md").read_text(encoding="utf-8")
    assert "[審查待修未處理]** R1" in md


def test_rejected_revision_is_kept_not_draft(flow_env):
    """修正稿被格式退回後就結束 → 收最後一次修正稿，不退回初稿（code review major 2）。"""
    ctx, _, _, flow, _, (p1, p2) = flow_env
    report_tool(flow).func(good(p1, p2))
    fixed = good(p1, p2)
    fixed["summary"] = "修正稿"
    fixed["offpage"][0]["limits"] = ""
    assert report_tool(flow).func(fixed)["status"] == "rejected"
    assert flow.finalize_pending()
    saved = json.loads((ctx.run_dir / "report.json").read_text(encoding="utf-8"))
    assert saved["report"]["summary"] == "修正稿" and saved["meta"]["revised"] is True
    assert "review_open" not in saved["meta"]


def test_review_failure_still_gives_fix_list(env, tmp_path):
    ctx, _, guard, (p1, p2) = env
    def broken(c, inp):
        raise RuntimeError("API down")
    flow = ReportFlow(ctx, experience_store=ExperienceStore(tmp_path / "e.json"), meta={"site": "s"}, guard=guard,
                      reviewer=broken)
    rep = good(p1, p2)
    rep["offpage"][0]["limits"] = ""
    out = report_tool(flow).func(rep)
    assert out["status"] == "review" and flow.review["status"] == "failed"
    assert any("limits" in i["problem"] and i["source"] == "程式" for i in out["fix_list"])


def test_review_agent_has_no_tools(monkeypatch):
    from seo_agent import review
    from seo_agent.model_env import ModelSettings
    got = {}

    def fake(model, tools, *, system_prompt, message, **kw):
        got.update(tools=tools, prompt=system_prompt, message=message)
        return {"tools_offered": [], "final_response": '說明\n{"items": [{"sentence": "C1", "problem": "p", "evidence_ids": ["E-0001"], "needs_evidence": true}]}',
                "api_calls": 1, "tokens": {"input": 1, "output": 1, "total": 2}, "model": "m"}
    monkeypatch.setattr(review, "run_agent", fake)
    out = review.run_review(ModelSettings(base_url="http://x", api_key="k"), {"input": {"report": {}, "evidence": []}},
                            run_id="r")
    assert got["tools"] == [] and out["status"] == "passed" and out["items"][0]["needs_evidence"] is True
    assert "delegate_task" not in got["prompt"]
    monkeypatch.setattr(review, "run_agent", lambda *a, **k: {**fake(*a, **k), "tools_offered": ["polite_fetch"]})
    assert review.run_review(ModelSettings(base_url="http://x", api_key="k"), {"input": {}}, run_id="r")["status"] == "failed"


def test_registered_research_tools_unchanged(tmp_path):
    from seo_agent.coverage import research_tools
    ctx = Context(tmp_path / "r")
    assert len(build_tools(ctx)) == 7
    tools, _ = research_tools(ctx, "https://2030.tw")
    assert all("why" in t.parameters["properties"] for t in tools)


def test_research_run_records_review_cost(tmp_path, monkeypatch):
    from seo_agent import research
    from seo_agent.model_env import ModelSettings

    def fake_agent(model, tools, *, message, **kw):
        submit = next(t for t in tools if t.name == "submit_report")
        out = submit.func({"summary": "s", "onpage": [], "offpage": [], "actions": [], "unknowns": []})
        assert out["status"] == "review"
        return {"tool_calls": [], "completed": True, "error": None, "api_calls": 10,
                "tokens": {"input": 1000, "output": 100, "total": 1100}}
    monkeypatch.setattr(research, "run_agent", fake_agent)
    calls = []
    reviewer = lambda c, inp: calls.append(1) or {"status": "passed", "items": [], "api_calls": 2,  # noqa: E731
                                                   "tokens": {"input": 50, "output": 5, "total": 55}, "elapsed_s": 1.0}
    site = FakeSite()
    site.search_ok = True
    result = research.run_research(ModelSettings(base_url="http://x", api_key="k"), {"fetch_delay_s": 0},
                                   run_dir=tmp_path / "run-r", transport=site.transport(),
                                   experience_path=tmp_path / "e.json", baseline_root=tmp_path / "b", reviewer=reviewer)
    assert calls == [1] and result["status"] == "passed"  # 初稿照收（沒修正稿），待修清單列為未處理
    rv = result["review"]
    assert rv["triggered"] == 1 and rv["revised"] is False and rv["cost"]["api_calls"] == 2
    assert rv["total_with_review"] == {"api_calls": 12, "tokens": {"input": 1050, "output": 105, "total": 1155}}
    assert (tmp_path / "run-r" / "review.json").exists() and (tmp_path / "run-r" / "report.md").exists()
