"""Tool 5 網域資料（RDAP＋WHOIS 備援＋DNS）、Tool 6 舊網址存檔（Wayback）。都是免費公開來源。"""
from __future__ import annotations

import json
import re
import socket
from urllib.parse import quote, urlsplit

from ..hermes_bridge import Tool
from .context import Context
from .fetcher import ToolError
from .web import _guard, decode

IANA_DNS = "https://data.iana.org/rdap/dns.json"
DOH = "https://cloudflare-dns.com/dns-query"
CDX = "https://web.archive.org/cdx/search/cdx"


def _bare(domain: str) -> str:
    d = domain.strip().lower()
    if "://" in d:
        d = urlsplit(d).hostname or d
    return d.split("/")[0].rstrip(".")


def _rdap_summary(data: dict) -> dict:
    events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", []) if isinstance(e, dict)}
    entities = []
    for ent in data.get("entities", []) or []:
        name = None
        for item in (ent.get("vcardArray") or [None, []])[1]:
            if isinstance(item, list) and item and item[0] == "fn":
                name = item[-1]
        entities.append({"roles": ent.get("roles"), "name": name, "handle": ent.get("handle")})
    return {"handle": data.get("handle"), "ldhName": data.get("ldhName"), "status": data.get("status"),
            "events": events, "nameservers": [n.get("ldhName") for n in data.get("nameservers", []) if isinstance(n, dict)],
            "entities": entities[:8], "port43": data.get("port43")}


def _whois(ctx: Context, server: str, domain: str) -> dict:
    with socket.create_connection((server, 43), timeout=15) as sock:
        sock.sendall((domain + "\r\n").encode())
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    body = b"".join(chunks)
    item = ctx.store.add(body, source=f"whois://{server}/{domain}", tool="domain_info", kind="whois", suffix=".txt")
    text = decode(body)
    return {**ctx.evidence_ref(item), "server": server, "text": text[:3000]}


def domain_tool(ctx: Context) -> Tool:
    @_guard
    def run(args: dict) -> dict:
        domain = _bare(args["domain"])
        out: dict = {"ok": True, "domain": domain, "sources": []}
        tld = domain.rsplit(".", 1)[-1]
        rdap_base = None
        try:
            boot = json.loads(ctx.fetcher.fetch(IANA_DNS, tool="domain_info", kind="rdap_bootstrap").body)
            for tlds, urls in boot.get("services", []):
                if tld in tlds and urls:
                    rdap_base = urls[0]
        except (ToolError, ValueError) as error:
            out["sources"].append({"source": "IANA RDAP bootstrap", "error": str(error)})
        if rdap_base:
            try:
                res = ctx.fetcher.fetch(rdap_base.rstrip("/") + "/domain/" + domain, tool="domain_info", kind="rdap",
                                        headers={"accept": "application/rdap+json, application/json"})
                if res.status == 200:
                    out["rdap"] = {**ctx.evidence_ref(res.evidence), **_rdap_summary(json.loads(res.body))}
                else:
                    out["sources"].append({"source": "RDAP", "status": res.status, **ctx.evidence_ref(res.evidence)})
            except (ToolError, ValueError) as error:
                out["sources"].append({"source": "RDAP", "error": str(error)})
        if "rdap" not in out or args.get("whois"):
            server = (out.get("rdap") or {}).get("port43") or {"tw": "whois.twnic.net.tw"}.get(tld, f"whois.nic.{tld}")
            try:
                out["whois"] = _whois(ctx, server, domain)
            except OSError as error:
                out["sources"].append({"source": f"WHOIS {server}", "error": f"{type(error).__name__}: {error}"})
        dns = {}
        for rtype in args.get("dns_types") or ["A", "AAAA", "NS", "MX", "TXT"]:
            try:
                res = ctx.fetcher.fetch(f"{DOH}?name={quote(domain)}&type={rtype}", tool="domain_info", kind="dns",
                                        headers={"accept": "application/dns-json"})
                data = json.loads(res.body)
                dns[rtype] = [a.get("data") for a in data.get("Answer", []) or []]
            except (ToolError, ValueError) as error:
                dns[rtype] = {"error": str(error)}
        out["dns"] = dns
        out["note"] = "註冊日期只代表目前這次註冊；過去是否換過主人要配合 wayback 時間線判斷。"
        return out

    return Tool("domain_info",
                "查網域公開資料：RDAP（註冊、到期、最後變更日期、狀態、註冊商、DNS 主機），查不到時用 WHOIS port 43 備援；"
                "再用 DNS-over-HTTPS 查 A/AAAA/NS/MX/TXT。whois=true 會同時查 WHOIS。",
                {"type": "object", "properties": {
                    "domain": {"type": "string"}, "whois": {"type": "boolean"},
                    "dns_types": {"type": "array", "items": {"type": "string"}}},
                 "required": ["domain"]}, run)


STATIC = re.compile(r"(?i)\.(js|css|map|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|eot)$")  # 只比對路徑，不看查詢字串


def _cdx(ctx: Context, params: str) -> tuple[list[list[str]], dict]:
    res = ctx.fetcher.fetch(f"{CDX}?{params}&output=json", tool="wayback", kind="wayback_cdx")
    if res.status != 200:
        raise ToolError("wayback_status", f"CDX 回 {res.status}")
    text = decode(res.body).strip()
    rows = json.loads(text) if text else []
    return rows, ctx.evidence_ref(res.evidence)


def wayback_tool(ctx: Context) -> Tool:
    @_guard
    def run(args: dict) -> dict:
        action = args.get("action", "timeline")
        target = args.get("url") or args.get("domain") or ""
        limit = min(int(args.get("limit", 200)), 2000)
        if action == "timeline":
            rows, ref = _cdx(ctx, f"url={quote(target, safe='')}&collapse=timestamp:6&fl=timestamp,statuscode,mimetype,original&limit={limit}")
            data = [dict(zip(rows[0], r, strict=False)) for r in rows[1:]] if rows else []
            years: dict[str, int] = {}
            for r in data:
                years[r["timestamp"][:4]] = years.get(r["timestamp"][:4], 0) + 1
            return {"ok": True, **ref, "target": target, "months_with_snapshots": len(data), "by_year": years,
                    "first": data[:3], "last": data[-3:]}
        if action == "old_urls":
            domain = _bare(target)
            extra = f"&from={args['from']}" if args.get("from") else ""
            extra += f"&to={args['to']}" if args.get("to") else ""
            if not args.get("include_static"):  # 在存檔服務那端就濾掉：limit 是在它那邊先算的，回來再濾，頁面網址已被靜態檔擠出去
                extra += "&filter=" + quote(r"!original:.*\.(js|css|map|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|eot)(\?.*)?$", safe="")
            rows, ref = _cdx(ctx, f"url={quote(domain)}/*&collapse=urlkey&fl=original,timestamp,statuscode&limit={limit}{extra}")
            data = [dict(zip(rows[0], r, strict=False)) for r in rows[1:]] if rows else []
            flt = (args.get("contains") or "").lower()
            if flt:
                data = [r for r in data if flt in r["original"].lower()]
            out = {"ok": True, **ref, "domain": domain, "count": len(data), "limit": limit,
                   "reached_limit": len(rows) - 1 >= limit if rows else False}
            if not args.get("include_static"):  # 2026-11-17 量到：80 列裡 56 列是 /_nuxt/*.js，把舊頁面網址擠掉
                data = [r for r in data if not STATIC.search(urlsplit(r["original"]).path)]  # 漏網保險，不回報計數
                out["count"] = len(data)
                out["static_files"] = "已在存檔服務端濾掉 js／css／圖片等靜態檔（數量不明）；include_static=true 可全列"
            return {**out, "urls": data[:300]}
        if action == "snapshot":
            ts = args.get("timestamp") or "2015"
            res = ctx.fetcher.fetch(f"https://web.archive.org/web/{ts}id_/{target}", tool="wayback", kind="wayback_snapshot")
            return {"ok": True, **ctx.evidence_ref(res.evidence), "status": res.status, "final_url": res.final_url,
                    "hint": "舊頁內容用 inspect_page 讀上面的 evidence_id（頁面本體）。"}
        if action == "check_current":
            urls = (args.get("urls") or [])[:30]
            checks = []
            for u in urls:
                try:
                    res = ctx.fetcher.fetch(u, follow_redirects=False, tool="wayback", kind="current_check",
                                            method=args.get("method", "GET"))
                    checks.append({"url": u, "status": res.status, "location": res.headers.get("location"),
                                   **ctx.evidence_ref(res.evidence)})
                except ToolError as error:
                    checks.append({"url": u, "error": error.code, "detail": error.detail})
                    if error.code in ("site_throttled", "site_paused"):
                        break
            return {"ok": True, "checks": checks}
        raise ToolError("bad_args", f"未知 action {action}")

    return Tool("wayback",
                "Internet Archive 舊網址存檔（免費）。action=timeline（url 或網域：每月有無存檔、各年數量、最早最晚）；"
                "old_urls（domain：存檔過的舊網址清單，可 contains 篩選、from/to 年份；預設在存檔服務端就濾掉 js／css／圖片等靜態檔（濾掉幾筆不知道），include_static=true 可全列；reached_limit=true 表示後面還有沒列到的網址，「查無」不成立，可用 from/to 縮小或加大 limit 再查）；snapshot（url＋timestamp：抓當年原始頁，"
                "之後用 inspect_page 看）；check_current（urls：舊網址現在回什麼，不跟轉址，最多 30 個）。遇 429/503 會停止。",
                {"type": "object", "properties": {
                    "action": {"type": "string", "enum": ["timeline", "old_urls", "snapshot", "check_current"]},
                    "url": {"type": "string"}, "domain": {"type": "string"}, "timestamp": {"type": "string"},
                    "contains": {"type": "string"}, "include_static": {"type": "boolean"}, "from": {"type": "string"}, "to": {"type": "string"},
                    "limit": {"type": "integer"}, "urls": {"type": "array", "items": {"type": "string"}},
                    "method": {"type": "string", "enum": ["GET", "HEAD"]}},
                 "required": ["action"]}, run)
