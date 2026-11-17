"""第 3 步：經驗層、停止判斷、Skill 讀入。（報告檢查改為 7 段，測試在 test_report_v3.py）"""
from __future__ import annotations

import json

import pytest

from seo_agent.hermes_bridge import Tool, ToolLog
from seo_agent.stop import StopGuard
from seo_agent.tools.context import Context


@pytest.fixture
def ctx(tmp_path):
    c = Context(tmp_path / "run")
    for i in range(3):
        c.store.add(f"page {i}".encode(), source=f"https://x/{i}", tool="polite_fetch", kind="page", suffix=".html")
    return c


def test_stop_after_five_calls_without_progress(ctx):
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard)
    same = log.wrap(Tool("polite_fetch", "", {}, lambda a: {"ok": True}))
    fresh = log.wrap(Tool("inspect_page", "", {}, lambda a: {"ok": True, "title": f"第 {len(ctx.store.ids())} 頁", **ctx.evidence_ref(
        ctx.store.add(str(len(ctx.store.ids())).encode() + b"new", source="s", tool="t", kind="k"))}))
    for _ in range(4):
        same({})
    fresh({})  # 新證據 → 歸零
    assert guard.streak == 0
    for _ in range(5):
        json.loads(same({}))
    blocked = json.loads(same({}))
    assert blocked["error"]["code"] == "stop_no_progress"


def test_stop_time_limit(ctx):
    now = [0.0]
    guard = StopGuard(ctx, clock=lambda: now[0])
    now[0] = 99 * 60
    assert guard.before("polite_fetch", {}) is None
    now[0] = 100 * 60  # 剩 20 分鐘：保留給報告與 ⑥ 審查（G-36）
    assert guard.before("polite_fetch", {})["error"]["code"] == "stop_time_limit"
    assert guard.before("submit_report", {}) is None


def test_derived_results_count(ctx):
    """審查 major 2：衍生查詢有新結果算進展；同樣結果不算。"""
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard)
    query = log.wrap(Tool("sitemap_tree", "", {}, lambda a: {"ok": True, "rows": [a.get("prefix") + "page-1"]}))
    first = json.loads(query({"prefix": "/a/"}))
    assert first["derived_evidence_id"] in ctx.store.ids() and guard.streak == 0
    for _ in range(3):
        query({"prefix": "/a/"})  # 同樣結果
    assert guard.streak == 3
    query({"prefix": "/b/"})  # 換角度查到新東西
    assert guard.streak == 0


def test_refetch_with_new_date_header_is_not_progress(ctx):
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard)
    tick = [0]

    def fetch(a):
        tick[0] += 1
        item = ctx.store.add(b"same body", source="u", tool="polite_fetch", kind="page")
        return {"ok": True, "evidence_id": item["id"], "headers": {"date": f"t{tick[0]}"}}
    f = log.wrap(Tool("polite_fetch", "", {}, fetch))
    f({})
    for _ in range(3):
        f({})
    assert guard.streak == 3
    derived = log.wrap(Tool("inspect_page", "", {}, lambda a: {"ok": True, "title": "x", "headers": {"date": str(tick)},
                                                              "fetched_at": str(tick)}))
    derived({})
    tick[0] += 1
    derived({})
    assert guard.streak == 1  # 第一次是新內容（歸零）；第二次只差日期，不算新


def test_refetch_changing_body_and_echoed_args_are_not_progress(ctx):
    """第三次審查 major：內容會變的重抓、換參數的零命中查詢都不算進展。"""
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard)
    n = [0]

    def dns(a):
        n[0] += 1
        ctx.store.add(f'{{"TTL": {300 - n[0]}}}'.encode(), source="https://dns.google/resolve?name=x", tool="domain_info",
                      kind="dns", meta={"method": "GET"})
        return {"ok": True, "records": [{"ttl": 300 - n[0], "data": "1.2.3.4"}]}
    d = log.wrap(Tool("domain_info", "", {}, dns))
    d({})
    assert guard.streak == 0
    d({})
    d({})
    assert guard.streak == 2
    search = log.wrap(Tool("sitemap_tree", "", {}, lambda a: {"ok": True, "query": a["query"], "matches": []}))
    search({"query": "a"})
    search({"query": "b"})
    assert guard.streak == 4
    hit = log.wrap(Tool("sitemap_tree", "", {}, lambda a: {"ok": True, "query": a["query"], "matches": ["/x/"]}))
    hit({"query": "c"})
    assert guard.streak == 0
    hit({"query": "d"})  # 同樣命中、只換參數
    assert guard.streak == 1


def test_text_match_on_existing_evidence_counts_new_findings(ctx):
    """第四次審查 major：對同一份舊證據用不同關鍵字比對，結果不同就算進展。"""
    eid = ctx.store.add(b"<html>a b</html>", source="u", tool="polite_fetch", kind="page")["id"]
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard)
    tm = log.wrap(Tool("text_match", "", {}, lambda a: {"ok": True, "evidence_id": a["evidence_id"],
                                                        "keywords": a["keywords"], "hits": {k: {"exact": 1, "contexts": [f"…{k} 前後文…"]} for k in a["keywords"]}}))
    first = json.loads(tm({"evidence_id": eid, "keywords": ["a"]}))
    assert "derived_evidence_id" in first and guard.streak == 0
    tm({"evidence_id": eid, "keywords": ["b"]})
    assert guard.streak == 0
    tm({"evidence_id": eid, "keywords": ["b"]})
    assert guard.streak == 1


def test_same_url_different_part_counts(ctx):
    """第五次審查 major：同一網址先看 summary 再看 jsonld，即使每次都重抓原檔，也要算進展。"""
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard)

    def inspect(a):
        item = ctx.store.add(b"<html>nonce" + str(len(ctx.store.ids())).encode(), source="https://x/", tool="polite_fetch",
                             kind="page", meta={"mobile": False, "method": "GET"})
        return {"ok": True, "evidence_id": item["id"], "part": a["part"], "data": {"part": a["part"] + "-data"}}
    ip = log.wrap(Tool("inspect_page", "", {}, inspect))
    ip({"url": "https://x/", "part": "summary"})
    ip({"url": "https://x/", "part": "jsonld"})
    assert guard.streak == 0
    ip({"url": "https://x/", "part": "jsonld"})
    assert guard.streak == 1


def test_zero_hit_queries_with_real_tools_stop(ctx):
    """第六次審查 major：用真實 sitemap_tree search 與 text_match 的回傳格式，換字零命中不能一直歸零。"""
    from seo_agent.tools.sitemap import sitemap_tool
    from seo_agent.tools.web import text_match_tool
    eid = ctx.store.add(b"<html><body><p>hello world</p></body></html>", source="https://x/", tool="polite_fetch",
                        kind="page", meta={"headers": {"content-type": "text/html"}})["id"]
    import sqlite3
    with sqlite3.connect(ctx.run_dir / "sitemap.sqlite") as db:  # 已 build 過的狀態；空資料庫現在會回錯誤（決策 #64）
        db.execute("CREATE TABLE IF NOT EXISTS urls(loc TEXT, lastmod TEXT, sitemap TEXT, section TEXT)")
        db.execute("INSERT INTO urls VALUES('https://x/a', NULL, 'https://x/sitemap.xml', '/a/')")
        db.execute("CREATE TABLE IF NOT EXISTS sitemaps(url TEXT PRIMARY KEY, status INTEGER, kind TEXT, n_urls INTEGER, "
                   "parent TEXT, found_by TEXT, evidence_id TEXT, note TEXT)")
        db.execute("INSERT INTO sitemaps VALUES('https://x/sitemap.xml', 200, 'urlset', 1, NULL, 'robots.txt', NULL, NULL)")
    guard = StopGuard(ctx)
    log = ToolLog(guard=guard)
    sm, tm = log.wrap(sitemap_tool(ctx)), log.wrap(text_match_tool(ctx))
    for i in range(3):
        assert json.loads(sm({"action": "search", "text": f"nothing{i}"}))["ok"] is True
    for i in range(3):
        assert json.loads(tm({"evidence_id": eid, "keywords": [f"zzz{i}"]}))["ok"] is True
    assert guard.streak == 2  # 兩種查詢各自只有第一次零命中算進展，之後換字都不算
    hit = json.loads(tm({"evidence_id": eid, "keywords": ["hello"]}))
    assert hit["ok"] is True and guard.streak == 0  # 真的命中才算
