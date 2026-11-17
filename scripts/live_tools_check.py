"""第 2 步的實網抽查：每個工具對 2030.tw 或公開來源各打少量請求，確認真的能用。結果寫到 reports/runs/<id>/live_tools.json。"""
from __future__ import annotations

import json
import sys
import time

from seo_agent import ROOT
from seo_agent.tools import build_tools
from seo_agent.tools.context import Context


def main() -> int:
    run_dir = ROOT / "reports" / "runs" / f"live-tools-{time.strftime('%Y%m%d-%H%M%S')}"
    ctx = Context(run_dir)
    t = {x.name: x.func for x in build_tools(ctx)}
    checks = {}
    home = t["polite_fetch"]({"url": "https://2030.tw/", "preview_chars": 0})
    checks["polite_fetch"] = {k: home.get(k) for k in ("ok", "status", "final_url", "evidence_id")}
    page = t["inspect_page"]({"evidence_id": home["evidence_id"]})
    checks["inspect_page"] = {"title": page.get("title"), "link_counts": page.get("link_counts"), "trackers": page.get("trackers")}
    tm = t["text_match"]({"evidence_id": home["evidence_id"], "keywords": ["3a娛樂城", "娛樂城"], "scopes": ["text", "html"]})
    checks["text_match"] = {k: {s: (v["exact"], v["loose"], list(v["variants"])[:3]) for s, v in r.items()}
                            for k, r in tm["results"].items()}
    sm = t["sitemap_tree"]({"action": "build", "site": "2030.tw"})
    checks["sitemap_tree"] = {"distinct_urls": sm.get("distinct_urls"), "files_ok": sm.get("sitemap_files_ok_total"),
                              "top_sections": sm.get("sections", [])[:6],
                              "folder_found": [f["url"] for f in sm.get("sitemap_files_ok", []) if f["found_by"] == "資料夾探測"]}
    dom = t["domain_info"]({"domain": "2030.tw", "dns_types": ["NS", "A"]})
    checks["domain_info"] = {"rdap_events": (dom.get("rdap") or {}).get("events"), "dns": dom.get("dns"), "errors": dom.get("sources")}
    wb = t["wayback"]({"action": "timeline", "url": "2030.tw"})
    checks["wayback"] = {k: wb.get(k) for k in ("ok", "by_year", "first", "error")}
    ws = t["web_search"]({"query": "site:2030.tw 3A娛樂城"})
    checks["web_search"] = {k: ws.get(k) for k in ("ok", "status", "http_status", "message", "results")}
    checks["record_thought"] = t["record_thought"]({"kind": "thought", "found": "實網抽查", "evidence_ids": [home["evidence_id"]]})
    checks["http_requests"] = len(ctx.fetcher.requests)
    (run_dir / "live_tools.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=1)[:6000])
    print("run_dir:", run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
