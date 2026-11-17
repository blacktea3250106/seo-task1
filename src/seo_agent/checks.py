"""報告的程式警告（G-47、G-46）：只引用外部說法、引用內容核對。結果只列進 ⑥ 待修清單，不直接擋交件。"""
from __future__ import annotations

# ---- 證據性質：外部網站（G-47）----
import json  # noqa: E402
import re  # noqa: E402

from .board import _url_target  # noqa: E402

PAGE_TOOLS = ("polite_fetch", "inspect_page", "text_match")


def _calls_by_evidence(ctx) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for c in ctx.read_jsonl(ctx.tool_calls_path):
        for key in ("evidence_id", "derived_evidence_id"):
            if c.get(key):
                out[c[key]] = c
    return out


def evidence_domain(ctx, eid: str, calls: dict | None = None) -> str | None:
    """證據內容來自哪個網站：抓頁類證據看網址；衍生資料看產生它的 Tool 呼叫目標。其他（搜尋、Wayback、WHOIS）回 None。"""
    item = ctx.store.get(eid)
    if not item:
        return None
    if item["kind"] == "page":
        src = (item.get("meta") or {}).get("final_url") or item["source"]
        return _url_target(src)["domain"]
    if item["kind"] == "derived":
        call = (calls if calls is not None else _calls_by_evidence(ctx)).get(eid)
        if call and call.get("tool") in PAGE_TOOLS and call.get("target"):
            return call["target"]["domain"]
    return None


def is_external(ctx, eid: str, calls: dict | None = None) -> bool:
    """競爭者網站以外的網站內容＝「外部說法」：只能當靈感，不能支持「對方做了什麼」（G-47）。"""
    site = getattr(ctx, "site_domain", None)
    dom = evidence_domain(ctx, eid, calls)
    return bool(site and dom and dom != site)


# ---- 引用內容核對〔E-0031:"2,273"〕（G-46）----
CITE = re.compile(r"〔(E-\d{4})[:：]\s*[\"“「](.+?)[\"”」]\s*〕")
_THOUSANDS = re.compile(r"(?<=\d)[,，](?=\d{3})")


def _texts_of(ctx, eid: str) -> list[str]:
    from .tools.web import decode
    raw = ctx.store.read(eid)
    text = decode(raw)
    out = [text, re.sub(r"<[^>]+>", " ", text)]
    if text.lstrip().startswith(("{", "[")):
        try:
            out.append(json.dumps(json.loads(text), ensure_ascii=False))
        except ValueError:
            pass
    return out


def citation_warnings(ctx, texts: list[tuple[str, str]]) -> list[dict]:
    """只核對固定格式〔E-0031:"..."〕：引號內容要在那份證據的原檔、正文或衍生 JSON 裡（text_match 寬鬆規則：
    全半形、大小寫、空白、千分位都不計較）。找不到 → 警告，列入 ⑥ 待修清單，不直接擋。texts＝[(句子編號, 文字)]。"""
    from .tools.textmatch import keyword_hits
    ids = set(ctx.store.ids())
    out = []
    for where, text in texts:
        for eid, quote in CITE.findall(text or ""):
            if eid not in ids:
                found = False
            else:
                q = _THOUSANDS.sub("", quote)
                found = any(keyword_hits(_THOUSANDS.sub("", t), q, contexts=0)["loose"] for t in _texts_of(ctx, eid))
            if not found:
                out.append({"kind": "citation", "where": where, "evidence_ids": [eid], "level": "警告",
                            "problems": [f"引用內容「{quote}」在 {eid} 的原檔、正文、衍生資料裡都找不到"]})
    return out
