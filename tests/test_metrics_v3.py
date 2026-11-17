"""三個評估數字（G-30）、run 摘要欄位（G-31）、依序 3 輪（G-32）、新舊拆題離線測試（G-33）。全部離線。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fixture_site import FakeSite

from seo_agent.coverage import research_tools
from seo_agent.decompose import (
    METHODS,
    build_prompt,
    fake_model,
    leaked_rubric,
    run_compare,
)
from seo_agent.evaluation import evaluate
from seo_agent.experience import ExperienceStore
from seo_agent.grader import load_rubric
from seo_agent.hermes_bridge import ToolLog
from seo_agent.metrics import new_findings, wasted_calls
from seo_agent.sequence import dry_run_fn, run_sequence
from seo_agent.stop import StopGuard
from seo_agent.tools.context import Context


def env(tmp_path, light=None):
    ctx = Context(tmp_path / "run", transport=FakeSite().transport(), delay_s=0, sleep=lambda s: None)
    ctx.light_test_routes = light or {}
    log = ToolLog(guard=StopGuard(ctx), ctx=ctx)
    t = {x.name: (lambda h: (lambda a: json.loads(h(a))))(log.wrap(x)) for x in research_tools(ctx, "https://2030.tw")[0]}
    return ctx, t


# ---- G-30 白做工次數 ----
def test_wasted_calls_counts_only_calls_without_new_evidence(tmp_path):
    route = {"EXP-001": [{"tool": "polite_fetch", "target": {"domain": "2030.tw", "path": "/news/"}}]}
    ctx, t = env(tmp_path, route)
    t["polite_fetch"]({"url": "https://2030.tw/"})           # 新證據
    t["polite_fetch"]({"url": "https://2030.tw/"})           # 同一頁再抓 → 白做工 1
    t["polite_fetch"]({"url": "https://2030.tw/news/", "why": "輕試 EXP-001"})  # 輕試 → 不算
    calls = ctx.read_jsonl(ctx.tool_calls_path)
    assert [c["new_evidence"] for c in calls if c["tool"] == "polite_fetch"] == [True, False, True]
    assert calls[2]["light_test_of"] == "EXP-001"
    assert wasted_calls(calls) == 1


def test_wasted_calls_skips_snapshot_and_guard_blocked():
    rows = [{"tool": "polite_fetch", "new_evidence": False, "same_as_snapshot": True},
            {"tool": "polite_fetch", "new_evidence": None, "blocked_by_guard": True},
            {"tool": "experience", "new_evidence": None},
            {"tool": "submit_report", "new_evidence": None},
            {"tool": "inspect_page", "new_evidence": False},
            {"tool": "polite_fetch", "new_evidence": False, "error": "robots_disallowed"}]
    assert wasted_calls(rows) == 2


def test_key_finding_and_new_findings(tmp_path):
    ctx, t = env(tmp_path)
    t["polite_fetch"]({"url": "https://2030.tw/"})
    b = t["polite_fetch"]({"url": "https://2030.tw/news/a/"})["evidence_id"]
    snap = ctx.store.add(b"snapshot", source="https://2030.tw/sitemap.xml", tool="baseline", kind="page")["id"]
    claims = [{"id": "S1", "text": "首頁有新聞區", "kind": "fact", "evidence_ids": [b]},
              {"id": "S2", "text": "/wordcup/ 是隱藏的娛樂城區，約 2,500 頁", "kind": "fact", "evidence_ids": [b, snap]}]
    rep = {"onpage": claims, "offpage": [], "strategy": claims}
    (ctx.run_dir / "report.json").write_text(json.dumps({"report": rep, "meta": {}}, ensure_ascii=False), encoding="utf-8")
    ev = evaluate(ctx.run_dir)
    kf = ev["key_finding"]
    assert kf["claim_id"] == "S2" and "T01" in kf["rubric_items"]
    assert kf["evidence_id"] == snap and kf["calls"] == 0          # 底稿快照：開始就有
    claims[1]["evidence_ids"] = [b]
    (ctx.run_dir / "report.json").write_text(json.dumps({"report": rep, "meta": {}}, ensure_ascii=False), encoding="utf-8")
    kf = evaluate(ctx.run_dir)["key_finding"]
    assert kf["evidence_id"] == b and kf["calls"] == 2              # fetch(1) + fetch(2)
    assert ev["new_findings"] is None
    ids = [i["id"] for i in load_rubric()["items"]]
    assert new_findings("ypn" + "n" * 11, "nyn" + "n" * 11, ids) == {"count": 1, "items": ["T01"]}


# ---- G-31 run 摘要 ----
def test_run_summary_fields(tmp_path, monkeypatch):
    from seo_agent import research
    from seo_agent.model_env import ModelSettings
    store = ExperienceStore(tmp_path / "exp" / "candidates.jsonl")
    store.save_all([{"id": "EXP-001", "status": "active", "situation": "s", "route": "用 polite_fetch 查", "result": "別走",
                     "avoid_reason": "會誤導", "paired_id": "", "evidence_ids": [], "source_run": "r0",
                     "route_tools": [{"tool": "polite_fetch", "domain": "2030.tw", "path": "/bad/"}]}])

    def fake_agent(model, tools, *, message, log, **kw):
        t = {x.name: (lambda h: (lambda a: json.loads(h(a))))(log.wrap(x)) for x in tools}  # 和真的 Hermes 一樣經過 ToolLog
        a = t["polite_fetch"]({"url": "https://2030.tw/news/a/", "why": "避開 EXP-001"})["evidence_id"]
        t["polite_fetch"]({"url": "https://2030.tw/news/a/"})
        t["polite_fetch"]({"url": "https://2030.tw/private/x"})
        t["submit_report"]({"summary": "s", "onpage": [{"id": "S1", "text": "/wordcup/ 娛樂城區約 2,500 頁", "kind": "fact",
                                                        "evidence_ids": [a]}],
                            "offpage": [], "actions": [], "unknowns": []})
        return {"tool_calls": log.calls, "completed": True, "error": None, "api_calls": 4,
                "tokens": {"input": 400, "output": 40, "total": 440}}
    monkeypatch.setattr(research, "run_agent", fake_agent)
    reviewer = lambda c, inp: {"status": "passed", "items": [], "api_calls": 1,  # noqa: E731
                               "tokens": {"input": 10, "output": 1, "total": 11}, "elapsed_s": 2.0}
    run_dir = tmp_path / "run-s"
    r = research.run_research(ModelSettings(base_url="http://x", api_key="k"), {"fetch_delay_s": 0}, run_dir=run_dir,
                              transport=FakeSite().transport(), experience_path=store.path,
                              baseline_root=tmp_path / "b", reviewer=reviewer)
    assert r["tokens"]["total"] == 440 and r["http_requests"] >= 1 and r["elapsed_s"] >= 0 and r["tool_calls_total"] == 4
    m = r["metrics"]
    assert m["wasted_calls"] >= 1
    assert {"tool": "polite_fetch", "domain": "2030.tw", "path": "/private/x"}.items() <= m["blocked"][0].items()
    assert m["saved_calls"]["count"] == 1 and m["saved_calls"]["items"][0]["experience_id"] == "EXP-001"
    assert r["review"]["cost"]["api_calls"] == 1 and r["review"]["total_with_review"]["tokens"]["total"] == 451
    assert m["key_finding"] is None and m["new_findings"] is None and "score" not in r   # 評估後才回填
    (run_dir / "result.json").write_text(json.dumps(r, ensure_ascii=False, default=str), encoding="utf-8")
    evaluate(run_dir)
    back = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert back["score"]["total"] > 0 and back["score"]["note"] == "只給人看"
    assert back["metrics"]["key_finding"]["claim_id"] == "S1" and back["metrics"]["wasted_calls"] == m["wasted_calls"]


# ---- G-32 依序 3 輪 ----
def test_sequence_order_and_experience_carried(tmp_path):
    order = []

    def run_fn(i, store_path, out_dir):
        store = ExperienceStore(store_path)
        order.append(("run", i, [e["id"] for e in store.active()]))
        run_dir = dry_run_fn(i, store_path, out_dir)
        if i == 1:  # 第 1 輪假裝寫下一條經驗並已通過審核（審核本身另有測試）
            store.save_all([{"id": "EXP-001", "status": "active", "situation": "s", "route": "用 polite_fetch 查",
                             "result": "照走", "avoid_reason": "", "paired_id": "", "evidence_ids": [],
                             "source_run": "dry-r1", "route_tools": []}])
        return run_dir

    from seo_agent import sequence
    real_eval, real_post = sequence.evaluate, sequence.post_run
    sequence.evaluate = lambda d, **kw: order.append(("eval", d.name, kw["prev_run_dir"] and kw["prev_run_dir"].name)) or real_eval(d, **kw)
    sequence.post_run = lambda d, s: order.append(("post", d.name)) or real_post(d, s)
    try:
        out = run_sequence(3, run_fn=run_fn, out_dir=tmp_path / "seq", direct_fn=lambda d: "direct", log=lambda s: None)
    finally:
        sequence.evaluate, sequence.post_run = real_eval, real_post
    assert order == [("run", 1, []), ("eval", "dry-r1", None), ("post", "dry-r1"),
                     ("run", 2, ["EXP-001"]), ("eval", "dry-r2", "dry-r1"), ("post", "dry-r2"),
                     ("run", 3, ["EXP-001"]), ("eval", "dry-r3", "dry-r2"), ("post", "dry-r3")]
    assert out["steps"][-1] == {"round": "direct", "step": "direct", "out": "direct"}
    assert (tmp_path / "seq" / "sequence.json").exists()
    with pytest.raises(FileExistsError):  # Run 1 一定從空經驗開始
        run_sequence(1, run_fn=run_fn, out_dir=tmp_path / "seq", log=lambda s: None)


def test_sequence_cli_dry_run(tmp_path):
    from seo_agent.sequence import main
    assert main(["--dry-run", "--out", str(tmp_path / "d")]) == 0
    steps = json.loads((tmp_path / "d" / "sequence.json").read_text(encoding="utf-8"))["steps"]
    assert [s["step"] for s in steps] == ["research", "evaluate", "post_run"] * 3 + ["direct"]


def _seq_run_fn(order):
    def run_fn(i, store_path, out_dir):
        store = ExperienceStore(store_path)
        order.append(("run", i, [e["id"] for e in store.active()]))
        run_dir = dry_run_fn(i, store_path, out_dir)
        if i == 1:
            store.save_all([{"id": "EXP-001", "status": "active", "situation": "s", "route": "用 polite_fetch 查",
                             "result": "照走", "avoid_reason": "", "paired_id": "", "evidence_ids": [],
                             "source_run": "dry-r1", "route_tools": []}])
        return run_dir
    return run_fn


def _seq_order(order, fn):
    from seo_agent import sequence
    real_eval = sequence.evaluate
    sequence.evaluate = lambda d, **kw: order.append(("eval", d.name, kw["prev_run_dir"] and kw["prev_run_dir"].name)) or real_eval(d, **kw)
    try:
        return fn()
    finally:
        sequence.evaluate = real_eval


def _strip(steps):
    return [{k: (Path(v).name if k == "run_dir" else v) for k, v in s.items()} for s in steps]


# ---- 決策 #52 接續 ----
def test_sequence_continue_equals_one_shot(tmp_path):
    a, b = [], []
    meta = {"runtime": "dry"}
    full = _seq_order(a, lambda: run_sequence(3, run_fn=_seq_run_fn(a), out_dir=tmp_path / "full", log=lambda s: None,
                                              direct_fn=lambda d: "direct", meta=meta))
    _seq_order(b, lambda: run_sequence(2, run_fn=_seq_run_fn(b), out_dir=tmp_path / "part", log=lambda s: None, meta=meta))
    part = _seq_order(b, lambda: run_sequence(1, run_fn=_seq_run_fn(b), out_dir=tmp_path / "part", log=lambda s: None,
                                              direct_fn=lambda d: "direct", resume=True, meta=meta))
    assert a == b  # 每輪帶入的經驗、評分時的上一輪都一樣
    assert _strip(full["steps"]) == _strip(part["steps"]) and part["rounds"] == 3
    again = run_sequence(0, run_fn=_seq_run_fn([]), out_dir=tmp_path / "part", log=lambda s: None,
                         direct_fn=lambda d: "direct", resume=True, meta=meta)
    assert sum(s["round"] == "direct" for s in again["steps"]) == 1  # 對照組只跑一次


def test_sequence_continue_refusals(tmp_path):
    from seo_agent.sequence import main
    def run(**kw):
        return run_sequence(1, run_fn=_seq_run_fn([]), out_dir=tmp_path / "s", log=lambda s: None, **kw)
    with pytest.raises(FileNotFoundError):  # 沒有前面的紀錄
        run(resume=True)
    run(meta={"runtime": "sim", "model": "a"})
    with pytest.raises(RuntimeError, match="model"):  # 換了模型
        run(resume=True, meta={"runtime": "sim", "model": "b"})
    (tmp_path / "s" / "dry-r2").mkdir()
    with pytest.raises(RuntimeError, match="資料夾已存在"):  # 上次中斷在第 2 輪
        run(resume=True, meta={"runtime": "sim", "model": "a"})
    (tmp_path / "s" / "dry-r2").rmdir()
    with (tmp_path / "s" / "experience" / "candidates.jsonl").open("a", encoding="utf-8") as f:
        f.write("\n")
    with pytest.raises(RuntimeError, match="經驗庫"):  # 最後一輪結束後經驗庫被改過
        run(resume=True, meta={"runtime": "sim", "model": "a"})
    seq = tmp_path / "s" / "sequence.json"
    d = json.loads(seq.read_text(encoding="utf-8"))
    d["steps"] = [x for x in d["steps"] if x["step"] != "post_run"]
    seq.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(RuntimeError, match="沒有完整結束"):  # 最後一輪缺下架判定／寫入審核
        run(resume=True, meta={"runtime": "sim", "model": "a"})
    for argv in (["--dry-run", "--continue", "--rounds", "1"], ["--dry-run", "--continue", "--out", str(tmp_path / "x")]):
        with pytest.raises(SystemExit):  # --continue 要同時給 --out 與 --rounds
            main(argv)


# ---- G-33 新舊拆題 ----
def test_decompose_offline(tmp_path):
    card = tmp_path / "data_card.md"
    card.write_text("## 資料卡：2030.tw\n- sitemap 1,234 頁\n- 選單 12 個連結", encoding="utf-8")
    s = run_compare(card, tmp_path / "out", model=fake_model, repeats=3)
    assert [(r["method"], r["n"]) for r in s["runs"]] == [("old", 1), ("new", 1), ("old", 2), ("new", 2), ("old", 3), ("new", 3)]
    assert all((tmp_path / "out" / r["file"]).exists() for r in s["runs"])
    for m in METHODS:
        p = build_prompt(m, card.read_text(encoding="utf-8"))
        assert "1,234" in p and leaked_rubric(p) == []
        assert "rubric" not in p.lower() and "評分表" not in p
    assert "差異先" in s["prompts"]["new"] and "骨架先" in s["prompts"]["old"]


def test_decompose_refuses_rubric_leak(tmp_path):
    point = load_rubric()["items"][0]["point"]
    card = tmp_path / "c.md"
    card.write_text(f"資料卡\n{point}", encoding="utf-8")
    with pytest.raises(ValueError):
        run_compare(card, tmp_path / "o", model=fake_model, repeats=1)


def test_sim_effort_flag():
    from seo_agent import sim
    try:
        sim.EFFORT = None
        assert "--effort" not in sim.claude_cmd("m", system_prompt_file=Path("p"), tools="")
        sim.EFFORT = "max"
        cmd = sim.claude_cmd("m", system_prompt_file=Path("p"), tools="")
        assert cmd[cmd.index("--effort") + 1] == "max"
    finally:
        sim.EFFORT = None


def test_sim_reviewer_model(tmp_path, monkeypatch):
    from seo_agent import sim
    seen = []
    monkeypatch.setattr(sim, "run_claude", lambda cmd, msg, **k: seen.append(cmd) or {"final_response": '{"items": []}'})
    sim.sim_reviewer("claude-opus-5-5", tmp_path / "r1")(None, {"report": {}})
    assert seen[0][seen[0].index("--model") + 1] == "claude-opus-5-5"
