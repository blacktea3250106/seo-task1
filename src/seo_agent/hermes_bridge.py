"""把專案工具註冊進 Hermes，並跑一次 Hermes 迴圈。只能在 worker 子程序內使用（HERMES_HOME 已設好）。"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from .model_env import ModelSettings

TOOLSET = "seo_v3"


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[[dict], dict]


class ToolLog:
    """記錄每次工具呼叫（名稱、參數、結果摘要、Evidence ID〔含衍生〕、目標網域與路徑、題號、耗時），
    給 Board、經驗反查路線 Tool 清單與停止判斷用（G-13）。

    題號：Tool 呼叫本身不帶題號；以最近一筆 research_log 的題號當作之後 Tool 呼叫的題號（決策 #50）。"""

    def __init__(self, guard=None, path=None, ctx=None) -> None:
        self.calls: list[dict] = []
        self.guard = guard  # 停止判斷：before() 可擋下呼叫，after() 可附提醒
        self.ctx = ctx      # 有 ctx 時：查證據來源算目標、每次呼叫後更新 board.json
        self.path = path or (ctx.tool_calls_path if ctx is not None else None)  # 每次呼叫寫一行到 tool_calls.jsonl
        self.question_id: str | None = None

    def wrap(self, tool: Tool) -> Callable:
        def handler(args, **_kwargs):
            args = args if isinstance(args, dict) else {}
            started = time.time()
            before_n = len(self.ctx.store.ids()) if self.ctx is not None else 0
            blocked = self.guard.before(tool.name, args) if self.guard else None
            if blocked is not None:
                result = blocked
            else:
                try:
                    result = tool.func(args)
                except Exception as error:  # 工具失敗回給模型，不讓 Hermes 收到 traceback
                    result = {"ok": False, "error": {"code": "tool_exception", "detail": f"{type(error).__name__}: {error}"}}
                if self.guard:
                    result = self.guard.after(tool.name, args, result, question_id=self.question_id)
            err = result.get("error") if isinstance(result, dict) else None
            error_ids: list[str] = []
            if blocked is None and isinstance(err, dict) and err.get("code") in TOOL_ERROR_CODES and self.ctx is not None:
                result, error_ids = _record_tool_error(self.ctx, tool.name, args, err, before_n, result)
            if tool.name == "research_log" and result.get("ok", True):
                self.question_id = result.get("question_id") or args.get("question_id") or self.question_id
            from .board import call_target
            record = {"n": len(self.calls) + 1, "at": round(started, 3), "tool": tool.name, "args": args,
                      "ok": result.get("ok", True), "error": err.get("code") if isinstance(err, dict) else err,
                      "evidence_id": result.get("evidence_id"), "derived_evidence_id": result.get("derived_evidence_id"),
                      "target": call_target(tool.name, args, self.ctx.store if self.ctx is not None else None),
                      "question_id": self.question_id, "light_test_of": result.get("light_test_of"),
                      "same_as_snapshot": bool(result.get("same_as_snapshot")), "error_evidence_ids": error_ids,
                      "new_evidence": getattr(self.guard, "last_progress", None) if blocked is None else None,
                      "blocked_by_guard": blocked is not None,
                      "elapsed_s": round(time.time() - started, 3), "streak": getattr(self.guard, "streak", None)}
            self.calls.append(record)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            if self.ctx is not None:
                from .board import write_board
                write_board(self.ctx)
            return json.dumps(result, ensure_ascii=False, default=str)
        return handler


# Tool 錯誤回傳（被擋、逾時、robots 不准抓、連不上、重試後仍失敗）：照舊記成證據、標未知（G-17、判定訊號定義「被擋」）。
# bad_args、approval_required 這類是呼叫方式錯或需人工批准，不是網站回傳，不記。
TOOL_ERROR_CODES = {"robots_disallowed", "network_error", "site_throttled", "site_paused", "wayback_status", "tool_exception"}


def _record_tool_error(ctx, name: str, args: dict, err: dict, before_n: int, result: dict) -> tuple[dict, list[str]]:
    """把錯誤存成一筆 kind=tool_error 的證據；這次呼叫途中存下的原檔（例如 429 回應）也一併標成錯誤回傳。"""
    from .board import call_target
    during = ctx.store.ids()[before_n:]
    target = call_target(name, args, ctx.store)
    body = json.dumps({"tool": name, "args": args, "error": err, "target": target, "status": "未知"}, ensure_ascii=False)
    item = ctx.store.add(body.encode(), source=f"{(target or {}).get('domain', '')}{(target or {}).get('path', '')}" or name,
                         tool=name, kind="tool_error", suffix=".json", meta={"tool_error": True, "error": err.get("code")})
    ids = during + [item["id"]]
    return {**result, "evidence_id": item["id"], "evidence_status": "未知"}, ids


def error_evidence_ids(ctx) -> set[str]:
    """哪些 Evidence ID 是 Tool 錯誤回傳（寫入審核第 2、6 項用）。"""
    out = {e["id"] for e in ctx.store.all() if e.get("kind") == "tool_error" or (e.get("meta") or {}).get("tool_error")}
    for c in ctx.read_jsonl(ctx.tool_calls_path):
        out.update(c.get("error_evidence_ids") or [])
    return out


def register(tools: list[Tool], log: ToolLog) -> None:
    from tools.registry import registry  # Hermes

    for tool in tools:
        schema = {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
        registry.register(name=tool.name, toolset=TOOLSET, schema=schema, handler=log.wrap(tool))


def oauth_credentials(model_id: str):
    """訂閱登入（決策 #62）：從 Hermes 的 credential pool 取 token。
    用 pool.select()（過期會先換新，換新的 token 由 Hermes 加鎖寫回 .hermes-auth 上層），
    並把 pool 交給 AIAgent，執行中遇到 401 也能換新。"""
    from agent.credential_pool import load_pool

    pool = load_pool("anthropic")
    entry = pool.select(model=model_id)
    if entry is None:
        raise RuntimeError("找不到 Hermes 訂閱登入；先執行 HERMES_HOME=.hermes-auth uv run hermes auth add anthropic")
    return entry.runtime_api_key, pool

def run_agent(model: ModelSettings, tools: list[Tool], system_prompt: str, message: str, *,
              run_id: str, max_iterations: int, budget_seconds: float, log: ToolLog | None = None) -> dict[str, Any]:
    log = log or ToolLog()
    register(tools, log)
    from run_agent import AIAgent

    api_key, pool = (oauth_credentials(model.model) if model.auth == "oauth" else (model.api_key, None))
    agent = AIAgent(base_url=model.base_url, api_key=api_key, provider="anthropic", model=model.model,
                    credential_pool=pool, enabled_toolsets=[TOOLSET], skip_memory=True, skip_background_review=True,
                    skip_context_files=True, quiet_mode=True, max_iterations=max_iterations,
                    run_budget_seconds=budget_seconds, ephemeral_system_prompt=system_prompt, session_id=run_id)
    offered = sorted(t["function"]["name"] for t in (getattr(agent, "tools", None) or []))
    result = agent.run_conversation(message, task_id=run_id) or {}
    return {"api_mode": agent.api_mode, "provider": agent.provider, "model": agent.model,
            "tools_offered": offered, "tool_calls": log.calls,
            "final_response": result.get("final_response"), "api_calls": result.get("api_calls"),
            "completed": result.get("completed"), "error": result.get("error"),
            "tokens": {k: int(getattr(agent, f"session_{k}_tokens", 0) or 0) for k in ("input", "output", "total")}}
