"""建置第 1 步的最小證明：Hermes 用 .env 金鑰叫 Opus，並成功呼叫 1 個工具。

工具回傳每次 run 隨機產生的代碼；模型最後回答中出現該代碼，才證明它真的呼叫了工具並讀到結果。
"""
from __future__ import annotations

import secrets

from .hermes_bridge import Tool, run_agent
from .model_env import ModelSettings


def run_smoke(model: ModelSettings, payload: dict, *, run_id: str) -> dict:
    code = "V3-" + secrets.token_hex(4).upper()

    def get_check_code(args: dict) -> dict:
        return {"ok": True, "check_code": code, "label": args.get("label", "")}

    tool = Tool(name="get_check_code",
                description="Return the check code for this run. Call it exactly once.",
                parameters={"type": "object", "properties": {"label": {"type": "string"}}, "required": []},
                func=get_check_code)
    out = run_agent(model, [tool], system_prompt="You are a test harness assistant. Use the provided tool.",
                    message="Call get_check_code once, then reply with only the check code it returned.",
                    run_id=run_id, max_iterations=4, budget_seconds=float(payload.get("budget_seconds", 120)))
    calls = [c for c in out["tool_calls"] if c["tool"] == "get_check_code"]
    checks = {
        "anthropic_messages_mode": out["api_mode"] == "anthropic_messages",
        "model_is_opus": out["model"] == model.model,
        "tool_offered": "get_check_code" in out["tools_offered"],
        "tool_called": len(calls) >= 1 and all(c["ok"] for c in calls),
        "code_in_answer": code in (out["final_response"] or ""),
    }
    return {"status": "passed" if all(checks.values()) else "failed", "checks": checks,
            "expected_code": code, **out}
