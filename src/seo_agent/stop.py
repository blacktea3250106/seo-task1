"""停止判斷（d-architecture 第 6 層）：
停止條件 A：連續 5 次工具呼叫沒有新證據、判斷也沒修正 → 擋下研究工具，請 AI 交報告。
   「進展」用穩定指紋判斷（與證據庫的 new_content 分開）：
   - polite_fetch：(工具, 類型, 來源網址, 手機/桌機, 方法) 第一次出現才算；重抓同一網址不算，就算內容含 nonce、TTL 也一樣。
   - 失敗（ok=false，例如人機驗證頁）一律不算進展。
   - 其他工具的成功結果（sitemap 查詢、文字比對、看單頁不同部分、搜尋、Wayback、網域資料）一律存成衍生證據並編號
     （d-architecture 第 53 行），只看衍生結果是不是新的（查詢字串在來源網址裡，不能用原檔指紋判斷）；
     雜湊前去掉日期／TTL 等易變欄位與原樣回傳的參數（同名欄位刪除；參數字串出現在值或 key 時換成 <arg>），
     所以換字的零命中查詢雜湊相同，只有第一次算；空結果不算進展。這個雜湊只當指紋（存在證據 meta.fingerprint），
     證據檔本身存 Tool 原樣結果，不換 <arg>（決策 #56）。
   2 個交卷動作（submit_report、experience）與別走經驗的輕試呼叫都不計入連續次數，也不讓它歸零（G-34、G-40）。
   輕試（決策 #71）：Tool 呼叫的 why 寫過別走（查不到）經驗編號（這次或之前的呼叫）＝已登記；之後 Tool 名稱和目標
   （網域、路徑）都跟原路線一樣的那 1 次呼叫（每條經驗每次研究只算 1 次）。路線由 ctx.light_test_routes 提供。
停止條件 B：總時間 120 分鐘安全網：最後 20 分鐘保留給第 6 步定稿與第 5 步審查，這時擋下研究 Tool（G-36）；Hermes 本身另設 120 分鐘硬上限。
停止條件只有 A、B（決策 #59 刪掉「問題答完就停」）。步驟編號同 README「一次 run 從頭到尾」。
時間回饋（決策 #59）：每次研究 Tool 的回傳附 time_used「已用 xx／上限 分」，上限＝這個 run 的 total_s；只寫事實，不加指示。
"""
from __future__ import annotations

import hashlib
import json
import re
import time

VOLATILE = {"date", "age", "at", "new_content", "sha256", "file", "bytes", "elapsed_s", "fetched_at", "stop_notice",
            "evidence_id", "derived_evidence_id", "cf-ray", "expires", "last-modified", "etag", "x-cache", "cf-cache-status",
            "ttl", "nonce", "request_id", "last update of rdap database", "last changed"}
VOLATILE_LINE = re.compile(r"(?im)^.*(last update of|>>>|最後更新|query time|timestamp).*$")


def _stable(value):
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in value.items() if str(k).lower() not in VOLATILE}
    if isinstance(value, list):
        return [_stable(v) for v in value]
    if isinstance(value, str) and "\n" in value:
        return VOLATILE_LINE.sub("", value)
    return value


def _scrub(value, words: set):
    """把原樣回傳的參數字串（值或當成 key）換成 <arg>，換字的零命中查詢就會得到同樣的雜湊。"""
    if isinstance(value, dict):
        return {("<arg>" if k in words else k): _scrub(v, words) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, words) for v in value]
    return "<arg>" if isinstance(value, str) and value in words else value


def _arg_words(args: dict) -> set:
    out = set()
    for v in args.values():
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str) and x.strip():
                out.add(x)
    return out


def _empty(value) -> bool:
    if isinstance(value, dict):
        return all(_empty(v) for k, v in value.items() if k != "ok")
    if isinstance(value, list):
        return all(_empty(v) for v in value)
    return value in (None, "", 0, False)

def derived_body(name: str, args: dict, result: dict) -> tuple[bytes, object, str]:
    """Tool 結果存成衍生證據：回 (存檔內容, 指紋用的穩定版, 指紋)。
    存檔內容是 Tool 原樣結果（不去欄位、不換 <arg>），審查與引用核對讀得到每個關鍵字的真實結果（決策 #56）；
    指紋用去掉易變欄位與原樣回傳參數的版本算，只用於進展判斷與比對網站底稿，換字的零命中查詢指紋相同。"""
    echo = {k for k in result if k in args}  # 只去掉與參數同名的回傳欄位
    stable = _scrub(_stable({k: v for k, v in result.items() if k not in echo}), _arg_words(args))
    fingerprint = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    body = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return body, stable, fingerprint


def derived_source(name: str, args: dict) -> str:
    return f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)[:300]}"


NO_PROGRESS_LIMIT = 5
TOTAL_S = 120 * 60
REPORT_RESERVE_S = 20 * 60
RAW_ONLY = {"polite_fetch"}  # 結果就是原檔本身，只看原檔指紋
SUBMIT_ACTIONS = ("submit_report", "experience")  # 2 個交卷動作，不是研究 Tool（G-40）
ALWAYS_ALLOWED = set(SUBMIT_ACTIONS)
# 程式在 Tool 外層附上的事實（決策 #71）：不是 Tool 結果，不存進衍生證據、不算進指紋；回給模型時照留
PROGRAM_NOTES = {"sections_not_yet_read"}


class StopGuard:
    def __init__(self, ctx, *, total_s: float = TOTAL_S, reserve_s: float = REPORT_RESERVE_S,
                 limit: int = NO_PROGRESS_LIMIT, clock=time.time):
        self.ctx, self.total_s, self.reserve_s, self.limit, self.clock = ctx, total_s, reserve_s, limit, clock
        self.started = clock()
        self.streak = 0
        self.events: list[dict] = []
        self._before = 0
        self._seen: set = set()
        self._light_tested: set = set()  # 這次研究已輕試過的經驗編號
        self._registered: set = set()  # why 欄寫過的經驗編號（決策 #71）
        self._snapshot: set = set()  # 網站底稿匯入的內容指紋（G-51）
        # research → revise（收到第 5 步待修清單：可回研究 Tool 補查 1 次，不受保留時間與連續次數限制）→ final（修完交出，不能再補查）
        self.phase = "research"
        self.recheck_calls = 0

    def before(self, name: str, args: dict) -> dict | None:
        self._before = len(self.ctx.store.ids())
        from .coverage import why_ids
        self._registered |= why_ids(args)
        if name in ALWAYS_ALLOWED:
            return None
        elapsed = self.clock() - self.started
        if self.phase == "final":
            self._event("after_review", elapsed)
            return {"ok": False, "error": {"code": "stop_after_review",
                    "detail": "報告已依待修清單修完交出；回 ④ 補查最多 1 次，已用過。report.py 的退回只要求改格式。"}}
        if self.phase == "revise":  # 回研究 Tool 補查（G-37、G-61）：只受 120 分鐘總時間限制
            if elapsed >= self.total_s:
                self._event("time", elapsed)
                return {"ok": False, "error": {"code": "stop_time_limit", "detail": "120 分鐘已到；請直接交修正後的報告。"}}
            self.recheck_calls += 1
            return None
        if elapsed >= self.total_s - self.reserve_s:
            self._event("time", elapsed)
            return {"ok": False, "error": {"code": "stop_time_limit",
                    "detail": f"已用 {elapsed / 60:.0f} 分鐘，接近 120 分鐘上限；請停止研究，用 submit_report 交報告。"}}
        if self.streak >= self.limit:
            self._event("no_progress", elapsed)
            return {"ok": False, "error": {"code": "stop_no_progress",
                    "detail": f"已連續 {self.streak} 次 Tool 呼叫沒有新證據；請停止研究、交報告。"}}
        return None

    def seed_snapshot(self) -> None:
        """網站底稿已匯入後呼叫：底稿內容都當作「看過」，第 3 步重抓或重查到一樣的內容不算新證據（決策 #46、#50）。"""
        for item in self.ctx.store.all():
            meta = item.get("meta") or {}
            if meta.get("snapshot"):  # 舊底稿的衍生證據存的就是穩定版，sha256 即指紋
                self._snapshot.add(meta.get("fingerprint") or item["sha256"])

    def light_test_of(self, name: str, args: dict) -> str | None:
        """這次呼叫是不是某條別走（查不到）經驗的輕試；是就回經驗編號。"""
        routes = getattr(self.ctx, "light_test_routes", None) or {}
        if not routes:
            return None
        from .board import call_target
        from .coverage import why_ids
        registered = self._registered | why_ids(args)
        target = call_target(name, args, self.ctx.store)
        for exp_id, route in routes.items():
            if exp_id in registered and exp_id not in self._light_tested and any(
                    step.get("tool") == name and step.get("target") == target for step in route):
                return exp_id
        return None

    def after(self, name: str, args: dict, result: dict, question_id: str | None = None) -> dict:
        """question_id：hermes_bridge 仍會傳入（舊題號機制），決策 #71 起不用。"""
        self.last_progress = None  # 這次呼叫有沒有帶來新證據；ToolLog 記進 tool_calls.jsonl，白做工次數據此算（G-30）
        if name in ALWAYS_ALLOWED:  # 交卷動作：不計入、不歸零
            return result
        light = self.light_test_of(name, args)
        args = {k: v for k, v in args.items() if k != "why"}  # why 不進證據來源與指紋
        ok = isinstance(result, dict) and bool(result.get("ok"))
        new_raw = False
        same_as_snapshot = False
        for item in self.ctx.store.all()[self._before:]:
            meta = item.get("meta") or {}
            key = ("raw", item["tool"], item["kind"], item["source"], meta.get("mobile"), meta.get("method"))
            if item["sha256"] in self._snapshot:  # 和底稿一樣：不算新證據（也不算白做工，交給指標程式判斷）
                same_as_snapshot = True
                self._seen.add(key)
                continue
            if key not in self._seen:
                self._seen.add(key)
                new_raw = True
        progress = ok and name in RAW_ONLY and new_raw  # polite_fetch：新網址／UA／方法才算
        if ok and name not in RAW_ONLY:  # 其他工具只看解析／查詢結果；原檔指紋只記錄不算進展
            core = {k: v for k, v in result.items() if k not in PROGRAM_NOTES}
            body, stable, fingerprint = derived_body(name, args, core)
            item = self.ctx.store.add(body, source=derived_source(name, args), tool=name, kind="derived", suffix=".json",
                                      meta={"fingerprint": fingerprint})
            result = {**result, "derived_evidence_id": item["id"]}
            key = ("derived", fingerprint)
            if fingerprint in self._snapshot:
                same_as_snapshot = True
            elif not _empty(stable) and key not in self._seen:
                self._seen.add(key)
                progress = True
        if same_as_snapshot and not progress and isinstance(result, dict):
            result = {**result, "same_as_snapshot": True}
        self.last_progress = progress
        if isinstance(result, dict):
            result = {**result, "time_used": self.time_used()}
        if light:  # 輕試：結果照存，但不算進連續次數、也不歸零
            self._light_tested.add(light)
            return {**result, "light_test_of": light} if isinstance(result, dict) else result
        self.streak = 0 if progress else self.streak + 1
        if self.streak >= self.limit - 1 and isinstance(result, dict):
            result = {**result, "stop_notice": f"已連續 {self.streak} 次沒有新證據（{self.limit} 次會停）。"}
        return result

    def time_used(self) -> str:
        """「已用 xx／上限 分」：研究 Tool 回傳與第 5 步待修清單都附這一行（決策 #59）。"""
        return f"已用 {(self.clock() - self.started) / 60:.0f}／{self.total_s / 60:.0f} 分"

    def _event(self, kind: str, elapsed: float) -> None:
        self.events.append({"kind": kind, "elapsed_s": round(elapsed, 1), "streak": self.streak})

    def summary(self) -> dict:
        return {"elapsed_s": round(self.clock() - self.started, 1), "final_streak": self.streak,
                "stop_events": self.events, "phase": self.phase, "recheck_calls": self.recheck_calls}
