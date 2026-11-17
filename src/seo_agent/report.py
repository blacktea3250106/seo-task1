"""報告與 submit_report 流程（決策 #71：精簡報告＋⑥ 獨立審查；G-45、G-61、G-37）。

報告 5 段：1 摘要 2 On-page 3 Off-page 4 優先行動 5 未知與限制；另有選填的 experience（用了／推翻了哪些經驗）。
submit_report 流程（決策 #49）：
- 第 1 次交（初稿）：程式固定觸發 1 次 ⑥ 獨立審查，待修清單存 runs/<id>/review.json（審查意見＋程式警告＋格式問題），
  退給模型修一次；這時可回研究補查（StopGuard.phase＝revise）。
- 第 2 次交（修正稿）：不再送審；只跑格式檢查。沒過只退回 1 次（StopGuard.phase＝final），第 3 次照收，沒過的項目寫進第 5 段。
格式檢查只看：引用的 Evidence ID 存在、fact 有證據、inference 有 limits、On-page／Off-page 不全空、經驗編號存在。
"""
from __future__ import annotations

import json
import re
import time

from .experience import entry_label
from .hermes_bridge import Tool

MAX_REJECTIONS = 1  # 修正稿的格式退回最多 1 次（G-37）
# 只給凍結的 grader.py（誠實度指標）引用。
ABSOLUTE = re.compile(r"(沒有|並無|無任何|不存在|只有|僅有|僅\s*\d|唯一|(?<!\d)0\s*(次|筆|個|頁)|零|從未|未曾|找不到|查無|全部|所有|全站|完全)")
SECTIONS = ("summary", "onpage", "offpage", "actions", "unknowns")
SECTION_TITLES = {"summary": "1. 摘要", "onpage": "2. On-page", "offpage": "3. Off-page", "actions": "4. 優先行動",
                  "unknowns": "5. 未知與限制"}
KIND = {"fact": "事實", "inference": "推論"}


def claims_of(rep: dict) -> list[dict]:
    return list(rep.get("onpage") or []) + list(rep.get("offpage") or [])


def check_report(rep: dict, *, evidence_ids: set[str], experience_ids: set[str]) -> list[str]:
    """回傳退回原因（空＝通過）。"""
    errors: list[str] = [f"缺少第 {SECTION_TITLES[s]} 段（{s}）" for s in SECTIONS if rep.get(s) is None]
    if not claims_of(rep):
        errors.append("onpage、offpage 不能都是空的")
    seen: set[str] = set()
    for c in claims_of(rep):
        cid = c.get("id") or "?"
        if cid in seen:
            errors.append(f"結論編號重複：{cid}")
        seen.add(cid)
        evs = list(c.get("evidence_ids") or [])
        if c.get("kind") not in KIND:
            errors.append(f"{cid}：kind 要是 fact 或 inference；試過仍不知道的放 unknowns")
        if missing := [e for e in evs if e not in evidence_ids]:
            errors.append(f"{cid}：證據編號不存在 {missing}")
        if c.get("kind") == "fact" and not evs:
            errors.append(f"{cid}：fact 至少要 1 個 Evidence ID")
        if c.get("kind") == "inference" and not (c.get("limits") or "").strip():
            errors.append(f"{cid}：inference 要寫 limits")
    exp = rep.get("experience") or {}
    for o in exp.get("overturned") or []:
        if o.get("experience_id") not in experience_ids:
            errors.append(f"experience.overturned 指到不存在的經驗 {o.get('experience_id')}")
        ids = o.get("evidence_ids") or []
        if not ids or [e for e in ids if e not in evidence_ids]:
            errors.append(f"experience.overturned {o.get('experience_id')}：要附存在的 Evidence ID")
    return errors


def external_only(rep: dict, ctx) -> dict:
    """程式標記（不退回）：只引用外部說法的結論（G-47）。"""
    from .checks import _calls_by_evidence, is_external
    calls = _calls_by_evidence(ctx)
    marks = {}
    for c in claims_of(rep):
        evs = [e for e in c.get("evidence_ids") or [] if ctx.store.get(e)]
        if evs and all(is_external(ctx, e, calls) for e in evs):
            marks[c.get("id")] = ["只引用外部說法"]
    return marks


def program_findings(rep: dict, ctx) -> list[dict]:
    """給 ⑥ 待修清單的程式警告：只引用外部說法（G-47）、引用內容核對（G-46）。只是警告，不擋交件。"""
    from .checks import citation_warnings
    items = []
    by_id = {c.get("id"): c for c in claims_of(rep)}
    for cid in external_only(rep, ctx):
        c = by_id[cid]
        items.append({"sentence": f"{cid}：{c.get('text')}", "evidence_ids": c.get("evidence_ids") or [],
                      "problem": "〔只引用外部說法〕引用的都是競爭者以外網站的內容，只能當靈感，不能支持對方做了什麼",
                      "needs_evidence": True})
    texts = [(c.get("id") or "?", c.get("text") or "") for c in claims_of(rep)] + [("摘要", str(rep.get("summary") or ""))]
    for w in citation_warnings(ctx, texts):
        items.append({"sentence": w["where"], "problem": w["problems"][0], "evidence_ids": w["evidence_ids"],
                      "needs_evidence": False})
    return [{"source": "程式", **i} for i in items]


def render_markdown(rep: dict, *, evidence: dict[str, dict], experience: dict[str, dict], meta: dict,
                    marks: dict | None = None) -> str:
    marks = marks or {}

    def ev(ids):
        return "、".join(f"[{e}]({evidence[e]['file']})" if e in evidence else e for e in ids or []) or "無"

    def line(c):
        flags = "".join(f"〔{t}〕" for t in marks.get(c.get("id"), []))
        lim = f"（限制：{c['limits']}）" if c.get("limits") else ""
        return f"- **[{KIND.get(c.get('kind'), '?')}] {c.get('id')}**{flags} {c.get('text')}{lim}　證據：{ev(c.get('evidence_ids'))}"

    base = meta.get("baseline") or {}
    out = [f"# {meta.get('site', '')} 競品 SEO 研究報告", "",
           f"- run：`{meta.get('run_id')}`　模型：`{meta.get('model')}`　產生：{meta.get('at')}",
           "- 標記：[事實]＝直接觀察、[推論]＝根據證據推想、未知＝試過仍不知道",
           f"- 網站底稿：hash `{str(base.get('hash', ''))[:12]}`，抓取時間 "
           + "；".join(f"{k} {v}" for k, v in (base.get("fetched_at") or {}).items()) + "（標「快照」的證據來自底稿）", ""]
    out += [f"## {SECTION_TITLES['summary']}", str(rep.get("summary") or ""), ""]
    out += [f"## {SECTION_TITLES['onpage']}", *[line(c) for c in rep.get("onpage") or []], ""]
    out += [f"## {SECTION_TITLES['offpage']}", *[line(c) for c in rep.get("offpage") or []], ""]
    out += [f"## {SECTION_TITLES['actions']}", ""]
    for n, a in enumerate(rep.get("actions") or [], 1):
        out.append(f"{n}. {a.get('action')}　理由：{a.get('rationale')}　依據：{'、'.join(a.get('based_on') or []) or '無'}")
    out += ["", f"## {SECTION_TITLES['unknowns']}", *[f"- {u}" for u in rep.get("unknowns") or []]]
    out += [f"- **[檢查未通過]** {i}" for i in meta.get("unresolved_issues") or []]
    out += [f"- **[審查待修未處理]** {i}" for i in meta.get("review_open") or []]
    exp = rep.get("experience") or {}
    used = exp.get("used") or []
    out += ["", "## 經驗", "- 自稱用了哪些使用中經驗（是否真的用到由程式看 Tool 紀錄判定，見 experience_judgement.json）："
            + ("、".join(f"{e}（{entry_label(experience[e])[:60] if e in experience else '不在經驗檔'}）" for e in used) or "無")]
    for o in exp.get("overturned") or []:
        out.append(f"- 推翻 {o.get('experience_id')}：{o.get('why') or ''}　證據：{ev(o.get('evidence_ids'))}")
    if summary := meta.get("run_summary"):
        out.append("- run 摘要：" + "；".join(f"{k} {v}" for k, v in summary.items()))
    return "\n".join(out) + "\n"


def write_incomplete_report(ctx, meta: dict, *, reason: str, coverage: dict | None = None) -> dict:
    """時間到或中途錯誤、模型沒交出報告時，由程式輸出標「未完成」的報告：只整理已有證據，不替模型下結論（G-38）。"""
    evidence = [{"id": e["id"], "source": e["source"], "tool": e["tool"], "kind": e["kind"]} for e in ctx.store.all()]
    data = {"meta": {**meta, "status": "未完成", "reason": reason}, "coverage": coverage or {}, "evidence": evidence}
    (ctx.run_dir / "report_incomplete.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 未完成報告：{meta.get('site', '')}", "", f"- 狀態：未完成（{reason}）",
             f"- 已存證據：{len(evidence)} 筆（見 evidence.jsonl）"]
    if coverage:
        lines.append(f"- 讀過的資料卡分區：{'、'.join(coverage.get('sections_read') or []) or '無'}")
        lines.append(f"- 還沒讀過的資料卡分區：{'、'.join(coverage.get('sections_not_yet_read') or []) or '無'}")
    (ctx.run_dir / "report_incomplete.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


REVISE_MESSAGE = ("這是 ⑥ 獨立審查＋程式檢查的待修清單（已存 review.json）。請依清單修一次，再用 submit_report 交修正稿；"
                  "不會再審第二次。needs_evidence 的項目可以回去用研究 Tool 補查：交出修正稿後就不能再查；"
                  "stale 的項目（靠快照等可能過期的資料）補查時要重抓即時資料。補查後仍改不了的，改成 inference 寫 limits，或移到 unknowns。")
# 實驗 shortfix（決策 #67，只模擬路徑）：待修清單改交給新的短 session，研究 session 收到這句就結束
DEFERRED_MESSAGE = ("初稿已收，⑥ 獨立審查已產生待修清單（已存 review.json）。修正會在新的 session 進行，"
                    "這個 session 到此結束：不用再呼叫 Tool，用一句話結束。")
ACCEPT_MESSAGE = "報告已存檔。若還沒用 experience(action=propose) 寫這次走過的路線，現在寫 1–3 條；寫完用一句話結束。"


class ReportFlow:
    """submit_report 的狀態：draft（初稿→⑥ 審查）→ revise（修一次，可補查）→ final（格式檢查）。"""

    def __init__(self, ctx, *, experience_store, meta: dict, guard=None, reviewer=None, on_accept=None):
        self.ctx, self.store, self.meta, self.guard = ctx, experience_store, meta, guard
        self.reviewer, self.on_accept = reviewer, on_accept
        self.stage, self.rejections, self.accepted = "draft", 0, False
        self.draft: dict | None = None
        self.last: dict | None = None  # 最後一次交的修正稿
        self.review: dict | None = None
        self.reviews_triggered = 0
        self.defer_fix = False  # 實驗 shortfix：True＝待修清單不回給這個 session，存進 fix_handoff 交給新 session
        self.fix_handoff: dict | None = None

    def _check(self, rep: dict) -> list[str]:
        return check_report(rep, evidence_ids=set(self.ctx.store.ids()), experience_ids={e["id"] for e in self.store.load()})

    def submit(self, rep: dict) -> dict:
        if self.accepted:
            return {"ok": True, "status": "already_accepted", "message": "報告已接受，請直接結束。"}
        errors = self._check(rep)
        self.ctx.append_jsonl(self.ctx.run_dir / "report_submissions.jsonl", {"stage": self.stage, "errors": errors, "report": rep})
        if self.stage == "draft":
            return self._run_review(rep, errors)
        self.stage, self.last = "final", rep
        if self.guard is not None:
            self.guard.phase = "final"  # 交出修正稿後不能再補查；之後的退回只改格式
        if errors and self.rejections < MAX_REJECTIONS:
            self.rejections += 1
            return {"ok": False, "status": "rejected", "rejections": self.rejections, "errors": errors,
                    "message": "只修正這些格式問題後再交（不能再補查；查不到的改成 inference 或移到 unknowns）。下一次會照收，沒過的項目列進第 5 段。"}
        return self.finalize(rep, errors, revised=True)

    def _run_review(self, rep: dict, errors: list[str]) -> dict:
        from .review import build_input
        self.draft, self.stage = rep, "revise"
        (self.ctx.run_dir / "report_draft.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        self.reviews_triggered += 1
        started = time.time()
        try:
            review = self.reviewer(self.ctx, build_input(self.ctx, rep)) if self.reviewer else {"status": "skipped"}
        except Exception as error:  # 審查失敗不擋流程，程式警告照樣進待修清單
            review = {"status": "failed", "error": f"{type(error).__name__}: {error}"}
        items = [{"source": "審查", **i} for i in review.get("items") or []]
        items += program_findings(rep, self.ctx)
        items += [{"source": "程式", "sentence": "格式", "problem": e, "evidence_ids": [], "needs_evidence": False}
                  for e in errors]
        for n, item in enumerate(items, 1):
            item["id"] = f"R{n}"
        self.review = {"status": review.get("status"), "items": items,
                       "cost": {"api_calls": review.get("api_calls"), "tokens": review.get("tokens"),
                                "elapsed_s": review.get("elapsed_s", round(time.time() - started, 1))},
                       "tools_offered": review.get("tools_offered"), "error": review.get("error"),
                       "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        (self.ctx.run_dir / "review.json").write_text(json.dumps(self.review, ensure_ascii=False, indent=2), encoding="utf-8")
        out = {"ok": False, "status": "review", "fix_list": items, "message": REVISE_MESSAGE}
        if self.guard is not None:
            self.guard.phase = "revise"
            out["time_used"] = self.guard.time_used()  # 只陳述時間事實（決策 #59）
        if self.defer_fix:
            self.fix_handoff = out
            return {"ok": True, "status": "review_deferred", "message": DEFERRED_MESSAGE}
        return out

    def finalize(self, rep: dict, errors: list[str], *, revised: bool) -> dict:
        self.accepted = True
        if self.guard is not None:
            self.guard.phase = "final"
        marks = external_only(rep, self.ctx)
        full_meta = {**self.meta, "unresolved_issues": errors, "rejections": self.rejections, "revised": revised,
                     "review_items": len((self.review or {}).get("items") or []), "marks": marks}
        if not revised and self.review:
            full_meta["review_open"] = [f"{i['id']} {i['sentence']}：{i['problem']}" for i in self.review["items"]]
        md = render_markdown(rep, evidence={e["id"]: e for e in self.ctx.store.all()},
                             experience={e["id"]: e for e in self.store.load()}, meta=full_meta, marks=marks)
        # strategy：給凍結的 grader.py 讀的結論清單（＝第 2、3 段結論合併），不是另一段報告
        saved = {**rep, "strategy": claims_of(rep)}
        (self.ctx.run_dir / "report.json").write_text(json.dumps({"meta": full_meta, "report": saved, "markdown": md},
                                                                 ensure_ascii=False, indent=2), encoding="utf-8")
        (self.ctx.run_dir / "report.md").write_text(md, encoding="utf-8")
        if self.on_accept:
            self.on_accept()
        return {"ok": True, "status": "accepted_with_issues" if errors else "accepted", "unresolved_issues": errors,
                "message": ACCEPT_MESSAGE}

    def finalize_pending(self) -> bool:
        """沒交出被接受的報告就結束：交過修正稿（被格式退回）就收最後一次修正稿；只交過初稿就收初稿，待修清單列為未處理。"""
        if self.accepted or self.draft is None:
            return False
        if self.last is not None:
            self.finalize(self.last, self._check(self.last), revised=True)
        else:
            self.finalize(self.draft, self._check(self.draft), revised=False)
        return True


CLAIMS = {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, "text": {"type": "string"}, "kind": {"type": "string", "enum": ["fact", "inference"]},
    "evidence_ids": {"type": "array", "items": {"type": "string"}}, "limits": {"type": "string"}},
    "required": ["id", "text", "kind", "evidence_ids"]}}


def report_tool(flow: ReportFlow) -> Tool:
    params = {"type": "object", "properties": {
        "summary": {"type": "string"}, "onpage": CLAIMS, "offpage": CLAIMS,
        "actions": {"type": "array", "description": "優先行動（依先後）", "items": {"type": "object", "properties": {
            "action": {"type": "string"}, "rationale": {"type": "string"},
            "based_on": {"type": "array", "items": {"type": "string"}, "description": "依據的結論 id"}},
            "required": ["action", "rationale"]}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "experience": {"type": "object", "description": "選填：這次用了哪些經驗、哪些被這次的證據推翻", "properties": {
            "used": {"type": "array", "items": {"type": "string"}, "description": "只顯示在報告裡，不參與判定"},
            "overturned": {"type": "array", "items": {"type": "object", "properties": {
                "experience_id": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "why": {"type": "string"}}, "required": ["experience_id", "evidence_ids"]}}}}},
        "required": list(SECTIONS)}
    return Tool("submit_report",
                "交出研究報告。第 1 次交會由程式觸發 1 次獨立審查並退回待修清單，依清單修一次再交；第 2 次交只做格式檢查"
                "（引用的 Evidence ID 存在、fact 有證據、inference 有 limits），最多退回 1 次。",
                params, flow.submit)
