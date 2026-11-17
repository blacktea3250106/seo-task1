"""Tool 2 sitemap 目錄樹：把網站所有 sitemap 讀進 SQLite，再用 5 種查詢看結構（需求 2.2）。

找 sitemap 的地方：robots.txt 的 Sitemap 行、/sitemap.xml、/sitemap_index.xml、/wp-sitemap.xml，
以及首頁連結裡每個第一層資料夾的 /<資料夾>/sitemap.xml（2030 盲審：娛樂城區的 sitemap 藏在資料夾底下）。
"""
from __future__ import annotations

import gzip
import io
import sqlite3
from collections import Counter, deque
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree.ElementTree import ParseError, iterparse

from ..hermes_bridge import Tool
from .context import Context
from .fetcher import ToolError
from .html_parse import parse_html
from .web import _guard, decode

MAX_SITEMAPS = 400
MAX_URLS = 300_000
DEFAULT_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")


def section_of(url: str, depth: int = 1) -> str:
    segs = [unquote(s) for s in urlsplit(url).path.split("/") if s]
    return "/" + "/".join(segs[:depth]) + ("/" if segs[:depth] else "") if segs else "/"


class SitemapDB:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.db = sqlite3.connect(ctx.run_dir / "sitemap.sqlite", check_same_thread=False)
        ctx.closers.append(self.db.close)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sitemaps(url TEXT PRIMARY KEY, status INTEGER, kind TEXT, n_urls INTEGER,
                parent TEXT, found_by TEXT, evidence_id TEXT, note TEXT);
            CREATE TABLE IF NOT EXISTS urls(loc TEXT, lastmod TEXT, sitemap TEXT, section TEXT);
            CREATE INDEX IF NOT EXISTS urls_section ON urls(section);
            CREATE INDEX IF NOT EXISTS urls_loc ON urls(loc);""")

    # ---- 建立 ----
    def build(self, site: str, extra_urls: list[str] | None = None, folders: list[str] | None = None) -> dict:
        parts = urlsplit(site if "://" in site else "https://" + site)
        origin = f"{parts.scheme}://{parts.netloc}"
        queue: deque[tuple[str, str | None, str]] = deque()
        self.ctx.fetcher.robots_allows(origin + "/")  # 先載入 robots
        rp = self.ctx.fetcher._robots.get(origin)  # noqa: SLF001
        for sm in (rp.site_maps() or []) if hasattr(rp, "site_maps") else []:
            queue.append((sm, None, "robots.txt"))
        for path in DEFAULT_PATHS:
            queue.append((origin + path, None, "常見位置"))
        for u in extra_urls or []:
            queue.append((u, None, "AI 指定"))
        found_folders = set(folders or [])
        try:
            home = self.ctx.fetcher.fetch(origin + "/", kind="page")
            page = parse_html(decode(home.body, home.headers.get("content-type", "")), home.final_url)
            for link in page["internal_links"]:
                seg = [s for s in urlsplit(link["url"]).path.split("/") if s]
                if seg and "." not in seg[0]:
                    found_folders.add(seg[0])
        except ToolError:
            pass
        for folder in sorted(found_folders)[:40]:
            queue.append((f"{origin}/{folder.strip('/')}/sitemap.xml", None, "資料夾探測"))

        seen = {r[0] for r in self.db.execute("SELECT url FROM sitemaps")}
        fetched = 0
        while queue and fetched < MAX_SITEMAPS:
            url, parent, found_by = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            fetched += 1
            self._read_one(url, parent, found_by, queue)
        self.db.commit()
        return {**self.summary(), "sitemap_files_tried": fetched, "queue_left": len(queue),
                "folders_probed": sorted(found_folders)[:40]}

    def _read_one(self, url: str, parent: str | None, found_by: str, queue: deque) -> None:
        try:
            res = self.ctx.fetcher.fetch(url, kind="sitemap", tool="sitemap_tree")
        except ToolError as error:
            self.db.execute("INSERT OR REPLACE INTO sitemaps VALUES(?,?,?,?,?,?,?,?)",
                            (url, None, "error", 0, parent, found_by, None, error.code))
            return
        eid = res.evidence["id"] if res.evidence else None
        body = res.body
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                pass
        if res.status != 200 or b"<" not in body[:500]:
            self.db.execute("INSERT OR REPLACE INTO sitemaps VALUES(?,?,?,?,?,?,?,?)",
                            (url, res.status, "missing", 0, parent, found_by, eid, None))
            return
        kind, n, rows = "unknown", 0, []
        try:
            loc = lastmod = None
            depth = 0  # start 後：urlset/sitemapindex＝1、url/sitemap＝2、直接子層 loc/lastmod＝3；end 事件先減回父層深度，所以判斷 depth == 2
            for event, el in iterparse(io.BytesIO(body), events=("start", "end")):
                tag = el.tag.rsplit("}", 1)[-1]
                if event == "start":
                    depth += 1
                    if tag in ("sitemapindex", "urlset") and kind == "unknown":
                        kind = tag
                    continue
                depth -= 1
                if depth == 2 and tag == "loc":  # 只認 <url>/<sitemap> 直接子層；<image:image> 裡的 <image:loc> 在更深層，不算
                    loc = (el.text or "").strip()
                elif depth == 2 and tag == "lastmod":
                    lastmod = (el.text or "").strip()
                elif tag in ("sitemap", "url"):
                    if loc:
                        n += 1
                        if tag == "sitemap":
                            queue.append((urljoin(url, loc), url, "sitemap 索引"))
                        elif len(rows) < MAX_URLS:
                            rows.append((loc, lastmod, url, section_of(loc)))
                    loc = lastmod = None
                    el.clear()
        except ParseError as error:
            kind = f"parse_error:{error}"
        self.db.executemany("INSERT INTO urls VALUES(?,?,?,?)", rows)
        self.db.execute("INSERT OR REPLACE INTO sitemaps VALUES(?,?,?,?,?,?,?,?)",
                        (url, res.status, kind, n, parent, found_by, eid, None))

    # ---- 查詢 ----
    def summary(self) -> dict:
        total = self.db.execute("SELECT COUNT(*), COUNT(DISTINCT loc) FROM urls").fetchone()
        # urls＝不重複網址數；rows＝含重複的列數（同一網址可能列在多個 sitemap 檔）。以前 urls 是列數，和 distinct_urls 並排會被當成篇數
        sections = [{"section": s, "urls": c, "rows": r, "share": round(c / total[1], 3) if total[1] else 0,
                     "lastmod_min": lo, "lastmod_max": hi}
                    for s, c, r, lo, hi in self.db.execute(
                        "SELECT section, COUNT(DISTINCT loc), COUNT(*), MIN(lastmod), MAX(lastmod) FROM urls "
                        "GROUP BY section ORDER BY 2 DESC LIMIT 40")]
        sections_total = self.db.execute("SELECT COUNT(DISTINCT section) FROM urls").fetchone()[0]
        files = [dict(zip(("url", "status", "kind", "n", "parent", "found_by", "evidence_id", "note"), r, strict=False))
                 for r in self.db.execute("SELECT * FROM sitemaps ORDER BY found_by, url")]
        ok_files = [f for f in files if f["kind"] in ("urlset", "sitemapindex")]
        bad = [f for f in files if f not in ok_files]
        # 計數用全部的檔（清單只列前 60 筆）；狀態 200 但不是 sitemap 的檔另標 kind，才看得出為什麼算讀不到
        by_status = Counter(str(f["status"] or f["note"] or "error") + (f"（{f['kind']}）" if f["status"] == 200 else "")
                            for f in bad)
        brief = lambda f: {"url": f["url"], "status": f["status"], "kind": f["kind"], "note": f["note"]}  # noqa: E731
        not_404 = [brief(f) for f in bad if f["status"] != 404]  # 從未截斷的清單篩，404 以外的不會被前 60 筆擠掉
        return {"url_rows": total[0], "distinct_urls": total[1], "sections": sections, "sections_total": sections_total,
                "sitemap_files_ok": ok_files[:80], "sitemap_files_ok_total": len(ok_files),
                "sitemap_files_not_ok_by_status": dict(by_status),
                "sitemap_files_not_ok_except_404": not_404[:20], "sitemap_files_not_ok_except_404_total": len(not_404),
                "sitemap_files_missing_or_error": [brief(f) for f in bad][:60]}

    def expand(self, prefix: str, depth: int) -> dict:
        rows = self.db.execute("SELECT loc FROM urls WHERE section = ? OR loc LIKE ?",
                               (prefix, "%" + prefix + "%")).fetchall()
        # matched／children 和 summary 的 urls 同口徑：不重複網址；rows 是列數（同一網址可能列在多個 sitemap 檔）
        locs = dict.fromkeys(loc for (loc,) in rows)
        counts: dict[str, int] = {}
        for loc in locs:
            path = unquote(urlsplit(loc).path)
            if prefix in path:
                key = section_of(loc, depth)
                counts[key] = counts.get(key, 0) + 1
        return {"prefix": prefix, "depth": depth, "matched": len(locs), "rows": len(rows),
                "children": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:60])}

    def search(self, text: str, limit: int) -> dict:
        rows = [r for r in self.db.execute("SELECT loc, lastmod, sitemap FROM urls") if text.lower() in unquote(r[0]).lower()]
        first: dict[str, str | None] = {}  # 不重複網址 → 第一次出現的 lastmod
        for loc, lastmod, _ in rows:
            first.setdefault(loc, lastmod)
        examples = [{"loc": unquote(loc), "lastmod": m} for loc, m in list(first.items())[:limit]]
        return {"query": text, "matches": len(first), "rows": len(rows), "by_sitemap": self._count(r[2] for r in rows),
                "examples": examples, "examples_shown": len(examples)}

    def by_month(self, section: str | None) -> dict:
        sql = "SELECT substr(lastmod,1,7), COUNT(DISTINCT loc) FROM urls {} GROUP BY 1 ORDER BY 1"  # 和分區 urls 同口徑：不重複網址
        rows = self.db.execute(sql.format("WHERE section = ?" if section else ""), (section,) if section else ()).fetchall()
        return {"section": section, "months": {m or "（無 lastmod）": c for m, c in rows}}

    def sample(self, section: str | None, n: int) -> dict:
        sql = "SELECT loc, lastmod FROM urls {} ORDER BY lastmod, loc"
        rows = self.db.execute(sql.format("WHERE section = ?" if section else ""), (section,) if section else ()).fetchall()
        if not rows:
            return {"section": section, "total": 0, "head": [], "middle": [], "tail": []}
        mid = len(rows) // 2
        pick = lambda part: [{"loc": unquote(loc), "lastmod": m} for loc, m in part]  # noqa: E731
        return {"section": section, "total": len(rows), "head": pick(rows[:n]),
                "middle": pick(rows[max(0, mid - n // 2): mid + (n + 1) // 2]), "tail": pick(rows[-n:])}

    def compare(self, urls: list[str] | None, expected_total: int | None, section: str | None) -> dict:
        out: dict = {}
        if urls:
            known = {unquote(r[0]).rstrip("/") for r in self.db.execute("SELECT loc FROM urls")}
            missing = [u for u in urls if unquote(u).rstrip("/") not in known]
            out.update({"given": len(urls), "in_sitemaps": len(urls) - len(missing), "not_in_sitemaps": missing[:100],
                        "not_in_sitemaps_total": len(missing)})
        if expected_total is not None:
            sql = "SELECT COUNT(DISTINCT loc) FROM urls" + (" WHERE section = ?" if section else "")
            actual = self.db.execute(sql, (section,) if section else ()).fetchone()[0]
            out.update({"section": section, "expected_total": expected_total, "in_sitemaps": actual,
                        "gap": expected_total - actual})
        return out

    @staticmethod
    def _count(values) -> dict:
        counts: dict[str, int] = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1])[:20])


BRIEF_SECTIONS = 10


def _brief(out: dict) -> dict:
    """build 給模型的精簡版（2026-11-17 量到：完整版 1.1 萬字，6 千字是資料卡已列過的分區表、2 千字是 404 清單，
    而且是每輪最早的回傳，之後每一步都重讀）。分區表用 action=summary 拿；資料沒有少，只是不預設全送。"""
    out = dict(out)
    out["sections"] = out["sections"][:BRIEF_SECTIONS]
    out.pop("sitemap_files_missing_or_error")  # 404 以外的已在 summary 從完整清單產生（sitemap_files_not_ok_except_404）
    out["folders_probed"] = len(out.get("folders_probed") or [])
    out["brief"] = (f"sections 只列網址最多的 {len(out['sections'])} 區（共 {out['sections_total']} 區）；"
                    "action=summary 列到前 40 區，更小的分區用 expand 或 search 查")
    return out


def sitemap_tool(ctx: Context) -> Tool:
    holder: dict = {}

    def db() -> SitemapDB:
        if "db" not in holder:
            holder["db"] = SitemapDB(ctx)
        return holder["db"]

    @_guard
    def run(args: dict) -> dict:
        action = args.get("action", "build")
        d = db()
        if action == "build":
            if not args.get("site"):
                raise ToolError("bad_args", "build 需要 site")
            out = {"ok": True, **d.build(args["site"], args.get("extra_urls"), args.get("folders"))}
            return out if args.get("detail") == "full" else _brief(out)
        # 還沒 build 就查，會把「沒資料」回成「0 筆／都不在 sitemap」這種假事實（2026-11-17 精簡版實跑抓到）。
        # 看 sitemaps 表：build 過但網站真的沒有 sitemap（全 404）時 urls 也是空的，那種情況要照常回 0 筆
        if d.db.execute("SELECT 1 FROM sitemaps LIMIT 1").fetchone() is None:
            raise ToolError("bad_args", "這次 run 還沒讀過 sitemap：先呼叫 action=build（site）再查詢")
        if action == "summary":
            return {"ok": True, **d.summary()}
        if action == "expand":
            return {"ok": True, **d.expand(args.get("prefix", "/"), int(args.get("depth", 2)))}
        if action == "search":
            return {"ok": True, **d.search(args.get("text", ""), int(args.get("limit", 20)))}
        if action == "by_month":
            return {"ok": True, **d.by_month(args.get("section"))}
        if action == "sample":
            return {"ok": True, **d.sample(args.get("section"), int(args.get("limit", 5)))}
        if action == "compare":
            return {"ok": True, **d.compare(args.get("urls"), args.get("expected_total"), args.get("section"))}
        raise ToolError("bad_args", f"未知 action {action}")

    return Tool("sitemap_tree",
                "把網站的 sitemap 全部讀進資料庫後查詢。action=build（site；會讀 robots 列出的、常見位置、"
                "以及首頁連結中各資料夾下的 /<資料夾>/sitemap.xml；可加 extra_urls、folders）→ 回總數、網址最多的 10 區、"
                "每個讀到的 sitemap 檔與它是怎麼找到的（found_by）、讀不到的檔依狀態碼計數（404 以外逐一列出）。"
                "之後：summary（網址最多的前 40 區的數量、佔比、lastmod 範圍）；expand（prefix, depth 往下展開；matched 是不重複網址數，rows 是列數，"
                "同一網址可能出現在多個 sitemap 檔；children 是各子分區的不重複網址數，最多列前 60 個）；"
                "search（text 網址含字；matches 是不重複網址數（沒有上限），rows 是列數，同一網址可能出現在多個 sitemap 檔；"
                "by_sitemap 是各 sitemap 檔的符合列數；examples 是不重複網址，最多列 limit 筆，examples_shown 是實際列出筆數）；"
                "by_month（section，看每月 lastmod）；sample（section，前中後段樣本）；"
                "compare（urls 清單看哪些不在 sitemap，或 expected_total＋section 比數量，例如對照 REST API 的 x-wp-total）。"
                "section 寫法如 /blog/。",
                {"type": "object", "properties": {
                    "action": {"type": "string", "enum": ["build", "summary", "expand", "search", "by_month", "sample", "compare"]},
                    "site": {"type": "string"}, "extra_urls": {"type": "array", "items": {"type": "string"}},
                    "folders": {"type": "array", "items": {"type": "string"}},
                    "prefix": {"type": "string"}, "depth": {"type": "integer"}, "text": {"type": "string"},
                    "section": {"type": "string"}, "limit": {"type": "integer"},
                    "urls": {"type": "array", "items": {"type": "string"}}, "expected_total": {"type": "integer"}},
                 "required": ["action"]}, run)
