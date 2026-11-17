"""每個研究 run 用獨立子程序：父程序先設 HERMES_HOME，子程序才第一次 import Hermes。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import ROOT
from .hermes_home import prepare_run_home, run_home_parent
from .model_env import load_model_settings

GLOBAL_HERMES_HOME = Path.home() / ".hermes"
RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def new_run_id(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"


def run_isolated(job: str, run_id: str, payload: dict, *, timeout_s: float,
                 out_root: Path = ROOT / "reports" / "runs", home_root: Path | None = None) -> dict:
    if not RUN_ID.fullmatch(run_id) or run_id in {".", ".."}:
        raise ValueError(f"不合法的 run_id：{run_id!r}")
    model = load_model_settings()  # 缺金鑰就在父程序先失敗
    run_home = prepare_run_home((home_root or run_home_parent(model.auth)) / run_id)
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "job.json").write_text(json.dumps({"job": job, "run_id": run_id, "payload": payload},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_", "OPENAI_"))}
    env.update(HERMES_HOME=str(run_home), PYTHONDONTWRITEBYTECODE="1",
               SEO_MODEL_BASE_URL=model.base_url, SEO_MODEL_AUTH=model.auth,
               SEO_MODEL_ID=payload.get("model") or model.model)
    if model.api_key:  # oauth 不傳金鑰；ANTHROPIC_*／CLAUDE_* 已拿掉，Hermes 只會用 .hermes-auth 的登入
        env["SEO_MODEL_API_KEY"] = model.api_key
    home_before = GLOBAL_HERMES_HOME.exists()
    proc = subprocess.run([sys.executable, "-m", "seo_agent.worker", job, str(run_dir)], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=timeout_s)
    result_path = run_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {"status": "worker_crashed"}
    result.update(worker_exit_code=proc.returncode,
                  global_hermes_home={"existed_before": home_before, "exists_after": GLOBAL_HERMES_HOME.exists()})
    if proc.returncode != 0:
        result["worker_stderr_tail"] = _redact(proc.stderr[-3000:], model.api_key)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return result


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "<redacted>") if secret else text
