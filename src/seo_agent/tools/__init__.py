"""7 個研究 Tool（需求 2.2）。build_tools(ctx) 回傳原始 Tool；研究 job 用 coverage.research_tools 再包一層。"""
from __future__ import annotations

from .context import Context


def build_tools(ctx: Context, names: list[str] | None = None):
    from .domain import domain_tool, wayback_tool
    from .search import search_tool
    from .sitemap import sitemap_tool
    from .web import fetch_tool, inspect_tool, text_match_tool

    tools = [fetch_tool(ctx), sitemap_tool(ctx), inspect_tool(ctx), text_match_tool(ctx), domain_tool(ctx),
             wayback_tool(ctx), search_tool(ctx)]
    return [t for t in tools if names is None or t.name in names]
