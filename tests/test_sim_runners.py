"""模擬執行者 --runner claude|codex|agy（決策 #57）：全部離線，用假的 CLI 執行檔，不打網路、不叫模型。"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from seo_agent import sim
from seo_agent.hermes_bridge import Tool, ToolLog
from seo_agent.sequence import dry_run_fn, run_sequence

# 模擬 runner 用 Unix socket 與 shell 假 CLI，Windows 不支援；正式 Hermes 路徑不受影響
pytestmark = pytest.mark.skipif(os.name == "nt", reason="模擬 runner 只支援 macOS／Linux")

CODEX_OK = [{"type": "thread.started", "thread_id": "t"},
            {"type": "item.completed", "item": {"type": "reasoning", "text": "想"}},
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "seo", "tool": "echo",
                                                "status": "completed"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": '{"items": []}'}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 3}}]
CODEX_SHELL = CODEX_OK[:2] + [{"type": "item.completed", "item": {"type": "command_execution", "command": "ls"}}] + CODEX_OK[2:]


@pytest.fixture(autouse=True)
def _reset():
    yield
    sim.set_runner("claude")
    sim.EFFORT = None
    sim.REVIEWER_MODEL = None


def fake_cli(tmp_path: Path, monkeypatch, name: str, events: list) -> Path:
    """假執行檔：記下 argv 與 stdin，印出固定的 JSONL 事件。"""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp_path / f"{name}-argv.json"
    exe = bindir / name
    exe.write_text(f"#!{sys.executable}\nimport json, sys\nstdin = sys.stdin.read()\n"
                   f"json.dump({{'argv': sys.argv[1:], 'stdin': stdin}}, open({str(log)!r}, 'w'))\n"
                   f"print({chr(10).join(json.dumps(e) for e in events)!r})\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}:" + __import__("os").environ["PATH"])
    return log


def test_claude_commands_unchanged():
    research = sim.claude_cmd("m", system_prompt_file=Path("p"), tools="", allowed="mcp__seo__*",
                              mcp_config=Path("c.json"), max_turns=400)
    assert research[:2] == ["claude", "-p"] and research[research.index("--tools") + 1] == ""
    assert research[research.index("--allowedTools") + 1] == "mcp__seo__*" and "--strict-mcp-config" in research
    assert sim.RUNNER == "claude" and sim.RUNTIME == "claude-code-cli" and "Claude Code CLI" in sim.SIM_NOTE


def test_codex_cmd_restricts_tools():
    sim.EFFORT = "high"
    spec = sim.mcp_spec("/tmp/s")
    cmd = sim.codex_cmd("gpt-x", system_prompt_file=Path("/r/system_prompt.md"), cwd=Path("/r/cwd"), mcp=spec)
    assert cmd[:3] == ["codex", "exec", "--json"] and cmd[cmd.index("-m") + 1] == "gpt-x" and cmd[-1] == "-"
    joined = " ".join(cmd)
    for flag in ("--ignore-user-config", "--ephemeral", "-s read-only", "--disable shell_tool", "--disable unified_exec",
                 'approval_policy="never"', 'web_search="disabled"', 'model_instructions_file="/r/system_prompt.md"',
                 'model_reasoning_effort="high"', f"mcp_servers.seo.command={json.dumps(sys.executable)}",
                 'mcp_servers.seo.args=["-m", "seo_agent.sim", "proxy", "/tmp/s"]'):
        assert flag in joined, flag
    assert "dangerously" not in joined
    assert "mcp_servers" not in " ".join(sim.codex_cmd("m", system_prompt_file=Path("p"), cwd=Path("c")))  # 審查：無 Tool


def test_agy_agent_file_and_cmd(tmp_path):
    sim.EFFORT = "max"
    p = sim.write_agy_agent(tmp_path, "# 系統提示\n內容", sim.mcp_spec("/tmp/s"))
    text = p.read_text(encoding="utf-8")
    assert p.parent == tmp_path / ".agents" / "agents" and text.endswith("---\n# 系統提示\n內容")
    front = dict(line.split(": ", 1) for line in text.split("---\n")[1].splitlines())
    assert json.loads(front["tools"]) == [] and json.loads(front["inheritMcp"]) is False
    assert list(json.loads(front["mcpServers"])) == ["seo"]
    cmd = sim.agy_cmd("gem", "任務")
    assert cmd[-2:] == ["-p", "任務"] and "--sandbox" in cmd and cmd[cmd.index("--effort") + 1] == "max"
    assert not any("dangerously" in c for c in cmd)


def test_parse_codex_events():
    out = sim.parse_codex("\n".join(json.dumps(e) for e in CODEX_SHELL))
    assert out["final_response"] == '{"items": []}' and out["error"] is None and out["completed"]
    assert out["tools_used"] == ["command_execution", "mcp__seo__echo"]
    assert out["tokens"] == {"input": 10, "output": 3, "total": 13}
    bad = sim.parse_codex(json.dumps({"type": "turn.failed", "error": {"message": "quota"}}))
    assert bad["error"] == "quota"
    assert sim.parse_codex("").get("result_missing")
    assert sim.non_project(["mcp__seo__echo", "seo/echo", "echo", "run_command"], {"echo"}) == ["run_command"]


def test_parse_stream_lists_tool_use():
    lines = [{"type": "assistant", "message": {"id": "a", "content": [{"type": "tool_use", "name": "Bash"}]}},
             {"type": "result", "subtype": "success", "is_error": False, "result": "x"}]
    assert sim.parse_stream("\n".join(json.dumps(x) for x in lines))["tools_used"] == ["Bash"]


@pytest.mark.parametrize("events,status", [(CODEX_OK[:1] + CODEX_OK[3:], "passed"), (CODEX_SHELL, "failed")])
def test_codex_reviewer_via_fake_cli(tmp_path, monkeypatch, events, status):
    log = fake_cli(tmp_path, monkeypatch, "codex", events)
    sim.set_runner("codex")
    res = sim.sim_reviewer("gpt-x", tmp_path / "r1")(None, {"report": {}})
    assert res["status"] == status and res["runner"] == "codex" and res["runtime"] == "codex-cli"
    saved = json.loads((tmp_path / "r1" / "r1-review" / "result.json").read_text(encoding="utf-8"))
    assert saved["runner"] == "codex" and saved["model"] == "gpt-x"
    argv = json.loads(log.read_text(encoding="utf-8"))
    assert "mcp_servers" not in " ".join(argv["argv"]) and argv["stdin"]  # 審查無 Tool；任務文字走 stdin


def _fake_session(monkeypatch, captured: dict):
    import seo_agent.research as research

    def open_session(model, payload, *, run_dir, reviewer):
        (run_dir / "system_prompt.md").write_text("系統提示", encoding="utf-8")
        tool = Tool("echo", "回聲", {"type": "object"}, lambda a: {"ok": True})
        log = ToolLog(path=run_dir / "tool_calls.jsonl")
        log.wrap(tool)({})  # 模型經 MCP 呼叫過 1 次專案 Tool
        return {"tools": [tool], "log": log, "message": "任務"}

    def close_session(s, out):  # 和真的 close_session 一樣：已交卷（accepted）就 passed，不看 error
        captured.update(out)
        return {"status": "passed", "status_label": "完成", **out}
    monkeypatch.setattr(research, "open_session", open_session)
    monkeypatch.setattr(research, "close_session", close_session)


@pytest.mark.parametrize("events,ok", [(CODEX_OK, True), (CODEX_SHELL, False)])
def test_codex_research_via_fake_cli(tmp_path, monkeypatch, events, ok):
    captured: dict = {}
    _fake_session(monkeypatch, captured)
    log = fake_cli(tmp_path, monkeypatch, "codex", events)
    sim.set_runner("codex")
    sim.EFFORT = "medium"
    r = sim.run_research_sim("gpt-x", {"total_minutes": 1}, run_dir=tmp_path / "run")
    job = json.loads((tmp_path / "run" / "job.json").read_text(encoding="utf-8"))
    assert job["runner"] == "codex" and job["model"] == "gpt-x" and job["effort"] == "medium"
    assert job["runtime"] == "codex-cli" and job["simulated"] is True
    assert r["runtime"] == "codex-cli" and "Codex CLI" in r["sim_note"] and "不是 Hermes" in r["sim_note"]
    assert (tmp_path / "run" / "sim_transcript.jsonl").read_text(encoding="utf-8").count("\n") >= len(events) - 1
    argv = " ".join(json.loads(log.read_text(encoding="utf-8"))["argv"])
    assert "mcp_servers.seo.command" in argv and "--disable shell_tool" in argv
    assert bool(captured["non_project_tools_used"]) is (not ok)
    saved = json.loads((tmp_path / "run" / "result.json").read_text(encoding="utf-8"))
    assert saved["status"] == r["status"] == ("passed" if ok else "interrupted")  # 交了卷也不能放行（M1）
    assert bool(saved.get("untrusted_run")) is (not ok)


def test_untrusted_run_skips_experience_writes(tmp_path, monkeypatch):
    from seo_agent import lifecycle
    from seo_agent.experience import ExperienceStore
    called = []
    monkeypatch.setattr(lifecycle, "judge_run", lambda *a: called.append("judge") or {"status": "done"})
    monkeypatch.setattr("seo_agent.audit.audit_run", lambda *a: called.append("audit") or {"status": "done"})
    store = ExperienceStore(tmp_path / "c.jsonl")
    (tmp_path / "result.json").write_text(json.dumps({"status": "interrupted", "untrusted_run": "用了 shell"}),
                                          encoding="utf-8")
    lc = lifecycle.post_run(tmp_path, store)
    assert called == [] and lc["audit"]["status"] == lc["judgement"]["status"] == "skipped_untrusted_run"
    (tmp_path / "result.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    lifecycle.post_run(tmp_path, store)
    assert called == ["judge", "audit"]


def test_agy_research_via_fake_cli(tmp_path, monkeypatch):
    captured: dict = {}
    _fake_session(monkeypatch, captured)
    events = [{"type": "assistant", "message": {"id": "a", "content": [{"type": "tool_use", "name": "mcp__seo__echo"}]}},
              {"type": "result", "subtype": "success", "is_error": False, "result": "完成"}]
    log = fake_cli(tmp_path, monkeypatch, "agy", events)
    sim.set_runner("agy")
    r = sim.run_research_sim("gem", {"total_minutes": 1}, run_dir=tmp_path / "run")
    assert r["status"] == "passed" and captured["non_project_tools_used"] == []
    argv = json.loads(log.read_text(encoding="utf-8"))["argv"]
    assert argv[argv.index("--agent") + 1] == sim.AGY_AGENT and argv[-1] == "任務"
    agent = (tmp_path / "run" / "sim_cwd" / ".agents" / "agents" / f"{sim.AGY_AGENT}.md").read_text(encoding="utf-8")
    assert agent.endswith("系統提示") and "mcpServers" in agent


def test_agy_format_mismatch_is_interrupted(tmp_path, monkeypatch):
    """ToolLog 有專案 Tool 呼叫，但 agy 輸出解析不到任何 Tool 呼叫 → 格式不符，不放行。"""
    _fake_session(monkeypatch, {})
    fake_cli(tmp_path, monkeypatch, "agy", [{"type": "tool_call", "tool": "run_command"},
                                            {"type": "result", "subtype": "success", "is_error": False, "result": "x"}])
    sim.set_runner("agy")
    r = sim.run_research_sim("gem", {"total_minutes": 1}, run_dir=tmp_path / "run")
    assert r["status"] == "interrupted" and "輸出格式不符" in r["untrusted_run"]


def test_claude_argv_via_fake_cli(tmp_path, monkeypatch):
    ok = [{"type": "system", "subtype": "init", "tools": []},
          {"type": "result", "subtype": "success", "is_error": False, "result": '{"items": []}'}]
    log = fake_cli(tmp_path, monkeypatch, "claude", ok)
    sim.sim_reviewer("m", tmp_path / "r1")(None, {"report": {}})
    review = json.loads(log.read_text(encoding="utf-8"))["argv"]
    assert "--mcp-config" not in review and "--allowedTools" not in review
    assert review[review.index("--tools") + 1] == "" and review[review.index("--max-turns") + 1] == "4"
    _fake_session(monkeypatch, {})
    sim.run_research_sim("m", {"total_minutes": 1}, run_dir=tmp_path / "run")
    research = json.loads(log.read_text(encoding="utf-8"))["argv"]
    assert research[research.index("--allowedTools") + 1] == "mcp__seo__*" and "--mcp-config" in research


def test_main_runner_args(monkeypatch):
    for argv in (["research", "--runner", "codex"],  # 沒給模型
                 ["research", "--runner", "codex", "--model", "m", "--effort", "max"],  # codex 不接受 max
                 ["sequence", "--runner", "agy", "--model", "m"]):  # 對照組只支援 claude
        with pytest.raises(SystemExit):
            sim.main(argv)


def test_continue_refuses_runner_change(tmp_path):
    def run(**kw):
        return run_sequence(1, run_fn=dry_run_fn, out_dir=tmp_path / "s", log=lambda s: None, **kw)
    run(meta={"runtime": "claude-code-cli", "model": "a"})  # 舊序列：沒記 runner
    run(resume=True, meta={"runtime": "claude-code-cli", "runner": "claude", "model": "a"})  # 舊的視為 claude，可接
    assert json.loads((tmp_path / "s" / "sequence.json").read_text(encoding="utf-8"))["runner"] == "claude"
    with pytest.raises(RuntimeError, match="runner"):
        run(resume=True, meta={"runtime": "claude-code-cli", "runner": "codex", "model": "a"})
