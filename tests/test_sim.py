"""模擬執行（sim.py）：MCP 轉接與 claude 輸出解析（離線）。"""
import json
import os

import pytest

from seo_agent.hermes_bridge import Tool, ToolLog
from seo_agent.sim import ToolServer, handle_rpc, parse_stream

# 模擬 runner 用 Unix socket 與 shell 假 CLI，Windows 不支援；正式 Hermes 路徑不受影響
pytestmark = pytest.mark.skipif(os.name == "nt", reason="模擬 runner 只支援 macOS／Linux")


def test_handle_rpc_list_and_call():
    calls = []

    def ask(req):
        calls.append(req)
        return {"tools": [{"name": "t"}]} if req["op"] == "list" else {"text": "{\"ok\": true}", "is_error": False}

    assert handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, ask) is None
    init = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "X"}}, ask)
    assert init["result"]["protocolVersion"] == "X" and "tools" in init["result"]["capabilities"]
    assert handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, ask)["result"]["tools"] == [{"name": "t"}]
    r = handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "t", "arguments": {"a": 1}}}, ask)
    assert r["result"]["content"][0]["text"] == "{\"ok\": true}" and calls[-1]["args"] == {"a": 1}
    assert handle_rpc({"jsonrpc": "2.0", "id": 4, "method": "nope"}, ask)["error"]["code"] == -32601


def test_tool_server_goes_through_toollog(tmp_path):
    import socket
    log = ToolLog(path=tmp_path / "calls.jsonl")
    srv = ToolServer([Tool("echo", "回聲", {"type": "object"}, lambda a: {"ok": True, "got": a})], log)
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(srv.path)
        f = s.makefile("rwb")
        f.write(b'{"op": "call", "name": "echo", "args": {"x": 1}}\n')
        f.flush()
        resp = json.loads(f.readline())
        assert json.loads(resp["text"])["got"] == {"x": 1}
        assert len(log.calls) == 1 and log.calls[0]["tool"] == "echo"
    finally:
        srv.close()


def test_parse_stream_error_and_usage():
    lines = [{"type": "system", "subtype": "init", "model": "m", "tools": ["mcp__seo__echo"]},
             {"type": "assistant", "message": {"id": "a"}}, {"type": "assistant", "message": {"id": "a"}},
             {"type": "assistant", "message": {"id": "b"}},
             {"type": "result", "subtype": "success", "is_error": False, "result": "done",
              "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 3}}]
    out = parse_stream("\n".join(json.dumps(x) for x in lines))
    assert out["api_calls"] == 2 and out["tokens"] == {"input": 15, "output": 3, "total": 18} and out["error"] is None
    bad = parse_stream(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True}))
    assert bad["error"].startswith("error_max_turns")
    assert parse_stream("").get("result_missing")
