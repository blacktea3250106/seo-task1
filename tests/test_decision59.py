"""決策 #59：時間回饋、停止條件只剩 2 個、經驗不記網址、每輪單獨評分（成本、待修處理結果、untrusted_run 排除）。全部離線。"""
from __future__ import annotations

import json

from test_audit_v3 import env as audit_env  # noqa: F401
from test_audit_v3 import failed, propose
from test_report_v3 import env, flow_env, good  # noqa: F401

from seo_agent.evaluation import review_outcomes, round_table
from seo_agent.experience import entry_label, site_problems
from seo_agent.report import report_tool
from seo_agent.sequence import dry_run_fn, run_sequence


# ---- 1. 時間回饋 ----
def test_research_tool_result_has_time_used(flow_env):  # noqa: F811
    ctx, tools, guard, flow, _, _ = flow_env
    guard.total_s = 90 * 60  # 上限讀 run 設定，不寫死 120
    guard.clock = lambda: guard.started + 12 * 60
    out = tools["polite_fetch"]({"url": "https://2030.tw/t/"})
    assert out["time_used"] == "已用 12／90 分"


def test_fix_list_has_time_used(flow_env):  # noqa: F811
    ctx, tools, guard, flow, _, (p1, p2) = flow_env
    guard.clock = lambda: guard.started + 30 * 60
    out = report_tool(flow).func(good(p1, p2))
    assert out["status"] == "review" and out["time_used"] == "已用 30／120 分"


# ---- 3. 經驗不記網址 ----
def test_entry_label_shows_tool_names_only():
    e = {"situation": "s", "route": "1. polite_fetch：抓，因為 x\n2. sitemap_tree：查，因為 y", "result": "照走",
         "route_tools": [{"tool": "polite_fetch", "domain": "2030.tw", "path": "/wordcup/3a娛樂城/"},
                         {"tool": "polite_fetch", "domain": "2030.tw", "path": "/news/"},
                         {"tool": "sitemap_tree", "domain": "2030.tw", "path": "/"}]}
    label = entry_label(e)
    assert "（實際 Tool：polite_fetch、sitemap_tree）" in label
    assert "2030.tw" not in label and "/wordcup" not in label and "/news" not in label
    assert e["route_tools"][0]["path"] == "/wordcup/3a娛樂城/"  # 原始資料照存


def test_site_problems_string_match():
    paths = {"/wordcup", "/wordcup/3a娛樂城", "/news"}
    assert site_problems({"situation": "在 2030.TW 看到", "route": ""}, "2030.tw", paths) == ["situation 含目標網域 2030.tw"]
    bad = site_problems({"situation": "x", "route": "1. polite_fetch：抓 /wordcup/3A娛樂城/，因為 y"}, "2030.tw", paths)
    assert bad and "route 含站內路徑 /wordcup" in bad[0]
    ok = {"situation": "選單有的區塊在主 sitemap 找不到", "route": "1. sitemap_tree：查 polite_fetch/inspect_page 手機/桌機，因為 /feed"}
    assert site_problems(ok, "2030.tw", paths) == []


def test_audit_item7_rejects_target_domain_and_paths(audit_env):  # noqa: F811
    ctx, t, store = audit_env
    a = t["polite_fetch"]({"url": "https://2030.tw/"})["evidence_id"]
    b = t["polite_fetch"]({"url": "https://2030.tw/news/a/"})["evidence_id"]
    propose(t, evidence_ids=[a, b])                                                     # P1 通用寫法
    propose(t, evidence_ids=[a, b], situation="2030.tw 選單有的區塊在 sitemap 找不到")     # P2 目標網域
    propose(t, evidence_ids=[a, b], route="1. polite_fetch：抓 /news/a/ 看內容，因為要核對\n"
                                         "2. inspect_page：看 canonical，因為要分清刻意不收錄")  # P3 站內路徑
    claims = [{"id": "S1", "text": "首頁有新聞區", "kind": "fact", "evidence_ids": [a, b]}]
    from test_audit_v3 import write_report
    write_report(ctx, claims)
    doc = json.loads((ctx.run_dir / "report.json").read_text(encoding="utf-8"))
    doc["meta"]["site"] = "https://2030.tw"
    (ctx.run_dir / "report.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    from seo_agent.audit import audit_run
    from seo_agent.evaluation import evaluate
    evaluate(ctx.run_dir)
    rec = audit_run(ctx.run_dir, store)
    assert failed(rec, "P1") == [] and failed(rec, "P2") == [7] and failed(rec, "P3") == [7]
    reason = next(x for x in rec["results"] if x["proposal_id"] == "P3")["failed"][0]["reason"]
    assert "站內路徑 /news" in reason
    saved = json.loads((ctx.run_dir / "experience_audit.json").read_text(encoding="utf-8"))
    assert "站內路徑 /news" in json.dumps(saved, ensure_ascii=False)  # 理由寫進 experience_audit.json
    assert [e["route_tools"] for e in store.active()][0][0]["domain"] == "2030.tw"  # 後台照存


def test_propose_rejects_paths_when_site_known(audit_env):  # noqa: F811
    ctx, t, _ = audit_env
    ctx.site_domain = "2030.tw"
    a = t["polite_fetch"]({"url": "https://2030.tw/news/a/"})["evidence_id"]
    out = propose(t, evidence_ids=[a], situation="/news/ 區塊在 sitemap 找不到")
    assert out["ok"] is False and "站內路徑" in out["error"]["detail"]


# ---- 9. 待修處理結果 ----
def _write(run_dir, review, draft, final, calls, revised=True):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "review.json").write_text(json.dumps({"items": review}, ensure_ascii=False), encoding="utf-8")
    (run_dir / "report_draft.json").write_text(json.dumps({"onpage": draft}, ensure_ascii=False), encoding="utf-8")
    (run_dir / "report.json").write_text(json.dumps({"meta": {"revised": revised}, "report": {"onpage": final}},
                                                    ensure_ascii=False), encoding="utf-8")
    (run_dir / "tool_calls.jsonl").write_text("".join(json.dumps(c) + "\n" for c in calls), encoding="utf-8")


def test_review_outcomes_rules(tmp_path):
    c = lambda i, **kw: {"id": i, "text": "t", "kind": "fact", "evidence_ids": ["E-0001"], **kw}  # noqa: E731
    draft = [c("ON1"), c("ON2"), c("ON3"), c("ON10"), c("ON4")]
    final = [c("ON1", evidence_ids=["E-0001", "E-0009"]), c("ON2", kind="inference", limits="l"), c("ON3"),
             c("ON10", text="改了字"), c("ON4", alternative="未排除")]
    review = [{"id": f"R{n}", "source": "審查", "sentence": s} for n, s in
              enumerate(["ON1：t", "ON2 t", "ON3：t", "ON10：t", "格式", "ON1 與 ON2", "ON4：t"], 1)]
    calls = [{"n": 1, "tool": "polite_fetch", "evidence_id": "E-0001"}, {"n": 2, "tool": "submit_report"},
             {"n": 3, "tool": "polite_fetch", "evidence_id": "E-0009"}]
    _write(tmp_path / "r", review, draft, final, calls)
    got = [o["outcome"] for o in review_outcomes(tmp_path / "r")]
    assert got == ["補查後修正", "降成推論", "沒處理", "需人工判定", "需人工判定", "需人工判定", "降成推論"]
    # 引用的是第 1 次交卷前就有的證據 → 不算補查
    _write(tmp_path / "s", review[:1], draft, [c("ON1", evidence_ids=["E-0001", "E-0009"])],
           [{"n": 1, "tool": "polite_fetch", "evidence_id": "E-0009"}, {"n": 2, "tool": "submit_report"}])
    assert review_outcomes(tmp_path / "s")[0]["outcome"] == "需人工判定"
    # 沒交修正稿（初稿照收）→ 全部沒處理
    _write(tmp_path / "u", review, draft, draft, calls, revised=False)
    assert {o["outcome"] for o in review_outcomes(tmp_path / "u")} == {"沒處理"}


def test_review_outcome_from_real_flow(flow_env):  # noqa: F811
    from seo_agent.hermes_bridge import ToolLog
    ctx, tools, guard, flow, _, (p1, p2) = flow_env
    submit = (lambda h: (lambda a: json.loads(h(a))))(ToolLog(guard=guard, ctx=ctx).wrap(report_tool(flow)))
    assert submit(good(p1, p2))["status"] == "review"       # 待修 R1 指 C2
    p3 = tools["polite_fetch"]({"url": "https://2030.tw/more/"})["evidence_id"]  # 回 ④ 補查
    rev = good(p1, p2)
    rev["offpage"][0]["evidence_ids"] = [p2, p3]
    submit(rev)
    from seo_agent.evaluation import evaluate
    ev = evaluate(ctx.run_dir)
    assert ev["review_outcomes"][0] == {"id": "R1", "source": "審查", "claim_id": "C2", "outcome": "補查後修正",
                                        "needs_evidence": True}
    assert "| R1 | 審查 | C2 | 是 | 補查後修正 |  |" in (ctx.run_dir / "review_outcomes.md").read_text(encoding="utf-8")


# ---- 4、6、10. 每輪單獨評分＋成本＋untrusted_run 排除 ----
def test_round_table_per_round_scores_and_untrusted(tmp_path):
    from seo_agent import sequence
    prevs = []
    real_eval = sequence.evaluate

    def run_fn(i, store_path, out_dir):
        run_dir = dry_run_fn(i, store_path, out_dir)
        res = json.loads((run_dir / "result.json").read_text())
        res.update(tool_calls_total=10 * i, elapsed_s=60.0 * i,
                   review={"total_with_review": {"api_calls": i, "tokens": {"total": 1000 * i}}})
        if i == 2:
            res["untrusted_run"] = "用了專案外 Tool：Bash"
        (run_dir / "result.json").write_text(json.dumps(res))
        return run_dir

    sequence.evaluate = lambda d, **kw: prevs.append(kw["prev_run_dir"] and kw["prev_run_dir"].name) or real_eval(d, **kw)
    try:
        run_sequence(3, run_fn=run_fn, out_dir=tmp_path / "seq", log=lambda s: None)
    finally:
        sequence.evaluate = real_eval
    assert prevs == [None, "dry-r1", "dry-r1"]  # 不可信的第 2 輪不當第 3 輪的比較基準
    rows = json.loads((tmp_path / "seq" / "rounds.json").read_text())["rows"]
    assert [r["compare"] for r in rows] == [True, False, True]
    for r in rows:  # 每輪的分數就是它自己的 evaluation.json，不扣前輪
        ev = json.loads((tmp_path / "seq" / f"dry-r{r['round']}" / "evaluation.json").read_text())
        assert r["score"] == ev["total"] and r["wrong_count"] == len(ev["judged_wrong"])
    assert rows[2]["cost"] == {"tool_calls": 30, "api_calls": 3, "tokens": 3000, "elapsed_s_reference": 180.0}
    md = (tmp_path / "seq" / "rounds.md").read_text()
    assert "否（untrusted_run：用了專案外 Tool：Bash）" in md and "秒數（參考）" in md
    assert round_table(tmp_path / "seq")["rows"] == rows
