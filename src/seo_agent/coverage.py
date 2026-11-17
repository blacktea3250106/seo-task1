"""研究 Tool 的兩層外包（決策 #71，C 方案）：只多給事實與一個選填欄位，不規定怎麼查。

- why：每個研究 Tool 多一個選填參數「這一步為什麼這樣做」。留在 tool_calls.jsonl（不進證據來源與進展指紋；Tool 錯誤時，錯誤證據本文會含原始參數），給 ⑧ 路線摘要與經驗判定用；
  用到經驗筆記時寫上經驗編號（例如 EXP-001），程式據此判定「有沒有用到」。Tool 本身收不到這個欄位。
- sections_not_yet_read：每次研究 Tool 回傳多附程式統計的事實——資料卡分區（sitemap 分區＋首頁選單分區）裡，
  到目前為止還沒有任何 Tool 讀過的。只看 Tool 呼叫參數裡的網址，不判讀內容。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .hermes_bridge import Tool

URL = re.compile(r"https?://[^\s\"\\']+")
EXP_ID = re.compile(r"\bEXP-\d{3}\b")
WHY = {"type": "string", "description": "這一步為什麼這樣做（一句話，選填）；照經驗筆記查時寫上經驗編號，例如 EXP-001"}
NOTE = "程式統計（只看 Tool 呼叫參數）：資料卡分區中還沒有任何 Tool 讀過的"


def section_of(url: str, domain: str | None) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not domain or host not in (domain, "www." + domain):  # 子網域（cdn.、m.）不算主站分區
        return None
    segs = [x for x in unquote(parts.path).split("/") if x]  # 資料卡的分區是 unquote 過的
    return ("/" + segs[0] + "/").lower() if segs else "/"


def card_sections(run_dir: Path) -> list[tuple[str, str]]:
    """資料卡裡出現過的分區（sitemap＋首頁選單），附資料卡上的數字。"""
    path = Path(run_dir) / "data_card.json"
    if not path.exists():
        return []
    card = json.loads(path.read_text(encoding="utf-8")).get("sources") or {}
    seen: dict[str, list[str]] = {}
    for s in (card.get("sitemap") or {}).get("sections") or []:
        seen.setdefault(s["section"].lower(), []).append(f"{s['urls']} 個 sitemap 網址")
    for sec, n in ((card.get("home_menu") or {}).get("sections") or {}).items():
        seen.setdefault(sec.lower(), []).append(f"{n} 個選單連結")
    return [(k, "、".join(v)) for k, v in seen.items()]


def why_ids(args: dict) -> set[str]:
    """why 欄寫到的經驗編號。"""
    return set(EXP_ID.findall(str((args or {}).get("why") or "")))


class Coverage:
    def __init__(self, ctx):
        self.ctx = ctx
        self.read: set[str] = set()
        self._card: list[tuple[str, str]] | None = None

    def note(self, args: dict) -> None:
        for u in URL.findall(json.dumps(args or {}, ensure_ascii=False)):
            s = section_of(u, getattr(self.ctx, "site_domain", None))
            if s:
                self.read.add(s)

    def not_yet_read(self) -> list[str]:
        if self._card is None:
            self._card = card_sections(self.ctx.run_dir)
        return [f"{s}（{info}）" for s, info in self._card if s not in self.read]

    def summary(self) -> dict:
        return {"sections_read": sorted(self.read), "sections_not_yet_read": self.not_yet_read()}


def with_why(tool: Tool) -> Tool:
    params = json.loads(json.dumps(tool.parameters))
    params.setdefault("properties", {})["why"] = WHY
    return Tool(tool.name, tool.description, params, lambda a, f=tool.func: f({k: v for k, v in a.items() if k != "why"}))


def with_coverage(tool: Tool, cov: Coverage) -> Tool:
    def run(args: dict, fn=tool.func):
        out = fn(args)
        cov.note(args)
        if isinstance(out, dict):
            out = {**out, "sections_not_yet_read": {"note": NOTE, "sections": cov.not_yet_read()}}
        return out
    return Tool(tool.name, tool.description, tool.parameters, run)


def research_tools(ctx, site: str) -> tuple[list[Tool], Coverage]:
    """7 個研究 Tool → inspect_page 附 page_text → 附 sections_not_yet_read → 加 why 欄。"""
    from .tools import build_tools
    from .tools.page_text import wrap_inspect
    cov = Coverage(ctx)
    tools = [with_why(with_coverage(t, cov)) for t in wrap_inspect(build_tools(ctx), ctx, site)]
    return tools, cov
