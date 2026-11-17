#!/usr/bin/env bash
# Demo：用 Hermes 實跑 1 輪（帶評分與經驗寫入審核），同時在畫面上即時顯示研究過程。
# 用法：scripts/live_demo.sh [輸出資料夾，預設 reports/sequence/hermes-live]
set -u
cd "$(dirname "$0")/.."
OUT="${1:-reports/sequence/hermes-live}"
mkdir -p "$(dirname "$OUT")"
LOG="$OUT.log"
MARK=$(mktemp)  # 只認這次之後才建立的 run 資料夾

uv run python -m seo_agent.sequence --rounds 1 --no-direct --out "$OUT" >"$LOG" 2>&1 &
SEQ=$!

RUN=""
while [ -z "$RUN" ] && kill -0 "$SEQ" 2>/dev/null; do
  sleep 1
  RUN=$(find reports/runs -maxdepth 2 -name job.json -path '*seq-r1*' -newer "$MARK" 2>/dev/null | head -1 | xargs -I{} dirname {})
done
rm -f "$MARK"
[ -n "$RUN" ] && uv run python scripts/watch_run.py "$RUN"

echo
echo "研究結束，程式接著做凍結評分與經驗寫入審核……"
wait "$SEQ"; CODE=$?
if [ -n "$RUN" ]; then
  clear
  uv run python scripts/watch_run.py "$RUN" --plain | tail -n 28
fi
echo
[ "$CODE" -eq 0 ] && echo "✓ 全部完成：$OUT" || echo "✗ 結束碼 $CODE，完整訊息在 $LOG"
