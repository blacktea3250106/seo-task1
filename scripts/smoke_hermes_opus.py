"""第 1 步最小證明（會真的呼叫 Opus 一兩次）。用法：uv run python scripts/smoke_hermes_opus.py"""
import json
import sys

from seo_agent.runner import new_run_id, run_isolated

result = run_isolated("smoke", new_run_id("smoke"), {"budget_seconds": 120}, timeout_s=300)
print(json.dumps({k: result.get(k) for k in ("status", "checks", "api_mode", "model", "tools_offered", "tool_calls",
                                             "api_calls", "final_response", "expected_code", "hermes_home_matches_run",
                                             "global_hermes_home", "worker_exit_code", "worker_stderr_tail")},
                 ensure_ascii=False, indent=2))
sys.exit(0 if result.get("status") == "passed" else 1)
