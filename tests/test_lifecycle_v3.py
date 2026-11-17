"""使用中經驗的判定與下架（G-21～G-28）。登記＝研究 Tool 的 why 寫經驗編號；推翻＝報告 experience.overturned（決策 #71）。
全部離線，用假站與手寫報告。"""
from __future__ import annotations

import json

import pytest
from fixture_site import FakeSite

from seo_agent.coverage import research_tools
from seo_agent.evaluation import evaluate
from seo_agent.experience import ExperienceStore, reject
from seo_agent.experience import main as exp_cli
from seo_agent.hermes_bridge import ToolLog
from seo_agent.lifecycle import judge_run, post_run
from seo_agent.stop import StopGuard
from seo_agent.tools.context import Context


def entry(i, result="照走", avoid="", paired="", tools=(("polite_fetch", "2030.tw", "/"),), status="active", **kw):
    return {"id": f"EXP-{i:03d}", "status": status, "situation": f"情況{i}", "route": f"用 {tools[0][0]} 查",
            "result": result, "avoid_reason": avoid, "paired_id": paired, "evidence_ids": [], "source_run": "r0",
            "route_tools": [{"tool": t, "domain": d, "path": p} for t, d, p in tools], **kw}


@pytest.fixture
def store(tmp_path):
    return ExperienceStore(tmp_path / "experience" / "candidates.jsonl")


class Run:
    """一個假 run：照腳本呼叫 Tool，寫報告、評分，再判定。"""

    def __init__(self, tmp_path, name, store):
        self.store = store
        self.ctx = Context(tmp_path / name, transport=FakeSite().transport(), delay_s=0, sleep=lambda s: None)
        self.ctx.light_test_routes = {e["id"]: [{"tool": t["tool"], "target": {"domain": t["domain"], "path": t["path"]}}
                                                for t in e["route_tools"]]
                                      for e in store.active() if e["result"] == "別走" and e["avoid_reason"] == "查不到"}
        log = ToolLog(guard=StopGuard(self.ctx), ctx=self.ctx)
        tools, _ = research_tools(self.ctx, "https://2030.tw")
        self.t = {x.name: (lambda h: (lambda a: json.loads(h(a))))(log.wrap(x)) for x in tools}
        self.overturned = []

    def fetch(self, url, why=None):
        return self.t["polite_fetch"]({"url": url, **({"why": why} if why else {})})

    def overturn(self, eid, evidence_ids):
        self.overturned.append({"experience_id": eid, "evidence_ids": list(evidence_ids), "why": "網站已變"})

    def finish(self, cited=(), wrong_claim=None, read=None):
        claims = [{"id": f"S{i}", "text": "首頁有新聞區", "kind": "fact", "evidence_ids": [e]} for i, e in enumerate(cited, 1)]
        if wrong_claim:
            claims.append({"id": "SX", "text": "娛樂城區沒有 sitemap", "kind": "fact", "evidence_ids": [wrong_claim]})
        rep = {"summary": "", "onpage": claims, "offpage": [], "actions": [], "unknowns": [],
               "experience": {"overturned": self.overturned}}
        rep["strategy"] = claims
        meta = {"experience_read": {"entry_ids": read if read is not None else [e["id"] for e in self.store.active()]}}
        (self.ctx.run_dir / "report.json").write_text(json.dumps({"report": rep, "meta": meta}, ensure_ascii=False),
                                                      encoding="utf-8")
        evaluate(self.ctx.run_dir)
        return judge_run(self.ctx.run_dir, self.store)


def verdict(rec, eid):
    return next(r for r in rec["results"] if r["id"] == eid)["verdict"]


# ---- G-22 ----
def test_used_means_why_on_route_tool_call(tmp_path, store):
    store.save_all([entry(1), entry(2), entry(3, tools=(("web_search", "web_search", "x"),))])
    r = Run(tmp_path, "r1", store)
    r.t["domain_info"]({"domain": "2030.tw", "why": "照 EXP-003 查"})  # domain_info 不在 EXP-003 路線上 → 不算
    a = r.fetch("https://2030.tw/", why="照 EXP-001、EXP-002 查")["evidence_id"]
    rec = r.finish(cited=[a])
    assert verdict(rec, "EXP-001") == "有用到＋有新東西" and verdict(rec, "EXP-002") == "有用到＋有新東西"
    assert verdict(rec, "EXP-003") == "沒用到"


def test_later_calls_without_why_do_not_count(tmp_path, store):
    """why 寫過一次編號後，之後沒寫編號的同類呼叫不算進這條經驗（code review major 4）。"""
    store.save_all([entry(1)])
    r = Run(tmp_path, "r1", store)
    r.fetch("https://2030.tw/", why="EXP-001")
    later = r.fetch("https://2030.tw/news/")["evidence_id"]  # 無關的抓取
    rec = r.finish(wrong_claim=later)
    assert verdict(rec, "EXP-001") == "有用到但沒新東西"
    assert store.get("EXP-001")["status"] == "active"


def test_fetch_before_registration_does_not_count(tmp_path, store):
    store.save_all([entry(1)])
    r = Run(tmp_path, "r1", store)
    a = r.fetch("https://2030.tw/")["evidence_id"]
    r.t["web_search"]({"query": "site:2030.tw", "why": "EXP-001"})
    assert verdict(r.finish(cited=[a]), "EXP-001") == "沒用到"


# ---- G-25 ----
def _used_no_new(tmp_path, store, name):
    r = Run(tmp_path, name, store)
    r.fetch("https://2030.tw/", why="EXP-001")
    return r.finish(cited=[])


def _unused(tmp_path, store, name):
    r = Run(tmp_path, name, store)
    r.fetch("https://2030.tw/")   # why 沒寫經驗編號 → 沒用到
    return r.finish()


def test_no_value_streak(tmp_path, store):
    store.save_all([entry(1)])
    assert verdict(_used_no_new(tmp_path, store, "r1"), "EXP-001") == "有用到但沒新東西"
    assert verdict(_unused(tmp_path, store, "r2"), "EXP-001") == "沒用到"       # 不算、也不中斷
    rec = _used_no_new(tmp_path, store, "r3")
    e = store.get("EXP-001")
    assert verdict(rec, "EXP-001") == "下架" and e["status"] == "retired" and e["retired_reason"] == "no_value"
    assert "EXP-001" not in (store.path.parent / "notes.md").read_text(encoding="utf-8")


def test_unused_three_times_stays(tmp_path, store):
    store.save_all([entry(1)])
    for n in ("r1", "r2", "r3"):
        _unused(tmp_path, store, n)
    assert store.get("EXP-001")["status"] == "active" and store.get("EXP-001")["unused_runs"] == 3


def test_new_stuff_resets_streak(tmp_path, store):
    store.save_all([entry(1)])
    _used_no_new(tmp_path, store, "r1")
    r = Run(tmp_path, "r2", store)
    a = r.fetch("https://2030.tw/", why="EXP-001")["evidence_id"]
    r.finish(cited=[a])
    _used_no_new(tmp_path, store, "r3")
    assert store.get("EXP-001")["status"] == "active" and store.get("EXP-001")["no_value_streak"] == 1


def test_judged_wrong_retires(tmp_path, store):
    store.save_all([entry(1)])
    r = Run(tmp_path, "r1", store)
    a = r.fetch("https://2030.tw/", why="EXP-001")["evidence_id"]
    r.finish(wrong_claim=a)
    assert store.get("EXP-001")["retired_reason"] == "judged_wrong"


def test_no_judgement_before_grade(tmp_path, store):
    store.save_all([entry(1)])
    r = Run(tmp_path, "r1", store)
    (r.ctx.run_dir / "report.json").write_text(json.dumps({"report": {}, "meta": {}}), encoding="utf-8")
    assert judge_run(r.ctx.run_dir, store)["status"] == "waiting_for_grade" and "history" not in store.get("EXP-001")


# ---- G-23 ----
NF = dict(result="別走", avoid="查不到", tools=(("polite_fetch", "2030.tw", "/news/"),))


def test_light_test_overturn_retires(tmp_path, store):
    store.save_all([entry(1, **NF)])
    r = Run(tmp_path, "r1", store)
    out = r.fetch("https://2030.tw/news/", why="輕試 EXP-001")
    assert out["light_test_of"] == "EXP-001"
    r.overturn("EXP-001", [out["evidence_id"]])
    rec = r.finish()
    e = store.get("EXP-001")
    assert verdict(rec, "EXP-001") == "下架" and e["retired_reason"] == "overturned" and e["retired_note"] == "網站已變"


def test_light_test_without_overturn_stays(tmp_path, store):
    store.save_all([entry(1, **NF)])
    r = Run(tmp_path, "r1", store)
    ev = r.fetch("https://2030.tw/news/", why="EXP-001")["evidence_id"]
    rec = r.finish(cited=[ev])          # 被報告引用但沒標推翻 → 仍不通
    assert verdict(rec, "EXP-001") == "仍不通" and store.get("EXP-001")["status"] == "active"


def test_no_light_test_and_error_light_test(tmp_path, store):
    store.save_all([entry(1, **NF), entry(2, result="別走", avoid="查不到", tools=(("polite_fetch", "2030.tw", "/private/x"),))])
    r = Run(tmp_path, "r1", store)
    r.fetch("https://2030.tw/private/x", why="EXP-002")    # robots 不准 → 輕試回傳 Tool 錯誤
    rec = r.finish()
    assert verdict(rec, "EXP-001") == "沒用到" and verdict(rec, "EXP-002") == "不算"
    assert rec["blocked"] == [{"domain": "2030.tw", "path": "/private/x"}]
    assert all(e["status"] == "active" for e in store.load())


def test_overturn_needs_real_evidence(tmp_path, store):
    """推翻不附或附不存在的 Evidence ID → 不下架（格式檢查之後照收的報告也一樣，code review major 3）。"""
    store.save_all([entry(1), entry(2)])
    r = Run(tmp_path, "r1", store)
    r.fetch("https://2030.tw/news/")  # why 沒寫編號
    r.overturn("EXP-001", [])
    r.overturn("EXP-002", ["E-9999"])
    rec = r.finish()
    assert verdict(rec, "EXP-001") == "沒用到" and verdict(rec, "EXP-002") == "沒用到"
    assert all(e["status"] == "active" for e in store.load())


def test_overturn_without_light_evidence_ignored(tmp_path, store):
    store.save_all([entry(1, **NF)])
    r = Run(tmp_path, "r1", store)
    r.fetch("https://2030.tw/news/", why="EXP-001")
    other = r.fetch("https://2030.tw/")["evidence_id"]
    r.overturn("EXP-001", [other])
    assert verdict(r.finish(), "EXP-001") == "仍不通"


# ---- G-24 ----
def test_planted_wrong_experience_overturned(tmp_path, store):
    store.save_all([entry(1, situation="故意放錯：首頁沒有任何新聞連結")])
    r = Run(tmp_path, "r1", store)
    a = r.fetch("https://2030.tw/", why="EXP-001")["evidence_id"]
    r.overturn("EXP-001", [a])
    r.finish()
    assert store.get("EXP-001")["retired_reason"] == "overturned"


# ---- G-26、G-28 ----
def test_reject_and_pair_follows(store):
    store.save_all([entry(1), entry(2, result="別走", avoid="會誤導", paired="EXP-001")])
    out = reject(store, "EXP-001", "這條方法在新站不適用")
    e1, e2 = store.get("EXP-001"), store.get("EXP-002")
    assert out["followed"] == ["EXP-002"] and e1["retired_reason"] == "rejected"
    assert e1["human_feedback"][0]["why"] == "這條方法在新站不適用"
    assert e2["retired_reason"] == "rejected" and "配對經驗已下架" in e2["retired_note"]
    again = reject(store, "EXP-001", "補充理由")
    assert again["retired"] is False and len(store.get("EXP-001")["human_feedback"]) == 2
    assert store.get("EXP-001")["retired_reason"] == "rejected"


def test_pair_follows_no_value(tmp_path, store):
    store.save_all([entry(1, no_value_streak=1), entry(2, result="別走", avoid="會誤導", paired="EXP-001")])
    rec = _used_no_new(tmp_path, store, "r1")
    assert rec["followed_pairs"] == ["EXP-002"] and store.get("EXP-002")["retired_reason"] == "no_value"


def test_cli_reject_only(store, capsys):
    store.save_all([entry(1)])
    assert exp_cli(["--store", str(store.path), "reject", "EXP-001", "不要了"]) == 0
    assert store.get("EXP-001")["retired_reason"] == "rejected"
    for cmd in ("approve", "disable"):
        with pytest.raises(SystemExit):
            exp_cli(["--store", str(store.path), cmd, "EXP-001"])


# ---- G-27 ----
def test_autonomy_approval_list():
    from seo_agent import ROOT
    acts = json.loads((ROOT / "config" / "autonomy.json").read_text(encoding="utf-8"))["approval_required_actions"]
    assert "經驗設為正式" not in acts
    assert {"修改寫入審核與下架的規則", "修改 Tool 程式", "永久刪除經驗", "修改評分表", "修改正解檔"} <= set(acts)


# ---- G-21：整條流程 ----
def test_full_loop_research_then_post_run(tmp_path, monkeypatch, store):
    from seo_agent import research
    from seo_agent.model_env import ModelSettings
    store.save_all([entry(1), entry(9, status="retired", retired_reason="rejected")])
    seen = {}

    def fake_agent(model, tools, *, message, system_prompt, **kw):
        seen["prompt"] = system_prompt
        t = {x.name: x.func for x in tools}
        a = t["polite_fetch"]({"url": "https://2030.tw/", "why": "照 EXP-001 查"})["evidence_id"]
        t["experience"]({"action": "propose", "situation": "首頁選單", "route": "1. sitemap_tree：搜選單分區的網址，因為主 sitemap 可能漏列子 sitemap\n2. inspect_page：看選單連結與 canonical，因為要分清刻意不收錄或漏列", "result": "照走",
                         "evidence_ids": [a]})
        t["submit_report"]({"summary": "s", "onpage": [{"id": "S1", "text": "首頁有新聞區", "kind": "fact",
                                                        "evidence_ids": [a]}],
                            "offpage": [], "actions": [], "unknowns": [], "experience": {"used": ["EXP-001"]}})
        return {"tool_calls": [], "completed": True, "error": None, "api_calls": 1, "tokens": {}}
    monkeypatch.setattr(research, "run_agent", fake_agent)
    reviewer = lambda c, inp: {"status": "passed", "items": [], "api_calls": 0, "tokens": {}, "elapsed_s": 0}  # noqa: E731
    run_dir = tmp_path / "run-x"
    result = research.run_research(ModelSettings(base_url="http://x", api_key="k"), {"fetch_delay_s": 0}, run_dir=run_dir,
                                   transport=FakeSite().transport(), experience_path=store.path,
                                   baseline_root=tmp_path / "b", reviewer=reviewer)
    assert "EXP-001" in seen["prompt"] and "EXP-009" not in seen["prompt"]       # 已下架不讀入
    notes = seen["prompt"].split("## 經驗筆記")[-1]   # Skill 本文的舊說法在第 10 步重寫時一起改
    assert notes.startswith("（使用中）") and not any(w in notes for w in ("正式", "候選", "停用"))
    meta = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))["meta"]
    assert meta["experience_read"]["entry_ids"] == ["EXP-001"] and len(meta["experience_read"]["notes_sha256"]) == 64
    assert result["experience_read"] == meta["experience_read"] and store.get("EXP-002") is None  # 新路線還沒進經驗檔
    assert post_run(run_dir, store)["audit"]["status"] == "waiting_for_grade"
    evaluate(run_dir)
    out = post_run(run_dir, store)
    assert out["audit"]["results"][0]["passed"] and store.get("EXP-010")["status"] == "active"
