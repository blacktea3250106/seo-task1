"""Tool 7 網路搜尋。只用免費、robots 允許的來源；遇人機驗證就回報未知，不繞過。"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, unquote, urlsplit

from ..board import experiments
from ..hermes_bridge import Tool
from .context import Context
from .fetcher import ToolError
from .web import _guard, decode

DDG = "https://html.duckduckgo.com/html/?q="
NOTE = ("查無結果≠沒被收錄：免費搜尋只看得到一部分，不能當作索引量或排名證據。"
        "標「外部說法」的是競爭者以外的網站，只能當靈感，不能支持「對方做了什麼」。")
CHALLENGE = ("anomaly-modal", "challenge-form", "captcha", "are you a robot", "unusual traffic", "bots use duckduckgo")


def search_tool(ctx: Context) -> Tool:
    @_guard
    def run(args: dict) -> dict:
        q = args["query"]
        blocked = getattr(ctx, "search_blocked", None)
        if blocked and "searchmemo" in experiments():  # 決策 #67：同一次 run 已被擋過，不再實際發請求（每輪都被擋、模型仍重試）
            return {"ok": False, "status": "unknown", "blocked_evidence_id": blocked, "request_sent": False,
                    "message": f"這次 run 稍早這個搜尋來源已回人機驗證（見 {blocked}），這次沒有再發請求；這題請標為未知（待確認）。",
                    "note": NOTE}
        try:
            res = ctx.fetcher.fetch(DDG + quote(q), tool="web_search", kind="search")
        except ToolError as error:
            return {"ok": False, "status": "unknown", "error": error.as_dict()["error"],
                    "message": "沒有可用的免費搜尋來源，這題請標為未知（待確認）。", "note": NOTE}
        html = decode(res.body, res.headers.get("content-type", ""))
        low = html.lower()
        if res.status != 200 or any(m in low for m in CHALLENGE):
            ctx.search_blocked = res.evidence["id"]
            return {"ok": False, "status": "unknown", **ctx.evidence_ref(res.evidence), "http_status": res.status,
                    "message": "搜尋來源回人機驗證或非 200，不繞過；這題請標為未知（待確認），寫明試過什麼。",
                    "note": NOTE}
        results = []
        for href, title in re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            if "uddg=" in href:
                href = unquote(parse_qs(urlsplit(href).query).get("uddg", [href])[0])
            row = {"url": href, "title": re.sub(r"<[^>]+>", "", title).strip()}
            host = (urlsplit(href).hostname or "").lower().removeprefix("www.")
            if ctx.site_domain and host and host != ctx.site_domain:
                row["label"] = "外部說法"  # 只能當靈感，不能支持「對方做了什麼」（G-47）
            results.append(row)
        return {"ok": True, **ctx.evidence_ref(res.evidence), "query": q, "results": results[:20],
                "source": "DuckDuckGo HTML（免費）", "note": NOTE}

    return Tool("web_search",
                "免費網路搜尋（DuckDuckGo HTML）。可用 site: 等語法。遇人機驗證不繞過，會回 status=unknown；"
                "此時請把該題標為未知並寫明試過什麼。查無結果不等於沒被收錄。付費 SERP API 不可用。",
                {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, run)
