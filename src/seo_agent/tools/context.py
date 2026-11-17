"""一次研究 run 共用的狀態：證據庫、禮貌抓取器、研究日誌。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx

from ..evidence import EvidenceStore
from .fetcher import PoliteFetcher


class Context:
    def __init__(self, run_dir: Path, *, transport: httpx.BaseTransport | None = None, delay_s: float = 1.5,
                 sleep=time.sleep, autonomy: dict | None = None):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.store = EvidenceStore(self.run_dir)
        self.fetcher = PoliteFetcher(self.store, delay_s=delay_s, transport=transport, sleep=sleep, autonomy=autonomy)
        self.tool_calls_path = self.run_dir / "tool_calls.jsonl"
        self.site_domain: str | None = None  # 競爭者網域；其他網站的內容標「外部說法」（G-47）
        self.light_test_routes: dict[str, list[dict]] = {}  # 別走（查不到）經驗的原路線，判斷輕試用（G-34）
        self._lock = threading.Lock()
        self.started = time.time()
        self.closers: list = []  # 要在 close() 釋放的資源（例如 sitemap.sqlite；Windows 開著的檔不能刪）

    def close(self) -> None:
        self.fetcher.close()
        while self.closers:
            self.closers.pop()()

    def append_jsonl(self, path: Path, record: dict) -> None:
        with self._lock, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def evidence_ref(self, item: dict | None) -> dict | None:
        if not item:
            return None
        return {"evidence_id": item["id"], "new_content": item["new_content"], "sha256": item["sha256"][:16]}
