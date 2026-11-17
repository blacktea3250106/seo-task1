"""第 2 步：8 個工具各自的離線測試（假網站，不連外網）。"""
from __future__ import annotations

import json

import httpx
import pytest
from fixture_site import FakeSite

from seo_agent.tools import build_tools
from seo_agent.tools.context import Context
from seo_agent.tools.fetcher import ToolError
from seo_agent.tools.textmatch import keyword_hits


@pytest.fixture
def env(tmp_path):
    site = FakeSite()
    slept: list[float] = []
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=1.5, sleep=slept.append)
    tools = {t.name: t.func for t in build_tools(ctx)}
    return ctx, tools, site, slept


def test_text_match_counts_3a_variants():
    r = keyword_hits("推薦 3A娛樂城 與 3a 娛樂城，還有3A-娛樂城。hash a3a9f", "3a娛樂城")
    assert r["exact"] == 0 and r["loose"] == 3
    assert set(r["variants"]) == {"3A娛樂城", "3a 娛樂城", "3A-娛樂城"}  # 回傳原文寫法
    assert keyword_hits("a3a娛樂城", "3a娛樂城")["loose"] == 0  # 英數邊界


def test_text_match_tool_scopes(env):
    ctx, tools, *_ = env
    out = tools["text_match"]({"url": "https://2030.tw/", "keywords": ["3a娛樂城", "娛樂城"]})
    assert out["ok"] and out["results"]["3a娛樂城"]["text"]["loose"] == 3
    assert out["results"]["3a娛樂城"]["text"]["exact"] == 0
    assert set(out["results"]["娛樂城"]) >= {"text", "html", "url", "title", "headings"}


def test_fetch_respects_robots_and_saves_evidence(env):
    ctx, tools, site, _ = env
    blocked = tools["polite_fetch"]({"url": "https://2030.tw/private/x"})
    assert blocked["ok"] is False and blocked["error"]["code"] == "robots_disallowed"
    ok = tools["polite_fetch"]({"url": "https://2030.tw/old-gov/"})
    assert ok["status"] == 200 and [h["status"] for h in ok["redirect_chain"]] == [301, 200]
    assert ctx.store.get(ok["evidence_id"])["sha256"].startswith(ok["sha256"])
    raw = tools["polite_fetch"]({"url": "https://2030.tw/old-gov/", "follow_redirects": False})
    assert raw["status"] == 301 and raw["headers"]["location"] == "https://2030.tw/"
    assert "<untrusted_web_content" in ok["preview"]


def test_www_shares_interval(env):
    ctx, tools, site, slept = env
    tools["polite_fetch"]({"url": "https://2030.tw/"})
    tools["polite_fetch"]({"url": "https://www.2030.tw/"})
    # 同站（含 www）每次請求之間都要等；robots 也算請求
    assert len(slept) >= 3 and all(0 < s <= 1.5 for s in slept)


def test_robots_5xx_means_disallow(env):
    _, tools, *_ = env
    out = tools["polite_fetch"]({"url": "https://robots503.example/page"})
    assert out["error"]["code"] == "robots_disallowed"


def test_429_retry_once_then_pause_site(env):
    ctx, tools, site, slept = env
    site.throttle["/news/"] = 2
    out = tools["polite_fetch"]({"url": "https://2030.tw/news/"})
    assert out["error"]["code"] == "site_throttled"
    assert site.calls.count("https://2030.tw/news/") == 2  # 原請求＋重試 1 次
    again = tools["polite_fetch"]({"url": "https://www.2030.tw/"})
    assert again["error"]["code"] == "site_paused"  # www 也一起停
    site.throttle["/about/"] = 1
    ctx2 = Context(ctx.run_dir.parent / "run2", transport=site.transport(), sleep=lambda s: None)
    tools2 = {t.name: t.func for t in build_tools(ctx2)}
    assert tools2["polite_fetch"]({"url": "https://2030.tw/about/"})["status"] == 404  # 429 一次後重試成功


def test_network_error_reported_not_raised(env):
    _, tools, *_ = env
    out = tools["polite_fetch"]({"url": "https://broken.example/"})
    assert out["ok"] is False and out["error"]["code"] == "network_error"


def test_paid_login_and_post_need_approval(env):
    ctx, tools, *_ = env
    for args in ({"url": "https://api.ahrefs.com/v3/site"}, {"url": "https://2030.tw/wp-login.php"},
                 {"url": "https://2030.tw/register/"}):
        assert tools["polite_fetch"](args)["error"]["code"] == "approval_required"
    lines = (ctx.run_dir / "approvals_pending.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and json.loads(lines[0])["status"] == "blocked_pending_human"
    with pytest.raises(ToolError):
        ctx.fetcher.check_allowed("https://2030.tw/", "POST")


def test_sitemap_finds_folder_sitemap(env):
    _, tools, *_ = env
    out = tools["sitemap_tree"]({"action": "build", "site": "2030.tw"})
    sections = {s["section"]: s["urls"] for s in out["sections"]}
    assert sections["/wordcup/"] == 7 and sections["/news/"] == 2
    found = {f["url"]: f["found_by"] for f in out["sitemap_files_ok"]}
    assert found["https://2030.tw/wordcup/sitemap.xml"] == "資料夾探測"
    assert found["https://2030.tw/sitemap_index.xml"] == "robots.txt"
    assert tools["sitemap_tree"]({"action": "search", "text": "casino-3"})["matches"] == 1
    months = tools["sitemap_tree"]({"action": "by_month", "section": "/wordcup/"})["months"]
    assert sum(months.values()) == 7
    sample = tools["sitemap_tree"]({"action": "sample", "section": "/wordcup/", "limit": 2})
    assert sample["total"] == 7 and len(sample["head"]) == 2
    cmp = tools["sitemap_tree"]({"action": "compare", "urls": ["https://2030.tw/news/a/", "https://2030.tw/news/zzz/"]})
    assert cmp["not_in_sitemaps"] == ["https://2030.tw/news/zzz/"]
    gap = tools["sitemap_tree"]({"action": "compare", "expected_total": 10, "section": "/news/"})
    assert gap["gap"] == 8
    assert tools["sitemap_tree"]({"action": "expand", "prefix": "/wordcup/", "depth": 2})["matched"] == 7


def test_sitemap_search_matches_is_total_not_limit(env):
    """matches 是全部符合筆數，examples 才受 limit 限制；examples_shown 標出實際列出幾筆。"""
    _, tools, *_ = env
    tools["sitemap_tree"]({"action": "build", "site": "2030.tw"})
    out = tools["sitemap_tree"]({"action": "search", "text": "/wordcup/", "limit": 3})
    assert out["matches"] == 7
    assert out["examples_shown"] == 3 == len(out["examples"])


def test_sitemap_image_loc_does_not_replace_page_loc(tmp_path):
    """決策 #56：<image:image><image:loc> 在頁面 <loc> 之後，不能蓋掉頁面網址；不帶圖片的列與 sitemap 索引照常。"""
    site = FakeSite()
    posts = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
 xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
<url><loc>https://2030.tw/news/a/</loc><lastmod>2026-01-02</lastmod>
<image:image><image:loc>https://2030.tw/wp-content/uploads/a.jpg</image:loc></image:image>
<image:image><image:loc>https://2030.tw/wp-content/uploads/a2.jpg</image:loc></image:image></url>
<url><loc>https://2030.tw/news/b/</loc><lastmod>2026-02-03</lastmod></url></urlset>"""
    base = site.handler
    site.handler = lambda request: (httpx.Response(200, text=posts, headers={"content-type": "application/xml"})
                                    if request.url.path == "/post-sitemap.xml" else base(request))
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=0, sleep=lambda s: None)
    tools = {t.name: t.func for t in build_tools(ctx)}
    out = tools["sitemap_tree"]({"action": "build", "site": "2030.tw"})
    assert out["ok"]
    assert tools["sitemap_tree"]({"action": "search", "text": "wp-content"})["matches"] == 0
    assert tools["sitemap_tree"]({"action": "search", "text": "/news/a/"})["matches"] == 1
    assert tools["sitemap_tree"]({"action": "search", "text": "/news/b/"})["matches"] == 1
    assert tools["sitemap_tree"]({"action": "search", "text": "casino-3"})["matches"] == 1  # 不帶圖片的 sitemap 照常
    found = {f["url"]: f["found_by"] for f in out["sitemap_files_ok"]}
    assert found["https://2030.tw/post-sitemap.xml"] == "sitemap 索引"  # sitemapindex 照常
    months = tools["sitemap_tree"]({"action": "by_month", "section": "/news/"})["months"]
    assert "2026-01" in json.dumps(months, ensure_ascii=False)


def test_inspect_page_positions_trackers_jsonld(env):
    _, tools, *_ = env
    out = tools["inspect_page"]({"url": "https://2030.tw/", "part": "all"})
    pos = {link["url"]: link["position"] for link in out["links"]}
    assert pos["https://2030.tw/wordcup/"] == "menu" and pos["https://2030.tw/about/"] == "footer"
    assert pos["https://agent.example.com/r?code=A1"] == "body"
    assert out["trackers"]["google_analytics_ga4"] == ["G-TEST12345"]
    assert out["jsonld_foreign_entities"] == ["https://2030.tw/mlb-old/"]
    assert out["signals"]["jsonld_entity_mismatch"] is True
    assert "3A娛樂城" in out["main_text"]
    reg = tools["inspect_page"]({"evidence_id": out["evidence_id"], "part": "links", "link_filter": "註冊"})
    assert reg["links_total"] == 1 and "sponsored" in reg["links"][0]["rel"]


def test_domain_info(env):
    _, tools, *_ = env
    out = tools["domain_info"]({"domain": "https://2030.tw/"})
    assert out["rdap"]["events"]["registration"].startswith("2026-04-15")
    assert out["dns"]["NS"] == ["zac.ns.cloudflare.com."]


def test_wayback(env):
    _, tools, *_ = env
    tl = tools["wayback"]({"action": "timeline", "url": "2030.tw"})
    assert tl["by_year"] == {"2015": 1}
    old = tools["wayback"]({"action": "old_urls", "domain": "2030.tw"})
    assert old["urls"][0]["original"] == "https://2030.tw/old-gov/"
    cur = tools["wayback"]({"action": "check_current", "urls": ["https://2030.tw/old-gov/"]})
    assert cur["checks"][0]["status"] == 301


def test_web_search_challenge_is_unknown(env):
    _, tools, *_ = env
    out = tools["web_search"]({"query": "site:2030.tw 娛樂城"})
    assert out["ok"] is False and out["status"] == "unknown" and "≠" in out["note"]


def test_class_based_regions():
    from seo_agent.tools.html_parse import parse_html
    html = ('<div class="jeg_header"><div class="jeg_nav_item"><a href="/wordcup/">娛樂城</a></div></div>'
            '<div class="entry-header"><h1>標題</h1><a href="/a/">內文</a></div>'
            '<div class="jeg_footer"><a href="/about/">關於</a></div><div role="complementary"><a href="/s/">側</a></div>')
    r = parse_html(html, "https://2030.tw/")
    pos = {link["url"]: link["position"] for link in r["internal_links"]}
    assert pos == {"https://2030.tw/wordcup/": "menu", "https://2030.tw/a/": "body",
                   "https://2030.tw/about/": "footer", "https://2030.tw/s/": "sidebar"}
    assert "標題" in r["main_text"] and "關於" not in r["main_text"]


# ---- 決策 #65：Tool 不把「沒查」回成「沒有」，數字口徑要分清楚 ----
def test_sitemap_query_before_build_is_error_but_empty_site_is_zero(env):
    ctx = env[0]
    import sqlite3

    from seo_agent.tools.sitemap import sitemap_tool
    tool = sitemap_tool(ctx).func
    out = tool({"action": "compare", "urls": ["https://x/a"]})
    assert out["ok"] is False and "build" in out["error"]["detail"]  # 還沒 build
    with sqlite3.connect(ctx.run_dir / "sitemap.sqlite") as db:  # build 過，但網站沒有 sitemap（404）
        db.execute("INSERT INTO sitemaps VALUES('https://x/sitemap.xml', 404, 'missing', 0, NULL, 'robots.txt', NULL, NULL)")
    assert tool({"action": "summary"})["url_rows"] == 0


def test_sitemap_section_counts_distinct_urls(env):
    ctx = env[0]
    import sqlite3

    from seo_agent.tools.sitemap import sitemap_tool
    tool = sitemap_tool(ctx).func
    assert tool({"action": "summary"})["ok"] is False  # 第一次呼叫才建表
    with sqlite3.connect(ctx.run_dir / "sitemap.sqlite") as db:
        db.execute("INSERT INTO sitemaps VALUES('https://x/s1.xml', 200, 'urlset', 2, NULL, 'robots.txt', NULL, NULL)")
        db.executemany("INSERT INTO urls VALUES(?,?,?,?)", [("https://x/a/1", "2026-01-01", "s1", "/a/"),
                                                            ("https://x/a/1", "2026-01-01", "s2", "/a/"),
                                                            ("https://x/a/2", "2026-01-02", "s1", "/a/")])
    out = tool({"action": "summary"})
    assert out["sections"][0]["urls"] == 2 and out["sections"][0]["rows"] == 3 and out["sections_total"] == 1
    assert tool({"action": "by_month", "section": "/a/"})["months"] == {"2026-01": 2}
    found = tool({"action": "search", "text": "/a/", "limit": 5})  # search／expand 和 summary 同口徑：不重複網址
    assert found["matches"] == 2 and found["rows"] == 3 and found["by_sitemap"] == {"s1": 2, "s2": 1}
    assert [e["loc"] for e in found["examples"]] == ["https://x/a/1", "https://x/a/2"] and found["examples_shown"] == 2
    tree = tool({"action": "expand", "prefix": "/a/", "depth": 2})
    assert tree["matched"] == 2 and tree["rows"] == 3 and sum(tree["children"].values()) == 2


def test_inspect_and_text_match_scopes(env):
    ctx = env[0]
    from seo_agent.tools.web import inspect_tool, text_match_tool
    html = ("<html><head><script>gtag('config','GT-ABC1234')</script></head><body><nav><a href='/x'>娛樂城</a></nav>"
            "<main><p>hello</p><a href='https://o.example/a' rel='nofollow'>o</a><a href='https://share.example/s'>s</a>"
            "<a href='/in' rel='nofollow'>in</a></main></body></html>").encode()
    eid = ctx.store.add(html, source="https://x.test/", tool="polite_fetch", kind="page",
                        meta={"headers": {"content-type": "text/html"}, "status": 200})["id"]
    page = inspect_tool(ctx).func({"evidence_id": eid})
    lc = page["link_counts"]
    assert lc["external"] == 2 and lc["nofollow"] == 2 and lc["external_nofollow"] == 1
    assert lc["external_followed_hosts"] == {"share.example": 1} and page["trackers"]["google_tag"] == ["GT-ABC1234"]
    hits = text_match_tool(ctx).func({"evidence_id": eid, "keywords": ["娛樂城"]})["results"]["娛樂城"]
    assert hits["text"]["exact"] == 0 and hits["all_text"]["exact"] == 1  # 選單裡有，正文區沒有


def test_build_is_brief_and_summary_is_full(env):
    """決策 #66：build 給模型的回傳不重送資料卡已有的分區表與 404 清單；資料仍可用 summary 拿到。"""
    _, tools, _, _ = env
    brief = tools["sitemap_tree"]({"action": "build", "site": "https://rival.example"})
    assert brief["ok"] and "sitemap_files_missing_or_error" not in brief and "action=summary" in brief["brief"]
    assert sum(brief["sitemap_files_not_ok_by_status"].values()) >= len(brief["sitemap_files_not_ok_except_404"])
    assert all(f["status"] != 404 for f in brief["sitemap_files_not_ok_except_404"])
    full = tools["sitemap_tree"]({"action": "summary"})
    assert "sitemap_files_missing_or_error" in full and full["distinct_urls"] == brief["distinct_urls"]
    assert len(full["sections"]) >= len(brief["sections"])


def test_inspect_refuses_tool_summary_id_and_names_the_page(env):
    """決策 #66：拿 Tool 整理結果（JSON）的編號去讀頁，要說清楚並指向頁面本體，不能回一份幾百字的「頁面」。"""
    ctx = env[0]
    from seo_agent.tools.web import inspect_tool
    page = ctx.store.add(b"<html><body><main><p>old page</p></main></body></html>", source="https://x.example/old",
                         tool="wayback", kind="wayback_snapshot", meta={"status": 200})
    derived = ctx.store.add(json.dumps({"ok": True, "evidence_id": page["id"], "status": 200}).encode(),
                            source="wayback:{}", tool="wayback", kind="derived", suffix=".json")
    out = inspect_tool(ctx).func({"evidence_id": derived["id"]})
    assert out["ok"] is False and page["id"] in json.dumps(out, ensure_ascii=False)
    assert inspect_tool(ctx).func({"evidence_id": page["id"], "part": "text"})["ok"] is True


def test_old_urls_skips_static_files():
    """只比對路徑：查詢字串裡的檔名不算靜態檔。"""
    from urllib.parse import urlsplit

    from seo_agent.tools.domain import STATIC
    static = lambda u: bool(STATIC.search(urlsplit(u).path))  # noqa: E731
    assert static("https://x.tw/assets/abc123.js") and static("https://x.tw/a/logo.PNG?v=2")
    assert not static("https://x.tw/old-short-link") and not static("https://x.tw/article/json-guide/")
    assert not static("https://x.tw/?attachment=logo.png") and not static("https://x.tw/index.php?file=a.js")


def test_review_excerpt_keeps_head_facts(env):
    """決策 #66：審查看的頁面摘錄要帶 meta robots、canonical、og 日期、JSON-LD 日期，否則會把有證據的結論判成沒證據。"""
    ctx = env[0]
    from seo_agent.review import _text
    html = ('<html><head><title>T</title><meta name="robots" content="noindex"><link rel="canonical" href="https://x.example/a">'
            '<meta property="article:published_time" content="2026-07-12T00:00:00+08:00">'
            '<script type="application/ld+json">{"@type":"Article","datePublished":"2026-11-10"}</script></head>'
            '<body><main><p>visible words</p></main></body></html>').encode()
    item = ctx.store.add(html, source="https://x.example/a", tool="polite_fetch", kind="page", meta={"status": 200})
    out = _text(ctx, item["id"])
    assert "noindex" in out and "datePublished=2026-11-10" in out and "https://x.example/a" in out and "visible words" in out


def test_review_excerpt_dates_survive_long_og(env):
    """審查 M2：og 很長時，JSON-LD 日期不能被擠掉；日期只取 JSON-LD 區塊，不掃整份 HTML。"""
    ctx = env[0]
    from seo_agent.review import _text
    html = ('<html><head><title>T</title>'
            + '<meta property="og:description" content="' + "長" * 1400 + '">'
            + '<meta property="og:image" content="https://x.example/' + "i" * 600 + '.jpg">'
            + '<meta property="article:modified_time" content="2026-11-10T00:00:00+08:00">'
            + '<script type="application/ld+json">{"@type":"Article","datePublished":"2026-07-12","dateModified":"2026-11-10"}</script>'
            + '</head><body><main><p>visible words</p><script>var other={"datePublished":"1999-01-01"}</script></main></body></html>').encode()
    item = ctx.store.add(html, source="https://x.example/a", tool="polite_fetch", kind="page", meta={"status": 200})
    out = _text(ctx, item["id"])
    assert "datePublished=2026-07-12" in out and "dateModified=2026-11-10" in out and "article:modified_time" in out
    assert "1999-01-01" not in out.split("〔可見文字〕")[0] and "長長長" not in out.split("〔可見文字〕")[0]


def test_snapshot_own_jsonld_is_not_foreign(env):
    """審查 M3：Wayback 快照要用原始網址解析，頁面自己的 JSON-LD @id 不能被標成錯置實體。"""
    ctx = env[0]
    from seo_agent.review import _text
    from seo_agent.tools.web import inspect_tool
    html = ('<html><head><title>Old</title><script type="application/ld+json">'
            '{"@type":"WebPage","@id":"https://old.example/about","url":"https://old.example/about"}</script></head>'
            '<body><main><p>old words</p></main></body></html>').encode()
    item = ctx.store.add(html, source="https://old.example/about", tool="wayback", kind="wayback_snapshot",
                         meta={"status": 200, "final_url": "https://web.archive.org/web/20200101000000id_/https://old.example/about"})
    assert "jsonld_foreign_entities" not in _text(ctx, item["id"]).split("〔可見文字〕")[0]
    assert not inspect_tool(ctx).func({"evidence_id": item["id"], "part": "all"}).get("jsonld_foreign_entities")


def test_inspect_refusal_does_not_call_a_listing_a_page(env):
    """審查 minor 1：derived 指向的原檔不是網頁（例如存檔清單）時，不能說它是「頁面本體」。"""
    ctx = env[0]
    from seo_agent.tools.web import inspect_tool
    cdx = ctx.store.add(b'[["original"],["https://x.example/a"]]', source="cdx", tool="wayback", kind="wayback_cdx",
                        suffix=".json", meta={"status": 200})
    derived = ctx.store.add(json.dumps({"ok": True, "evidence_id": cdx["id"]}).encode(), source="wayback:{}",
                            tool="wayback", kind="derived", suffix=".json")
    detail = json.dumps(inspect_tool(ctx).func({"evidence_id": derived["id"]}), ensure_ascii=False)
    assert "頁面本體" not in detail and "不是網頁" in detail


def test_experiment_switches_default_off_and_add_only_facts(env, monkeypatch):
    """決策 #67：實驗開關預設關；已被擋的搜尋不重發。（multi 隨 research_log 移除，決策 #71）"""
    ctx, tools, site, _ = env
    monkeypatch.setenv("SEO_EXPERIMENT", "searchmemo")
    ctx.search_blocked = "E-0001"
    before = len(site.calls)
    memo = tools["web_search"]({"query": "x"})
    assert memo["ok"] is False and memo["request_sent"] is False and len(site.calls) == before
    assert memo["blocked_evidence_id"] == "E-0001" and "evidence_id" not in memo  # 這次沒抓東西，不冒充這次的證據


def test_leaninspect_skips_only_repeated_blocks(env, monkeypatch):
    """實驗開關 leaninspect：關閉時照舊全送；開啟時 part=all 不重送同一次 run 已回傳過、內容完全相同的
    同位置連結組與 JSON-LD 區塊（改成一行事實），只在這頁的照送，指定 part=links 仍全送。"""
    ctx = env[0]
    from seo_agent.tools.web import inspect_tool
    org = '{"@type":"Organization","@id":"https://x.test/#org","name":"' + "N" * 200 + '"}'
    menu = "".join(f"<a href='/menu-{i}/'>menu {i}</a>" for i in range(12))

    def page(name):
        html = (f"<html><head><script type='application/ld+json'>{org}</script>"
                f"<script type='application/ld+json'>{{\"@type\":\"Article\",\"headline\":\"{name}\"}}</script></head>"
                f"<body><nav>{menu}</nav><main><p>{name}</p><a href='/only-{name}/'>{name}</a></main></body></html>")
        return ctx.store.add(html.encode(), source=f"https://x.test/{name}", tool="polite_fetch", kind="page",
                             meta={"headers": {"content-type": "text/html"}, "status": 200})["id"]
    a, b = page("a"), page("b")
    off = inspect_tool(ctx)
    full = [off.func({"evidence_id": e, "part": "all"}) for e in (a, b)]
    assert "links_not_resent" not in full[1] and len(full[1]["jsonld_raw"]) == 2 and len(full[1]["links"]) == 13
    monkeypatch.setenv("SEO_EXPERIMENT", "leaninspect")
    tool = inspect_tool(ctx)
    first, second = tool.func({"evidence_id": a, "part": "all"}), tool.func({"evidence_id": b, "part": "all"})
    assert first == full[0]  # 第一次照常全送
    assert second["links_not_resent"] == [f"menu 位置 12 個連結：與 {a} 那次回傳相同，未重送（part=links 可取回）"]
    assert [link["url"] for link in second["links"]] == ["https://x.test/only-b/"]  # 只在這頁的連結照送
    assert second["jsonld_raw"][0] == f"與 {a} 那次回傳相同，未重送（part=jsonld 可取回）" and '"b"' in second["jsonld_raw"][1]
    rest = lambda o: {k: v for k, v in o.items() if k not in ("links", "links_not_resent", "jsonld_raw")}  # noqa: E731
    assert rest(second) == rest(full[1])
    assert tool.func({"evidence_id": b, "part": "links"})["links"] == full[1]["links"]  # 指定 part 取回完整資料
    assert tool.func({"evidence_id": a, "part": "all"}) == first  # 同一頁重讀不省略：兩次回傳相同（停止判斷照舊）
    assert tool.func({"evidence_id": b, "part": "all"}) == second


def test_old_urls_does_not_claim_a_static_count(env):
    """審查必修 1：靜態檔在存檔服務端就濾掉，本地數不到；不能回「略過 0 筆」讓模型以為存檔裡沒有靜態檔。"""
    ctx, tools, *_ = env
    out = tools["wayback"]({"action": "old_urls", "domain": "2030.tw"})
    assert out["ok"] and "static_files_skipped" not in out and "數量不明" in out["static_files"]
    assert "static_files" not in tools["wayback"]({"action": "old_urls", "domain": "2030.tw", "include_static": True})
    desc = next(t.description for t in build_tools(ctx) if t.name == "wayback")
    assert "略過幾筆" not in desc and "include_static=true 可全列" in desc


def test_review_head_facts_mark_truncation_and_skip_og_image(env):
    """審查必修 4：JSON-LD 日期最多 6 筆，被截斷要標；og:image:* 不放。"""
    ctx = env[0]
    from seo_agent.review import _text
    dates = ",".join(f'{{"@type":"Article","datePublished":"2026-01-0{i}"}}' for i in range(1, 9))
    html = ('<html><head><title>T</title><meta property="og:type" content="article">'
            '<meta property="og:image:type" content="image/png"><meta property="og:image:secure_url" content="https://x/i.png">'
            f'<script type="application/ld+json">[{dates}]</script></head><body><main><p>v</p></main></body></html>').encode()
    item = ctx.store.add(html, source="https://x.example/a", tool="polite_fetch", kind="page", meta={"status": 200})
    head = _text(ctx, item["id"]).split("〔可見文字〕")[0]
    assert head.count("datePublished=") == 6 and "jsonld_dates" in head and "…（截斷）" in head
    assert "og:type" in head and "og:image" not in head


def test_sitemap_not_404_list_comes_from_full_list(env):
    """審查必修 5：404 很多時，404 以外的讀不到的檔不能因清單先截到 60 筆而消失。"""
    ctx = env[0]
    import sqlite3

    from seo_agent.tools.sitemap import _brief, sitemap_tool
    tool = sitemap_tool(ctx).func
    tool({"action": "summary"})  # 建表
    with sqlite3.connect(ctx.run_dir / "sitemap.sqlite") as db:
        db.executemany("INSERT INTO sitemaps VALUES(?,?,?,?,?,?,?,?)",
                       [(f"https://x/{i:03d}/sitemap.xml", 404, "missing", 0, None, "a", None, None) for i in range(70)]
                       + [(f"https://x/z{i}.xml", 500, "missing", 0, None, "z", None, None) for i in range(3)])
    full = tool({"action": "summary"})
    assert len(full["sitemap_files_missing_or_error"]) == 60 and full["sitemap_files_not_ok_except_404_total"] == 3
    brief = _brief(full)
    assert [f["status"] for f in brief["sitemap_files_not_ok_except_404"]] == [500, 500, 500]


def test_inspect_reports_links_written_in_script(env):
    """script 字串裡的 <a href> 不在 HTML 連結統計內：照實另回一個欄位（筆數＋外部主機），不改既有統計。"""
    ctx = env[0]
    from seo_agent.tools.html_parse import parse_html
    from seo_agent.tools.web import inspect_tool
    base = ("<main><p>hello</p><a href='https://o.example/a' rel='nofollow'>o</a>"
            "<a href='https://share.example/s'>s</a><a href='/in' rel='nofollow'>in</a></main>")

    def add(html, name):
        return ctx.store.add(html.encode(), source=f"https://x.test/{name}", tool="polite_fetch", kind="page",
                             meta={"headers": {"content-type": "text/html"}, "status": 200})["id"]
    plain = add(f"<html><body>{base}</body></html>", "plain")
    noise = ("<script type='application/ld+json'>{\"@type\":\"Organization\",\"url\":\"https://jsonld.example/\","
             "\"description\":\"<a href='https://jsonld.example/x'>j</a>\"}</script>"
             "<script src='https://cdn.example/a.js'></script>"
             "<script>fetch('https://api.example/v1'); var u = 'https://plain.example/'; el.href = 'https://set.example/';"
             "for (i = 0; i<a.length; i++) {}</script>"
             "<script type='application/json'>{\"html\":\"<a href=\\\"https://x.example/\\\">x</a>\"}</script>")  # 不是 JS，不算
    js = ("<script>document.write(\"<a href=\\\"https:\\/\\/partner.example\\/x\\\" target=\\\"_blank\\\">p</a>\");"
          "var t = '<a class=\\'b\\' href=\\'https://partner.example/y\\'>q</a>' + "
          "'<a href=\"https://other.example/z\">r</a><a href=\"https://x.test/self\">s</a>';</script>")
    scripted = add(f"<html><head>{noise}</head><body>{base}{js}</body></html>", "scripted")
    tool = inspect_tool(ctx)
    out_plain, out = tool.func({"evidence_id": plain, "part": "all"}), tool.func({"evidence_id": scripted, "part": "all"})
    assert "links_in_script" not in out_plain  # 沒有就不輸出
    assert parse_html(f"<html><head>{noise}</head><body>{base}</body></html>", "https://x.test/")["links_in_script"] == \
        {"count": 0, "external_hosts": []}  # JSON-LD、script src、fetch／一般網址字串都不算
    lis = out["links_in_script"]
    assert lis["count"] == 4 and lis["external_hosts"] == ["other.example", "partner.example"] and lis["note"]
    assert out["link_counts"] == out_plain["link_counts"] and out["links"] == out_plain["links"]  # 既有統計不變
    assert out["link_counts"]["external"] == 2 and out["link_counts"]["nofollow"] == 2
    assert tool.func({"evidence_id": scripted, "part": "text"}).get("links_in_script") is None
