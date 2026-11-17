"""網站底稿、匯入、資料卡、Wayback 日期、④ 即時資料、命令列（G-50–G-54、G-48）。全部離線。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fixture_site import FakeSite

from seo_agent.baseline import SOURCES, Baseline, prepare
from seo_agent.hermes_bridge import ToolLog
from seo_agent.stop import StopGuard
from seo_agent.tools import build_tools
from seo_agent.tools.context import Context

FIXTURES = Path(__file__).parent / "fixtures"
KW = ["娛樂城", "3A娛樂城"]


def ensure(root, site, **kw):
    return Baseline("https://2030.tw", root=root).ensure(KW, transport=site.transport(), delay_s=0,
                                                          sleep=lambda s: None, **kw)


def hosts(site):
    from urllib.parse import urlsplit
    return {urlsplit(u).hostname for u in site.calls if not u.endswith("/robots.txt")}


# ---- G-50 ----
def test_build_then_reuse_without_requests(tmp_path):
    site = FakeSite()
    site.search_ok = True
    data = ensure(tmp_path, site)
    assert data["action"] == "built" and set(data["sources"]) == set(SOURCES)
    assert all(s["ok"] and s["fetched_at"] and s["sha256"] for s in data["sources"].values())
    assert data["baseline_hash"] and (tmp_path / "2030.tw" / "baseline.json").exists()
    assert 6 <= len([u for u in site.calls if not u.endswith("/robots.txt")]) <= 20  # 約 10–20 次請求
    again = FakeSite()
    assert ensure(tmp_path, again)["action"] == "reused" and again.calls == []
    www = FakeSite()  # 同一網域（www 也算同一份）
    assert Baseline("https://www.2030.tw/", root=tmp_path).ensure(KW, transport=www.transport(), delay_s=0,
                                                                  sleep=lambda s: None)["action"] == "reused"
    assert www.calls == []


def test_failed_sources_are_recorded_and_only_they_refetch(tmp_path):
    first = FakeSite()  # 搜尋回人機驗證頁 → 2 個搜尋來源失敗
    data = ensure(tmp_path, first)
    failed = [s for s, v in data["sources"].items() if not v["ok"]]
    assert failed == ["search_1", "search_2"] and all(data["sources"][s]["error"] for s in failed)
    second = FakeSite()
    second.search_ok = True
    data2 = ensure(tmp_path, second)
    assert data2["action"] == "refetched_failed" and data2["refetched"] == ["search_1", "search_2"]
    assert hosts(second) == {"html.duckduckgo.com"}  # 其他來源請求數 0
    assert all(v["ok"] for v in data2["sources"].values()) and data2["baseline_hash"] != data["baseline_hash"]


def test_refresh_refetches_everything(tmp_path):
    site = FakeSite()
    site.search_ok = True
    ensure(tmp_path, site)
    again = FakeSite()
    again.search_ok = True
    data = ensure(tmp_path, again, refresh=True)
    assert data["action"] == "built" and data["refetched"] == list(SOURCES)
    assert {"2030.tw", "ccrdap.twnic.tw", "web.archive.org", "html.duckduckgo.com"} <= hosts(again)


def test_still_seven_tools(tmp_path):
    assert len(build_tools(Context(tmp_path / "r"))) == 7


# ---- G-51 ----
@pytest.fixture
def prepared(tmp_path):
    site = FakeSite()
    site.search_ok = True
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=0, sleep=lambda s: None)
    prep = prepare(ctx, "https://2030.tw", KW, root=tmp_path / "baselines", transport=site.transport(), delay_s=0,
                   sleep=lambda s: None)
    return ctx, prep, site


def test_import_marks_snapshot_and_traces_back(prepared, tmp_path):
    ctx, prep, _ = prepared
    items = ctx.store.all()
    assert items and all(i["meta"]["snapshot"] and i["meta"]["fetched_at"] and i["meta"]["baseline_hash"] for i in items)
    root = tmp_path / "baselines" / "2030.tw"
    base_index = {json.loads(line)["id"]: json.loads(line) for line in (root / "evidence.jsonl").read_text().splitlines()}
    for old, new in prep["mapping"].items():
        assert ctx.store.read(new) == (root / base_index[old]["file"]).read_bytes()
    from seo_agent.report import check_report
    eid = prep["card"]["sources"]["sitemap"]["evidence_ids"][0]
    rep = {"onpage": [{"id": "S1", "text": "t", "kind": "fact", "evidence_ids": [eid]}]}
    errors = check_report(rep, evidence_ids=set(ctx.store.ids()), experience_ids=set())
    assert not any(eid in e for e in errors)


def test_import_is_not_new_evidence(prepared):
    ctx, _, site = prepared
    guard = StopGuard(ctx)
    guard.seed_snapshot()
    log = ToolLog(guard=guard, ctx=ctx)
    fetch = next(t for t in build_tools(ctx) if t.name == "polite_fetch")
    call = log.wrap(fetch)
    before = len(site.calls)
    outs = [json.loads(call({"url": "https://2030.tw/"})) for _ in range(5)]
    assert len(site.calls) > before  # ④ 真的有發請求（不讀底稿）
    assert all(o.get("same_as_snapshot") for o in outs) and guard.streak == 5
    assert json.loads(call({"url": "https://2030.tw/"}))["error"]["code"] == "stop_no_progress"
    rows = ctx.read_jsonl(ctx.tool_calls_path)
    assert all(r["same_as_snapshot"] for r in rows if r["ok"])  # 指標程式據此不算白做工（G-30）


# ---- G-52、G-53 ----
def test_data_card_side_by_side_only(prepared):
    ctx, prep, _ = prepared
    card, md = prep["card"], prep["markdown"]
    assert set(card["sources"]) == set(SOURCES)
    assert card["sources"]["home_menu"]["sections"] == {"/wordcup/": 1, "/news/": 1}  # 來自 inspect_page 的選單位置
    sm = card["sources"]["sitemap"]
    assert {s["section"] for s in sm["sections"]} >= {"/wordcup/", "/news/"} and sm["url_rows"] == 9
    for word in ("對不上", "矛盾", "差異", "不一致", "可疑", "疑點"):
        assert word not in md
    rubric = json.loads((Path(__file__).parents[1] / "eval" / "rubric_2030.json").read_text(encoding="utf-8"))
    for item in rubric["items"]:
        assert item["point"] not in md
    assert (ctx.run_dir / "data_card.md").exists() and (ctx.run_dir / "data_card.json").exists()


def test_failed_source_marked_on_card(tmp_path):
    site = FakeSite()
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=0, sleep=lambda s: None)
    card = prepare(ctx, "https://2030.tw", KW, root=tmp_path / "b", transport=site.transport(), delay_s=0,
                   sleep=lambda s: None)["card"]
    assert card["sources"]["search_1"]["status"] == "失敗" and card["sources"]["search_1"]["error"]


def test_wayback_dates_parsed_from_real_cdx(tmp_path):
    """2030.tw 舊站是政府網站案例：日期取自 CDX 原檔（2026-11-16 實查），不取 172 字元的包裝資料。"""
    site = FakeSite()
    site.search_ok = True
    site.timeline = (FIXTURES / "wayback_2030_timeline_20261116.json").read_text(encoding="utf-8")
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=0, sleep=lambda s: None)
    wb = prepare(ctx, "https://2030.tw", KW, root=tmp_path / "b", transport=site.transport(), delay_s=0,
                 sleep=lambda s: None)["card"]["sources"]["wayback"]
    assert wb["earliest"][:4] == "2020" and wb["latest"][:4] == "2026"  # 與 rubric T05 正解一致
    assert wb["earliest"] == "2020-03-02" and wb["latest"] == "2026-01-05"
    assert sorted(wb["by_year"]) == [str(y) for y in range(2020, 2027)] and sum(wb["by_year"].values()) == wb["snapshots"]
    assert ctx.store.get(wb["date_evidence_id"])["kind"] == "wayback_cdx"


# ---- G-54 ----
def test_rebuilding_sitemap_in_run_matches_snapshot(prepared):
    """審查 M1（決策 #66）：模型拿到的是精簡版 build；重做底稿已做過的 build 仍要判成和底稿一樣，不算進展。"""
    ctx, _, _ = prepared
    guard = StopGuard(ctx)
    guard.seed_snapshot()
    call = ToolLog(guard=guard, ctx=ctx).wrap(next(t for t in build_tools(ctx) if t.name == "sitemap_tree"))
    out = json.loads(call({"action": "build", "site": "https://2030.tw"}))
    assert out["ok"] and "brief" in out and out.get("same_as_snapshot") is True


def test_research_tools_fetch_live_not_baseline(prepared):
    ctx, _, site = prepared
    tools = {t.name: t.func for t in build_tools(ctx)}
    assert not (ctx.run_dir / "sitemap.sqlite").exists() or tools["sitemap_tree"]({"action": "summary"})["ok"] is False  # 還沒 build：回錯誤，不回 0 筆
    before = len(site.calls)
    tools["wayback"]({"action": "timeline", "url": "2030.tw"})
    assert len(site.calls) > before


def test_research_message_has_card_and_meta(tmp_path, monkeypatch):
    from seo_agent import research
    from seo_agent.model_env import ModelSettings
    seen = {}

    def fake_agent(model, tools, *, message, **kw):
        seen["message"] = message
        return {"tool_calls": [], "completed": True, "error": None}
    monkeypatch.setattr(research, "run_agent", fake_agent)
    site = FakeSite()
    site.search_ok = True
    result = research.run_research(ModelSettings(base_url="http://x", api_key="k"), {"fetch_delay_s": 0},
                                   run_dir=tmp_path / "run-a", transport=site.transport(),
                                   experience_path=tmp_path / "e.json", baseline_root=tmp_path / "b")
    assert "## 資料卡：2030.tw" in seen["message"] and result["baseline"]["action"] == "built"
    data = json.loads((tmp_path / "run-a" / "report_incomplete.json").read_text(encoding="utf-8"))
    assert set(data["meta"]["baseline"]["fetched_at"]) == set(SOURCES)


# ---- G-48 ----
def test_cli_parse():
    from seo_agent.cli import parse, payload
    a = parse(["run", "--site", "https://2030.tw", "--keywords", "娛樂城,3A娛樂城", "--out", "runs/r-1", "--refresh"])
    assert a.out == Path("runs/r-1") and a.keywords == KW and a.refresh
    assert payload(a) == {"site": "https://2030.tw", "keywords": KW, "refresh": True, "total_minutes": 120}
    assert parse(["run", "--site", "x", "--keywords", "a"]).out.parent == Path("runs")
    with pytest.raises(SystemExit):
        parse(["run", "--site", "x", "--keywords", "a", "--out", "runs/bad id"])
