"""確定性評分器（需求 3：評估方法與結果）。

- 14 項重點逐項用固定規則比對報告文字：同一行內每組正規式都要命中才算數。
- 每項 full=1、partial=0.5、沒有=0；命中 wrong 規則記為「說錯」（0 分並列出原句）。
- 不呼叫任何 AI；同一份報告永遠同分。限制：只看字面，不判斷證據真假，換說法可能漏抓（見 eval/README.md）。

- 6 項分開列、不合總分（d-architecture 第 10 點）：完整度、正確度、誠實度、可追溯、建議有根據、新發現。
  後四項需要 V3 的結構化 report.json＋證據庫；舊的 Markdown 報告只算前兩項，其他標「不適用」。

用法：python -m seo_agent.grader REPORT.md|RUN_DIR [--rubric eval/rubric_2030.json] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import ROOT

RUBRIC = ROOT / "eval" / "rubric_2030.json"


def load_rubric(path: Path = RUBRIC) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# 審查 major 3：寫成「未知／限制／未通過檢查」的句子不算找到重點。
SKIP_HEADING = re.compile(r"未知|限制|unknown|limitation|self-critique|自我檢討|自我批判|未通過|下一步|next step", re.I)
SKIP_LINE = re.compile(r"^\W{0,6}\[?(未知|unknown)\]?[：:\]]|\[檢查未通過\]", re.I)


def _lines(text: str) -> list[str]:
    """回傳要評分的行：跳過標題含 SKIP_HEADING 的整段（到下一個同級或更高標題為止）與標成未知的行。"""
    out, skip_level = [], None
    for ln in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            level = len(m.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and SKIP_HEADING.search(m.group(2)):
                skip_level = level
            continue
        if skip_level is None and ln.strip() and not SKIP_LINE.search(ln):
            out.append(ln)
    return out


def _hit(groups: list[list[str]] | None, lines: list[str]) -> str | None:
    """回傳第一行「每組都命中」的原句；沒有則 None。"""
    if not groups:
        return None
    for ln in lines:
        if all(any(re.search(p, ln, re.I) for p in g) for g in groups):
            return ln.strip()
    return None


def grade(text: str, rubric: dict | None = None) -> dict:
    rubric = rubric or load_rubric()
    pts = rubric["scoring"]
    lines = _lines(text)
    items, total = [], 0.0
    for it in rubric["items"]:
        wrong = next((ln.strip() for ln in lines for p in it.get("wrong", []) if re.search(p, ln, re.I)), None)
        full = _hit(it.get("full"), lines)
        part = None if full else _hit(it.get("partial"), lines)
        if wrong:
            mark, quote = "x", wrong
        elif full:
            mark, quote = "y", full
        elif part:
            mark, quote = "p", part
        else:
            mark, quote = "n", None
        score = {"y": pts["full"], "p": pts["partial"], "n": pts["missing"], "x": pts["wrong"]}[mark]
        total += score
        items.append({"id": it["id"], "point": it["point"], "mark": mark, "score": score,
                      "quote": (quote or "")[:240]})
    return {"rubric": rubric["version"], "total": total, "max": len(rubric["items"]),
            "marks": "".join(i["mark"] for i in items), "wrong": [i["id"] for i in items if i["mark"] == "x"],
            "items": items}


def _ratio(ok: int, n: int) -> dict:
    return {"ok": ok, "of": n, "rate": round(ok / n, 3) if n else None}


def dimensions(run_dir: Path, rubric: dict | None = None) -> dict:
    """V3 run 的 6 項指標（各自獨立，不加總）。"""
    from .report import ABSOLUTE
    rubric = rubric or load_rubric()
    data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    rep, meta = data["report"], data.get("meta", {})
    claims_all = list(rep.get("strategy") or []) + list(rep.get("evidence") or [])
    g = grade("\n".join((c.get("text") or "").replace("\n", " ") for c in claims_all), rubric)  # 只評主張，不評未知段
    ev = {}
    for ln in (run_dir / "evidence.jsonl").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            e = json.loads(ln)
            ev[e["id"]] = e
    claims = list(rep.get("strategy") or []) + list(rep.get("evidence") or [])
    traced = sum(1 for c in claims if c.get("evidence_ids")
                 and all(i in ev and (run_dir / ev[i]["file"]).exists() for i in c["evidence_ids"]))
    absolute = [c for c in claims if ABSOLUTE.search(c.get("text") or "")]
    abs_ok = sum(1 for c in absolute if (c.get("scope") or "").strip() and len(set(c.get("evidence_ids") or [])) >= 2)
    inf = [c for c in claims if c.get("kind") == "inference"]
    inf_ok = sum(1 for c in inf if (c.get("limits") or "").strip())
    ids = {c.get("id") for c in claims}
    actions = rep.get("actions") or []
    act_ok = sum(1 for a in actions if a.get("based_on") and all(r in ids for r in a["based_on"]))
    one = {"version": rubric["version"], "scoring": rubric["scoring"], "items": rubric["items"]}
    novel = [c.get("id") + "：" + (c.get("text") or "")[:80] for c in claims
             if grade(c.get("text") or "", one)["total"] == 0]
    return {
        "完整度": {"score": g["total"], "max": g["max"], "marks": g["marks"]},
        "正確度": {"wrong_items": g["wrong"], "check_issues_left": meta.get("unresolved_issues") or [], "rejections": meta.get("rejections")},
        "誠實度": {"absolute_scoped_2ev": _ratio(abs_ok, len(absolute)), "inference_with_limits": _ratio(inf_ok, len(inf)),
                 "unknowns": len(rep.get("unknowns") or [])},
        "可追溯": {"claims_with_existing_evidence": _ratio(traced, len(claims))},
        "建議有根據": {"actions_based_on_valid_claims": _ratio(act_ok, len(actions))},
        "新發現": {"claims_outside_14": len(novel), "list_for_human": novel,
                 "note": "只列出不屬於 14 項的主張；是否為真且有價值要人工看"},
        "grade": g,
    }


def report_text(path: Path) -> str:
    """接受 report.md 或 V3 的 report.json（取 markdown 欄或整份 JSON 文字）。"""
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(raw)
        return data.get("markdown") or json.dumps(data, ensure_ascii=False, indent=1)
    return raw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report", type=Path)
    ap.add_argument("--rubric", type=Path, default=RUBRIC)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rubric = load_rubric(a.rubric)
    if a.report.is_dir():
        dims = dimensions(a.report, rubric)
        if a.json:
            print(json.dumps(dims, ensure_ascii=False, indent=2))
            return 0
        for k, v in dims.items():
            if k != "grade":
                print(f"{k}: {json.dumps({x: y for x, y in v.items() if x != 'list_for_human'}, ensure_ascii=False)}")
        result = dims["grade"]
    else:
        result = grade(report_text(a.report), rubric)
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{a.report.name}: {result['total']:g}/{result['max']}  {result['marks']}  說錯={result['wrong']}")
        for i in result["items"]:
            print(f"  {i['id']} {i['mark']} {i['point']}" + (f"\n      ↳ {i['quote'][:120]}" if i["quote"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
