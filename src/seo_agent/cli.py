"""命令列（G-48）：
python -m seo_agent.cli run --site https://2030.tw --keywords 娛樂城,3A娛樂城 --out runs/<run_id> [--refresh]

--out 的最後一段當 run_id，上一層當輸出根目錄；--refresh 強制整份重抓網站底稿（G-50）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runner import RUN_ID, new_run_id


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m seo_agent.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="研究一個競爭者網站")
    r.add_argument("--site", required=True)
    r.add_argument("--keywords", required=True, help="逗號分隔，例如 娛樂城,3A娛樂城")
    r.add_argument("--out", type=Path, help="runs/<run_id>；省略時自動產生 run_id")
    r.add_argument("--refresh", action="store_true", help="強制整份重抓網站底稿")
    r.add_argument("--minutes", type=float, default=120)
    args = ap.parse_args(argv)
    args.keywords = [k.strip() for k in args.keywords.replace("，", ",").split(",") if k.strip()]
    if not args.keywords:
        ap.error("--keywords 至少一個")
    if args.out is None:
        args.out = Path("runs") / new_run_id("run")
    if not RUN_ID.fullmatch(args.out.name):
        ap.error(f"--out 最後一段不是合法 run_id：{args.out.name}")
    return args


def payload(args: argparse.Namespace) -> dict:
    return {"site": args.site, "keywords": args.keywords, "refresh": args.refresh, "total_minutes": args.minutes}


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    from .runner import run_isolated
    result = run_isolated("research", args.out.name, payload(args), timeout_s=args.minutes * 60 + 1800,
                          out_root=args.out.parent.resolve())
    print(json.dumps({k: result.get(k) for k in ("run_id", "status", "status_label", "elapsed_s", "tool_calls_total")},
                     ensure_ascii=False))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
