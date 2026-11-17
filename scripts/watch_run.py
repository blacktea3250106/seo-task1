"""Demo 用的進度畫面：只讀 run 資料夾裡的紀錄檔，把研究過程畫成終端機畫面。

不改研究流程、不寫入 run 資料夾。上方固定：流程燈號、時間條、跑分；下方逐行顯示 AI 正在查什麼、為什麼查（why）。

  即時：uv run python scripts/watch_run.py <run_dir>             （研究跑的同時開另一個終端機）
  重播：uv run python scripts/watch_run.py <run_dir> --replay 20   （照原本時間軸 20 倍速重播）
  純文字：uv run python scripts/watch_run.py <run_dir> --plain      （一次印完，不用即時畫面）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

# 配色只用 紅（失敗）、白（內容；dim＝次要）、綠（完成）、黃（進行中／需要注意）
# 符號只用 ✓ ✗ ● ○ ? 和半形數字：①②、⏺、⎿ 這類字元在終端機寬度不一，會和後面的字疊在一起
STAGES = ["接案", "網站底稿", "研究", "初稿", "審查", "定稿", "經驗"]
HINT = {"接案": "讀任務和使用中的經驗", "網站底稿": "程式先抓 robots、sitemap、Wayback、首頁選單、WHOIS",
        "研究": "AI 自己決定查什麼、查多深；每行後面是它寫的理由",
        "初稿": "AI 交出初稿", "審查": "Reviewer Agent（沒有 Tool）只看報告和證據挑錯",
        "定稿": "AI 依審查意見補查、改寫", "經驗": "AI 寫下這次的查法，給下一次參考"}
VERB = {"inspect_page": "讀網頁", "sitemap_tree": "查 sitemap", "wayback": "查 Wayback", "polite_fetch": "抓網頁",
        "text_match": "數關鍵字", "domain_info": "查網域註冊", "web_search": "搜尋", "experience": "讀經驗"}
ERR = {"robots_disallowed": "robots.txt 不允許，不抓", "rejected": "格式不合被退回", "site_throttled": "網站限速，稍後再試"}
BLOCKED = "被擋（人機驗證或非 200），不繞過，記成未知"


def _ts(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return datetime.fromisoformat(str(v)).timestamp()


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # 即時模式下最後一行可能還沒寫完
    return out


def _json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _short(s: str, n: int = 70) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _fit(t: Text, width: int) -> Text:
    """依終端機格數裁切（中文一字兩格），超出加「…」，不折行。"""
    t = t.copy()
    t.truncate(max(10, width - 1), overflow="ellipsis")
    return t


def _mmss(s: float) -> str:
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def _where(url: str, site: str) -> str:
    """網址縮成外行人看得懂的位置：同站只留路徑，Wayback 存檔寫成年月。"""
    url = unquote(url or "")
    m = re.search(r"web\.archive\.org/web/(\d{6})\d*[^/]*/(.+)", url)
    if m:
        return f"{m.group(1)[:4]}-{m.group(1)[4:6]} 的舊存檔 {_where(m.group(2), site)}"
    u = urlparse(url)
    if not u.netloc:
        return url
    host = u.netloc.removeprefix("www.")
    return (u.path or "/") if host == site else host + (u.path if u.path not in ("", "/") else "")


def _target(a: dict, evid: dict, site: str) -> str:
    if a.get("url"):
        return _where(a["url"], site)
    if a.get("evidence_id"):
        return _where((evid.get(a["evidence_id"]) or {}).get("source", ""), site)
    if a.get("query"):
        return f"「{a['query']}」"
    if a.get("keywords"):
        return "「" + " / ".join(map(str, a["keywords"][:3])) + "」"
    if a.get("section"):
        return str(a["section"])
    return str(a.get("domain") or "")


def summarize(run: Path, eid: str | None) -> str:
    """把 Tool 的整理結果（衍生證據）縮成一句；沒有可讀的摘要就回空字串。"""
    d = _json(run / "raw" / f"{eid}.json") if eid else {}
    if not isinstance(d, dict) or not d:
        return ""
    if d.get("headings") is not None:
        h1 = [h["text"] for h in d["headings"] if h.get("level") == 1]
        return f"標題：{' / '.join(h1)}" if h1 else "沒有主標題"
    if isinstance(d.get("results"), dict):
        return " · ".join(f"{k} {((v.get('all_text') or v.get('text') or {}).get('exact', 0))} 次"
                          for k, v in d["results"].items())
    if d.get("distinct_urls") is not None:
        return f"{d['distinct_urls']} 個網址，分 {d.get('sections_total', '?')} 區"
    if d.get("matches") is not None:
        return f"找到 {d['matches']} 筆"
    if isinstance(d.get("months"), dict):
        return " · ".join(f"{m} {n} 筆" for m, n in list(d["months"].items())[:4])
    if isinstance(d.get("urls"), list):
        return f"{d.get('count', len(d['urls']))} 個舊網址"
    if isinstance(d.get("checks"), list):
        return f"{len(d['checks'])} 個舊網址查現況"
    if d.get("rdap") is not None:
        r = d["rdap"] if isinstance(d["rdap"], dict) else {}
        dates = r.get("events") or r.get("dates") or {}
        reg = next((str(v)[:10] for k, v in dates.items() if "regist" in k), "") if isinstance(dates, dict) else ""
        return f"註冊日 {reg}" if reg else "已查註冊資料"
    if d.get("total") is not None:
        return f"共 {d['total']} 筆"
    return ""


def review_outcomes(run: Path) -> dict[str, int]:
    """review_outcomes.md 的「程式判定」欄計數；沒有檔案回空。"""
    p = run / "review_outcomes.md"
    out: dict[str, int] = {}
    for line in (p.read_text(encoding="utf-8").splitlines() if p.exists() else []):
        cols = [c.strip() for c in line.split("|")]
        if len(cols) > 5 and re.fullmatch(r"R\d+", cols[1]):
            out[cols[5]] = out.get(cols[5], 0) + 1
    return out


def _model_id() -> str:
    """研究還沒寫 result.json 時，用和研究程序相同的設定（.env＋環境變數 SEO_MODEL_ID）。"""
    try:
        from seo_agent.model_env import load_model_settings
        return load_model_settings().model
    except Exception:  # 沒有 .env 或金鑰時（例如只是重播）不影響畫面
        return "?"


def load_events(run: Path) -> tuple[dict, list[dict]]:
    """把各紀錄檔整理成依時間排序的事件。"""
    msg = (run / "message.md").read_text(encoding="utf-8") if (run / "message.md").exists() else ""
    kw = re.findall(r"\[([^\]]+)\]", msg.splitlines()[1]) if msg.count("\n") >= 1 else []
    job, result, card = _json(run / "job.json"), _json(run / "result.json"), _json(run / "data_card.json")
    kw = kw or job.get("payload", {}).get("keywords") or ["娛樂城", "3A娛樂城"]  # Hermes 實跑沒有 message.md；預設同 research.py
    calls = _jsonl(run / "tool_calls.jsonl")
    evid = {e["id"]: e for e in _jsonl(run / "evidence.jsonl")}
    subs = _jsonl(run / "report_submissions.jsonl")
    props = _jsonl(run / "experience_proposals.jsonl")
    review = _json(run / "review.json")
    start = result.get("started_at") or (calls[0]["at"] if calls else (run / "job.json").stat().st_mtime)
    p = job.get("payload", {})
    site = str(card.get("domain") or "?").removeprefix("www.")
    info = {"site": site, "keywords": kw, "model": result.get("model") or job.get("model") or _model_id(),
            "limit_s": float(p.get("total_minutes", 120)) * 60, "start": start, "simulated": job.get("simulated"),
            "result": result,
            "review": {i.get("id"): i.get("problem", "") for i in (_json(run / "review.json").get("items") or [])}}
    ev: list[dict] = []
    read = (result.get("experience_read") or {}).get("entry_ids")
    ev.append({"t": start, "kind": "start", "exp": read})
    ev.append({"t": start, "kind": "baseline", "sources": card.get("sources", {})})
    n_sub = n_exp = 0
    for c in calls:
        t, a, tool = c["at"], c.get("args") or {}, c["tool"]
        base = {"t": t, "ok": c.get("ok")}
        if tool == "submit_report":
            sub = subs[n_sub] if n_sub < len(subs) else {}
            n_sub += 1
            ev.append(base | {"kind": "report", "stage": sub.get("stage"),
                              "errors": sub.get("errors") or ([c["error"]] if c.get("error") else [])})
        elif tool == "experience" and a.get("action", "propose") != "list":
            ok = c.get("ok")
            pr = (props[n_exp] if n_exp < len(props) else {}) if ok else {}  # 被退回的提案不會寫進檔案
            n_exp += bool(ok)
            ev.append(base | {"kind": "experience", "err": ERR.get(c.get("error"), c.get("error")),
                              "text": pr.get("situation") or a.get("situation") or a.get("text", ""),
                              "result": pr.get("result") or a.get("result", "")})
        else:
            ev.append(base | {"kind": "tool", "verb": VERB.get(tool, tool), "why": a.get("why", ""),
                              "where": _target(a, evid, site), "err": ERR.get(c.get("error"), BLOCKED),
                              "got": summarize(run, c.get("derived_evidence_id")),
                              "eid": (c.get("derived_evidence_id") or c.get("evidence_id")) if c.get("ok") else None})
    for e in evid.values():
        ev.append({"t": _ts(e["at"]) if e.get("at") else start, "kind": "evidence"})
    if review.get("at"):
        items = review.get("items") or []
        ev.append({"t": _ts(review["at"]), "kind": "review", "n": len(items),
                   "first": [_short(i.get("problem", ""), 70) for i in items[:2]]})
    if result.get("status"):
        ev.append({"t": start + float(result.get("elapsed_s") or 0), "kind": "end", "r": result})
    ev.sort(key=lambda e: e["t"])
    return info, ev


class View:
    def __init__(self, info: dict, run: Path):
        self.info, self.run = info, run
        self.cur = -1  # 目前站的位置；同一時間只亮一個燈
        self.lines: list[Text] = []
        self.cur_why = ""
        self.answered: set[str] = set()
        self.actions = self.evidence = self.blocked = 0
        self.review_n: int | None = None
        self.finished = False
        self.end: dict = {}

    def add(self, *parts, indent=2):
        t = Text(" " * indent)
        for p in parts:
            t.append(*p) if isinstance(p, tuple) else t.append(p)
        last = self.lines[-1].plain.split("  ×")[0] if self.lines else None
        if t.plain and t.plain == last:  # 連續做同一件事合成一行
            prev = self.lines[-1].plain
            n = int(prev.split("  ×")[1]) + 1 if "  ×" in prev else 2
            t.append(f"  ×{n}", "dim")
            self.lines[-1] = t
            return
        self.lines.append(t)

    def go(self, stage: str):
        i = STAGES.index(stage)
        if i <= self.cur:
            return
        self.cur = i
        if self.lines:
            self.add("", indent=0)
        self.add((f"{i + 1} {stage}", "bold"), (f"  {HINT[stage]}", "dim"), indent=0)

    def apply(self, e: dict):
        k = e["kind"]
        if k == "evidence":
            self.evidence += 1
            return
        if k == "tool" and self.cur < STAGES.index("研究"):
            self.go("研究")
        if k in ("tool", "report", "experience"):
            self.actions += 1
        if k == "start":
            self.go("接案")
            n = len(e["exp"]) if e["exp"] is not None else "?"
            self.add((f"讀到 {n} 條經驗 · 只讀網站、不改任何東西 · 時間上限 {int(self.info['limit_s'] // 60)} 分鐘", "dim"))
        elif k == "baseline":
            self.go("網站底稿")
            for v in e["sources"].values():
                good = v.get("status") == "成功"
                extra = {"robots＋全部 sitemap": f"{v.get('distinct_urls', '')} 個網址",
                         "Wayback": f"{v.get('earliest', '')} 起 {v.get('snapshots', '')} 筆存檔",
                         "首頁選單": f"{v.get('menu_links', '')} 個連結"}.get(v.get("label"), "")
                self.add(("✓ " if good else "✗ ", "green" if good else "red"), v.get("label", ""),
                         (f"  {extra if good else '人機驗證，不繞過，記成未知'}", "dim" if good else "red"))
        elif k == "tool":
            self.cur_why = e["why"]
            where = (f"  {_short(e['where'], 40)}", "white") if e["where"] else ""
            if e["ok"]:
                got = (f"  → {_short(e['got'], 50)}", "dim") if e["got"] else ""
                eid = (f"  {e['eid']}", "dim") if e.get("eid") else ""
                self.add(("✓ ", "green"), (e["verb"], "bold"), where, got, eid)
            else:
                self.blocked += 1
                self.add(("✗ ", "red"), (e["verb"], "bold"), where, (f"  → {_short(e['err'], 40)}", "red"))
            rid = re.match(r"(R\d+)", e["why"] or "")
            if STAGES[self.cur] == "定稿" and rid and self.info["review"].get(rid.group(1)) \
                    and rid.group(1) not in self.answered:  # 同一條審查意見只顯示一次
                self.answered.add(rid.group(1))
                self.add((f"回應審查 {rid.group(1)}：{_short(self.info['review'][rid.group(1)], 70)}", "yellow"), indent=4)
            if e["why"]:
                self.add((f"為什麼：{_short(e['why'], 80)}", "dim"), indent=4)
        elif k == "report":
            if e.get("stage") == "draft" and not e["errors"]:
                self.go("初稿")
                self.add(("✓ ", "green"), "初稿交出，送去審查")
                self.go("審查")
            elif e["ok"]:
                self.go("定稿")
                self.add(("✓ 定稿通過格式檢查", "bold green"))
                done = review_outcomes(self.run)
                if done:
                    self.add((f"審查 {sum(done.values())} 項 → " + "、".join(f"{k} {v}" for k, v in done.items()), "white"))
            else:
                self.add(("✗ ", "red"), (f"報告被程式退回：{_short('；'.join(map(str, e['errors'])), 60)}", "red"))
        elif k == "review":
            self.go("審查")
            self.review_n = e["n"]
            self.add(("! ", "yellow"), (f"挑出 {e['n']} 個要修的地方", "yellow"), ("，例如：", "dim"))
            for p in e["first"]:
                self.add((f"- {p}", "dim"), indent=4)
            self.go("定稿")
        elif k == "experience":
            self.go("經驗")
            if e.get("err") or not e.get("ok"):
                self.add(("✗ ", "red"), (f"一條經驗{e.get('err') or '被退回'}，AI 重寫", "red"))
                return
            col = "green" if e["result"] == "照走" else "yellow"
            self.add(("+ ", "white"), (f"[{e['result'] or '?'}] ", col), _short(e["text"], 90))
        elif k == "end":
            audit = _json(self.run / "experience_audit.json").get("results") or []
            if audit:
                self.go("經驗")
                self.add(("寫入審核（程式，7 條規則）", "bold"))
                for a in audit:
                    ok = a.get("passed")
                    self.add(("✓ " if ok else "✗ ", "green" if ok else "red"), a.get("proposal_id", "?"),
                             (f"  通過 → {a.get('experience_id')}，下一輪開始就會讀到" if ok
                              else f"  退回：{'、'.join(map(str, a.get('failed') or []))}", "green" if ok else "red"))
            acts = (_json(self.run / "report.json").get("report") or {}).get("actions") or []
            if acts:
                self.add("", indent=0)
                self.add(("行動建議（報告前 3 條）", "bold"), indent=0)
                for n, a in enumerate(acts[:3], 1):
                    self.add(f"{n}. {_short(a.get('action', ''), 90)}")
            r = self.end = e["r"]
            self.finished = True
            self.cur = len(STAGES)
            ok = r.get("status") == "passed"
            self.add("", indent=0)
            self.add(("✓ 完成" if ok else f"✗ {r.get('status_label') or r.get('status')}", "bold green" if ok else "bold red"),
                     (f"  {_mmss(float(r.get('elapsed_s') or 0))}", "dim"), indent=0)
            for name, label in (("report.md", "報告"), ("board.json", "看板"), ("experience_proposals.jsonl", "經驗")):
                if (self.run / name).exists():
                    self.add((f"{label}  ", "dim"), (os.path.relpath(self.run / name), "underline"))  # 相對路徑較短，VS Code 可直接點開
            self.add(("評分在跑完後另外做：Grader Agent 盲評可信 SEO 技術數；經驗要先過寫入審核，下一輪才會用到", "dim"))

    def header(self, now: float, replay: float | None, tick: float, width: int) -> Group:
        i, blink = self.info, int(tick * 2) % 2 == 0
        top = Text()
        top.append("seo-agent", "bold")
        top.append(f"   {i['site']} · {' / '.join(i['keywords'])} · {i['model']}", "dim")
        if i.get("simulated"):
            top.append(" · sim", "dim")
        else:
            top.append(" · Hermes", "bold white")
        if replay:
            top.append(f" · 重播 ×{replay:g}", "yellow")

        flow = Text()
        for n, s in enumerate(STAGES):
            if n < self.cur:
                flow.append(f"✓ {n + 1} {s}", "green")
            elif n == self.cur:
                flow.append(f"● {n + 1} {s}", "bold yellow" if blink else "bold white")
            else:
                flow.append(f"○ {n + 1} {s}", "dim")
            if n < len(STAGES) - 1:
                flow.append(" ── ", "green" if n < self.cur else "dim")

        el = min(now - i["start"], i["limit_s"])
        if self.finished and self.end.get("elapsed_s"):
            el = float(self.end["elapsed_s"])
        rows = _bar(el / i["limit_s"], f"{_mmss(el)} / {_mmss(i['limit_s'])}")
        rows.append("\n跑分   ", "dim")
        score = [f"動作 {self.actions}", f"證據 {self.evidence}", f"被擋 {self.blocked}"]
        if self.review_n is not None:
            score.append(f"審查挑錯 {self.review_n}")
        tok = (self.end.get("tokens") or {}).get("total")
        if tok:
            score.append(f"token {tok / 1e6:.1f}M")
        rows.append(" · ".join(score), "white")

        now_t = Text()
        if self.finished:
            now_t.append("✓ 跑完了，報告位置在最下面", "bold green")
        else:
            now_t.append("● ", "bold yellow" if blink else "bold white")
            stage = STAGES[max(self.cur, 0)]
            now_t.append(stage, "bold")
            if stage in ("研究", "定稿") and self.cur_why:
                now_t.append(f"  {_short(self.cur_why, 70)}", "white")
            else:
                now_t.append(f"  {HINT[stage]}", "dim")
        return Group(_fit(top, width), Text(""), _fit(flow, width), Text(""), rows, Text(""), _fit(now_t, width),
                     Text("─" * (width - 1), "dim"))

    def frame(self, now: float, replay: float | None, tick: float, width: int, height: int) -> Group:
        room = max(3, height - 10)
        return Group(self.header(now, replay, tick, width), *(_fit(t, width) for t in self.lines[-room:]))


def _bar(frac: float, right: str, width: int = 40) -> Text:
    frac = max(0.0, min(1.0, frac))
    full = int(round(frac * width))
    t = Text("時間   ", "dim")
    t.append("━" * full, "white")
    t.append("─" * (width - full), "dim")
    t.append(f"  {right}", "white")
    return t


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--replay", type=float, metavar="倍速", help="照原本時間軸重播，例如 20")
    ap.add_argument("--plain", action="store_true", help="一次印完全部，不用即時畫面")
    a = ap.parse_args()
    run, con = a.run_dir, Console()
    if a.plain:
        info, events = load_events(run)
        v = View(info, run)
        for e in events:
            v.apply(e)
        con.print(v.header(events[-1]["t"], a.replay, 0, con.width))
        for line in v.lines:
            con.print(_fit(line, con.width))
        return
    t0 = time.time()
    info, events = load_events(run)
    with Live(console=con, screen=True, auto_refresh=False) as live:
        while True:
            if not a.replay:
                info, events = load_events(run)
            tick = time.time()
            now = info["start"] + (tick - t0) * a.replay if a.replay else tick
            v = View(info, run)
            for e in events:
                if e["t"] <= now:
                    v.apply(e)
            live.update(v.frame(now, a.replay, tick, con.width, con.size.height), refresh=True)
            if v.finished:
                time.sleep(3)
                break
            time.sleep(0.25)
    con.print(v.header(now, a.replay, 0, con.width))
    for line in v.lines[-12:]:
        con.print(_fit(line, con.width))


if __name__ == "__main__":
    main()
