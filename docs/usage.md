# 進階使用：手動命令、輸出檔、專案結構

一鍵啟動見 [README](../README.md#1-快速開始)。這裡是逐步命令與檔案說明。

## 手動命令（逐步）

```bash
# 1. 安裝。Hermes 只能 editable 安裝，原始碼放在 vendor/hermes-agent（不進 git）；
#    先用腳本下載 v2026.9.24、commit f97608f 的 tarball 並驗 sha256，再安裝
python3 scripts/fetch_hermes.py
uv sync --extra dev

# 2. 金鑰：複製後填入 SEO_MODEL_API_KEY（.env 已被 git 忽略）
cp .env.example .env
#    或改用訂閱登入：.env 設 SEO_MODEL_AUTH=oauth，再登入一次（登入檔在 .hermes-auth/，不進 git）
#    uv run python -m seo_agent.hermes_home && HERMES_HOME=.hermes-auth uv run hermes auth add anthropic

# 3. 離線測試（不連網、不叫模型）
uv run pytest -q

# 4. 最小證明：Hermes 叫 Opus 呼叫 1 個 Tool（需要金鑰或登入，會花額度）
uv run python scripts/smoke_hermes_opus.py

# 5. 研究一次（第 1–7 步；會連 2030.tw 與模型；--refresh 強制重抓網站底稿）
uv run python -m seo_agent.cli run --site https://2030.tw --keywords 娛樂城,3A娛樂城 --out reports/runs/<run_id>

# 6a. 程式評分（凍結 grader）：成本、待修處理結果、參考用 14 項與程式判錯數
uv run python -m seo_agent.evaluation reports/runs/<run_id> --prev reports/runs/<上一輪>
#     依序實驗的每輪對照表（rounds.md；untrusted_run 標「不列入比較」）
uv run python -m seo_agent.evaluation --table reports/sequence/<資料夾>
# 6b. 主分數（可信 SEO 技術數）不是命令：由 Grader Agent 照 eval/README.md 的做法核對

# 7. 經驗：下架判定＋寫入審核（要先跑 6a）
uv run python -m seo_agent.lifecycle reports/runs/<run_id>

# 8. 人工下架一條經驗
uv run python -m seo_agent.experience reject EXP-001 "理由"
```

其他命令：

- 連網測試：`uv run pytest -m live`
- 依序帶經驗跑 3 輪＋One Shot 對照 1 次（每輪自動做完評分、下架判定、寫入審核）：
  - 乾跑（不叫模型）：`uv run python -m seo_agent.sequence --dry-run --out reports/sequence/dry-test`
  - 實跑：`uv run python -m seo_agent.sequence --rounds 3 --out reports/sequence/<名稱>`
  - 批次實驗（sim 執行器）：`uv run python -m seo_agent.sim sequence --rounds 3 --model sonnet --minutes 120 --out reports/sequence/<名稱>`
  - 接著再加輪：在原命令加 `--continue --rounds <再加幾輪>`。
    - 限同一個資料夾、同一種跑法與模型，只能接在完整結束的那一輪之後。
    - 例：`uv run python -m seo_agent.sim sequence --continue --rounds 1 --model sonnet --out reports/sequence/<名稱>`
  - 換執行者（Codex CLI／Antigravity CLI；同一套 Tool 與審查）：
    - 加 `--runner codex` 或 `--runner agy`，必須給 `--model`，並加 `--no-direct`（不跑 One Shot）。
    - 例：`uv run python -m seo_agent.sim sequence --runner codex --model <模型> --effort high --rounds 1 --no-direct --out reports/sequence/<名稱>`
    - `--continue` 時換 runner 會被拒絕。
- 評分器先證明會抓錯：`uv run pytest tests/test_grader.py -q`
- 評分規則凍結檢查：`shasum -a 256 -c eval/FROZEN.sha256`

每個 run 的輸出都在 `--out` 資料夾：

| 檔案 | 內容 |
|---|---|
| `report.md`／`report.json` | 5 段報告（開頭標網站底稿的 hash 與抓取時間） |
| `report_incomplete.md`／`.json` | 中斷或時間到時的未完成報告，附讀過／還沒讀過的分區 |
| `report_draft.json` | 第 4 步初稿 |
| `data_card.md` | 資料卡 |
| `board.json` | 程式產生的進度摘要（證據數、呼叫數、填了 why 的次數）；給人看，模型不讀 |
| `evidence.jsonl`＋`raw/` | 證據原檔與 sha256 |
| `tool_calls.jsonl` | 每次 Tool 呼叫（含選填的 `why`） |
| `review.json` | 第 5 步 Reviewer Agent 的待修清單 |
| `review_outcomes.md` | 待修清單每項的處理結果（評分時產生） |
| `experience_proposals.jsonl`／`route_summary.json` | 第 7 步寫下的路線／路線摘要 |
| `experience_judgement.json`／`experience_audit.json` | 下架判定（經驗有沒有用到、被推翻）／寫入審核結果 |
| `evaluation.json`／`result.json` | 凍結 grader 評分／run 摘要 |
| `approvals_pending.jsonl` | 被擋下、等人工批准的動作 |

## 一次 run 的每一步與輸出檔

比喻：像偵探接案。助理先把公開資料整理成一張卡（第 2 步），偵探自己決定先查什麼、查多深（第 3 步），助理只在旁邊報時、提醒「哪些區還沒看過」；報告寫完先給另一個人挑毛病（第 5 步），修好才交（第 6 步），最後把「哪條路好走、哪條路別走」記進筆記本（第 7 步）。筆記要等事後有人核過（評分＋審核），下次才拿得到。

**run 內（`cli run` 一條命令自動跑完 1–7）：**

| 步驟 | 誰 | 輸出檔 | 自動／手動 |
|---|---|---|---|
| 1 接案 | 程式：讀任務文字與使用中經驗 | `system_prompt.md`、`message.md` | 自動 |
| 2 網站底稿 | 程式：抓 robots／sitemap／Wayback／首頁選單／WHOIS 與兩個關鍵字搜尋，只抓不判讀；每個網站只建一次 | `baselines/<網域>/`、`data_card.md` | 自動（`--refresh` 強制重抓） |
| 3 研究 | 模型＋Hermes：自己用 7 個 Tool 查，每次呼叫可附 `why` | `evidence.jsonl`＋`raw/`、`tool_calls.jsonl`、`board.json` | 自動 |
| 4 初稿 | 模型：`submit_report` | `report_draft.json` | 自動 |
| 5 審查 | Reviewer Agent：沒有 Tool，只看報告與引用證據，挑錯 | `review.json`（待修清單） | 自動 |
| 6 定稿 | 模型依待修清單修一次（可先補查）；程式做格式檢查 | `report.md`／`report.json`（沒交成時 `report_incomplete.md`） | 自動 |
| 7 寫經驗 | 模型：`experience` 提出 0–3 條路線 | `experience_proposals.jsonl`、`route_summary.json` | 自動 |

**run 外（經驗要走完這段才會變成使用中）：**

| 步驟 | 誰 | 輸出檔 | 自動／手動 |
|---|---|---|---|
| 評分 | 凍結 grader（`evaluation.py`）：成本、參考用 14 項、程式判錯數、待修處理結果 | `evaluation.json`、`review_outcomes.md` | 手動命令 6a；`sequence` 自動 |
| 經驗下架判定＋寫入審核 | 程式（`lifecycle.py`、`audit.py`），讀凍結 grader 的判錯 | `experience_judgement.json`、`experience_audit.json`；通過的寫進 `experience/` | 手動命令 7；`sequence` 自動 |
| 可信 SEO 技術數（主分數） | Grader Agent 遮名盲評 | 評分紀錄（例：`docs/research/credible-rescore/`） | 手動派 Agent；**不影響經驗** |

- `sequence` 命令會依序跑完「run → 評分 → 下架判定＋寫入審核」，再開下一輪。
- 經驗的下架與寫入只看凍結 grader 的判錯（可重現、不花額度），不看 Grader Agent 的分數。

## 專案結構

```
src/seo_agent/
  cli.py, runner.py, worker.py           # 入口；每個 run 一個獨立子程序
  hermes_bridge.py, hermes_home.py       # Hermes 串接、獨立 HERMES_HOME
  baseline.py                            # 第 2 步網站底稿
  research.py, skill/SKILL.md            # 研究任務、提示與規則（Skill）
  tools/                                 # 7 個 Tool（tools/page_text.py：inspect_page 附頁面文字）
  coverage.py                            # why 欄、sections_not_yet_read
  evidence.py, board.py                  # 證據庫、進度摘要 Board
  stop.py                                # 停止條件 A、B＋時間回饋
  review.py, checks.py, report.py        # 第 5 步 Reviewer Agent、程式檢查、5 段報告
  experience.py, audit.py, lifecycle.py  # 經驗、寫入審核、下架判定
  evaluation.py, metrics.py, grader.py   # 凍結 grader 評分與過程數字
  sequence.py, sim.py                    # 依序實驗、sim 執行器
  decompose.py                           # 歷史實驗（舊拆題法），不在主流程
config/autonomy.json                     # Autonomy Boundary
eval/                                    # 凍結的評分規則與校準報告
baselines/                               # 網站底稿（每站一份）
experience/                              # 使用中經驗（candidates.jsonl、notes.md）
tests/                                   # 離線測試（live 測試要加 -m live）
docs/                                    # 架構圖、AI 開發紀錄、建置紀錄、實驗紀錄
scripts/fetch_hermes.py                  # 取得鎖定版 Hermes（clone 後第一步）
.github/workflows/ci.yml                 # CI：lint＋離線測試
reports/                                 # 每個 run 的輸出、評分、日誌
```
