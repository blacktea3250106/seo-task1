"""經驗層（需求 2.3、2.4；補充三 ⑤⑥，決策 #35、#39、#41）。

- 每條經驗記一條「路線」：情況 → 路線（用哪些 Tool、怎麼查）→ 結果（照走／別走＋原因）＋ Evidence ID（G-10）。
- 兩個檔（G-11）：
  - experience/candidates.jsonl：只放通過寫入審核的條目；狀態只存在這裡（active 使用中／retired 已下架）。
  - experience/notes.md：Skill 的一部分，由程式依使用中條目重新產生，不手改。
- ⑧ 寫經驗：Opus 用 experience(action=propose) 寫情況、路線、結果並列出 Evidence ID；先存在這次 run 的
  experience_proposals.jsonl，不進經驗檔。路線 Tool 清單由程式從 Evidence ID 反查 Tool 呼叫紀錄（G-12），
  Opus 不自己填。研究結束時程式整理路線摘要（G-14），附在每條經驗旁，一起送寫入審核。
- 路線固定用箭頭模板（ROUTE_TEMPLATE）：每步一行「編號. Tool：做什麼，因為 為什麼」，2–4 步；格式不合
  propose 直接退回請 Opus 重寫，寫入審核第 1 項再檢查一次（format_problems）。每步寫「因為」，下次網站變了
  Opus 才判斷得出哪一步不適用，不會照抄。
- 不自動改 Tool：經驗只寫進 notes.md。永久刪除需人工 --confirm。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path

from . import ROOT
from .hermes_bridge import Tool

EXPERIENCE_DIR = ROOT / "experience"
DEFAULT_PATH = EXPERIENCE_DIR / "candidates.jsonl"
STATUSES = ("active", "retired")
STATUS_LABEL = {"active": "使用中", "retired": "已下架"}
RETIRED_REASONS = {"no_value": "沒用", "overturned": "錯誤", "judged_wrong": "判錯", "rejected": "你下 reject"}
RESULTS = ("照走", "別走")
AVOID_REASONS = ("查不到", "會誤導")
RESEARCH_TOOLS = ("polite_fetch", "sitemap_tree", "inspect_page", "text_match", "domain_info", "wayback", "web_search")
MAX_LEN = 300
MIN_STEPS, MAX_STEPS, MAX_STEP_LEN = 2, 4, 90
ROUTE_TEMPLATE = ("1. <Tool 名稱>：<做什麼>，因為 <為什麼>\n2. <Tool 名稱>：<做什麼>，因為 <為什麼>\n（2–4 步，一步一行）")
_STEP = re.compile(r"^\s*\d+\s*[.、．)）]\s*(.+?)\s*$")
_STRIP = re.compile(r"https?://\S+|(?:[\w-]+\.)+[a-z]{2,}(?:/\S*)?|/[\w./-]*|\bE-\d{4}\b|\bEXP-\d{3}\b|\bP\d+\b", re.I)


def _has_site_number(text: str) -> bool:
    """去掉網址、網域、路徑與編號後，還有 2 位數以上的數字＝網站上的數量或日期（屬於結論）。"""
    return bool(re.search(r"\d{2,}", _STRIP.sub(" ", text)))


def route_steps(route: str) -> tuple[list[str], list[str]]:
    """把路線切成步驟；回傳（步驟內容, 不是編號步驟的行）。"""
    steps, bad = [], []
    for line in (route or "").splitlines():
        if not line.strip():
            continue
        m = _STEP.match(line)
        (steps.append(m.group(1)) if m else bad.append(line.strip()))
    return steps, bad


def format_problems(p: dict) -> list[str]:
    """寫入審核第 1 項（方法不是結論）：只看格式，不比對關鍵字（決策 #50）。

    - situation：單段、≤300 字、不含網站上的數字。
    - route：照 ROUTE_TEMPLATE，2–4 步、一步一行；每步 ≤90 字、寫出 1 個研究 Tool、寫「因為」、不含網站上的數字。
    """
    out = []
    sit = (p.get("situation") or "").strip()
    if not sit:
        out.append("situation 空白")
    if "\n" in sit:
        out.append("situation 不是單段文字")
    if len(sit) > MAX_LEN:
        out.append(f"situation 超過 {MAX_LEN} 字")
    if _has_site_number(sit):
        out.append("situation 含網站上的數字")
    route = (p.get("route") or "").strip()
    if not route:
        return out + ["route 空白"]
    steps, bad = route_steps(route)
    if bad:
        out.append(f"route 每行要是編號步驟（{ROUTE_TEMPLATE.splitlines()[0]}）：「{bad[0][:20]}」")
    if not MIN_STEPS <= len(steps) <= MAX_STEPS:
        out.append(f"route 要 {MIN_STEPS}–{MAX_STEPS} 步，現在 {len(steps)} 步")
    for i, step in enumerate(steps, 1):
        if len(step) > MAX_STEP_LEN:
            out.append(f"route 第 {i} 步超過 {MAX_STEP_LEN} 字")
        if not any(t in step for t in RESEARCH_TOOLS):
            out.append(f"route 第 {i} 步沒寫用哪個 Tool")
        if "因為" not in step:
            out.append(f"route 第 {i} 步沒寫「因為」")
        if _has_site_number(step):
            out.append(f"route 第 {i} 步含網站上的數字")
    return out
_PATH_TOKEN = re.compile(r"(?<![\w.:/])/[^\s，。、；：:（）()「」『』\[\]【】<>\"']+")


def site_paths(ctx) -> set[str]:
    """這個 run 出現過的站內路徑（證據來源網址＋sitemap 目錄樹），每條路徑的每一層前綴都算，小寫、解碼。"""
    from urllib.parse import unquote, urlsplit
    domain = (getattr(ctx, "site_domain", None) or "").lower()
    urls = []
    for item in ctx.store.all():
        urls += [item.get("source") or "", (item.get("meta") or {}).get("final_url") or ""]
    db = ctx.run_dir / "sitemap.sqlite"
    if db.exists():
        import sqlite3
        con = sqlite3.connect(db)
        try:
            urls += [r[0] for r in con.execute("SELECT loc FROM urls")]
        except sqlite3.Error:
            pass
        finally:
            con.close()
    out: set[str] = set()
    for u in urls:
        if "://" not in u:
            continue
        parts = urlsplit(u)
        host = (parts.hostname or "").lower()
        if not domain or not (host == domain or host.endswith("." + domain)):
            continue
        segs = [x for x in unquote(parts.path).lower().split("/") if x]
        out |= {"/" + "/".join(segs[:i]) for i in range(1, len(segs) + 1)}
    return out


def site_problems(p: dict, domain: str | None, paths: set[str]) -> list[str]:
    """寫入審核第 7 項（決策 #59）：situation、route 含目標網域，或含這個 run 出現過的站內路徑 → 不收。
    只做字串比對：網域整段比對（不分大小寫）；路徑取文字裡以 / 開頭的片段，解碼後逐層比對站內路徑。"""
    from urllib.parse import unquote
    out = []
    for field in ("situation", "route"):
        text = (p.get(field) or "").lower()
        if domain and domain.lower() in text:
            out.append(f"{field} 含目標網域 {domain}")
        hits = set()
        for m in _PATH_TOKEN.findall(text):
            segs = [x for x in unquote(m).split("/") if x]
            hits |= {"/" + "/".join(segs[:i]) for i in range(1, len(segs) + 1)} & paths  # 片段的任一層前綴是站內路徑
        hits = sorted(hits, key=len)
        if hits:
            out.append(f"{field} 含站內路徑 {'、'.join(hits[:3])}")
    return out


PROPOSALS = "experience_proposals.jsonl"
ROUTE_SUMMARY = "route_summary.json"
NOT_RESEARCH = ("experience", "submit_report")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def entry_label(e: dict) -> str:
    """給 notes.md 與報告用的一行說明。"""
    result = e.get("result", "")
    if result == "別走" and e.get("avoid_reason"):
        result += f"（{e['avoid_reason']}" + (f"，正確查法見 {e['paired_id']}" if e.get("paired_id") else "") + "）"
    # 只顯示 Tool 名（去重）；網域、路徑留在 route_tools 給審核用，不顯示給研究 Agent（決策 #59）
    tools = "、".join(dict.fromkeys(t["tool"] for t in e.get("route_tools") or []))
    steps, bad = route_steps(e.get("route", ""))
    route = "\n".join(f"  {i}. {x}" for i, x in enumerate(steps, 1)) if steps and not bad else f"  {e.get('route', '')}"
    return (f"情況：{e.get('situation', '')}\n  路線：\n{route}" + (f"\n  （實際 Tool：{tools}）" if tools else "")
            + f"\n  結果：{result}")


class ExperienceStore:
    """candidates.jsonl（一行一條）＋ notes.md（每次存檔後重新產生）。"""

    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)
        self.notes_path = self.path.with_name("notes.md")
        self._lock = threading.Lock()

    def load(self) -> list[dict]:
        return _read_jsonl(self.path)

    def active(self) -> list[dict]:
        return [e for e in self.load() if e["status"] == "active"]

    def get(self, eid: str) -> dict | None:
        return next((e for e in self.load() if e["id"] == eid), None)

    def save_all(self, items: list[dict]) -> None:
        for e in items:
            if e["status"] not in STATUSES:
                raise ValueError(f"{e['id']} 狀態只能是 {STATUSES}")
            if (e["status"] == "retired") != bool(e.get("retired_reason")):
                raise ValueError(f"{e['id']}：retired 一定要有 retired_reason，active 一定沒有")
            if e.get("retired_reason") and e["retired_reason"] not in RETIRED_REASONS:
                raise ValueError(f"{e['id']}：retired_reason 只能是 {tuple(RETIRED_REASONS)}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in items), encoding="utf-8")
        tmp.replace(self.path)
        self.write_notes()

    def next_id(self, items: list[dict] | None = None) -> str:
        items = self.load() if items is None else items
        nums = [int(e["id"].split("-")[1]) for e in items if e["id"].startswith("EXP-")]
        return f"EXP-{max(nums, default=0) + 1:03d}"

    def notes_markdown(self) -> str:
        active = self.active()
        if not active:
            return "## 經驗筆記（使用中）\n（目前沒有使用中的經驗。）\n"
        lines = ["## 經驗筆記（使用中）",
                 "（每條是上次研究真的走過、有 Evidence ID 的路線；決定怎麼查時參考。照走：照路線查，但一定重新取證；"
                 "別走（查不到）：用同一 Tool、同一目標輕試 1 次，抓即時資料；別走（會誤導）：不重試。"
                 "照某條經驗查時，在那次 Tool 呼叫的 why 寫上經驗編號；這次證據推翻某條經驗時，寫在報告的 experience.overturned。）"]
        for e in sorted(active, key=lambda x: x["id"]):
            lines.append(f"- [{e['id']}｜{e.get('result', '')}] {entry_label(e)}")
        return "\n".join(lines) + "\n"

    def write_notes(self) -> str:
        text = self.notes_markdown()
        self.notes_path.parent.mkdir(parents=True, exist_ok=True)
        self.notes_path.write_text(text, encoding="utf-8")
        return text

    def notes_snapshot(self) -> dict:
        """這次 run 讀了哪個版本、哪些條目（G-21）。"""
        text = self.write_notes()
        return {"notes_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "entry_ids": [e["id"] for e in sorted(self.active(), key=lambda x: x["id"])], "text": text}

    def delete(self, eid: str, *, why: str) -> None:
        with self._lock:
            items = self.load()
            keep = [e for e in items if e["id"] != eid]
            if len(keep) == len(items):
                raise KeyError(f"沒有經驗 {eid}")
            self.save_all(keep)
        log = self.path.with_name("experience_deleted.jsonl")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": _now(), "id": eid, "by": "human", "why": why}, ensure_ascii=False) + "\n")


# ---- 下架（G-24～G-26、G-28）：只來自規則或使用者 reject，AI 不能自行下架 ----
def retire(items: list[dict], eid: str, reason: str, *, note: str = "", run_id: str | None = None) -> bool:
    """把使用中的條目改成已下架；已下架的不動。回傳是否有改。"""
    if reason not in RETIRED_REASONS:
        raise ValueError(f"retired_reason 只能是 {tuple(RETIRED_REASONS)}")
    for e in items:
        if e["id"] == eid and e["status"] == "active":
            e.update(status="retired", retired_reason=reason, retired_at=_now(), retired_note=note,
                     retired_run=run_id)
            return True
    return False


def cascade_pairs(items: list[dict], *, run_id: str | None = None) -> list[str]:
    """別走（會誤導）跟著配對的照走經驗下架：原因相同，備註「配對經驗已下架」（G-26）。"""
    by = {e["id"]: e for e in items}
    out = []
    for e in items:
        pair = by.get(e.get("paired_id") or "")
        if (e["status"] == "active" and e.get("result") == "別走" and e.get("avoid_reason") == "會誤導"
                and pair is not None and pair["status"] == "retired"):
            retire(items, e["id"], pair["retired_reason"], note=f"配對經驗已下架（{pair['id']}）", run_id=run_id)
            out.append(e["id"])
    return out


def reject(store: "ExperienceStore", eid: str, why: str) -> dict:
    """人工指令 reject：使用中 → 已下架（rejected）；已下架的只追加理由。理由寫進 human_feedback（G-28）。"""
    if not why.strip():
        raise ValueError("reject 要寫理由")
    items = store.load()
    e = next((x for x in items if x["id"] == eid), None)
    if e is None:
        raise KeyError(f"沒有經驗 {eid}")
    e.setdefault("human_feedback", []).append({"at": _now(), "action": "reject", "why": why})
    changed = retire(items, eid, "rejected", note="使用者 reject")
    followed = cascade_pairs(items)
    store.save_all(items)
    return {"id": eid, "retired": changed, "status": e["status"], "followed": followed}


# ---- G-12：路線 Tool 清單由程式從 Evidence ID 反查 ----
def route_tools(ctx, evidence_ids: list[str]) -> list[dict]:
    """查出產生這些 Evidence ID 的 Tool 呼叫（含衍生證據），整理成 Tool 名稱與目標（網域、路徑），依呼叫順序。"""
    wanted = set(evidence_ids or [])
    out: list[dict] = []
    for c in _read_jsonl(ctx.tool_calls_path):
        hit = [e for e in (c.get("evidence_id"), c.get("derived_evidence_id")) if e and e in wanted]
        if not hit or c.get("tool") in NOT_RESEARCH:
            continue
        target = c.get("target") or {}
        out.append({"tool": c["tool"], "domain": target.get("domain"), "path": target.get("path"), "evidence_ids": hit,
                    "call_n": c.get("n")})
    return out


# ---- G-14：路線摘要（Tool 呼叫紀錄，含每步的 why；決策 #71） ----
def build_route_summary(ctx) -> dict:
    calls = [c for c in _read_jsonl(ctx.tool_calls_path) if c.get("tool") not in NOT_RESEARCH]
    steps = [{"n": c.get("n"), "tool": c["tool"], "target": c.get("target"),
              "why": str((c.get("args") or {}).get("why") or ""),
              "evidence_ids": [e for e in (c.get("evidence_id"), c.get("derived_evidence_id")) if e],
              "ok": not c.get("error"), "light_test_of": c.get("light_test_of")} for c in calls]
    return {"at": _now(), "steps": steps}


def write_route_summary(ctx) -> dict:
    summary = build_route_summary(ctx)
    (ctx.run_dir / ROUTE_SUMMARY).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def route_summary_for(summary: dict, evidence_ids: list[str]) -> list[dict]:
    """附在單條經驗旁的路線摘要：只取產生這條經驗 Evidence ID 的那幾步。"""
    wanted = set(evidence_ids or [])
    return [st for st in summary.get("steps", []) if wanted & set(st["evidence_ids"])]


def load_proposals(ctx) -> list[dict]:
    return _read_jsonl(ctx.run_dir / PROPOSALS)


def proposals_for_audit(ctx) -> list[dict]:
    """⑧ 收尾：每條經驗附路線摘要，一起送寫入審核。"""
    path = ctx.run_dir / ROUTE_SUMMARY
    summary = json.loads(path.read_text(encoding="utf-8")) if path.exists() else write_route_summary(ctx)
    return [{**p, "route_summary": route_summary_for(summary, p.get("evidence_ids"))} for p in load_proposals(ctx)]


def propose(ctx, run_id: str, args: dict) -> dict:
    """⑧ 寫一條路線。只檢查欄位格式；內容由研究結束、評分出來後的寫入審核判斷。"""
    fields = {k: str(args.get(k) or "").strip() for k in ("situation", "route", "result", "avoid_reason", "paired_id")}
    if not fields["situation"] or not fields["route"]:
        raise ValueError("situation（情況）與 route（路線：用哪些 Tool、怎麼查）都要填")
    if problems := format_problems(fields) + site_problems(fields, getattr(ctx, "site_domain", None), site_paths(ctx)):
        raise ValueError("格式不合，請照模板重寫：" + "；".join(problems) + f"。route 模板：\n{ROUTE_TEMPLATE}")
    if fields["result"] not in RESULTS:
        raise ValueError(f"result 只能是 {RESULTS}")
    if fields["result"] == "別走":
        if fields["avoid_reason"] not in AVOID_REASONS:
            raise ValueError(f"別走要寫 avoid_reason，只能是 {AVOID_REASONS}")
        if fields["avoid_reason"] != "會誤導":
            fields["paired_id"] = ""
    else:
        fields["avoid_reason"] = fields["paired_id"] = ""
    ids = [str(e) for e in args.get("evidence_ids") or []]
    existing = load_proposals(ctx)
    item = {"id": f"P{len(existing) + 1}", "source_run": run_id, "at": _now(), **fields, "evidence_ids": ids,
            "route_tools": route_tools(ctx, ids)}
    ignored = sorted(k for k in args if k not in ("action", "situation", "route", "result", "avoid_reason", "paired_id",
                                                  "evidence_ids"))
    if ignored:
        item["ignored_fields"] = ignored  # 例如 Opus 自填的 Tool 清單：不採用
    ctx.append_jsonl(ctx.run_dir / PROPOSALS, item)
    return item


def experience_tool(store: ExperienceStore, run_id: str, ctx) -> Tool:
    def run(args: dict) -> dict:
        action = args.get("action")
        try:
            if action == "propose":
                item = propose(ctx, run_id, args)
                return {"ok": True, "id": item["id"], "status": "待審核", "route_tools": item["route_tools"],
                        "message": "已記下；研究結束、評分出來後由程式做寫入審核，通過才變使用中。"}
            if action == "list":
                return {"ok": True, "items": [{"id": e["id"], "result": e.get("result"), "text": entry_label(e)}
                                              for e in store.active()]}
            if action in ("disable", "retire", "approve", "formal", "activate", "delete", "reject"):
                ctx.append_jsonl(ctx.run_dir / "approvals_pending.jsonl",
                                 {"at": _now(), "action": f"experience.{action}", "id": args.get("id"),
                                  "status": "blocked_pending_human"})
                return {"ok": False, "error": {"code": "not_allowed",
                                               "detail": "AI 不能自行下架或刪除經驗；經驗錯了請在報告的 experience.overturned 附 Evidence ID 推翻。"}}
            return {"ok": False, "error": {"code": "bad_args", "detail": f"未知 action {action}"}}
        except (ValueError, KeyError) as error:
            return {"ok": False, "error": {"code": "rejected", "detail": str(error)}}

    return Tool("experience",
                "⑧ 寫經驗（交卷動作，不能查資料）。action=propose：寫一條這次真的走過的路線——situation 情況（一段，看到什麼現象）、"
                "route 路線（照模板，一步一行、2–4 步：「1. <Tool 名稱>：<做什麼>，因為 <為什麼>」；需要核對的步驟直接寫進路線；"
                "格式不合會退回重寫）、result 照走／別走、"
                "avoid_reason 別走原因（查不到／會誤導）、paired_id（會誤導時寫：正確查法的照走經驗編號）、"
                "evidence_ids 這條路線用到的 Evidence ID。路線上的 Tool 清單由程式從 Evidence ID 反查，不用自己填。"
                "只寫方法，不寫網站上的數字；不寫網址、網域、路徑，要寫換個網站也能用的方法。action=list：列出使用中經驗。",
                {"type": "object", "properties": {
                    "action": {"type": "string", "enum": ["propose", "list"]},
                    "situation": {"type": "string"}, "route": {"type": "string"},
                    "result": {"type": "string", "enum": list(RESULTS)},
                    "avoid_reason": {"type": "string", "enum": list(AVOID_REASONS)},
                    "paired_id": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}}},
                 "required": ["action"]}, run)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m seo_agent.experience", description="人工管理經驗")
    ap.add_argument("--store", type=Path, default=DEFAULT_PATH)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("reject", help="下架一條經驗（理由寫進 human_feedback）")
    r.add_argument("id")
    r.add_argument("why", help="理由")
    p = sub.add_parser("delete", help="永久刪除（需 --confirm）")
    p.add_argument("id")
    p.add_argument("--why", required=True)
    p.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)
    store = ExperienceStore(args.store)
    try:
        if args.cmd == "list":
            for e in store.load():
                reason = f"（{RETIRED_REASONS[e['retired_reason']]}）" if e.get("retired_reason") else ""
                print(f"{e['id']}\t{STATUS_LABEL[e['status']]}{reason}\t{entry_label(e)}")
        elif args.cmd == "reject":
            out = reject(store, args.id, args.why)
            msg = "已下架（你下 reject）" if out["retired"] else "原本就已下架，只追加理由"
            print(f"{args.id} {msg}" + (f"；配對跟著下架：{'、'.join(out['followed'])}" if out["followed"] else ""))
        elif args.cmd == "delete":
            if not args.confirm:
                print("永久刪除需要加 --confirm", file=sys.stderr)
                return 2
            store.delete(args.id, why=args.why)
            print(f"{args.id} 已永久刪除（紀錄在 experience_deleted.jsonl）")
    except (ValueError, KeyError) as error:
        print(f"拒絕：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
