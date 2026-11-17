"""Board（runs/<id>/board.json）：研究進度摘要，由程式依 Tool 呼叫紀錄與證據庫產生，模型不直接寫。
每次 Tool 呼叫後更新（hermes_bridge.ToolLog）。決策 #71 起沒有題目清單；也放共用的 Tool 呼叫目標（網域、路徑，G-13）
與實驗開關。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlsplit


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _url_target(value: str) -> dict:
    value = (value or "").strip()
    parts = urlsplit(value if "://" in value else "https://" + value)
    host = (parts.hostname or "").lower()
    return {"domain": host[4:] if host.startswith("www.") else host, "path": parts.path or "/"}


def call_target(tool: str, args: dict, store=None) -> dict | None:
    """Tool 呼叫的目標（網域、路徑）。web_search 沒有網址，目標記成搜尋字串。"""
    args = args or {}
    if tool == "web_search" and args.get("query"):
        return {"domain": "web_search", "path": str(args["query"])}
    for key in ("url", "site", "domain"):
        if args.get(key):
            return _url_target(str(args[key]))
    urls = args.get("urls")
    if isinstance(urls, list) and urls:
        return _url_target(str(urls[0]))
    if args.get("evidence_id") and store is not None:
        item = store.get(args["evidence_id"])
        if item:
            src = item.get("meta", {}).get("final_url") or item.get("source", "")
            if "://" in src:
                return _url_target(src)
    return None


EXPERIMENTS = ("leaninspect", "searchmemo", "shortfix")


def experiments() -> set[str]:
    """實驗開關（決策 #67）：環境變數 SEO_EXPERIMENT 逗號分隔；預設全關，行為和原本一樣。沒定義的名稱直接報錯。"""
    import os
    names = {x.strip() for x in os.environ.get("SEO_EXPERIMENT", "").split(",") if x.strip()}
    unknown = sorted(names - set(EXPERIMENTS))
    if unknown:
        raise ValueError(f"SEO_EXPERIMENT 有沒定義的開關：{', '.join(unknown)}；合法名稱：{', '.join(EXPERIMENTS)}")
    return names


def build_board(ctx) -> dict:
    calls = [c for c in _read(ctx.tool_calls_path) if c.get("tool") not in ("submit_report", "experience")]
    return {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "evidence_index": "evidence.jsonl",
            "evidence_total": len(ctx.store.ids()), "tool_calls_total": len(calls),
            "why_filled": sum(1 for c in calls if str((c.get("args") or {}).get("why") or "").strip())}


def write_board(ctx) -> dict:
    board = build_board(ctx)
    path = ctx.run_dir / "board.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(board, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return board
