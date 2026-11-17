"""實驗 shortfix（決策 #67，只模擬路徑）：交初稿、審查出待修清單後，研究 session 結束，另開短 session 修正＋寫經驗。
全部離線：假網站、假審查、假執行者（經 ToolServer socket 呼叫專案 Tool），不叫模型。"""
from __future__ import annotations

import json
import os
import socket

import pytest
from fixture_site import FakeSite

from seo_agent import sim

# 模擬 runner 用 Unix socket 與 shell 假 CLI，Windows 不支援；正式 Hermes 路徑不受影響
pytestmark = pytest.mark.skipif(os.name == "nt", reason="模擬 runner 只支援 macOS／Linux")

REPORT = {"summary": "s", "onpage": [], "offpage": [], "actions": [], "limits": {}, "process": {}}


def call(sock_path: str, name: str, args: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    f = s.makefile("rwb")
    f.write((json.dumps({"op": "call", "name": name, "args": args}) + "\n").encode())
    f.flush()
    resp = json.loads(f.readline())
    s.close()
    return json.loads(resp["text"])


@pytest.fixture
def harness(tmp_path, monkeypatch):
    import seo_agent.research as research
    real_open = research.open_session
    site = FakeSite()
    site.search_ok = True
    monkeypatch.setattr(research, "open_session", lambda model, payload, *, run_dir, reviewer: real_open(
        model, {**payload, "fetch_delay_s": 0}, run_dir=run_dir, reviewer=reviewer, transport=site.transport(),
        experience_path=tmp_path / "e.json", baseline_root=tmp_path / "b"))
    reviews = []
    monkeypatch.setattr(sim, "sim_reviewer", lambda model, run_dir: lambda c, inp: reviews.append(1) or {
        "status": "passed", "items": [{"sentence": "C1", "problem": "措辭太滿", "evidence_ids": [],
                                       "needs_evidence": False}],
        "api_calls": 1, "tokens": {"input": 5, "output": 1, "total": 6}, "elapsed_s": 0.1})
    sessions: list[dict] = []

    def fake_cli(model, message, *, system_prompt_file, cwd, timeout_s, transcript, mcp=None, mcp_config=None,
                 max_turns=None):
        sock = mcp["args"][-1]
        got = {"message": message, "transcript": transcript.name, "results": []}
        sessions.append(got)
        transcript.write_text(json.dumps({"session": len(sessions)}) + "\n", encoding="utf-8")
        if len(sessions) == 1:  # 研究 session：交初稿，之後還想再查
            got["results"].append(call(sock, "submit_report", REPORT))
            got["results"].append(call(sock, "polite_fetch", {"url": "https://2030.tw/x/"}))
            tokens = {"input": 1000, "output": 100, "total": 1100}
        else:  # 修正 session：交修正稿直到收下（格式退回最多 1 次）
            for _ in range(3):
                r = call(sock, "submit_report", REPORT)
                got["results"].append(r)
                if r.get("ok"):
                    break
            tokens = {"input": 200, "output": 20, "total": 220}
        return {"model": model, "tools_offered": ["mcp__seo__submit_report"], "tools_used": [], "api_calls": 3,
                "final_response": "完成", "completed": True, "num_turns": 3, "stop_reason": "success",
                "cost_usd_equiv": 0.5, "tokens": tokens, "error": None, "runtime": sim.RUNTIME, "runner": sim.RUNNER,
                "simulated": True, "exit_code": 0, "elapsed_s": 10.0 * len(sessions)}
    monkeypatch.setattr(sim, "run_agent_cli", fake_cli)
    return tmp_path / "run", sessions, reviews


def test_shortfix_off_is_unchanged(harness, monkeypatch):
    run_dir, sessions, reviews = harness
    monkeypatch.delenv("SEO_EXPERIMENT", raising=False)
    r = sim.run_research_sim("m", {"total_minutes": 1}, run_dir=run_dir)
    assert len(sessions) == 1 and reviews == [1]
    first, again = sessions[0]["results"]
    assert first["status"] == "review" and first["fix_list"]  # 待修清單照舊回給同一個 session
    assert again.get("error") != "session_closed"
    job = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))
    assert "phases" not in r and "experiment" not in job and "experiments" not in job and "experiments" not in r
    assert not (run_dir / "sim_transcript_fix.jsonl").exists() and r["status"] == "passed"
    assert r["review"]["revised"] is False  # 沒交修正稿：初稿照收（finalize_pending）


def test_shortfix_splits_sessions(harness, monkeypatch):
    run_dir, sessions, reviews = harness
    monkeypatch.setenv("SEO_EXPERIMENT", "shortfix")
    r = sim.run_research_sim("m", {"total_minutes": 1}, run_dir=run_dir)
    assert len(sessions) == 2 and reviews == [1]  # 審查只跑 1 次
    first, again = sessions[0]["results"]
    assert first["status"] == "review_deferred" and "fix_list" not in first  # 待修清單不回給研究 session
    assert again["error"] == "session_closed"  # 研究 session 交初稿後不能再用 Tool
    msg = sessions[1]["message"]
    assert msg.startswith((run_dir / "message.md").read_text(encoding="utf-8"))  # 原任務訊息
    assert "措辭太滿" in msg and '"summary": "s"' in msg and "E-0001｜" in msg  # 待修清單、初稿、Evidence 索引
    assert (run_dir / "message_fix.md").read_text(encoding="utf-8") == msg
    assert sessions[1]["results"][-1]["ok"]  # 修正稿走原本的 final 規則收下
    assert r["status"] == "passed" and r["review"]["revised"] is True and r["review"]["triggered"] == 1
    ph = r["phases"]
    assert ph["research"]["tool_calls"] == 1 and ph["fix"]["tool_calls"] == len(sessions[1]["results"])
    assert ph["research"]["transcript"] == "sim_transcript.jsonl" and ph["fix"]["transcript"] == "sim_transcript_fix.jsonl"
    assert r["tokens"] == ph["total"]["tokens"] == {"input": 1200, "output": 120, "total": 1320}
    assert r["elapsed_s"] == 30.0 and r["api_calls"] == 6 and r["tool_calls_total"] == ph["total"]["tool_calls"]
    assert (run_dir / "sim_transcript.jsonl").exists() and (run_dir / "sim_transcript_fix.jsonl").exists()
    saved = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert saved["phases"] == ph
    job = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))
    assert job["experiments"] == ["shortfix"] and "experiment" not in job and saved["experiments"] == ["shortfix"]


def test_shortfix_without_draft_runs_one_session(harness, monkeypatch):
    run_dir, sessions, _ = harness
    monkeypatch.setenv("SEO_EXPERIMENT", "shortfix")

    def no_submit(model, message, **kw):
        sessions.append({})
        kw["transcript"].write_text("", encoding="utf-8")
        return {"tokens": {"input": 1, "output": 1, "total": 2}, "error": None, "elapsed_s": 1.0, "tools_used": []}
    monkeypatch.setattr(sim, "run_agent_cli", no_submit)
    r = sim.run_research_sim("m", {"total_minutes": 1}, run_dir=run_dir)
    assert len(sessions) == 1 and "phases" not in r and r["status"] == "incomplete"


def test_merge_outs_keeps_missing_cost_as_none():
    a = {"cost_usd_equiv": None, "tokens": {}, "elapsed_s": 1.0}
    assert sim.merge_outs(a, dict(a))["cost_usd_equiv"] is None
    assert sim.merge_outs({**a, "cost_usd_equiv": 0.5}, a)["cost_usd_equiv"] == 0.5


def test_experiments_rejects_unknown_name(monkeypatch):
    from seo_agent.board import experiments
    monkeypatch.setenv("SEO_EXPERIMENT", "shortfix,typo")
    with pytest.raises(ValueError, match="typo.*合法名稱"):
        experiments()
    for removed in ("coverage", "cardex"):  # 已移除的實驗開關也算打錯
        monkeypatch.setenv("SEO_EXPERIMENT", removed)
        with pytest.raises(ValueError, match=f"{removed}.*合法名稱"):
            experiments()
    monkeypatch.setenv("SEO_EXPERIMENT", "leaninspect,searchmemo,shortfix")
    assert experiments() == {"leaninspect", "searchmemo", "shortfix"}
    monkeypatch.delenv("SEO_EXPERIMENT")
    assert experiments() == set()


def test_continue_rejects_changed_experiments(tmp_path):
    (tmp_path / "sequence.json").write_text(json.dumps({"steps": []}), encoding="utf-8")  # 舊資料沒有這欄＝全關
    sim.check_continue_experiments(tmp_path, [], True)
    with pytest.raises(RuntimeError, match="experiments"):
        sim.check_continue_experiments(tmp_path, ["shortfix"], True)
    (tmp_path / "sequence.json").write_text(json.dumps({"steps": [], "experiments": ["shortfix"]}), encoding="utf-8")
    sim.check_continue_experiments(tmp_path, ["shortfix"], True)
    with pytest.raises(RuntimeError, match="experiments"):
        sim.check_continue_experiments(tmp_path, [], True)
    sim.check_continue_experiments(tmp_path, [], False)  # 不是接續就不比
