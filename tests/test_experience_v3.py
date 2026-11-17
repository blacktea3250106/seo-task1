"""經驗格式（G-10）、candidates.jsonl＋notes.md（G-11）、路線 Tool 清單反查（G-12）、路線摘要（G-14）。全部離線。"""
from __future__ import annotations

import json

import pytest
from fixture_site import FakeSite

from seo_agent.experience import (
    ExperienceStore,
    experience_tool,
    load_proposals,
    proposals_for_audit,
    route_tools,
    write_route_summary,
)
from seo_agent.hermes_bridge import ToolLog
from seo_agent.research import system_prompt
from seo_agent.stop import StopGuard
from seo_agent.tools import build_tools
from seo_agent.tools.context import Context


@pytest.fixture
def env(tmp_path):
    site = FakeSite()
    site.search_ok = True
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=0, sleep=lambda s: None)
    log = ToolLog(guard=StopGuard(ctx), ctx=ctx)
    from seo_agent.coverage import research_tools
    tools = {t.name: (lambda h: (lambda a: json.loads(h(a))))(log.wrap(t)) for t in research_tools(ctx, "https://2030.tw")[0]}
    store = ExperienceStore(tmp_path / "experience" / "candidates.jsonl")
    tools["experience"] = (lambda h: (lambda a: json.loads(h(a))))(log.wrap(experience_tool(store, "run1", ctx)))
    return ctx, tools, store


def entry(i, status="active", **kw):
    return {"id": f"EXP-{i:03d}", "status": status, "situation": f"情況{i}", "route": f"路線{i}", "result": "照走",
            "avoid_reason": "", "paired_id": "", "evidence_ids": ["E-0001"], "source_run": "r0",
            "route_tools": [{"tool": "polite_fetch", "domain": "2030.tw", "path": "/"}], **kw}


# ---- G-10 ----
def test_three_kinds_saved_with_fields(env):
    ctx, t, store = env
    page = t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    exp = t["experience"]
    a = exp({"action": "propose", "situation": "選單有的區塊在主 sitemap 找不到", "route": "1. sitemap_tree：搜選單分區的網址，因為主 sitemap 可能漏列子 sitemap\n2. inspect_page：看選單連結與 canonical，因為要分清刻意不收錄或漏列",
             "result": "照走", "evidence_ids": [page]})
    b = exp({"action": "propose", "situation": "想知道外鏈數", "route": "1. web_search：搜 link: 查外鏈，因為想知道外鏈數\n2. polite_fetch：讀搜尋結果頁，因為確認是否真的沒資料", "result": "別走",
             "avoid_reason": "查不到", "evidence_ids": [page]})
    c = exp({"action": "propose", "situation": "判斷某頁有沒有被收錄", "route": "1. web_search：搜網址看有沒有結果，因為想知道收錄\n2. web_search：沒結果就判定沒收錄，因為以為查無就是未收錄",
             "result": "別走", "avoid_reason": "會誤導", "paired_id": a["id"], "evidence_ids": [page]})
    assert [x["id"] for x in (a, b, c)] == ["P1", "P2", "P3"] and all(x["status"] == "待審核" for x in (a, b, c))
    rows = load_proposals(ctx)
    assert [(r["result"], r["avoid_reason"], r["paired_id"]) for r in rows] == [
        ("照走", "", ""), ("別走", "查不到", ""), ("別走", "會誤導", "P1")]
    assert all(r["situation"] and r["route"] and r["source_run"] == "run1" for r in rows)
    assert store.load() == []  # 研究中寫的路線不進經驗檔（評分後審核通過才進，G-20）


@pytest.mark.parametrize("args", [
    {"situation": "", "route": "r", "result": "照走"},
    {"situation": "s", "route": "用 polite_fetch 讀首頁", "result": "照走"},   # 沒照箭頭模板
    {"situation": "s", "route": "r", "result": "差點判斷錯"},
    {"situation": "s", "route": "r", "result": "別走"},
    {"situation": "s", "route": "r", "result": "別走", "avoid_reason": "不划算"},
])
def test_bad_fields_rejected(env, args):
    _, t, _ = env
    assert t["experience"]({"action": "propose", **args})["error"]["code"] == "rejected"


def test_experience_tool_cannot_retire_or_activate(env):
    ctx, t, _ = env
    for action in ("disable", "formal", "approve", "delete"):
        assert t["experience"]({"action": action, "id": "EXP-001"})["error"]["code"] == "not_allowed"
    assert len(ctx.read_jsonl(ctx.run_dir / "approvals_pending.jsonl")) == 4
    assert set(next(x for x in build_tools(ctx) + [experience_tool(ExperienceStore(ctx.run_dir / "e.jsonl"), "r", ctx)]
                    if x.name == "experience").parameters["properties"]["action"]["enum"]) == {"propose", "list"}


# ---- G-11 ----
def test_store_files_and_notes(tmp_path):
    store = ExperienceStore(tmp_path / "experience" / "candidates.jsonl")
    store.save_all([entry(1), entry(2, "retired", retired_reason="rejected"),
                    entry(3, result="別走", avoid_reason="會誤導", paired_id="EXP-001")])
    lines = (tmp_path / "experience" / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and {json.loads(x)["status"] for x in lines} == {"active", "retired"}
    notes = (tmp_path / "experience" / "notes.md").read_text(encoding="utf-8")
    assert "EXP-001" in notes and "EXP-003" in notes and "EXP-002" not in notes  # 只放使用中
    assert "別走（會誤導，正確查法見 EXP-001）" in notes and "使用中" in notes
    for old in ("候選", "正式", "停用", "candidate", "formal"):
        assert old not in notes
    (tmp_path / "experience" / "notes.md").write_text("手改", encoding="utf-8")
    items = store.load()
    items[0] = {**items[0], "status": "retired", "retired_reason": "no_value"}
    store.save_all(items)  # 狀態變更 → 重新產生，手改被覆蓋
    notes = (tmp_path / "experience" / "notes.md").read_text(encoding="utf-8")
    assert "手改" not in notes and "[EXP-001｜" not in notes and "[EXP-003｜" in notes
    assert notes in system_prompt(store)


@pytest.mark.parametrize("bad", [
    {"status": "candidate"}, {"status": "formal"}, {"status": "retired"}, {"status": "active", "retired_reason": "rejected"},
    {"status": "retired", "retired_reason": "bored"}])
def test_store_only_two_statuses(tmp_path, bad):
    with pytest.raises(ValueError):
        ExperienceStore(tmp_path / "c.jsonl").save_all([entry(1, **bad)])


# ---- G-12 ----
def test_route_tools_from_evidence_ids(env):
    ctx, t, _ = env
    page = t["polite_fetch"]({"url": "https://www.2030.tw/news/a/"})["evidence_id"]
    t["polite_fetch"]({"url": "https://2030.tw/"})  # 沒被列出 → 不在清單
    tm = t["text_match"]({"evidence_id": page, "keywords": ["娛樂城"]})
    search = t["web_search"]({"query": "site:2030.tw 娛樂城"})["evidence_id"]
    out = t["experience"]({"action": "propose", "situation": "s", "route": "1. sitemap_tree：搜選單分區的網址，因為主 sitemap 可能漏列子 sitemap\n2. inspect_page：看選單連結與 canonical，因為要分清刻意不收錄或漏列", "result": "照走",
                           "evidence_ids": [page, tm["derived_evidence_id"], search],
                           "route_tools": [{"tool": "domain_info"}]})  # Opus 自填的 Tool 清單被忽略
    got = [(x["tool"], x["domain"], x["path"]) for x in out["route_tools"]]
    assert got == [("polite_fetch", "2030.tw", "/news/a/"), ("text_match", "2030.tw", "/news/a/"),
                   ("web_search", "web_search", "site:2030.tw 娛樂城")]
    row = load_proposals(ctx)[0]
    assert row["ignored_fields"] == ["route_tools"] and "domain_info" not in json.dumps(row["route_tools"])
    assert route_tools(ctx, ["E-9999"]) == []


# ---- G-14 ----
def test_route_summary_follows_call_order(env):
    ctx, t, _ = env
    t["sitemap_tree"]({"action": "build", "site": "https://2030.tw"})
    p1 = t["polite_fetch"]({"url": "https://2030.tw/", "why": "看首頁選單"})["evidence_id"]
    t["inspect_page"]({"evidence_id": p1, "part": "links"})
    t["experience"]({"action": "propose", "situation": "s", "route": "1. sitemap_tree：搜選單分區的網址，因為主 sitemap 可能漏列子 sitemap\n2. inspect_page：看選單連結與 canonical，因為要分清刻意不收錄或漏列", "result": "照走", "evidence_ids": [p1]})
    summary = write_route_summary(ctx)
    assert [s["tool"] for s in summary["steps"]] == ["sitemap_tree", "polite_fetch", "inspect_page"]
    assert summary["steps"][1]["why"] == "看首頁選單" and summary["steps"][1]["evidence_ids"] == [p1]
    assert (ctx.run_dir / "route_summary.json").exists()
    audit = proposals_for_audit(ctx)
    assert [st["tool"] for st in audit[0]["route_summary"]] == ["polite_fetch", "inspect_page"]  # 只取碰到它 Evidence ID 的步


def test_notes_show_route_steps(tmp_path):  # 箭頭模板：notes.md 一步一行，Opus 讀得順
    from seo_agent.experience import ROUTE_TEMPLATE, format_problems
    store = ExperienceStore(tmp_path / "candidates.jsonl")
    route = "1. sitemap_tree：搜分區網址，因為 index 可能漏列\n2. inspect_page：看 canonical，因為要分清刻意或漏列"
    store.save_all([{"id": "EXP-001", "status": "active", "situation": "選單有分區、sitemap 找不到", "route": route,
                     "result": "照走", "avoid_reason": "", "paired_id": "", "evidence_ids": [], "route_tools": []}])
    notes = store.notes_markdown()
    assert "情況：選單有分區" in notes and "\n  1. sitemap_tree：" in notes and "\n  2. inspect_page：" in notes
    assert "\n  結果：照走" in notes
    assert format_problems({"situation": "s", "route": route}) == [] and "因為" in ROUTE_TEMPLATE
