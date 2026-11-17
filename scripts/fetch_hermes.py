#!/usr/bin/env python3
"""取得鎖定版 Hermes 原始碼到 vendor/hermes-agent（clone 後第一步，uv sync 之前執行）。

Hermes 的 build backend 拒絕打包 wheel／sdist，只支援 editable 安裝，所以不能用 URL 依賴。
本腳本下載固定 commit 的 GitHub tarball、驗證 sha256、解壓到 vendor/hermes-agent，並寫入
vendor/hermes-agent/.seo_agent_pin.json。已存在且 pin 相符時不重抓。只用標準函式庫。

用法：python3 scripts/fetch_hermes.py [--from-file 已下載的.tar.gz]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "f97608f178d1ffeca59860195ab7da295f7c8e5f"
TAG = "v2026.9.24"
URL = f"https://github.com/NousResearch/hermes-agent/archive/{COMMIT}.tar.gz"
SHA256 = "babbdb9706ad1c96708d75914afb45d809cd4b73dec1ceae233a6814f5ed97e3"
DEST = ROOT / "vendor" / "hermes-agent"
PIN = {"repo": "NousResearch/hermes-agent", "tag": TAG, "commit": COMMIT, "url": URL, "sha256": SHA256}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-file", type=Path)
    args = parser.parse_args()
    pin_file = DEST / ".seo_agent_pin.json"
    if pin_file.is_file() and json.loads(pin_file.read_text()) == PIN:
        print(json.dumps({"status": "already_present", **PIN}))
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "hermes.tar.gz"
        if args.from_file:
            shutil.copyfile(args.from_file, archive)
        else:
            with urllib.request.urlopen(URL, timeout=600) as response, archive.open("wb") as out:
                shutil.copyfileobj(response, out)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != SHA256:
            print(json.dumps({"status": "sha256_mismatch", "expected": SHA256, "actual": digest}), file=sys.stderr)
            return 1
        extract = Path(tmp) / "x"
        with tarfile.open(archive) as tar:
            tar.extractall(extract, filter="data")  # data filter：拒絕絕對路徑、..、裝置檔
        top = extract / f"hermes-agent-{COMMIT}"
        if not top.is_dir():
            print("tarball 結構不符", file=sys.stderr)
            return 1
        if DEST.exists():
            shutil.rmtree(DEST)
        DEST.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(top), DEST)
    pin_file.write_text(json.dumps(PIN, indent=2) + "\n")
    print(json.dumps({"status": "fetched", **PIN}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
