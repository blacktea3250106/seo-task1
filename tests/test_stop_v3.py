"""停止條件（G-34、G-40、G-35、G-36、G-38）。全部離線，不實跑研究。"""
from __future__ import annotations

import json

import pytest
from fixture_site import FakeSite

from seo_agent.hermes_bridge import Tool, ToolLog
from seo_agent.stop import SUBMIT_ACTIONS, StopGuard
from seo_agent.tools import build_tools
from seo_agent.tools.context import Context


@pytest.fixture
def env(tmp_path):
    ctx = Context(tmp_path / "run", transport=FakeSite().transport(), delay_s=0, sleep=lambda s: None)
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard, ctx=ctx)
    tools = {t.name: (lambda h: (lambda a: json.loads(h(a))))(log.wrap(t)) for t in build_tools(ctx)}
    return ctx, guard, log, tools


# ---- G-34：輕試＝why 寫過別走（查不到）經驗編號後，同 Tool、同目標的 1 次呼叫（決策 #71）----
def test_light_tests_do_not_count(env):
    ctx, guard, log, tools = env
    routes = {f"EXP-00{i}": [{"tool": "polite_fetch", "target": {"domain": "2030.tw", "path": f"/gone{i}/"}}] for i in range(5)}
    ctx.light_test_routes = routes
    for i in range(5):
        out = tools["polite_fetch"]({"url": f"https://2030.tw/gone{i}/", "why": f"輕試 EXP-00{i}"})  # FakeSite 回 404
        assert out.get("light_test_of") == f"EXP-00{i}"
    assert guard.streak == 0
    calls = [c for c in ctx.read_jsonl(ctx.tool_calls_path) if c["tool"] == "polite_fetch"]
    assert [c["light_test_of"] for c in calls] == [f"EXP-00{i}" for i in range(5)]


def test_light_test_needs_registration_and_counts_once(env):
    ctx, guard, log, tools = env
    ctx.light_test_routes = {"EXP-001": [{"tool": "polite_fetch", "target": {"domain": "2030.tw", "path": "/gone/"}}]}
    tools["polite_fetch"]({"url": "https://2030.tw/gone/"})  # 沒登記 → 一般呼叫（新網址算進展）
    tools["domain_info"]({"domain": "2030.tw", "why": "順便登記 EXP-001"})  # 之前的 why 寫過也算登記
    assert tools["polite_fetch"]({"url": "https://2030.tw/gone/"})["light_test_of"] == "EXP-001"
    streak = guard.streak
    assert "light_test_of" not in tools["polite_fetch"]({"url": "https://2030.tw/gone/"})  # 第 2 次不再免計
    assert guard.streak == streak + 1


# ---- G-40 ----
def test_seven_research_tools_and_two_submit_actions(env):
    ctx, guard, log, tools = env
    assert len(build_tools(ctx)) == 7 and not set(SUBMIT_ACTIONS) & set(tools)
    assert SUBMIT_ACTIONS == ("submit_report", "experience")
    before = len(ctx.store.ids())
    for name in SUBMIT_ACTIONS:
        for _ in range(6):
            log.wrap(Tool(name, "", {}, lambda a: {"ok": True}))({})
    assert guard.streak == 0 and len(ctx.store.ids()) == before  # 不計入、不產生衍生證據


# ---- G-38 ----
@pytest.mark.parametrize("error,status,label", [(None, "incomplete", "未完成"), ("APIError: 529 overloaded", "interrupted", "中斷")])
def test_unfinished_runs(tmp_path, monkeypatch, error, status, label):
    from seo_agent import research
    from seo_agent.model_env import ModelSettings

    def fake_agent(model, tools, **kw):
        by = {t.name: t.func for t in tools}
        by["polite_fetch"]({"url": "https://2030.tw/news/a/", "why": "看新聞頁"})
        return {"tool_calls": [], "completed": False, "error": error}
    monkeypatch.setattr(research, "run_agent", fake_agent)
    run_dir = tmp_path / "run-x"
    result = research.run_research(ModelSettings(base_url="http://x", api_key="k"), {"fetch_delay_s": 0},
                                   run_dir=run_dir, transport=FakeSite().transport(),
                                   experience_path=tmp_path / "exp.json", baseline_root=tmp_path / "baselines")
    assert result["status"] == status and result["status_label"] == label
    data = json.loads((run_dir / "report_incomplete.json").read_text(encoding="utf-8"))
    assert data["meta"]["status"] == "未完成" and "/news/" in data["coverage"]["sections_read"]
    assert data["evidence"] and (run_dir / "evidence.jsonl").exists()
    assert "讀過的資料卡分區" in (run_dir / "report_incomplete.md").read_text(encoding="utf-8")
    assert result["coverage"]["sections_read"] == ["/news/"] and "why_filled" in result  # fake_agent 不經 ToolLog，不寫紀錄


# ---- 決策 #56：衍生證據存原樣結果，進展指紋仍用換 <arg> 的穩定版 ----
def _fake_text_match(args):
    hits = {"娛樂城": 3, "出金": 2}
    return {"ok": True, "keywords": args["keywords"], "results": {"E-0001": {
        k: {"exact": hits.get(k, 0), "loose": hits.get(k, 0), "variants": {k: hits.get(k, 0)} if hits.get(k) else {}}
        for k in args["keywords"]}}}


def test_derived_evidence_keeps_every_keyword(env):
    ctx, guard, log, tools = env
    call = log.wrap(Tool("text_match", "", {}, _fake_text_match))
    out = json.loads(call({"keywords": ["娛樂城", "出金"]}))
    saved = json.loads(ctx.store.read(out["derived_evidence_id"]))
    assert set(saved["results"]["E-0001"]) == {"娛樂城", "出金"}
    assert saved["results"]["E-0001"]["出金"]["exact"] == 2 and saved["keywords"] == ["娛樂城", "出金"]
    assert "<arg>" not in ctx.store.read(out["derived_evidence_id"]).decode("utf-8")
    assert guard.streak == 0


def test_zero_hit_keyword_swap_still_same_fingerprint(env):
    ctx, guard, log, tools = env
    call = log.wrap(Tool("text_match", "", {}, _fake_text_match))
    first = json.loads(call({"keywords": ["百家樂"]}))  # 零命中：空結果不算進展
    assert guard.streak == 1
    second = json.loads(call({"keywords": ["老虎機"]}))  # 換字的零命中查詢：指紋相同，仍不算進展
    assert guard.streak == 2
    a, b = (ctx.store.get(o["derived_evidence_id"]) for o in (first, second))
    assert a["meta"]["fingerprint"] == b["meta"]["fingerprint"] and a["sha256"] != b["sha256"]
    assert "老虎機" in ctx.store.read(b["id"]).decode("utf-8")


def test_legacy_snapshot_without_fingerprint_still_matches(env):
    """舊底稿的衍生證據存的是穩定版、沒有 meta.fingerprint：sha256 即指紋，重查同結果仍算和底稿一樣（決策 #56）。"""
    from seo_agent.stop import derived_body
    ctx, guard, log, tools = env
    args = {"keywords": ["娛樂城", "出金"]}
    _, stable, fingerprint = derived_body("text_match", args, _fake_text_match(args))
    old = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    item = ctx.store.add(old, source="snapshot", tool="text_match", kind="derived", suffix=".json", meta={"snapshot": True})
    assert item["sha256"] == fingerprint
    guard.seed_snapshot()
    out = json.loads(log.wrap(Tool("text_match", "", {}, _fake_text_match))(args))
    assert out.get("same_as_snapshot") and guard.streak == 1
