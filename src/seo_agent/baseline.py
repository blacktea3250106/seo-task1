"""網站底稿（② 程式準備，補充三 ①；決策 #46、#50；G-50–G-54）。

- 底稿放專案內 `baselines/<網域>/`，用網域當鍵：baseline.json（每個來源的結果、抓取時間、hash、失敗原因）、
  evidence.jsonl＋raw/（原檔）。
- 有底稿就直接讀、不重抓；上次失敗的來源只重抓那幾個；沒有就跑固定偵察；`refresh=True` 整份重抓。
- 固定偵察 6 個來源（約 10–20 次請求），由程式直接呼叫現有 Tool 的函式（Tool 仍是 8 個）：
  robots＋全部 sitemap、首頁選單（inspect_page 的連結位置）、WHOIS（domain_info）、Wayback、關鍵字搜尋 ×2。
- 程式只抓、不判讀：資料卡只把各來源的數字並排（分區、日期範圍、數量），不標哪裡對不上（決策 #43）。
- 匯入這次 run 的證據庫時，每筆標「快照＋抓取時間＋底稿 hash」，Evidence ID 照常可追回原檔（G-51）。
- ④ 的 Tool 一律抓即時資料，不讀底稿（G-54）：sitemap.sqlite 不複製進 run。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import ROOT
from .stop import derived_body, derived_source
from .tools.context import Context

BASELINE_ROOT = ROOT / "baselines"
SOURCES = ("sitemap", "home_menu", "whois", "wayback", "search_1", "search_2")
LABELS = {"sitemap": "robots＋全部 sitemap", "home_menu": "首頁選單", "whois": "WHOIS／RDAP", "wayback": "Wayback",
          "search_1": "關鍵字搜尋 1", "search_2": "關鍵字搜尋 2"}


def domain_key(site: str) -> str:
    host = (urlsplit(site if "://" in site else "https://" + site).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _calls(site: str, keywords: list[str]) -> dict:
    """每個來源要呼叫的 Tool 與參數（程式固定，不判讀）。"""
    origin = f"https://{domain_key(site)}"
    kw = list(keywords) + ["", ""]
    return {"sitemap": ("sitemap_tree", {"action": "build", "site": origin, "detail": "full"}),
            "home_menu": ("inspect_page", {"url": origin + "/", "part": "links", "max_links": 500}),
            "whois": ("domain_info", {"domain": domain_key(site)}),
            "wayback": ("wayback", {"action": "timeline", "url": domain_key(site)}),
            "search_1": ("web_search", {"query": kw[0]}),
            "search_2": ("web_search", {"query": kw[1]})}


class Baseline:
    def __init__(self, site: str, *, root: Path = BASELINE_ROOT):
        self.site, self.domain = site, domain_key(site)
        self.dir = Path(root) / self.domain
        self.path = self.dir / "baseline.json"

    def load(self) -> dict | None:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else None

    def save(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")  # 同時跑多個 run 時各寫各的暫存檔，避免互相搬走
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def ensure(self, keywords: list[str], *, refresh: bool = False, transport=None, delay_s: float = 1.5,
               sleep=time.sleep) -> dict:
        """回傳底稿；需要時跑固定偵察（全部或只補失敗的來源）。"""
        if refresh and self.dir.exists():
            shutil.rmtree(self.dir)  # 只刪程式自己產生的這個網域底稿資料夾
        data = self.load() or {"domain": self.domain, "site": self.site, "keywords": list(keywords), "sources": {}}
        todo = [s for s in SOURCES if not (data["sources"].get(s) or {}).get("ok")]
        if not todo:
            data["action"] = "reused"
            return data
        ctx = Context(self.dir, transport=transport, delay_s=delay_s, sleep=sleep)
        try:
            from .tools import build_tools
            tools = {t.name: t for t in build_tools(ctx)}
            calls = _calls(self.site, keywords)
            for name in todo:
                tool, args = calls[name]
                if name == "sitemap":
                    (self.dir / "sitemap.sqlite").unlink(missing_ok=True)
                before = len(ctx.store.ids())
                try:
                    result = tools[tool].func(args)
                except Exception as error:  # 來源失敗逐項記下，不擋其他來源
                    result = {"ok": False, "error": {"code": "exception", "detail": f"{type(error).__name__}: {error}"}}
                ok = bool(isinstance(result, dict) and result.get("ok"))
                raw_ids = ctx.store.ids()[before:]
                derived_id = None
                if ok:
                    body, _, fingerprint = derived_body(tool, args, result)
                    if name == "sitemap":  # 存檔用完整版；指紋用模型在 run 裡會拿到的精簡版算，重做同一次 build 才比得到底稿
                        from .tools.sitemap import _brief
                        fingerprint = derived_body(tool, {k: v for k, v in args.items() if k != "detail"}, _brief(result))[2]
                    derived_id = ctx.store.add(body, source=derived_source(tool, args), tool=tool, kind="derived",
                                               suffix=".json", meta={"fingerprint": fingerprint})["id"]
                ids = raw_ids + ([derived_id] if derived_id else [])
                shas = [ctx.store.get(i)["sha256"] for i in ids]
                data["sources"][name] = {
                    "label": LABELS[name], "tool": tool, "args": args, "ok": ok, "fetched_at": _now(),
                    "evidence_ids": ids, "derived_evidence_id": derived_id,
                    "sha256": hashlib.sha256("".join(shas).encode()).hexdigest(),
                    "result": result if ok else None,
                    "error": None if ok else (result.get("error") or {"code": result.get("status", "failed"),
                                                                        "detail": result.get("message")})}
        finally:
            ctx.close()
        data["updated_at"] = _now()
        data["baseline_hash"] = hashlib.sha256(json.dumps(
            {s: (data["sources"].get(s) or {}).get("sha256") for s in SOURCES}, sort_keys=True).encode()).hexdigest()
        data["action"] = "built" if len(todo) == len(SOURCES) else "refetched_failed"
        data["refetched"] = todo
        self.save(data)
        return data


def import_into_run(ctx: Context, baseline: dict, *, root: Path = BASELINE_ROOT) -> dict[str, str]:
    """把底稿原檔複製進這次 run 的證據庫（停止條件開始計算前）。回傳 {底稿編號: 這次 run 的 Evidence ID}。"""
    src_dir = Path(root) / baseline["domain"]
    index = {}
    if (src_dir / "evidence.jsonl").exists():
        for line in (src_dir / "evidence.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                index[item["id"]] = item
    mapping: dict[str, str] = {}
    for name in SOURCES:
        src = baseline["sources"].get(name) or {}
        for old in src.get("evidence_ids") or []:
            item = index.get(old)
            if not item or old in mapping:
                continue
            body = (src_dir / item["file"]).read_bytes()
            suffix = Path(item["file"]).suffix or ".bin"
            meta = {**(item.get("meta") or {}), "snapshot": True, "fetched_at": item["at"],
                    "baseline_hash": baseline["baseline_hash"], "baseline_id": old, "baseline_source": name}
            new = ctx.store.add(body, source=item["source"], tool=item["tool"], kind=item["kind"], suffix=suffix, meta=meta)
            mapping[old] = new["id"]
    return mapping


# ---- 資料卡（只並排數字，不標對不上）----
def _wayback_dates(raw: bytes) -> dict:
    """Wayback 日期由程式解析（G-53）：讀 CDX 原檔（不是 172 字元的包裝資料），回最早、最晚日期與各年數量。"""
    rows = json.loads(raw.decode("utf-8") or "[]")
    if not rows:
        return {"snapshots": 0}
    head, body = rows[0], rows[1:]
    stamps = sorted(r[head.index("timestamp")] for r in body)
    years: dict[str, int] = {}
    for ts in stamps:
        years[ts[:4]] = years.get(ts[:4], 0) + 1
    fmt = lambda ts: f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"  # noqa: E731
    return {"snapshots": len(stamps), "earliest": fmt(stamps[0]) if stamps else None,
            "latest": fmt(stamps[-1]) if stamps else None, "by_year": years}


def _menu(result: dict, domain: str) -> dict:
    links = [link for link in result.get("links") or [] if link.get("position") == "menu"]
    sections: dict[str, int] = {}
    for link in links:
        parts = urlsplit(link["url"])
        if domain_key(parts.netloc or domain) != domain:
            continue
        seg = [s for s in parts.path.split("/") if s]
        key = "/" + seg[0] + "/" if seg else "/"
        sections[key] = sections.get(key, 0) + 1
    return {"menu_links": len(links), "sections": sections}


# 每個 Evidence ID 是什麼檔（決策 #64）：只說明檔案種類與 HTTP 狀態，不判讀內容。
# 起因：資料卡只列一串編號，模型常拿第一個（其實是別站的 robots.txt）當成註冊日或 sitemap 數字的證據。
KIND_LABELS = {"derived": "Tool 整理結果（JSON）", "robots": "robots.txt（抓取許可，不是內容）", "sitemap": "sitemap 原檔",
               "page": "網頁原檔", "rdap": "RDAP 註冊資料", "rdap_bootstrap": "RDAP 查詢入口", "dns": "DNS 紀錄",
               "whois": "WHOIS 原文", "wayback_cdx": "Wayback 存檔清單", "wayback_snapshot": "Wayback 舊頁原檔",
               "search": "搜尋結果頁"}


def _evidence_kinds(ctx: Context, ids: list[str]) -> list[dict]:
    """把 Evidence ID 依種類分組；HTTP 狀態不是 200 的另外標出（例如 202 人機驗證頁）。"""
    groups: dict[str, list[str]] = {}
    for i in ids:
        item = ctx.store.get(i) or {}
        label = KIND_LABELS.get(item.get("kind"), item.get("kind") or "其他")
        status = (item.get("meta") or {}).get("status")
        if status not in (None, 200):
            label += f"，HTTP {status}"
        groups.setdefault(label, []).append(i)
    return [{"what": k, "ids": v} for k, v in groups.items()]


def _id_ranges(ids: list[str]) -> str:
    """連號縮寫：E-0003、E-0004、E-0005 → E-0003～E-0005。"""
    out, run = [], []
    for i in ids:
        if run and i[:2] == run[-1][:2] and i[2:].isdigit() and run[-1][2:].isdigit() and int(i[2:]) == int(run[-1][2:]) + 1:
            run.append(i)
            continue
        if run:
            out.append(run)
        run = [i]
    if run:
        out.append(run)
    return "、".join(r[0] if len(r) == 1 else f"{r[0]}、{r[1]}" if len(r) == 2 else f"{r[0]}～{r[-1]}" for r in out)


def build_data_card(ctx: Context, baseline: dict, mapping: dict[str, str]) -> dict:
    """各來源的數字並排；Evidence ID 用這次 run 的編號。失敗的來源標失敗，不留空。"""
    card = {"domain": baseline["domain"], "baseline_hash": baseline["baseline_hash"],
            "fetched_at": {s: (baseline["sources"].get(s) or {}).get("fetched_at") for s in SOURCES}, "sources": {}}
    for name in SOURCES:
        src = baseline["sources"].get(name) or {}
        ids = [mapping[i] for i in src.get("evidence_ids") or [] if i in mapping]
        entry = {"label": LABELS[name], "fetched_at": src.get("fetched_at"), "evidence_ids": ids,
                 "evidence_kinds": _evidence_kinds(ctx, ids)}
        if not src.get("ok"):
            err = src.get("error") or {}
            entry.update(status="失敗", error=f"{err.get('code')}: {err.get('detail')}")
            card["sources"][name] = entry
            continue
        res = src["result"]
        entry["status"] = "成功"
        if name == "sitemap":
            entry.update(url_rows=res.get("url_rows"), distinct_urls=res.get("distinct_urls"),
                         sitemap_files=res.get("sitemap_files_ok_total"),
                         sections_total=res.get("sections_total"),
                         sections=[{k: s.get(k) for k in ("section", "urls", "rows", "lastmod_min", "lastmod_max")}
                                   for s in res.get("sections") or []])
        elif name == "home_menu":
            entry.update(_menu(res, baseline["domain"]))
        elif name == "whois":
            rdap = res.get("rdap") or {}
            entry.update(dates=rdap.get("events") or {}, whois_text_chars=len((res.get("whois") or {}).get("text", "")))
        elif name == "wayback":
            cdx = next((i for i in ids if ctx.store.get(i)["kind"] == "wayback_cdx"), None)
            entry.update(_wayback_dates(ctx.store.read(cdx)) if cdx else {"snapshots": res.get("months_with_snapshots")})
            entry["date_evidence_id"] = cdx
        else:
            results = res.get("results") or []
            entry.update(query=res.get("query") or src["args"]["query"], results=len(results),
                         results_on_site=sum(1 for r in results if domain_key(r.get("url", "")) == baseline["domain"]))
        card["sources"][name] = entry
    return card


def data_card_markdown(card: dict) -> str:
    lines = [f"## 資料卡：{card['domain']}（網站底稿 hash {card['baseline_hash'][:12]}）",
             "以下是 ② 固定偵察抓到的數字，程式只並排、不判讀。Evidence ID 可追回原檔（標「快照」）。", ""]
    for name, e in card["sources"].items():
        lines.append(f"### {e['label']}（抓取 {e.get('fetched_at') or '—'}）")
        kinds = e.get("evidence_kinds") or []
        lines.append("- Evidence ID：" + ("；".join(f"{g['what']} {_id_ranges(g['ids'])}" for g in kinds) or "無"))
        if e["status"] == "失敗":
            lines += [f"- 失敗：{e.get('error')}", ""]
            continue
        if name == "sitemap":
            lines.append(f"- 網址列數 {e['url_rows']}、不重複網址 {e['distinct_urls']}、sitemap 檔 {e['sitemap_files']}")
            for s in e["sections"]:
                # 舊底稿沒有 rows：那時的 urls 是含重複的列數，照實標
                n = f"{s['urls']} 個不重複網址（{s['rows']} 列）" if s.get("rows") is not None else f"{s['urls']} 列（可能含重複網址）"
                lines.append(f"- 分區 {s['section']}：{n}，lastmod {s['lastmod_min'] or '—'} ～ {s['lastmod_max'] or '—'}")
            if e.get("sections_total") and e["sections_total"] > len(e["sections"]):
                lines.append(f"- 只列網址最多的 {len(e['sections'])} 區，共 {e['sections_total']} 區")
        elif name == "home_menu":
            lines.append(f"- 選單連結 {e['menu_links']} 個")
            for sec, n in e["sections"].items():
                lines.append(f"- 分區 {sec}：{n} 個選單連結")
        elif name == "whois":
            for k, v in e["dates"].items():
                lines.append(f"- {k}：{v}")
            if not e["dates"]:
                lines.append("- RDAP 沒有日期欄位")
        elif name == "wayback":
            lines.append(f"- 存檔 {e.get('snapshots')} 筆（每月最多 1 筆），日期範圍 {e.get('earliest') or '—'} ～ {e.get('latest') or '—'}"
                         f"（取自 {e.get('date_evidence_id') or '—'}）")
            for y, n in (e.get("by_year") or {}).items():
                lines.append(f"- {y} 年：{n} 筆")
        else:
            lines.append(f"- 搜尋「{e['query']}」：{e['results']} 筆結果，其中 {e['results_on_site']} 筆在 {card['domain']}")
        lines.append("")
    return "\n".join(lines)


def prepare(ctx: Context, site: str, keywords: list[str], *, refresh: bool = False, root: Path = BASELINE_ROOT,
            transport=None, delay_s: float = 1.5, sleep=time.sleep) -> dict:
    """② 程式準備：確保底稿 → 匯入 run 證據庫 → 產資料卡（存 data_card.json／.md）。"""
    baseline = Baseline(site, root=root).ensure(keywords, refresh=refresh, transport=transport, delay_s=delay_s,
                                                sleep=sleep)
    mapping = import_into_run(ctx, baseline, root=root)
    card = build_data_card(ctx, baseline, mapping)
    md = data_card_markdown(card)
    (ctx.run_dir / "data_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    (ctx.run_dir / "data_card.md").write_text(md, encoding="utf-8")
    return {"baseline": {k: baseline.get(k) for k in ("domain", "baseline_hash", "updated_at", "action", "refetched")},
            "fetched_at": card["fetched_at"], "card": card, "markdown": md, "mapping": mapping}
