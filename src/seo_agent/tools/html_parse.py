"""Tool 3「看單頁」的解析器（沿用 V2 adapters/html_parse.py，加上連結位置、追蹤碼、正文）。

只用標準函式庫 html.parser。輸出是觀察，缺的欄位就是 None／空清單，不推測。
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

CJK = re.compile(r"[㐀-鿿豈-﫿]")
CHALLENGE_MARKERS = ("cf-challenge", "challenge-platform", "Just a moment...", "captcha", "請完成驗證", "Attention Required")
CHALLENGE_MAX_TEXT = 1000
SOFT_404_MARKERS = ("找不到頁面", "頁面不存在", "page not found", "404 not found")
REGIONS = ("nav", "header", "footer", "aside")  # 連結所在區塊（2030 盲審：/wordcup/ 只出現在導覽，不在 sitemap）
ROLE_REGION = {"navigation": "nav", "banner": "header", "contentinfo": "footer", "complementary": "aside"}
# 很多 WordPress 主題用 <div class="...nav/menu/footer/sidebar..."> 而不是語意標籤（2030.tw 實測：jeg_nav_*）
CLASS_REGION = [
    ("nav", re.compile(r"(^|[-_])(nav|navbar|navigation|menu|mainmenu|topbar)([-_]|$)")),
    ("header", re.compile(r"^((site|jeg|main|global|top|page)[-_])?header$")),
    ("footer", re.compile(r"(^|[-_])footer([-_]|$)")),
    ("aside", re.compile(r"(^|[-_])(sidebar|widget[-_]?area)([-_]|$)")),
]
POSITION = {"nav": "menu", "header": "menu", "footer": "footer", "aside": "sidebar", None: "body"}
TRACKERS = {
    "google_analytics_ga4": r"\bG-[A-Z0-9]{6,12}\b", "google_analytics_ua": r"\bUA-\d{4,10}-\d{1,4}\b",
    "google_tag_manager": r"\bGTM-[A-Z0-9]{4,9}\b", "google_tag": r"\bGT-[A-Z0-9]{6,12}\b", "google_ads": r"\bAW-\d{6,12}\b",
    "facebook_pixel": r"fbq\(\s*[\x27\"]init[\x27\"]\s*,\s*[\x27\"](\d{8,20})", "microsoft_clarity": r"clarity\.ms/tag/([a-z0-9]{6,14})",
    "cloudflare_insights": r"static\.cloudflareinsights\.com", "yandex_metrica": r"mc\.yandex\.ru",
}
# 寫在 script 字串裡的 <a href="http(s)://...">（JS 插入的連結，HTML 解析看不到）；需先還原 \" \' \/ 跳脫
SCRIPT_ANCHOR = re.compile(r"""<a\s[^<>]*?\bhref\s*=\s*["']?(https?://[^"'\s<>\\]+)""", re.I)
SCRIPT_ANCHOR_MAX_HOSTS = 10
PAGE_ENTITY_TYPES = {"WebPage", "CollectionPage", "ItemPage", "Article", "NewsArticle", "BlogPosting"}


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr", "param"}


def _is_js(script_type: str | None) -> bool:
    """script 的 type 是 JS：沒寫、含 javascript、或 module。"""
    t = (script_type or "").strip()
    return not t or "javascript" in t or t == "module"


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.meta: list[dict] = []
        self.links: list[dict] = []
        self.link_tags: list[dict] = []
        self.headings: list[dict] = []
        self.images: list[dict] = []
        self.jsonld: list[str] = []
        self.scripts: list[str] = []  # 非 JSON-LD 的 script 內文
        self.html_lang: str | None = None
        self.text_parts: list[str] = []
        self.main_parts: list[str] = []
        self._stack: list[str] = []
        self._rstack: list[str | None] = []  # 和 _stack 對齊：該層屬於哪個區塊
        self._heading: dict | None = None
        self._anchor: dict | None = None
        self._in_title = self._in_script = False
        self._script_type: str | None = None
        self._script_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.html_lang = a.get("lang") or None
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            self.meta.append(a)
        elif tag == "link":
            self.link_tags.append(a)
        elif tag == "a":
            region = next((r for r in reversed(self._rstack) if r), None)
            self._anchor = {"href": a.get("href"), "rel": a.get("rel", ""), "text": "", "region": region}
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading = {"level": int(tag[1]), "text": ""}
        elif tag == "img":
            self.images.append({"src": a.get("src"), "alt": a.get("alt") if "alt" in a else None})
        elif tag == "script":
            self._in_script = True
            self._script_type = a.get("type", "").lower()
            self._script_buf = []
        elif tag == "style":
            self._in_script = True
            self._script_type = "style"
        if tag not in VOID:
            self._stack.append(tag)
            self._rstack.append(self._region_of(tag, a))

    @staticmethod
    def _region_of(tag: str, a: dict) -> str | None:
        if tag in REGIONS:
            return tag
        if a.get("role") in ROLE_REGION:
            return ROLE_REGION[a["role"]]
        tokens = (a.get("class", "") + " " + a.get("id", "")).lower().split()
        for region, rx in CLASS_REGION:
            if any(rx.search(t) for t in tokens):
                return region
        return None

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._anchor is not None:
            self._anchor["text"] = self._anchor["text"].strip()
            self.links.append(self._anchor)
            self._anchor = None
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._heading is not None:
            self._heading["text"] = self._heading["text"].strip()
            self.headings.append(self._heading)
            self._heading = None
        elif tag in {"script", "style"}:
            if self._script_type == "application/ld+json":
                self.jsonld.append("".join(self._script_buf))
            elif tag == "script" and _is_js(self._script_type):  # application/json、text/template 等不是 JS，不收
                self.scripts.append("".join(self._script_buf))
            self._in_script = False
            self._script_type = None
        if tag in self._stack:  # 關到最近的同名標籤（容忍沒關好的 HTML）
            while self._stack:
                self._rstack.pop()
                if self._stack.pop() == tag:
                    break

    def handle_data(self, data):
        if self._in_script:
            if self._script_type != "style":
                self._script_buf.append(data)
            return
        if self._in_title:
            self.title.append(data)
        if self._heading is not None:
            self._heading["text"] += data
        if self._anchor is not None:
            self._anchor["text"] += data
        self.text_parts.append(data)
        if not any(self._rstack):
            self.main_parts.append(data)


def _jsonld_types(blocks: list[str]) -> tuple[list[str], int, list[str]]:
    """回傳 (types, invalid_blocks, page_entity_urls)。page_entity_urls：頁面型實體宣告的 @id／url／mainEntityOfPage。"""
    types, invalid, entity_urls = [], 0, []
    for block in blocks:
        try:
            data = json.loads(block)
        except ValueError:
            invalid += 1
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                t = item.get("@type")
                names = [t] if isinstance(t, str) else [x for x in t if isinstance(x, str)] if isinstance(t, list) else []
                types.extend(names)
                if PAGE_ENTITY_TYPES & set(names):
                    main = item.get("mainEntityOfPage")
                    main = main.get("@id") if isinstance(main, dict) else main
                    entity_urls.extend(u for u in (item.get("@id"), item.get("url"), main) if isinstance(u, str) and u)
                stack.extend(v for k, v in item.items() if k in {"@graph", "mainEntity", "itemListElement"})
    return sorted(set(types)), invalid, entity_urls


def _script_links(scripts: list[str], host: str) -> dict:
    """script 字串裡的 a 標籤 href（只數 http(s) 絕對網址）。只計數與列外部主機，不看 rel、不判讀。"""
    count, hosts = 0, set()
    for body in scripts:
        body = body.replace("\\/", "/").replace('\\"', '"').replace("\\'", "'")
        for href in SCRIPT_ANCHOR.findall(body):
            count += 1
            try:
                target = (urlsplit(href).hostname or "").lower()
            except ValueError:
                continue
            if target and target != host and not target.endswith("." + host):
                hosts.add(target)
    return {"count": count, "external_hosts": sorted(hosts)[:SCRIPT_ANCHOR_MAX_HOSTS]}


def _same_page(a: str, b: str) -> bool:
    norm = lambda u: unquote(u.split("#", 1)[0]).rstrip("/").lower()  # noqa: E731
    return norm(a) == norm(b)


def parse_html(html: str, url: str) -> dict:
    p = _Parser()
    p.feed(html)
    p.close()
    host = (urlsplit(url).hostname or "").lower()
    text = re.sub(r"\s+", " ", " ".join(p.text_parts)).strip()
    metas = {}
    for m in p.meta:
        key = (m.get("name") or m.get("property") or "").lower()
        if key:
            metas.setdefault(key, []).append(m.get("content"))
    canonicals = [link.get("href") for link in p.link_tags if "canonical" in link.get("rel", "").lower().split()]
    hreflang = [{"lang": link.get("hreflang"), "href": link.get("href")} for link in p.link_tags
                if "alternate" in link.get("rel", "").lower().split() and link.get("hreflang")]
    internal, external, nofollow = [], [], 0
    for link in p.links:
        href = link.get("href")
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(url, href)
        target = (urlsplit(absolute).hostname or "").lower()
        if "nofollow" in link.get("rel", "").lower():
            nofollow += 1
        (internal if target == host or target.endswith("." + host) else external).append(
            {"url": absolute, "text": re.sub(r"\s+", " ", link["text"])[:80], "rel": link.get("rel") or None,
             "position": POSITION.get(link["region"], "body")})
    jsonld_types, jsonld_invalid, entity_urls = _jsonld_types(p.jsonld)
    page_url = canonicals[0] if len(canonicals) == 1 and canonicals[0] else url
    foreign_entities = sorted({u for u in entity_urls if not _same_page(urljoin(url, u), urljoin(url, page_url))})
    lowered = html.lower()
    signals = {
        # 一般頁面也可能含 recaptcha 表單或 Cloudflare challenge-platform 腳本：標記＋本文很短才算驗證頁（site_live 實測誤判）
        "challenge_page": any(m.lower() in lowered for m in CHALLENGE_MARKERS) and len(text) < CHALLENGE_MAX_TEXT,
        "soft_404_text": any(m.lower() in text.lower() for m in SOFT_404_MARKERS),
        "thin_text": len(text) < 200,
        "multiple_canonicals": len(canonicals) > 1,
        "conflicting_robots": len(set(metas.get("robots", []))) > 1,
        # 頁面型 JSON-LD 的 @id／url 指向別頁（2030 盲審發現 8：A 把別頁的 @id 判為通過）
        "jsonld_entity_mismatch": bool(foreign_entities),
    }
    main_text = re.sub(r"\s+", " ", " ".join(p.main_parts)).strip()
    trackers = {}
    for name, pattern in TRACKERS.items():
        found = sorted(set(re.findall(pattern, html)))
        if found:
            trackers[name] = found[:5] if isinstance(found[0], str) and found[0] else ["present"]
    generator = (metas.get("generator") or [None])[0]
    return {
        "all_text": text,  # 整頁 HTML 文字（含選單、頁首、頁尾、側欄；不看 CSS）
        "title": "".join(p.title).strip() or None,
        "meta_description": (metas.get("description") or [None])[0],
        "meta_robots": metas.get("robots", []),
        "canonicals": canonicals,
        "hreflang": hreflang,
        "html_lang": p.html_lang,
        "headings": p.headings,
        "h1_count": sum(1 for h in p.headings if h["level"] == 1),
        "internal_links": internal,
        "external_links": external,
        "nofollow_links": nofollow,
        "links_in_script": _script_links(p.scripts, host),  # 不在上面三項統計內
        "images": len(p.images),
        "images_missing_alt": sum(1 for i in p.images if not i["alt"]),
        "jsonld_types": jsonld_types,
        "jsonld_invalid_blocks": jsonld_invalid,
        "jsonld_foreign_entities": foreign_entities[:5],
        "jsonld_raw": [b.strip()[:4000] for b in p.jsonld[:6]],
        "text_chars": len(text),
        "cjk_chars": len(CJK.findall(text)),
        "text_excerpt": text[:300],
        "main_text": main_text,
        "trackers": trackers,
        "generator": generator,
        "og": {k: v[0] for k, v in metas.items() if k.startswith("og:") or k.startswith("article:")},
        "signals": signals,
    }
