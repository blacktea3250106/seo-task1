"""記錄層（決策 #71）：Evidence ID 格式、Board 進度摘要（G-09）、Tool 呼叫紀錄（G-13）、why 欄、
sections_not_yet_read（資料卡分區還沒讀過的）、inspect_page 附 page_text。全部離線。"""
from __future__ import annotations

import json
import re

import pytest
from fixture_site import FakeSite

from seo_agent.coverage import research_tools, section_of
from seo_agent.hermes_bridge import ToolLog
from seo_agent.stop import StopGuard
from seo_agent.tools.context import Context


@pytest.fixture
def env(tmp_path):
    site = FakeSite()
    site.search_ok = True
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=0, sleep=lambda s: None)
    ctx.site_domain = "2030.tw"
    (ctx.run_dir / "data_card.json").write_text(json.dumps({"sources": {
        "sitemap": {"sections": [{"section": "/news/", "urls": 3}, {"section": "/wordcup/", "urls": 2}]},
        "home_menu": {"sections": {"/news/": 4, "/forum/": 1}}}}), encoding="utf-8")
    log = ToolLog(guard=StopGuard(ctx), ctx=ctx)
    research, cov = research_tools(ctx, "https://2030.tw")
    tools = {t.name: (lambda h: (lambda a: json.loads(h(a))))(log.wrap(t)) for t in research}
    return ctx, tools, log, cov


def add_ev(ctx, n, *, source=None, tool="polite_fetch", kind="page"):
    return [ctx.store.add(f"body {source or i} {i} {tool}".encode(), source=source or f"https://2030.tw/p{i}/", tool=tool,
                          kind=kind)["id"] for i in range(n)]


def test_evidence_id_format(env):
    ctx, *_ = env
    ids = add_ev(ctx, 2)
    assert ids == ["E-0001", "E-0002"] and all(re.fullmatch(r"E-\d{4}", i) for i in ids)
    assert (ctx.run_dir / "raw" / "E-0001.bin").exists()


# ---- G-09：Board 只剩程式產生的進度摘要 ----
def test_board_is_progress_summary(env):
    ctx, tools, *_ = env
    tools["polite_fetch"]({"url": "https://2030.tw/news/a/", "why": "看新聞頁"})
    tools["polite_fetch"]({"url": "https://2030.tw/"})
    board = json.loads((ctx.run_dir / "board.json").read_text(encoding="utf-8"))
    assert board["tool_calls_total"] == 2 and board["why_filled"] == 1 and board["evidence_index"] == "evidence.jsonl"
    assert board["evidence_total"] == len(ctx.store.ids()) and "questions" not in board


# ---- G-13 ----
def test_tool_call_log_fields(env):
    ctx, tools, *_ = env
    tools["sitemap_tree"]({"action": "build", "site": "https://2030.tw"})
    tools["sitemap_tree"]({"action": "summary", "why": "看全貌"})
    page = tools["polite_fetch"]({"url": "https://www.2030.tw/news/a/"})
    tools["text_match"]({"evidence_id": page["evidence_id"], "keywords": ["娛樂城"]})
    tools["web_search"]({"query": "site:2030.tw 娛樂城"})
    by_tool = {}
    for c in ctx.read_jsonl(ctx.tool_calls_path):
        by_tool.setdefault(c["tool"], []).append(c)
    summary = by_tool["sitemap_tree"][1]
    assert summary["derived_evidence_id"] in ctx.store.ids() and summary["args"]["why"] == "看全貌"
    tm = by_tool["text_match"][0]
    assert tm["derived_evidence_id"] and tm["target"] == {"domain": "2030.tw", "path": "/news/a/"}
    assert by_tool["polite_fetch"][0]["target"] == {"domain": "2030.tw", "path": "/news/a/"}
    assert by_tool["sitemap_tree"][0]["target"]["domain"] == "2030.tw"
    assert by_tool["web_search"][0]["target"] == {"domain": "web_search", "path": "site:2030.tw 娛樂城"}


# ---- 決策 #71：why 欄 ----
def test_why_is_logged_but_not_passed_to_tool(env):
    ctx, tools, *_ = env
    a = tools["polite_fetch"]({"url": "https://2030.tw/news/a/", "why": "照 EXP-001 查"})
    b = tools["polite_fetch"]({"url": "https://2030.tw/news/a/", "why": "換個說法"})
    assert a["ok"] and b["ok"]
    item = ctx.store.get(a["evidence_id"])
    assert "EXP-001" not in json.dumps(item, ensure_ascii=False)  # why 不進證據來源
    calls = ctx.read_jsonl(ctx.tool_calls_path)
    assert calls[0]["args"]["why"] == "照 EXP-001 查" and calls[1]["new_evidence"] is False  # 換 why 不算新證據


# ---- 決策 #71：sections_not_yet_read ----
def test_sections_not_yet_read(env):
    ctx, tools, _, cov = env
    first = tools["polite_fetch"]({"url": "https://2030.tw/news/a/"})
    secs = first["sections_not_yet_read"]["sections"]
    assert not any(x.startswith("/news/") for x in secs)
    assert any(x.startswith("/wordcup/（2 個 sitemap 網址") for x in secs) and any(x.startswith("/forum/") for x in secs)
    tools["polite_fetch"]({"url": "https://other.example/wordcup/x"})  # 別的網站不算讀過
    assert any(x.startswith("/wordcup/") for x in cov.not_yet_read())
    assert cov.summary()["sections_read"] == ["/news/"]


def test_section_of():
    assert section_of("https://www.2030.tw/News/a/", "2030.tw") == "/news/"
    assert section_of("https://2030.tw", "2030.tw") == "/"
    assert section_of("https://evil2030.tw/x/", "2030.tw") is None


def test_inspect_page_adds_page_text(env):
    ctx, tools, *_ = env
    tools["polite_fetch"]({"url": "https://2030.tw/"})
    out = tools["inspect_page"]({"url": "https://2030.tw/news/a/"})
    assert out["ok"] and "page_text" in out and "page_text_note" in out
    assert out["page_text_total_chars"] >= len(out["page_text"])


def test_zero_hit_queries_still_stop_with_wrappers(env):
    """正式包裝順序下（sections_not_yet_read 每次不同），零命中查詢仍不算進展，連續 5 次會停（code review blocker）。"""
    ctx, tools, log, cov = env
    ev = tools["polite_fetch"]({"url": "https://2030.tw/news/a/"})["evidence_id"]
    urls = ["https://2030.tw/news/", "https://2030.tw/wordcup/", "https://2030.tw/forum/", "https://2030.tw/x/",
            "https://2030.tw/y/", "https://2030.tw/z/", "https://2030.tw/w/"]
    for u in urls:  # 第 1 次零命中算新結果；之後換字、換分區都是同一個指紋
        out = tools["text_match"]({"url": u, "keywords": ["zzzqqq"], "evidence_id": ev})
    assert not any(c["new_evidence"] for c in log.calls[2:7])
    assert log.calls[-1]["blocked_by_guard"] and out["error"]["code"] == "stop_no_progress"
    body = (ctx.run_dir / ctx.store.get(log.calls[1]["derived_evidence_id"])["file"]).read_text(encoding="utf-8")
    assert "sections_not_yet_read" not in body  # 程式附的事實不存進證據


def test_section_of_unquote_and_subdomain():
    assert section_of("https://2030.tw/%E6%96%B0%E8%81%9E/a", "2030.tw") == "/新聞/"
    assert section_of("https://www.2030.tw/News/", "2030.tw") == "/news/"
    assert section_of("https://cdn.2030.tw/wp-content/x.jpg", "2030.tw") is None
