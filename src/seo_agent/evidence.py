"""證據層：每份原始資料存成 raw/E-0001.<副檔名>，index 一行一筆（編號、來源、sha256、時間、工具）。

網頁內容只當資料：回給模型時包在 untrusted 標記內，且不會被當成指令執行。
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path


class EvidenceStore:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.raw_dir = self.run_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.run_dir / "evidence.jsonl"
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}
        self._hashes: set[str] = set()
        if self.index_path.exists():
            for line in self.index_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    self._items[item["id"]] = item
                    self._hashes.add(item["sha256"])

    def add(self, body: bytes, *, source: str, tool: str, kind: str, suffix: str = ".bin", meta: dict | None = None) -> dict:
        """存一份原始檔，回傳 index 紀錄；`new_content` 表示這份內容（sha256）本 run 第一次看到。"""
        digest = hashlib.sha256(body).hexdigest()
        with self._lock:
            eid = f"E-{len(self._items) + 1:04d}"
            path = self.raw_dir / f"{eid}{suffix}"
            path.write_bytes(body)
            new = digest not in self._hashes
            self._hashes.add(digest)
            item = {"id": eid, "source": source, "tool": tool, "kind": kind, "sha256": digest, "bytes": len(body),
                    "file": str(path.relative_to(self.run_dir)), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "new_content": new, "meta": meta or {}}
            self._items[eid] = item
            with self.index_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            return item

    def get(self, eid: str) -> dict | None:
        return self._items.get(eid)

    def read(self, eid: str) -> bytes:
        item = self._items.get(eid)
        if not item:
            raise KeyError(f"沒有這個證據編號：{eid}")
        return (self.run_dir / item["file"]).read_bytes()

    def ids(self) -> list[str]:
        return list(self._items)

    def all(self) -> list[dict]:
        return list(self._items.values())
