"""研究子程序入口：python -m seo_agent.worker <job> <run_dir>。父程序已設 HERMES_HOME。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if not os.environ.get("HERMES_HOME"):
        print("worker 需要父程序設定 HERMES_HOME", file=sys.stderr)
        return 2
    job, run_dir = argv[1], Path(argv[2])
    payload = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))["payload"]
    from .model_env import load_model_settings

    model = load_model_settings()
    if job == "smoke":
        from .smoke import run_smoke
        result = run_smoke(model, payload, run_id=run_dir.name)
    elif job == "review":
        from .review import run_review
        result = run_review(model, payload, run_id=run_dir.name)
    elif job == "research":
        from .research import run_research
        result = run_research(model, payload, run_dir=run_dir)
    else:
        print(f"未知 job：{job}", file=sys.stderr)
        return 2
    import hermes_constants  # 確認 Hermes 實際用的 home 就是本 run 的 home

    actual = Path(hermes_constants.get_hermes_home()).resolve()
    result["hermes_home_matches_run"] = actual == Path(os.environ["HERMES_HOME"]).resolve()
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
