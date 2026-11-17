"""評估後的附加紀錄（G-29 判錯結論；G-30 回填關鍵發現與新發現數；G-31 回填總分到 run 摘要）。

- 不改凍結的 grader.py 與 rubric：只呼叫 grader.grade，逐句（每個結論）再評一次，找出被判錯的結論。
- 判錯結論紀錄＝每個被判錯的結論＋它引用的 Evidence ID；寫入審核第 4 項與「判錯」下架都讀這份（判定訊號定義 A、D）。
- 有 evaluation.json＝「評分出來了」；沒有就不做寫入審核、也不判定下架。

- 總分只給人看：不拿來判斷單條經驗要不要收或下架。
- 每輪單獨評分（決策 #59）：每輪的成績就是它自己的 14 項分數＋說錯幾條，不扣前幾輪已寫過的；new_findings 只當參考。
  另記成本（Tool 呼叫次數、Token；秒數只當參考）、⑥ 待修每項的處理結果、是否 untrusted_run（不列入比較）。
  序列的每輪成績表：python -m seo_agent.evaluation --table SEQ_DIR（寫 rounds.md／rounds.json）。
  這些只在評分端，不進任何 Agent 的提示。

用法：python -m seo_agent.evaluation RUN_DIR [--prev 上一輪 RUN_DIR]
      python -m seo_agent.evaluation --table SEQ_DIR
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .grader import dimensions, grade, load_rubric
from .metrics import key_finding, new_findings

EVALUATION = "evaluation.json"
CLAIM_SECTIONS = ("onpage", "offpage")


def claims_of(rep: dict) -> list[dict]:
    claims = [c for s in CLAIM_SECTIONS for c in (rep.get(s) or [])]
    return claims or list(rep.get("strategy") or [])  # 舊格式報告


def judged_wrong(rep: dict, rubric: dict | None = None) -> list[dict]:
    """逐個結論用凍結規則評分；命中 wrong 規則（mark x）的結論記下它引用的 Evidence ID。"""
    rubric = rubric or load_rubric()
    out = []
    for c in claims_of(rep):
        g = grade((c.get("text") or "").replace("\n", " "), rubric)
        if g["wrong"]:
            out.append({"claim_id": c.get("id"), "text": (c.get("text") or "")[:240], "rubric_items": g["wrong"],
                        "evidence_ids": list(c.get("evidence_ids") or [])})
    return out


def judged_wrong_evidence(run_dir: Path) -> set[str] | None:
    """評分出來 → 判錯結論引用的全部 Evidence ID；評分還沒出來 → None。"""
    path = Path(run_dir) / EVALUATION
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return {e for w in data.get("judged_wrong", []) for e in w["evidence_ids"]}


OUTCOMES = ("補查後修正", "降成推論", "沒處理", "需人工判定")


def _claims_by_id(rep: dict | None) -> dict[str, dict]:
    return {c.get("id"): c for c in claims_of(rep or {}) if c.get("id")}


def review_outcomes(run_dir: Path) -> list[dict] | None:
    """⑥ 待修清單每一項最後的處理結果（決策 #59；不用 LLM，只比對初稿與修正稿）。
    - 待修項的 sentence 只對到初稿 1 條結論編號時才由程式判定，否則「需人工判定」。
    - 補查後修正：修正稿這條結論多引用的 Evidence ID，有在第 1 次 submit_report 之後才產生的。
    - 降成推論：fact 改成 inference，或另一種可能新標「未排除」。
    - 沒處理：這條結論的文字、類別、證據、另一種可能、限制都和初稿一樣；或根本沒交修正稿（初稿照收）。
    - 其他（改了字但沒新證據、結論被刪掉）：需人工判定。沒有 review.json → None。"""
    import re
    run_dir = Path(run_dir)
    review_path, draft_path, final_path = run_dir / "review.json", run_dir / "report_draft.json", run_dir / "report.json"
    if not review_path.exists():
        return None
    items = json.loads(review_path.read_text(encoding="utf-8")).get("items") or []
    draft = _claims_by_id(json.loads(draft_path.read_text(encoding="utf-8")) if draft_path.exists() else None)
    final_doc = json.loads(final_path.read_text(encoding="utf-8")) if final_path.exists() else {}
    revised = bool((final_doc.get("meta") or {}).get("revised"))
    final = _claims_by_id(final_doc.get("report"))
    calls = []
    if (run_dir / "tool_calls.jsonl").exists():
        calls = [json.loads(x) for x in (run_dir / "tool_calls.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    first_submit = next((i for i, c in enumerate(calls) if c.get("tool") == "submit_report"), None)  # 依檔案行序
    after = {e for c in (calls[first_submit + 1:] if first_submit is not None else [])
             for e in (c.get("evidence_id"), c.get("derived_evidence_id")) if e}
    keys = ("text", "kind", "evidence_ids", "alternative", "alternative_evidence_ids", "limits")
    out = []
    for it in items:
        sentence = it.get("sentence") or ""
        ids = [cid for cid in draft if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(cid)}(?![A-Za-z0-9_])", sentence)]
        cid = ids[0] if len(ids) == 1 else None
        if not revised and final_doc:
            outcome = "沒處理"
        elif cid is None or cid not in final:
            outcome = "需人工判定"
        else:
            d, f = draft[cid], final[cid]
            ev = lambda c: set(c.get("evidence_ids") or []) | set(c.get("alternative_evidence_ids") or [])  # noqa: E731
            if (ev(f) - ev(d)) & after:
                outcome = "補查後修正"
            elif (d.get("kind") == "fact" and f.get("kind") == "inference") or (
                    "未排除" in (f.get("alternative") or "") and "未排除" not in (d.get("alternative") or "")):
                outcome = "降成推論"
            elif all(d.get(k) == f.get(k) for k in keys):
                outcome = "沒處理"
            else:
                outcome = "需人工判定"
        out.append({"id": it.get("id"), "source": it.get("source"), "claim_id": cid, "outcome": outcome,
                    "needs_evidence": bool(it.get("needs_evidence"))})
    return out


def run_cost(summary: dict | None) -> dict:
    """每輪成本：Tool 呼叫次數與 Token（含 ⑥ 審查）；秒數只當參考。"""
    summary = summary or {}
    total = ((summary.get("review") or {}).get("total_with_review") or {})
    tokens = (total.get("tokens") or summary.get("tokens") or {}).get("total")
    return {"tool_calls": summary.get("tool_calls_total"), "api_calls": total.get("api_calls", summary.get("api_calls")),
            "tokens": tokens, "elapsed_s_reference": summary.get("elapsed_s")}


def write_review_table(run_dir: Path, outcomes: list[dict] | None) -> None:
    """待修處理結果表：程式判定＋一欄空白給人工確認或補判（「需人工判定」的項目一定要人工填）。"""
    if outcomes is None:
        return
    lines = ["# ⑥ 待修處理結果（評分端，研究 Agent 看不到）", "",
             "程式只比對初稿與修正稿；「需人工判定」的項目請在最後一欄填 補查後修正／降成推論／沒處理。", "",
             "| 待修 | 來源 | 對應結論 | 要補證據 | 程式判定 | 人工確認 |", "|---|---|---|---|---|---|"]
    for o in outcomes:
        lines.append(f"| {o['id']} | {o['source']} | {o['claim_id'] or '—'} | {'是' if o['needs_evidence'] else '否'} | "
                     f"{o['outcome']} |  |")
    (Path(run_dir) / "review_outcomes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate(run_dir: Path, rubric: dict | None = None, *, prev_run_dir: Path | None = None) -> dict:
    run_dir = Path(run_dir)
    rubric = rubric or load_rubric()
    rep = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))["report"]
    dims = dimensions(run_dir, rubric)
    result_path = run_dir / "result.json"
    summary = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
    prev = Path(prev_run_dir) / EVALUATION if prev_run_dir else None
    prev_marks = json.loads(prev.read_text(encoding="utf-8"))["marks"] if prev and prev.exists() else None
    marks = dims["grade"]["marks"]
    result = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rubric": rubric["version"],
              "total": dims["grade"]["total"], "max": dims["grade"]["max"], "marks": marks,
              "dimensions": {k: v for k, v in dims.items() if k != "grade"},
              "judged_wrong": judged_wrong(rep, rubric),
              "key_finding": key_finding(run_dir, claims_of(rep), rubric,
                                         started_at=(summary or {}).get("started_at")),
              "prev_run": str(prev_run_dir) if prev_run_dir else None,
              "new_findings": new_findings(marks, prev_marks, [i["id"] for i in rubric["items"]])}
    result["wrong_count"] = len(result["judged_wrong"])  # 主指標之一：說錯幾條（程式；另需人工核對）
    result["cost"] = run_cost(summary)
    result["untrusted_run"] = (summary or {}).get("untrusted_run")  # 有值＝不列入比較（決策 #59）
    result["review_outcomes"] = review_outcomes(run_dir)
    write_review_table(run_dir, result["review_outcomes"])
    (run_dir / EVALUATION).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if summary is not None:  # 回填 run 摘要（G-31）
        summary.setdefault("metrics", {}).update(key_finding=result["key_finding"], new_findings=result["new_findings"])
        summary["score"] = {"total": result["total"], "max": result["max"], "marks": marks, "note": "只給人看"}
        result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return result


def round_table(seq_dir: Path) -> dict:
    """序列的每輪成績表（決策 #59）：每輪自己的分數，不扣前輪；untrusted_run 標明並排除在比較之外。
    「人工」欄留空：14 項人工逐句核對與說錯條數由人遮住 run 名稱盲評後填。寫 rounds.json／rounds.md。"""
    seq_dir = Path(seq_dir)
    steps = json.loads((seq_dir / "sequence.json").read_text(encoding="utf-8")).get("steps") or []
    rows = []
    for st in steps:
        if st.get("step") != "research":
            continue
        run_dir = Path(st["run_dir"])
        ev_path, res_path = run_dir / EVALUATION, run_dir / "result.json"
        ev = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else {}
        res = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {}
        untrusted = ev.get("untrusted_run") or res.get("untrusted_run")
        counts = {k: sum(1 for o in ev.get("review_outcomes") or [] if o["outcome"] == k) for k in OUTCOMES}
        rows.append({"round": st["round"], "run": run_dir.name, "status": res.get("status"),
                     "score": ev.get("total"), "max": ev.get("max"),
                     "wrong_count": ev.get("wrong_count", len(ev.get("judged_wrong") or []) if ev else None),
                     "cost": ev.get("cost") or run_cost(res), "review_outcomes": counts,
                     "compare": not untrusted, "untrusted_run": untrusted})
    data = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rows": rows,
            "note": "每輪單獨評分；不列入比較＝untrusted_run；秒數只當參考；累計表只當參考（決策 #59）"}
    (seq_dir / "rounds.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    cell = lambda v: "—" if v is None else str(v)  # noqa: E731
    lines = ["# 每輪成績（每輪單獨評分，不扣前輪）", "",
             "- 主指標：14 項（程式＋人工核對）＋說錯幾條；人工欄遮住 run 名稱盲評後填。",
             "- 成本：Tool 呼叫次數、Token；秒數只當參考。判定規則見 eval/README.md。", "",
             "| 輪 | 14 項（程式） | 14 項（人工） | 說錯（程式） | 說錯（人工） | Tool 呼叫 | Token | 秒數（參考） | "
             "待修：補查後修正／降成推論／沒處理／需人工 | 列入比較 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c, o = r["cost"], r["review_outcomes"]
        score = f"{r['score']:g}/{r['max']}" if r["score"] is not None else "—"
        compare = "是" if r["compare"] else f"否（untrusted_run：{r['untrusted_run']}）"
        lines.append(f"| {r['round']} | {score} |  | {cell(r['wrong_count'])} |  | {cell(c.get('tool_calls'))} | "
                     f"{cell(c.get('tokens'))} | {cell(c.get('elapsed_s_reference'))} | "
                     f"{'／'.join(str(o[k]) for k in OUTCOMES)} | {compare} |")
    (seq_dir / "rounds.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path, nargs="?")
    ap.add_argument("--prev", type=Path, default=None, help="上一輪的 run 資料夾（算新發現數，只當參考）")
    ap.add_argument("--table", type=Path, default=None, help="序列資料夾：寫每輪成績表 rounds.md／rounds.json")
    args = ap.parse_args(argv)
    if args.table is not None:
        print(json.dumps({"rows": len(round_table(args.table)["rows"])}, ensure_ascii=False))
        return 0
    if args.run_dir is None:
        ap.error("要給 RUN_DIR 或 --table SEQ_DIR")
    r = evaluate(args.run_dir, prev_run_dir=args.prev)
    print(json.dumps({k: r[k] for k in ("total", "max", "marks")} | {"judged_wrong": len(r["judged_wrong"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
