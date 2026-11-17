"""Run 1 → Run 3 依序帶經驗（G-32；決策 #26；需求 2.3）。

- Run 1 用空經驗庫（＝初始版本）；Run 2、3 用同一個經驗庫，依序跑。
- 每輪結束、下一輪開始前，一定先做完：評分（evaluation.py）→ 下架判定 → 寫入審核（lifecycle.post_run）。
- 每輪單獨評分（決策 #59）：每輪寫完就更新 rounds.md／rounds.json（每輪自己的 14 項＋說錯幾條＋成本）；
  新發現數（對上一輪）只當參考，上一輪是 untrusted_run 時不拿它當比較基準，那一輪在成績表標「不列入比較」。
- 對照組（同模型不帶經驗）：另開一個 --out 資料夾跑 --rounds 1 --no-direct（模擬用 seo_agent.sim sequence，runner／模型／effort 與主實驗相同）；Run 1 一定從空經驗庫開始。
- 另 1 次直接叫 Opus 對照（scripts/direct_opus.py），在 3 輪之後跑，不和學習的 3 輪混在一起。
- dry-run：不叫模型、不連網，用假 run 走完整個順序，確認步驟與檔案都對。

用法：
  uv run python -m seo_agent.sequence --dry-run          # 乾跑（離線）
  uv run python -m seo_agent.sequence [--rounds 3]       # 實跑（會打 2030.tw 與模型；需使用者另行決定）
  uv run python -m seo_agent.sequence --continue --rounds 1 --out <同一資料夾>  # 接在已完成的輪次之後（決策 #52）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from . import ROOT
from .evaluation import evaluate, round_table
from .experience import ExperienceStore
from .lifecycle import post_run

RunFn = Callable[[int, Path, Path], Path]  # (第幾輪, 經驗檔, 這組實驗的資料夾) → 這輪的 run 資料夾


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


LEGACY_META = {"runner": "claude"}  # 決策 #57 之前的模擬序列沒記 runner，都是 claude


def _resume_state(out_dir: Path, store_path: Path, meta: dict) -> tuple[list, int, Path]:
    """接續（決策 #52）：只能接在「完整結束的那一輪」之後，且經驗庫、執行方式都要和上次一致。"""
    seq = out_dir / "sequence.json"
    if not store_path.exists() or not seq.exists():
        raise FileNotFoundError(f"找不到可接續的經驗庫或 sequence.json：{out_dir}")
    old = json.loads(seq.read_text(encoding="utf-8"))
    steps = old["steps"]
    research = [s for s in steps if s["step"] == "research"]
    if not research or not any(s["step"] == "post_run" and s["round"] == research[-1]["round"] for s in steps):
        raise RuntimeError("上次最後一輪沒有完整結束（缺下架判定／寫入審核），不能接續")
    for k, v in meta.items():
        if old.get(k, LEGACY_META.get(k)) != v:
            raise RuntimeError(f"執行方式不一致，不能接續：{k} 上次是 {old.get(k)!r}，這次是 {v!r}")
    if old.get("experience_sha256") != _sha(store_path):
        raise RuntimeError("經驗庫在上次最後一輪結束後被改過（可能是中斷在半輪中間），不能接續")
    start = research[-1]["round"] + 1
    # 只對 dry／sim 有效（run 資料夾在 out_dir 裡）；實跑每輪開新 run_id，中斷時靠上面的經驗庫 sha 擋
    leftover = [d.name for d in out_dir.iterdir() if d.is_dir() and d.name.endswith(f"-r{start}")]
    if leftover:
        raise RuntimeError(f"第 {start} 輪的資料夾已存在（上次可能中斷在這輪）：{leftover}")
    bad = {s["round"] for s in steps if s["step"] == "evaluate" and s.get("untrusted_run")}
    trusted = [s for s in research if s["round"] not in bad]
    return steps, start, (Path(trusted[-1]["run_dir"]) if trusted else None)


def run_sequence(rounds: int, *, run_fn: RunFn, out_dir: Path, direct_fn: Callable[[Path], object] | None = None,
                 log: Callable[[str], None] = print, resume: bool = False, meta: dict | None = None) -> dict:
    """依序跑 rounds 輪。resume=True 時接在同一個 out_dir 已完成的輪次之後，再加 rounds 輪。"""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    store_path = out_dir / "experience" / "candidates.jsonl"
    meta = meta or {}
    if resume:
        steps, start, prev = _resume_state(out_dir, store_path, meta)
    else:
        if store_path.exists():
            raise FileExistsError(f"經驗庫已存在，Run 1 必須從空經驗開始：{store_path}")
        steps, start, prev = [], 1, None
    store = ExperienceStore(store_path)

    def write() -> dict:
        done = [s["round"] for s in steps if s["step"] == "research"]
        summary = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **meta, "rounds": len(done),
                   "experience": str(store_path), "experience_sha256": _sha(store_path), "steps": steps}
        (out_dir / "sequence.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str),
                                               encoding="utf-8")
        round_table(out_dir)
        return summary

    for i in range(start, start + rounds):
        active_before = [e["id"] for e in store.active()]
        log(f"Run {i}：開始（帶入使用中經驗 {len(active_before)} 條）")
        run_dir = Path(run_fn(i, store_path, out_dir)).resolve()
        steps.append({"round": i, "step": "research", "run_dir": str(run_dir), "experience_in": active_before})
        ev = evaluate(run_dir, prev_run_dir=prev)
        steps.append({"round": i, "step": "evaluate", "total": ev["total"], "marks": ev["marks"],
                      "wrong_count": ev["wrong_count"], "untrusted_run": ev["untrusted_run"],
                      "new_findings": ev["new_findings"]})
        lc = post_run(run_dir, store)
        steps.append({"round": i, "step": "post_run", "judgement": lc["judgement"].get("status"),
                      "audit": lc["audit"].get("status"), "active_after": [e["id"] for e in store.active()]})
        log(f"Run {i}：評分 {ev['total']:g}/{ev['max']}，下架判定與寫入審核完成，使用中經驗 {len(store.active())} 條")
        if not ev["untrusted_run"]:  # 不可信的那一輪不當下一輪的比較基準（決策 #59）
            prev = run_dir
        write()  # 每輪結束就存，中斷後可從這輪之後接
    if direct_fn is not None and not any(s["round"] == "direct" for s in steps):  # 對照組只跑一次
        log("對照組：直接叫 Opus 1 次")
        steps.append({"round": "direct", "step": "direct", "out": str(direct_fn(out_dir))})
    return write()


def live_run_fn(i: int, store_path: Path, out_dir: Path) -> Path:
    from .runner import new_run_id, run_isolated
    run_id = new_run_id(f"seq-r{i}")
    run_isolated("research", run_id, {"total_minutes": 120, "max_iterations": 400, "fetch_delay_s": 1.5,
                                      "experience_path": str(store_path)}, timeout_s=9000)
    return ROOT / "reports" / "runs" / run_id


def live_direct_fn(out_dir: Path) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "direct_opus.py")], cwd=ROOT).returncode


def dry_run_fn(i: int, store_path: Path, out_dir: Path) -> Path:
    """假 run：寫出一份最小但格式正確的報告、呼叫紀錄與經驗提案，不叫模型、不連網。"""
    from .tools.context import Context
    run_dir = out_dir / f"dry-r{i}"
    ev = Context(run_dir).store.add(f"dry-run {i}".encode(), source="dry-run", tool="dry_run", kind="fixture")["id"]
    read = [e["id"] for e in ExperienceStore(store_path).active()]
    claim = {"id": "S1", "text": f"第 {i} 輪乾跑的結論（假資料）", "kind": "fact", "evidence_ids": [ev]}
    rep = {"summary": "", "onpage": [claim], "offpage": [], "actions": [], "unknowns": [], "strategy": [claim]}
    (run_dir / "report.json").write_text(json.dumps({"report": rep, "meta": {"experience_read": {"entry_ids": read}}},
                                                    ensure_ascii=False), encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps({"status": "dry_run", "started_at": time.time(), "metrics": {}}),
                                         encoding="utf-8")
    return run_dir


def check_continue_args(ap: argparse.ArgumentParser, a: argparse.Namespace) -> None:
    if a.resume and (a.out is None or a.rounds is None):
        ap.error("--continue 必須同時給 --out（上次的資料夾）與 --rounds（再加幾輪）")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rounds", type=int, default=None, help="要跑幾輪（預設 3；--continue 時是再加幾輪，必填）")
    ap.add_argument("--dry-run", action="store_true", help="離線乾跑，不叫模型、不連網")
    ap.add_argument("--continue", dest="resume", action="store_true", help="接在 --out 已完成的輪次之後（決策 #52）")
    ap.add_argument("--no-direct", action="store_true", help="不跑直接叫 Opus 的對照")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    check_continue_args(ap, a)
    tag = "dry" if a.dry_run else "live"
    out = a.out or ROOT / "reports" / "sequence" / f"{tag}-{time.strftime('%Y%m%d-%H%M%S')}"
    direct = None if a.no_direct else ((lambda d: "（乾跑：略過直接叫 Opus）") if a.dry_run else live_direct_fn)
    summary = run_sequence(3 if a.rounds is None else a.rounds, run_fn=dry_run_fn if a.dry_run else live_run_fn, out_dir=out,
                           direct_fn=direct, resume=a.resume, meta={"runtime": tag})
    print(json.dumps({"out": str(out), "steps": len(summary["steps"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
