"""⑥ 獨立審查（決策 #49；G-61、G-56）。

- 由程式在 Opus 交出報告初稿後固定觸發，一個 run 只 1 次，一次審完整份報告。
- 不用 Hermes 的 delegate_task：程式另開一個 Hermes Agent（獨立子程序），Tool 清單是空的（不能上網、不能呼叫研究 Tool）。
- 用預設模型，和研究用的一樣。
- 只拿到報告和報告引用證據的原文；不看 Board、Tool 呼叫紀錄。
- 結果與程式警告合成待修清單，存 runs/<id>/review.json；審查花的請求數、token、耗時記進 run 摘要。
"""
from __future__ import annotations

import json
import re
import time

from .hermes_bridge import run_agent
from .model_env import ModelSettings

EVIDENCE_CHARS = 4000  # 每份證據給審查看的字數上限（控制 token；原檔仍可由 Evidence ID 追回）

REVIEW_PROMPT = """你是獨立審查者。你只拿到一份競品 SEO 研究報告，和報告引用的證據原文。你沒有任何 Tool，不能上網，也看不到研究過程。

請順著報告的思路整份看，找出：
- 推錯的地方：證據說的和結論不一樣、從證據推不出這個結論、把推論寫成事實。
- 證據撐不起的地方：只有一份證據、樣本太小、證據和結論講的不是同一件事。
- 否定結論（沒有／讀不到／做不到）要特別注意：有沒有可能其實是被擋、逾時、抓錯頁、樣本不夠；
  排除另一種可能的證據，是不是來自另一種方法（不同 Tool 或不同來源）。
- 結論是不是只靠可能過期的資料（證據標「快照」，附抓取時間）。
- 行動建議是不是真的由前面的結論支持。
要看哪些由你自己判斷。沒有問題的地方不用寫。

只輸出一個 JSON 物件，不要其他文字：
{"items": [{"sentence": "報告裡的哪一句（寫結論編號與原文）", "problem": "問題是什麼",
            "evidence_ids": ["相關的 Evidence ID"], "needs_evidence": true 或 false,
            "stale": true 或 false}]}
needs_evidence＝要補查證據才能修；stale＝結論靠可能過期的快照資料，補查時要重抓即時資料。"""


def _text(ctx, eid: str) -> str:
    from .tools.web import decode
    text = decode(ctx.store.read(eid))
    head = ""
    if "<html" in text[:2000].lower() or "<body" in text.lower():
        head = _head_facts(ctx, eid, text)
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return head + text[:EVIDENCE_CHARS] + ("…（截斷）" if len(text) > EVIDENCE_CHARS else "")


HEAD_KEYS = ("meta_robots", "canonicals", "jsonld_types", "jsonld_foreign_entities", "title", "trackers")
OG_KEYS = re.compile(r"(?i)^(?!og:image:).*(time|type|url)$")  # og:title／description／image（含 og:image:*）和 title 重複或很長，不放
HEAD_DATES = 6    # JSON-LD 日期最多列幾筆
HEAD_CHARS = 300  # 每個欄位最多幾字


def _head_facts(ctx, eid: str, html: str) -> str:
    """頁面去掉標籤後只剩可見文字，meta robots、canonical、og 日期、JSON-LD 都不見；
    審查因此把有證據的結論判成「證據裡沒有」（2026-11-17 Opus 實跑 26 項待修裡有 4 項是這樣，模型為此多查 6 次、刪掉 1 條成立的結論）。
    這裡把同一份原檔裡的這幾個欄位（程式解析，不判讀）放在摘錄最前面。日期排最前、逐欄限長，長的 og 才不會把日期擠掉。"""
    from .tools.html_parse import parse_html
    from .tools.web import page_url
    item = ctx.store.get(eid) or {}
    try:
        page = parse_html(html, page_url(item) if item else "")
    except Exception:  # 解析不了就只給文字，和以前一樣
        return ""
    facts: dict = {}
    dates: list[str] = []
    for block in page.get("jsonld_raw") or []:  # 只看 JSON-LD 區塊，依出現順序
        for k, v in re.findall(r'"(date(?:Published|Modified))"\s*:\s*"([^"]{4,40})"', str(block)):
            if f"{k}={v}" not in dates:
                dates.append(f"{k}={v}")
    if dates:
        facts["jsonld_dates"] = dates[:HEAD_DATES]
    og = {k: v for k, v in (page.get("og") or {}).items() if OG_KEYS.search(str(k))}
    if og:
        facts["og"] = og
    for k in HEAD_KEYS:
        if page.get(k):
            facts[k] = page[k]
    if not facts:
        return ""
    parts = []
    for k, v in facts.items():
        s = json.dumps(v, ensure_ascii=False)
        cut = len(s) > HEAD_CHARS or (k == "jsonld_dates" and len(dates) > HEAD_DATES)
        parts.append(f"{k}: " + s[:HEAD_CHARS] + ("…（截斷）" if cut else ""))
    return "〔原檔 head／JSON-LD 欄位（程式解析）〕" + "；".join(parts) + "\n〔可見文字〕"


def cited_ids(rep: dict) -> list[str]:
    from .checks import CITE
    from .report import claims_of
    ids: list[str] = []
    for c in claims_of(rep):
        for e in c.get("evidence_ids") or []:
            if e not in ids:
                ids.append(e)
        for e, _ in CITE.findall(c.get("text") or ""):
            if e not in ids:
                ids.append(e)
    return ids


def build_input(ctx, rep: dict) -> dict:
    """審查拿到的全部東西：報告＋報告引用證據的原文（不含研究過程）。"""
    evidence = []
    for eid in cited_ids(rep):
        item = ctx.store.get(eid)
        if not item:
            evidence.append({"id": eid, "missing": True})
            continue
        meta = item.get("meta") or {}
        evidence.append({"id": eid, "tool": item["tool"], "kind": item["kind"], "source": item["source"],
                         "snapshot": bool(meta.get("snapshot")), "fetched_at": meta.get("fetched_at") or item["at"],
                         "http_status": meta.get("status"), "text": _text(ctx, eid)})
    return {"report": rep, "evidence": evidence}


def review_message(review_input: dict) -> str:
    return ("以下是要審查的報告與證據（JSON）。\n\n" + json.dumps(review_input, ensure_ascii=False, indent=1))


def parse_items(text: str | None) -> list[dict] | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out = []
    for i in items:
        if isinstance(i, dict) and (i.get("problem") or "").strip():
            out.append({"sentence": str(i.get("sentence") or ""), "problem": str(i["problem"]),
                        "evidence_ids": [str(e) for e in i.get("evidence_ids") or []],
                        "needs_evidence": bool(i.get("needs_evidence")), "stale": bool(i.get("stale"))})
    return out


def run_review(model: ModelSettings, payload: dict, *, run_id: str) -> dict:
    """worker 子程序裡跑：沒有任何 Tool 的 Hermes Agent。"""
    started = time.time()
    out = run_agent(model, [], system_prompt=REVIEW_PROMPT, message=review_message(payload["input"]), run_id=run_id,
                    max_iterations=int(payload.get("max_iterations", 4)),
                    budget_seconds=float(payload.get("budget_seconds", 600)))
    items = parse_items(out.get("final_response"))
    status = "passed"
    if out.get("tools_offered"):
        status, items = "failed", None  # 審查 Agent 不能拿到任何 Tool
    elif items is None:
        status = "failed"
    return {"status": status, "items": items or [], "tools_offered": out.get("tools_offered"),
            "api_calls": out.get("api_calls"), "tokens": out.get("tokens"), "error": out.get("error"),
            "elapsed_s": round(time.time() - started, 1), "model": out.get("model")}


def default_reviewer(ctx, review_input: dict, *, run_id: str, model: str | None, budget_seconds: float = 600) -> dict:
    """父（研究）程序呼叫：另開獨立子程序跑審查，輸出放 runs/<id>/<id>-review/。"""
    from .runner import run_isolated
    rid = f"{run_id}-review"[:64]
    return run_isolated("review", rid, {"input": review_input, "model": model, "budget_seconds": budget_seconds},
                        timeout_s=budget_seconds + 300, out_root=ctx.run_dir)
