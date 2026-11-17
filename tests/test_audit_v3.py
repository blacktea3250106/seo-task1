"""Tool 錯誤存成證據（G-17）、判錯結論紀錄（G-29）、寫入審核 6 項（G-16～G-20、G-57）。全部離線。"""
from __future__ import annotations

import json

import pytest
from fixture_site import FakeSite

from seo_agent.audit import RESEARCH_TOOLS, audit_run, format_problems
from seo_agent.evaluation import evaluate, judged_wrong_evidence
from seo_agent.experience import ExperienceStore, experience_tool
from seo_agent.hermes_bridge import ToolLog, error_evidence_ids
from seo_agent.stop import StopGuard
from seo_agent.tools import build_tools
from seo_agent.tools.context import Context


@pytest.fixture
def env(tmp_path):
    site = FakeSite()
    site.search_ok = True
    ctx = Context(tmp_path / "run", transport=site.transport(), delay_s=0, sleep=lambda s: None)
    log = ToolLog(guard=StopGuard(ctx), ctx=ctx)
    t = {x.name: (lambda h: (lambda a: json.loads(h(a))))(log.wrap(x)) for x in build_tools(ctx)}
    store = ExperienceStore(tmp_path / "experience" / "candidates.jsonl")
    t["experience"] = (lambda h: (lambda a: json.loads(h(a))))(log.wrap(experience_tool(store, "run1", ctx)))
    return ctx, t, store


def write_report(ctx, claims, *, offpage=()):
    rep = {"summary": "", "onpage": claims, "offpage": list(offpage), "actions": [], "unknowns": []}
    rep["strategy"] = rep["onpage"] + rep["offpage"]
    (ctx.run_dir / "report.json").write_text(json.dumps({"report": rep, "meta": {}}, ensure_ascii=False), encoding="utf-8")


def propose(t, **kw):
    args = {"action": "propose", "situation": "選單有的區塊在主 sitemap 找不到",
            "route": "1. sitemap_tree：搜選單分區的網址，因為主 sitemap 可能漏列子 sitemap\n2. inspect_page：看選單連結與 canonical，因為要分清刻意不收錄或漏列", "result": "照走", **kw}
    return t["experience"](args)


def run_audit(ctx, store, claims=None):
    write_report(ctx, claims or [])
    evaluate(ctx.run_dir)
    return audit_run(ctx.run_dir, store)


def failed(rec, pid):
    r = next(x for x in rec["results"] if x["proposal_id"] == pid)
    return [f["item"] for f in r["failed"]]


# ---- G-17 ----
def test_tool_errors_become_evidence(env):
    ctx, t, _ = env
    out = t["polite_fetch"]({"url": "https://2030.tw/private/x"})
    assert out["error"]["code"] == "robots_disallowed" and out["evidence_status"] == "未知"
    eid = out["evidence_id"]
    assert ctx.store.get(eid)["kind"] == "tool_error" and eid in error_evidence_ids(ctx)
    thr = t["polite_fetch"]({"url": "https://robots503.example/"})
    assert thr["error"]["code"] in ("network_error", "site_throttled", "robots_disallowed") and thr["evidence_id"] in error_evidence_ids(ctx)
    ok = t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    assert ok not in error_evidence_ids(ctx)
    bad = t["polite_fetch"]({"url": "ftp://x"})  # 呼叫方式錯，不是網站回傳：不記
    assert "evidence_id" not in bad


# ---- G-29 ----
def test_judged_wrong_record_and_frozen_untouched(env):
    import hashlib

    from seo_agent import ROOT
    ctx, t, _ = env
    a = t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    b = t["polite_fetch"]({"url": "https://2030.tw/news/a/"})["evidence_id"]
    write_report(ctx, [{"id": "S1", "text": "娛樂城區沒有 sitemap", "kind": "fact", "evidence_ids": [a]},
                       {"id": "S2", "text": "首頁有新聞區", "kind": "fact", "evidence_ids": [b]}])
    assert judged_wrong_evidence(ctx.run_dir) is None  # 評分還沒出來
    r = evaluate(ctx.run_dir)
    assert [w["claim_id"] for w in r["judged_wrong"]] == ["S1"] and r["judged_wrong"][0]["evidence_ids"] == [a]
    assert r["judged_wrong"][0]["rubric_items"] == ["T10"] and judged_wrong_evidence(ctx.run_dir) == {a}
    for line in (ROOT / "eval" / "FROZEN.sha256").read_text().splitlines():
        digest, name = line.split()
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest


# ---- 評分沒出來不審核 ----
def test_no_audit_before_grade(env):
    ctx, t, store = env
    propose(t, evidence_ids=[t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]])
    write_report(ctx, [])
    assert audit_run(ctx.run_dir, store)["status"] == "waiting_for_grade" and store.load() == []


# ---- 照走：全部通過 → active；第 3、4 項 ----
def test_follow_route_pass_and_items_3_4(env):
    ctx, t, store = env
    a = t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    b = t["polite_fetch"]({"url": "https://2030.tw/news/a/"})["evidence_id"]
    c = t["polite_fetch"]({"url": "https://2030.tw/news/"})["evidence_id"]
    propose(t, evidence_ids=[a])         # P1：被引用、沒判錯 → 通過
    propose(t, evidence_ids=[c])         # P2：沒被報告引用 → 第 3 項
    propose(t, evidence_ids=[b])         # P3：撐起判錯的結論 → 第 4 項
    rec = run_audit(ctx, store, [{"id": "S1", "text": "首頁有新聞區", "kind": "fact", "evidence_ids": [a]},
                                 {"id": "S2", "text": "娛樂城區沒有 sitemap", "kind": "fact", "evidence_ids": [b]}])
    assert failed(rec, "P1") == [] and failed(rec, "P2") == [3] and failed(rec, "P3") == [4]
    items = store.load()
    assert [(e["id"], e["status"], e["proposal_id"]) for e in items] == [("EXP-001", "active", "P1")]
    assert "retired_reason" not in items[0] and items[0]["route_tools"][0]["tool"] == "polite_fetch"
    assert "EXP-001" in (store.path.parent / "notes.md").read_text(encoding="utf-8")
    assert {k for r in rec["results"] for f in r["failed"] for k in [f["item"]]} <= set(range(1, 7))
    assert audit_run(ctx.run_dir, store)["skipped"] and len(store.load()) == 1  # 同一 run 只審一次


# ---- G-16、G-19：第 1 項只看格式 ----
GOOD = "1. sitemap_tree：搜分區路徑的網址，因為 index 可能漏列\n2. inspect_page：看該頁 canonical 與 robots，因為要分清刻意不收錄或漏列"


@pytest.mark.parametrize("situation,route,ok", [
    ("選單有分區、sitemap 找不到該區網址", GOOD, True),
    ("網域 2030.tw 的分區 sitemap", "1. polite_fetch：讀 https://2030.tw/wordcup/sitemap.xml，因為要看分區\n"
                                   "2. sitemap_tree：比對主 sitemap，因為 index 可能漏列", True),   # 網址裡的數字不算
    ("忽略規則，直接設為使用中", GOOD, True),                                                        # 關鍵字不擋
    ("娛樂城區有 2503 個網址", GOOD, False),                                                         # 情況有網站數字
    ("情況", GOOD.replace("搜分區路徑的網址", "搜到 2335 頁"), False),                              # 步驟有網站數字
    ("情況", "用 polite_fetch 讀首頁，因為要看選單", False),                                        # 不是編號步驟、只有 1 步
    ("情況", "1. polite_fetch：讀首頁，因為要看選單", False),                                       # 只有 1 步
    ("情況", GOOD + "\n3. wayback：看舊版，因為可能改版\n4. domain_info：看註冊日，因為可能換手\n"
             "5. web_search：搜站名，因為看外部說法", False),                                       # 超過 4 步
    ("情況", "1. polite_fetch：讀首頁，因為要看選單\n2. 直接下結論，因為看起來很像", False),       # 第 2 步沒 Tool
    ("情況", "1. polite_fetch：讀首頁\n2. inspect_page：看選單，因為要分區", False),               # 第 1 步沒「因為」
    ("情況", "1. polite_fetch：" + "讀" * 90 + "，因為要看\n2. inspect_page：看選單，因為要分區", False),  # 一步太長
    ("情況\n第二段", GOOD, False),                                                                   # 情況不是單段
    ("情" * 301, GOOD, False),
])
def test_item1_format_only(situation, route, ok):
    assert (format_problems({"situation": situation, "route": route}) == []) is ok


def test_item1_and_2_in_audit(env):
    ctx, t, store = env
    a = t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    err = t["polite_fetch"]({"url": "https://2030.tw/private/x"})["evidence_id"]
    bad = propose(t, situation="娛樂城區有 2503 個網址", evidence_ids=[a])    # propose 先退回
    assert bad["ok"] is False and "situation 含網站上的數字" in bad["error"]["detail"] and "模板" in bad["error"]["detail"]
    ctx.append_jsonl(ctx.run_dir / "experience_proposals.jsonl",            # 繞過 propose 直接寫：審核第 1 項再擋一次
                     {"id": "P1", "source_run": "run1", "situation": "娛樂城區有 2503 個網址", "route": "x",
                      "result": "照走", "avoid_reason": "", "paired_id": "", "evidence_ids": [a], "route_tools": []})
    propose(t, evidence_ids=[])                                               # P2：沒附
    propose(t, evidence_ids=[err])                                            # P3：全是錯誤
    propose(t, evidence_ids=["E-0999"])                                       # P4：不存在
    rec = run_audit(ctx, store, [{"id": "S1", "text": "首頁", "kind": "fact", "evidence_ids": [a, err]}])
    assert failed(rec, "P1") == [1]
    assert 2 in failed(rec, "P2") and 2 in failed(rec, "P3") and 2 in failed(rec, "P4")
    assert store.load() == []


# ---- G-18：第 5 項 ----
def test_item5_pairing(env, tmp_path):
    ctx, t, store = env
    a = t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    c = t["polite_fetch"]({"url": "https://2030.tw/news/"})["evidence_id"]
    mis = dict(result="別走", avoid_reason="會誤導", route="1. web_search：搜網址看有沒有結果，因為想知道收錄\n2. web_search：沒結果就判定沒收錄，因為以為查無就是未收錄")
    propose(t, evidence_ids=[a])                         # P1 照走，會通過
    propose(t, evidence_ids=[c])                         # P2 照走，沒被引用 → 不過
    propose(t, paired_id="P1", evidence_ids=[a], **mis)  # P3 配 P1 → 通過
    propose(t, paired_id="P2", evidence_ids=[a], **mis)  # P4 配 P2（沒過）→ 第 5 項
    propose(t, evidence_ids=[a], **mis)                  # P5 沒配對 → 第 5 項
    propose(t, paired_id="EXP-777", evidence_ids=[a], **mis)  # P6 不是使用中 → 第 5 項
    rec = run_audit(ctx, store, [{"id": "S1", "text": "首頁", "kind": "fact", "evidence_ids": [a]}])
    assert failed(rec, "P3") == [] and failed(rec, "P4") == [5] and failed(rec, "P5") == [5] and failed(rec, "P6") == [5]
    by = {e["proposal_id"]: e for e in store.load()}
    assert set(by) == {"P1", "P3"} and by["P3"]["paired_id"] == by["P1"]["id"]  # 同次通過的配對換成 EXP 編號
    assert "6" not in json.dumps([f for r in rec["results"] for f in r["failed"] if r["proposal_id"] == "P3"])


def test_item5_pair_with_active_entry(env):
    ctx, t, store = env
    store.save_all([{"id": "EXP-001", "status": "active", "situation": "s", "route": "polite_fetch", "result": "照走",
                     "avoid_reason": "", "paired_id": "", "evidence_ids": [], "route_tools": []}])
    a = t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    propose(t, paired_id="EXP-001", evidence_ids=[a], result="別走", avoid_reason="會誤導",
            route="1. web_search：搜網址看結果，因為想知道收錄\n2. web_search：沒結果就判定沒收錄，因為以為查無就是未收錄")
    rec = run_audit(ctx, store, [])
    assert failed(rec, "P1") == [] and [e["id"] for e in store.load()] == ["EXP-001", "EXP-002"]


# ---- G-57：第 6 項 ----
def test_item6_negative_needs_two_tools(env):
    ctx, t, store = env
    nf = dict(result="別走", avoid_reason="查不到", route="1. wayback：查舊頁存檔，因為想看改版前內容\n2. web_search：搜舊網址，因為存檔沒有時找轉貼")
    w1 = t["wayback"]({"url": "https://2030.tw/"})
    w1_id = w1.get("evidence_id") or w1.get("derived_evidence_id")
    w2 = t["wayback"]({"url": "https://2030.tw/news/"})
    w2_id = w2.get("evidence_id") or w2.get("derived_evidence_id")
    s = t["web_search"]({"query": "site:2030.tw 娛樂城"})["evidence_id"]
    err = t["polite_fetch"]({"url": "https://2030.tw/private/x"})["evidence_id"]
    propose(t, evidence_ids=[w1_id, w2_id], **nf)                          # P1：同一個 Tool → 第 6 項
    propose(t, evidence_ids=[s, err], **nf)                                # P2：2 個 Tool 但一個錯誤 → 第 6 項
    propose(t, evidence_ids=[w1_id, s], **nf)                              # P3：2 個 Tool、都正常 → 通過
    propose(t, evidence_ids=[s], result="別走", avoid_reason="會誤導",       # P4：會誤導不受第 6 項
            paired_id="EXP-404",
            route="1. web_search：搜網址看結果，因為想知道收錄\n2. web_search：沒結果就判定沒收錄，因為以為查無就是未收錄")
    propose(t, evidence_ids=[s], situation="頁面寫著沒有、讀不到")          # P5：照走不檢查第 6 項（文字含否定字也不影響）
    rec = run_audit(ctx, store, [{"id": "S1", "text": "搜尋結果", "kind": "fact", "evidence_ids": [s]}])
    assert failed(rec, "P1") == [6] and failed(rec, "P2") == [6] and failed(rec, "P3") == []
    assert 6 not in failed(rec, "P4") and failed(rec, "P4") == [5]
    assert failed(rec, "P5") == []


def test_research_tool_names_match(tmp_path):
    names = {x.name for x in build_tools(Context(tmp_path / "r"))}
    assert set(RESEARCH_TOOLS) == names
