"""Task1 one-command launcher (macOS / Linux / Windows).

Builds a clean, lockfile-pinned environment, then shows one research run of the SEO Agent:

    1. fetch the pinned Hermes source (sha256 verified)
    2. `uv sync --frozen` into .venv (uv downloads Python 3.12 if missing)
    3. optionally run the Task1 test suite
    4. ask for an Anthropic API key (hidden, never written to disk; Enter = replay a recorded run)
    5. with a key: research 2030.tw live through Hermes and watch it on screen;
       without a key: replay a recorded Hermes run at 20x speed (no model calls, no network)

Usually started through ./start_task1.sh (macOS/Linux) or .\\start_task1.ps1 (Windows),
which install uv when it is missing and then run:

    uv run --no-project --python 3.12 python start_task1.py [--offline] [--test]

Standard library only, so it runs before any dependency is installed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "t1-output"
RECORDED = ROOT / "reports" / "runs" / "seq-r1-20261117-225453"  # Hermes 實跑（Sonnet 5.5）
DEFAULT_MODEL = "claude-opus-5-5"
SITE, KEYWORDS = "https://2030.tw", "娛樂城,3A娛樂城"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")

# Windows 在輸出被導向（CI、Tee-Object）時預設 cp1252，中文會讓 print 直接丟例外
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

UTF8_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def step(n: int, total: int, title: str) -> None:
    print(f"\n==> [{n}/{total}] {title}", flush=True)


def run(cmd: list[str], env: dict[str, str] | None = None, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, env=env, **kwargs)


def must(cmd: list[str], what: str, env: dict[str, str] | None = None) -> None:
    if run(cmd, env=env).returncode != 0:
        sys.exit(f"\n[失敗] {what}。上方是原始錯誤訊息；修正後重跑即可（已完成的步驟會略過）。")


def find_uv() -> str:
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        sys.exit("找不到 uv。請改用 ./start_task1.sh（macOS/Linux）或 .\\start_task1.ps1（Windows），"
                 "它們會先安裝 uv；或參考 https://docs.astral.sh/uv/getting-started/installation/")
    return uv


def ask_api_key(offline: bool) -> str:
    if offline:
        return ""
    key = os.environ.get("SEO_MODEL_API_KEY", "").strip()
    if key:
        print("使用環境變數 SEO_MODEL_API_KEY。")
        return key
    if not sys.stdin.isatty():
        print("非互動環境：改為重播已錄好的 run。")
        return ""
    print("要用真實模型研究 2030.tw 嗎？貼上 Anthropic API key（輸入不會顯示，也不會存檔）。")
    print("真實研究約 10 分鐘、會花 API 額度，只讀公開網頁。取得 API key：https://console.anthropic.com/settings/keys")
    try:
        return getpass.getpass("直接按 Enter = 重播已錄好的 run（不花額度）：").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def watch(run_dir: Path, env: dict[str, str], replay: bool) -> None:
    cmd = [str(VENV_PYTHON), "scripts/watch_run.py", str(run_dir)]
    if not sys.stdout.isatty():
        cmd.append("--plain")  # CI、導向檔案時不用即時畫面
    elif replay:
        cmd += ["--replay", "20"]
    run(cmd, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Task1 one-command launcher")
    parser.add_argument("--offline", action="store_true", help="不問 API key，重播已錄好的 run")
    parser.add_argument("--test", action="store_true", help="建好環境後先跑 Task1 測試")
    args = parser.parse_args()

    if sys.version_info < (3, 11):
        sys.exit("需要 Python 3.11 以上；建議用 start_task1.sh／start_task1.ps1 啟動，uv 會自動準備 Python 3.12。")
    uv = find_uv()
    total = 5 if args.test else 4
    n = 0

    n += 1
    step(n, total, "下載鎖定版 Hermes（驗 sha256；已存在就略過）")
    must([sys.executable, "scripts/fetch_hermes.py"], "下載 Hermes", env=UTF8_ENV)

    n += 1
    step(n, total, "依 uv.lock 建立 .venv（Python 3.12）")
    must([uv, "sync", "--python", "3.12", "--extra", "dev", "--frozen"], "建立環境", env=UTF8_ENV)

    env = dict(UTF8_ENV)
    if args.test:
        n += 1
        step(n, total, "Task1 離線測試（不連網、不呼叫模型）")
        must([str(VENV_PYTHON), "-m", "pytest", "-q"], "Task1 測試", env=env)

    n += 1
    step(n, total, "選擇模式")
    key = ask_api_key(args.offline)

    n += 1
    if not key:
        env.pop("SEO_MODEL_API_KEY", None)
        step(n, total, f"重播已錄好的 run：{RECORDED.relative_to(ROOT)}（Hermes 實跑紀錄；20 倍速）")
        watch(RECORDED, env, replay=True)
        print(f"\n報告全文：{(RECORDED / 'report.md').relative_to(ROOT)}")
        print("要看真實研究：重跑並貼上 API key，或先設定環境變數 SEO_MODEL_API_KEY。")
        return 0

    env["SEO_MODEL_API_KEY"] = key
    env["SEO_MODEL_ID"] = os.environ.get("SEO_MODEL_ID") or DEFAULT_MODEL
    out = OUT / time.strftime("run-%Y%m%d-%H%M%S")
    out.parent.mkdir(exist_ok=True)
    step(n, total, f"用 Hermes 研究 {SITE}（{env['SEO_MODEL_ID']}；輸出到 {out.relative_to(ROOT)}）")
    log = (OUT / f"{out.name}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([str(VENV_PYTHON), "-m", "seo_agent.cli", "run", "--site", SITE, "--keywords", KEYWORDS,
                             "--out", str(out)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    while not (out / "job.json").exists() and proc.poll() is None:
        time.sleep(0.5)
    watcher = None
    if proc.poll() is None:
        cmd = [str(VENV_PYTHON), "scripts/watch_run.py", str(out)] + ([] if sys.stdout.isatty() else ["--plain"])
        watcher = subprocess.Popen(cmd, cwd=ROOT, env=env) if sys.stdout.isatty() else None
    code = proc.wait()
    if watcher:
        try:
            watcher.wait(timeout=10)  # 正常結束時畫面會自己收尾；研究失敗沒有結果檔時才強制關
        except subprocess.TimeoutExpired:
            watcher.terminate()
            watcher.wait()
    elif (out / "result.json").exists():
        watch(out, env, replay=False)
    log.close()
    if code != 0:
        print(f"\n[失敗] 研究結束碼 {code}；完整訊息在 {(OUT / (out.name + '.log')).relative_to(ROOT)}"
              "（常見原因：API key 錯誤或額度不足）。")
    elif (out / "report.md").is_file():
        print(f"\n報告全文：{(out / 'report.md').relative_to(ROOT)}")
    return code


if __name__ == "__main__":
    sys.exit(main())
