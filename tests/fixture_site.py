"""離線測試用的假網站（httpx.MockTransport）。模擬 2030.tw 的幾個關鍵結構，不連外網。"""
from __future__ import annotations

import json

import httpx

HOME = """<html><head><title>2030 首頁</title><link rel="canonical" href="https://2030.tw/">
<meta name="description" content="新聞">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"NewsArticle","@id":"https://2030.tw/mlb-old/","url":"https://2030.tw/mlb-old/"}</script>
<script>gtag('config','G-TEST12345');</script></head>
<body><nav><a href="/wordcup/">娛樂城</a><a href="/news/">新聞</a></nav>
<main><h1>首頁</h1><p>今天推薦 3A娛樂城 與 3a 娛樂城，還有3A-娛樂城。hash a3a9f 不算。</p>
<a href="https://agent.example.com/r?code=A1" rel="nofollow sponsored">立即註冊</a></main>
<footer><a href="/about/">關於</a></footer></body></html>"""

ROBOTS = "User-agent: *\nDisallow: /wp-admin/\nDisallow: /private/\nSitemap: https://2030.tw/sitemap_index.xml\n"
INDEX = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://2030.tw/post-sitemap.xml</loc></sitemap></sitemapindex>"""
POSTS = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://2030.tw/news/a/</loc><lastmod>2026-01-02</lastmod></url>
<url><loc>https://2030.tw/news/b/</loc><lastmod>2026-02-03</lastmod></url></urlset>"""
WORDCUP = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">""" + "".join(
    f"<url><loc>https://2030.tw/wordcup/casino-{i}/</loc><lastmod>2026-0{1 + i % 3}-01</lastmod></url>" for i in range(7)
) + "</urlset>"


class FakeSite:
    def __init__(self):
        self.calls: list[str] = []
        self.throttle: dict[str, int] = {}  # 路徑 → 還要回幾次 429
        self.timeline: str | None = None  # 指定 Wayback timeline 回應（例如實查原檔）
        self.search_ok = False  # False：搜尋回人機驗證頁

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        host, path = request.url.host, request.url.path
        if path in self.throttle and self.throttle[path] > 0:
            self.throttle[path] -= 1
            return httpx.Response(429, headers={"retry-after": "1"}, text="slow down")
        if host == "broken.example":
            raise httpx.ConnectError("boom", request=request)
        if host == "robots503.example":
            return httpx.Response(503, text="down")
        if host in ("2030.tw", "www.2030.tw"):
            if path == "/robots.txt":
                return httpx.Response(200, text=ROBOTS)
            if path == "/old-gov/":
                return httpx.Response(301, headers={"location": "https://2030.tw/"})
            if path == "/":
                return httpx.Response(200, text=HOME, headers={"content-type": "text/html; charset=utf-8"})
            if path == "/sitemap_index.xml":
                return httpx.Response(200, text=INDEX, headers={"content-type": "application/xml"})
            if path == "/post-sitemap.xml":
                return httpx.Response(200, text=POSTS, headers={"content-type": "application/xml"})
            if path == "/wordcup/sitemap.xml":
                return httpx.Response(200, text=WORDCUP, headers={"content-type": "application/xml"})
            return httpx.Response(404, text="not found", headers={"content-type": "text/html"})
        if host == "data.iana.org":
            if path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, json={"services": [[["tw"], ["https://ccrdap.twnic.tw/tw/"]]]})
        if host == "ccrdap.twnic.tw":
            if path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, json={"ldhName": "2030.tw", "status": ["active"], "port43": "whois.twnic.net.tw",
                                             "events": [{"eventAction": "registration", "eventDate": "2026-04-15T00:00:00Z"}],
                                             "nameservers": [{"ldhName": "zac.ns.cloudflare.com"}]})
        if host == "cloudflare-dns.com":
            if path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, json={"Answer": [{"data": "zac.ns.cloudflare.com."}]})
        if host == "web.archive.org":
            if path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if path.startswith("/cdx/"):
                if "collapse=urlkey" in url:
                    return httpx.Response(200, text=json.dumps([["original", "timestamp", "statuscode"],
                                                                ["https://2030.tw/old-gov/", "20150101000000", "200"]]))
                if self.timeline is not None:
                    return httpx.Response(200, text=self.timeline)
                return httpx.Response(200, text=json.dumps([["timestamp", "statuscode", "mimetype", "original"],
                                                            ["20150101000000", "200", "text/html", "https://2030.tw/"]]))
        if host == "html.duckduckgo.com":
            if path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /html/\n")
            if self.search_ok:
                return httpx.Response(200, text='<a class="result__a" href="https://2030.tw/wordcup/casino-1/">娛樂城</a>'
                                                '<a class="result__a" href="https://other.example/x">其他</a>')
            return httpx.Response(202, text="<form id='challenge-form'>anomaly-modal</form>")
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
