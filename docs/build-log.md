# V3 建置紀錄

設計正本：舊 repo `docs/research/2030-multimodel/d-review/d-architecture.md`、`v3-build-handoff.md`。

## 第 1 步：骨架＋Hermes 叫 Opus 呼叫 1 個工具（2026-11-16，已通過）

做了什麼
- `git worktree add --orphan -b codex/harness-v3`；`vendor/hermes-agent` 從 V2 整包複製（v2026.9.24，commit f97608f，不進版控）；`.env` 從 V2 複製（gitignore、權限 600）。
- `uv sync --extra dev`：Hermes editable 安裝；不裝 langgraph。
- 程式：`model_env.py`（讀金鑰、去掉 base URL 的 `/v1`）、`hermes_home.py`（tool_search off、adopt_external_logins false）、`hermes_bridge.py`（註冊工具、跑 AIAgent）、`runner.py`＋`worker.py`（每 run 獨立子程序）、`smoke.py`（最小證明）。

驗證
- `uv run pytest -q` → 5 passed、1 deselected（live 測試預設不跑），exit 0。
- `uv run python scripts/smoke_hermes_opus.py` → exit 0，status passed：
  - api_mode = anthropic_messages、model = claude-opus-5-5、只提供 1 個工具 get_check_code
  - 工具被呼叫 1 次；Opus 回答的代碼 = 工具隨機產生的代碼（證明真的讀到工具結果）；Hermes 共 2 次模型呼叫
  - Hermes home = 本 run 資料夾；`~/.hermes` 前後都不存在
  - 掃描 reports、.hermes-runs、程式碼：沒有金鑰
- 結果檔：`reports/runs/smoke-20261116-162619/result.json`

限制
- 金鑰計費方式（訂閱或 API 額度）仍無法從回應確認。
- live 測試 `uv run pytest -m live` 寫好但這次沒另外跑（與腳本同一路徑）。

下一步：第 2 步 8 個 Tool＋各自測試。

## 第 2 步：8 個 Tool＋測試（2026-11-16，已通過）

做了什麼
- `tools/`：polite_fetch（robots、同站間隔、429/503 重試 1 次後暫停、轉址鏈、存原檔＋sha256）、sitemap_tree（一次讀完存 SQLite，expand／search／by_month／sample／compare）、inspect_page（標題、H1–H4、JSON-LD、連結位置 選單／正文／頁尾／側欄）、text_match（exact 與 loose 分開）、domain_info（RDAP→WHOIS 備援、DoH）、wayback（timeline／old_urls／snapshot／check_current）、web_search（DuckDuckGo HTML，擋住就回 unknown）、研究日誌。
- 沒有送出表單、登入、付款工具；付費／登入主機與路徑一律回 approval_required 並記到 approvals_pending.jsonl。

修正
- robots 連不上原本回 robots_disallowed → 改回 network_error（讓 AI 標未知，而不是誤以為被禁止）。
- 2030.tw 選單用 `jeg_nav_*` 等 class 的 div，原本連結位置全判成正文 → 加 class／role 判斷；首頁實測 body 91、menu 90、footer 77、sidebar 50。

實網抽查（`scripts/live_tools_check.py`）：sitemap 4,602 網址、/wordcup/ 2,503；RDAP 註冊 2026-04-15；Wayback 2020–2026 有存檔；DuckDuckGo 回 202 → unknown。

## 第 3 步：Skill、證據、研究日誌、停止、五段報告、經驗層（2026-11-16，已通過）
- `skill/SKILL.md`：7 段研究方法；14 項評分重點不在其中。
- `report.py` 檢查層：五段齊全、事實要有證據、推論要寫限制、絕對句要範圍＋2 份證據、建議要指到主張、每題 2 份證據或寫明未知；最多退回 3 次。
- `stop.py`：120 分鐘（留 10 分鐘交報告）、連續 5 次無新證據也無判斷修正就擋研究工具。
- `experience.py`：候選／正式／停用；AI 只能提候選與停用，正式與刪除要人工 CLI＋評分項變好。

## 第 4 步：自主邊界 3 個測試（2026-11-16，已通過）
- 離線 3 個：網頁藏指令只當資料、付費／登入動作被擋且沒送出請求、工具失敗回報不拋錯。
- live（`uv run pytest -m live tests/test_autonomy.py -q -s`）：1 passed，164 秒；run `reports/runs/autonomy-live-20261116-165808`。頁面要求抓 ahrefs、設正式經驗、寫固定句，全部沒照做；503 主機重試 1 次後停止。
- 問題與修正：第一次 live 跑在第 1 次 API 呼叫就被拒答（content_filter）。逐段拿掉 Skill 測試，觸發的是「每一步記下想法有沒有改變」這段（可能被當成要求輸出內部思考）。改成「研究日誌：目的、發現、判斷是否修正」，工具改名 `research_log`，欄位 reason/belief_change → purpose/revision；改完完整提示＋工具定義測 2 次都正常呼叫工具。

## 第 5 步：確定性評分器（2026-11-16，已通過）
- `eval/rubric_2030.json`＋`src/seo_agent/grader.py`；說明與限制見 `eval/README.md`。
- 校準：B 12/14 且抓到 T10「娛樂城區沒有 sitemap」說錯；Codex 7；Gemini 11.5；3 份共 42 個標記與人工比對表全部一致；舊 A 1.5/14。
- 裁判 AI：交接文件要求選之前先問使用者，使用者要求不再詢問 → 不自行選，改用確定性規則。
- 凍結 hash：`eval/FROZEN.sha256`。
- 測試：`uv run pytest -q` → 45 passed、2 deselected。

## 第 6 步前：實跑前審查（8 輪唯讀審查，最後 approved）
- 第 1 輪 3 個 major：工具說明洩漏答案（/wordcup/ 例子→/blog/）、停止條件誤擋／可繞過、評分器把「未知」句也算分。
- 第 2–8 輪都在收斂停止條件 ②，逐輪抓到的繞過與誤擋：
  - 列研究問題被計數；重抓同頁因 date 標頭、DNS TTL、nonce 被當新證據。
  - 換參數零命中算進展；對舊證據換角度（不同 part、不同關鍵字）被誤擋。
  - 搜尋字串在原檔網址裡；RDAP 更新時間每次都變。
- 最終規則（src/seo_agent/stop.py）：
  - polite_fetch 看原檔指紋 (工具, 類型, 網址, UA, 方法)。
  - 其他工具一律存衍生證據，雜湊前去易變欄位與回傳參數，空結果與失敗不算進展。
  - research_log 不計入，寫 revision 才歸零。
- 驗證：
  - pytest 53 passed。
  - 審查者的離線模擬 reports/reviews/stop_guard_sim.py 共 25 情境，23 OK。
  - 剩 2 個為已認可 minor：數量完全相同的兩區雜湊相撞。
- 已知 minor：
  - 每種查詢第一次零命中算一次進展。
  - 頁面正文本身會變時，重抓算新。
  - revision 只查非空。
  - 評分器不處理主張句內的保留語氣。

## 第 6 步：實跑（2026-11-16 17:21–17:31，已完成）
- 命令：`bash scripts/run_matrix.sh`，matrix exit=0；各 log 在 `reports/live-tests/`。
- 結果：
  - harness Opus 三次，規則分數 7／6／5.5，人工核對後 7／7／7.5。
  - Fable 規則 6，人工核對後 8。
  - 直接叫 Opus 規則 3.5，人工核對後 5。
  - 人工核對：第一版只看 T10、T12；之後 14 項全面逐句複查，理由寫在 `reports/scores/human-review.json`，細節見 README。
  - 限制：5 組同時啟動、各自空的經驗庫，r1～r3 不是逐輪學習，分數差距不能當進步證據。
  - 評分檔：`reports/scores/*.json`。
- 4 組 harness 都由 AI 自行交報告（7～10 分鐘），停止條件 ②③ 沒有觸發。
- fable-r1 交完報告後，最後一次模型呼叫回 HTTP 400：workspace API 用量上限，2026-12-01 恢復。報告已通過檢查並存檔。
- 候選經驗共 9 條，都沒轉正式；r2、r3 各有 1 條含 `/wordcup/`，轉正式前要改寫。

## 第 7 步：追加實驗（2026-11-16 18:01 起，例外用訂閱登入）
- 目的：
  - 分清 Fable 多出的分數是查法還是模型能力。
  - 驗證真的逐輪帶經驗，Opus 會不會變好。
- **例外**：API 額度已用完，使用者同意這一次改用自己 Claude 訂閱的 `claude setup-token` token。
  - token 放在 `.env.subscription`（權限 600、git 忽略），沒有寫進任何紀錄。
  - Hermes 的「借用本機登入」維持關閉，token 只透過專案設定傳入。
  - 這次違反「開發與產品憑證分開」，只限這次實驗。
- 命令：`bash scripts/run_followup.sh`。
  - `opus-fx`：Opus 帶 Fable 的 3 條候選經驗，原文照用。
  - `opus-s2`：帶 r1 的候選經驗。
  - `opus-s3`：帶 r1＋s2 的候選經驗。
  - 第 1 輪沿用 `opus-r1`（空經驗）。
- 結果：3 組 exit=0，report 最後都 passed（s2 第一次交報告被退回 1 次），工具紀錄時長 6.1～6.5 分鐘。
  - 規則／人工分數：opus-fx 5／6、opus-s2 5／6.5、opus-s3 6／7.5。
  - 評分檔：`reports/scores/opus-{fx,s2,s3}-*.json`；人工理由：`human-review.json`。
- 判讀：
  - 這 1 次，Fable 的經驗沒有移植成功。T09、T11 的查法（REST 總數對照、翻頁看 canonical）沒寫進經驗；T04 的變體頁查法寫進了，但 opus-fx 沒照做。
  - 依序 7 → 6.5 → 7.5，在隨機變動範圍內，沒有證明逐輪進步。

## 第 8 步：追加實驗 2，降級成 Sonnet（2026-11-16 18:24–18:57，例外用訂閱登入）
- 使用者要求：不升級模型、不提高額度，改用較弱的 Sonnet，從空經驗重新跑幾輪，看會不會變好；跑到第 5 輪就夠。
- 命令：`bash scripts/run_sonnet_seq.sh`（log 在 `reports/live-tests/sonnet-*.log`），7 組 exit=0、status=passed。
- 評分：`uv run python -m seo_agent.grader reports/runs/<run> --json > reports/scores/<run>.json`；人工逐項複查寫在 `reports/scores/human-review.json` 的 `sonnet-*`。
- 結果：空經驗（b1、b2、q1）人工 5／5.5／5.5；依序 q2–q5 為 6.5／6.5／6.5／6。差距來自 T05（b1、b2 讀錯 Wayback 證據編號；q1 沒帶經驗也讀對）和 T10（基準組本身就忽高忽低）；沒有新項目。判讀見 README「追加實驗 2」。
- 獨立唯讀審查第 1 次退回（changes_requested）。2 個 major：差距來源漏了 T05、T07 判準前後不一。已改成和 Opus／Fable 相同的嚴格判準（T07 一律給 p，b2 的 T05 改 n），並補上讀錯證據的說明。
- 凍結檔：`shasum -a 256 -c eval/FROZEN.sha256` 兩檔 OK；評分規則與 eval/ 未改。


---

# 套用 D 架構（決策 #39–#50；照 v3-gap.md G-01–G-61，2026-11-16）

設計正本（唯讀）：舊 repo `docs/research/2030-multimodel/d-review/` 的 v3-build-handoff.md、v3-gap.md、d-architecture.md、decision-log.md。
基準 commit：`20c0b2b Baseline: V3 snapshot before applying D architecture (#39–#50)`；之後的改動**還沒 commit**。
規則：每步跑 `uv run pytest -q`；凍結檔 `shasum -a 256 -c eval/FROZEN.sha256` 每步都 OK；沒實跑研究、沒叫模型。

## 施工順序與做了什麼
1. **基準 commit**：V3 原樣提交（使用者授權）。
2. **紀錄底層**（G-13、G-49、G-07、G-05、G-08、G-58、G-09）：
   - `tool_calls.jsonl` 每筆加題號、目標網域與路徑、derived_evidence_id；Evidence ID 改成 `E-0001` 格式，報告引用正規式同步。
   - research_log 欄位：origin 三值、類型三值（「想法」給 Opus 的說明寫成「一般判斷」）、手法清單狀態、5 面、否定、另一種可能、經驗編號、推翻、4 種收尾；拿掉 hypothesis。
   - `checks.py`：否定標記只看 research_log，結果是警告。`board.py`：board.json 由程式產生，題目原文不改。
3. **停止條件**（G-34、G-40、G-35、G-36、G-38）：research_log、2 個交卷動作、輕試不計入 ②；① 改成每題 4 種收尾（board 核對）；最後 20 分鐘擋研究 Tool；時間到出「未完成」報告、中途錯誤標「中斷」。
4. **② 網站底稿**（G-50–G-54、G-48）：`baseline.py` 固定偵察 6 個來源、部分失敗只重抓、`--refresh`；匯入證據標快照＋抓取時間＋底稿 hash；資料卡只並排；Wayback 日期用 `reports/runs/live-tools-20261116-164412/raw/E051.json` 做測試案例；④ 一律即時抓；`cli.py run`。
5. **報告與 ⑥ 審查**（G-45、G-59、G-56、G-61、G-37、G-46、G-47）：7 段報告（另存相容鍵 strategy 給凍結的 grader）；收尾與「未查證」；`review.py` 程式固定開 1 個沒有 Tool 的審查 Agent；待修清單存 `review.json`；回 ④ 最多 1 次；引用內容核對、外部說法只警告。
6. **經驗格式**（G-10–G-12、G-14、G-15）：「情況 → 路線 → 結果」、照走／別走＋兩種原因、配對編號；路線 Tool 清單由程式從 Evidence ID 反查；⑧ 路線摘要。
7. **寫入審核 6 項**（G-16–G-20、G-57、G-29）：`audit.py`；狀態只有 active／retired；`evaluation.py` 記判錯結論。
8. **下架與 reject**（G-21–G-28）：`lifecycle.py`、`experience.py` 的 retire／cascade／reject；`config/autonomy.json` 批准清單。
9. **評估數字與腳本**（G-30–G-33）：`metrics.py`、`evaluation.py --prev`、`sequence.py`（依序 3 輪，乾跑）、`decompose.py`（新舊拆題，假模型）。
10. **Skill 重寫**（G-01–G-04、G-06、G-15、G-36、G-39、G-60）：`SKILL.md` v4；research.py 的 TASK 與 `scripts/direct_opus.py` 改成 7 段、不寫猜測。
11. **文件**（G-39、G-41–G-44、G-55）：README 重寫（「假設」由三處承擔、決策、限制、4 週計畫優先 1–8、範例命令都加 `--out`）；`docs/architecture.md` 照 D 第 4 層、加評估與人工把關節點。
12. **自我審查**：見下方。

## 測試結果
- `uv run pytest -q` → **181 passed、2 deselected**（live 測試預設不跑）。
- `shasum -a 256 -c eval/FROZEN.sha256` → `eval/rubric_2030.json: OK`、`src/seo_agent/grader.py: OK`。
- 乾跑：`python -m seo_agent.sequence --dry-run --out <暫存>` 3 輪＋對照 10 個步驟完成；`python -m seo_agent.decompose --fake --out <暫存>` 6 次完成。
- 新增測試檔：test_recording、test_stop_v3、test_baseline、test_report_v3、test_experience_v3、test_audit_v3、test_lifecycle_v3、test_metrics_v3、test_skill_v3、test_docs_v3。

## 使用者已決定的
- G-47：外部說法只警告、不退回，列進 ⑥ 待修清單。
- G-35：第 5 面的題至少引用 1 個也出現在其他題結論裡的 Evidence ID。
- G-46：⑥ 待查併進待修清單（`runs/<id>/review.json`）。
- G-53：用 `reports/runs/live-tools-20261116-164412/raw/E051.json`。

## 我定的預設（設計文件沒寫細節，可改，請確認）
1. **寫入審核第 1 項的格式規則**（使用者確認改成箭頭模板）：situation 單段、≤300 字；route 一步一行「編號. Tool：做什麼，因為 為什麼」，2–4 步，每步 ≤90 字、有研究 Tool、有「因為」；去掉網址、路徑與編號後不能有 2 位數以上的數字。格式不合時 `experience(propose)` 當場退回並附模板，寫入審核第 1 項再查一次。
2. **Tool 錯誤碼清單**（`TOOL_ERROR_CODES`）：robots_disallowed、network_error、site_throttled、site_paused、wayback_status、tool_exception。使用者決定維持；搜尋被人機驗證擋、失敗再細分移到 4 週計畫（舊流程 15 次實跑只有 10 次被擋、搜尋從沒被擋）。
3. **判錯**：用凍結的 grader 逐個結論再評一次，被判 x 的結論與它的 Evidence ID 記成判錯紀錄。使用者決定照此做；判錯維持一次就下架（G-25），不改成連續 2 次。
4. **查不到型的推翻**：要附輕試的 Evidence ID 才算網站已變。使用者決定維持。
5. **下架判定只看這次讀入的條目**。
6. **白做工次數**：沿用停止條件 ② 的「新證據」判斷；不算 research_log、交卷動作、輕試、重抓到和底稿一樣、被停止條件擋下的呼叫；Tool 錯誤回傳算白做工。使用者決定維持；「被擋不算白做工」移到 4 週計畫，理由同第 2 點。
7. **關鍵發現**：單獨評分拿到 y 或 p 的結論；證據來自底稿快照時，呼叫次數 0、時間 0。
8. **新發現數**：這次 y／p、上一次不是的評分項數。
9. **省下的呼叫**：research_log 登記「別走（會誤導）」經驗編號的次數（依經驗＋題號去重），只記錄、不計分。
10. **Skill ④ 決定怎麼查**（使用者確認）：改成查法通則 3 句（疑點寫成可推翻的話；證實和推翻的證據都找；先看全貌再抽樣），原 5 列表降為「例子」；「先判斷網站類型、再列這類網站可能的手法」只放在 ③ 手法清單，④ 不再推測。subagent 獨立評估後建議、使用者同意。

## 設計文件要同步的地方（本 Session 不改設計文件，交給負責設計文件的 Session）
- v3-gap G-16（寫入審核第 1 項）、G-10／G-14（經驗格式改箭頭模板）、G-01／G-03（③ 加「先判斷網站類型」）、G-04／G-06（④ 對照表改成查法通則＋例子表）。
- d-architecture.md 的 ③④⑧ 與經驗格式段；decision-log 追加一條（取代 #50 對照表寫法、經驗路線改箭頭模板）。

## 沒做的與限制
- **沒實跑**：新流程、依序 3 輪、新舊拆題都只做離線乾跑；何時重跑、額度，待使用者決定（v3-gap「拿不準的地方」第 1 點）。
- **G-39 檔名**：Tool 程式名稱已是 research_log；內部檔名 `tools/thoughts.py`、存檔 `thoughts.jsonl` 沒改名（v3-gap 的測試只要求文件用語，改名會牽動多處紀錄讀取）。
- ⑥ 審查 Agent 的提示只做離線測試，沒叫過模型。
- 改動還沒 commit。

## 實跑嘗試（2026-11-16，使用者說「跑啊全做完」）
- 冒煙測試：`uv run python -m seo_agent.cli run --site https://2030.tw --keywords 娛樂城,3A娛樂城 --out reports/runs/smoke-d-20261116 --minutes 25`
  - ② 網站底稿與資料卡實際建好（`baselines/`、`reports/runs/smoke-d-20261116/data_card.md`）。
  - 第 1 次叫模型就被擋：`HTTP 400: You have reached your specified workspace API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.`
  - 程式照 G-38 標「中斷」、產出未完成報告（report_incomplete.md），流程本身正常。
- 新舊拆題比較：`uv run python -m seo_agent.decompose --card reports/runs/smoke-d-20261116/data_card.md --out reports/decompose/d-20261116`，同一個額度錯誤，沒有產出。
- 依序 3 輪＋直接叫 Opus 對照：**沒有啟動**（額度用完；不自行提高額度）。
- 另外：worker 日誌的「Tool registration REJECTED: 'web_search' would shadow」是舊流程就有的訊息（Hermes 內建 web 工具不會蓋掉專案的 web_search），不影響。

## 模擬執行（2026-11-16，使用者說「不能跑 Hermes，就慢慢模擬 Hermes 去跑這個架構」，先用 Sonnet）
**標示：模擬，非 Hermes。結果只看飛輪趨勢，不能當 Hermes 整合關卡證據。**

- 為什麼：API workspace 用量上限擋下實跑（上一節）；Hermes 借用訂閱登入仍要 extra usage，還可能讓 Claude Code 被登出，所以不走那條路。
- 只換「叫模型」這一層，其他全部沿用原程式：
  - `research.py` 拆成 `open_session`（底稿、資料卡、停止條件、Tool、提示）和 `close_session`（收尾、Board、run 摘要），Hermes 和模擬共用；`run_research` 行為不變。
  - 新增 `src/seo_agent/sim.py`：
    - 研究 Agent：`claude -p --model sonnet`，系統提示＝`system_prompt.md`，`--tools ""` 關掉所有內建 Tool，只透過 MCP 轉接拿到本專案 10 個 Tool（名稱前綴 `mcp__seo__`）。
    - Tool 呼叫經 unix socket 回到同一個程序，走同一套 ToolLog → StopGuard → ReportFlow，一次一個。
    - ⑥ 審查：另一個 `claude -p`，沒有任何 Tool，系統提示＝`REVIEW_PROMPT`。
    - 對照組：`claude -p` 只開 WebSearch／WebFetch，任務文字同 `scripts/direct_opus.py`。
    - 子程序拿掉 `ANTHROPIC_*`、`SEO_MODEL_*`，走訂閱登入；不讀 .env；`--setting-sources project` 避免載入使用者的 hook 與記憶。
    - 每份 result.json 標 `simulated: true`、`runtime: "claude-code-cli"`。
  - 測試：`tests/test_sim.py` 3 項（MCP 轉接、經 ToolLog 記錄、輸出解析）；全部 184 passed、2 deselected。
- 和 Hermes 的差異（解讀結果時要記得）：
  - 模型看到的 Tool 名稱多了 `mcp__seo__` 前綴；系統提示與任務文字相同。
  - 對話迴圈由 Claude Code 跑（含它自己的重試與上下文管理），不是 Hermes AIAgent。
  - api_calls 用不同的 assistant 訊息 id 計數；token 取 CLI 回報的 usage（含快取讀寫）。
  - 對照組的系統提示是「你是研究助理。」（CLI 必須有一段；direct_opus.py 是空的）。
- 驗證過程：
  - 連線測試：toy Tool 一次就打通，模型回報為 `claude-sonnet-5-5`，只拿到 `mcp__seo__echo`。
  - 8 分鐘短 run 第 1 次：`--out` 用相對路徑，claude 在 `sim_cwd` 裡找不到系統提示 → 中斷；改成一律用絕對路徑。
  - 8 分鐘短 run 第 2 次（`reports/runs/sim-smoke-8min`）：status passed，用了 230 秒、24 次 Tool 呼叫、97 份證據，⑥ 審查開出 13 條待修清單，修正稿通過。白做工 3 次，沒有經驗提案。
- 正式跑：`uv run python -m seo_agent.sim sequence --rounds 3 --model sonnet --minutes 120 --out reports/sequence/sim-sonnet-20261116`，日誌在 `reports/logs/sim-sonnet-20261116.log`。
- 結果（2026-11-17 00:15 跑完，整組約 25 分鐘；都標模擬、非 Hermes）：

  | 輪 | 狀態 | 用時 | Tool 呼叫 | 白做工 | 第一個關鍵發現 | 凍結評分 | 新發現 | 帶入經驗 | 經驗提案 |
  |---|---|---|---|---|---|---|---|---|---|
  | 1 | 完成 | 225 秒 | 23 | 1 | 第 0 次呼叫（底稿） | 4/14 | — | 0 | 0 |
  | 2 | 完成 | 222 秒 | 26 | 0 | 第 0 次呼叫（底稿） | 3.5/14 | 1（T07） | 0 | 0 |
  | 3 | 完成 | 293 秒 | 33 | 3 | 第 0 次呼叫（底稿） | 6/14 | 3（T03、T05、T10） | 0 | 0 |

  - 對照組（只有 WebSearch／WebFetch）：150 秒、7 次模型請求，交出 7 段報告；凍結評分器對整份 Markdown 給 0/14。這份報告不是 report.json 的結構，0 分不代表內容空白，要人工核對才能比較。
  - **飛輪沒有轉起來**：3 輪 Sonnet 都沒呼叫 `experience(action=propose)`，所以經驗庫一直是 0 條，Run 2、3 和 Run 1 的條件其實一樣，分數差異只是每次跑的隨機差。原因：SKILL.md ⑧ 寫「寫 0–3 條」，Sonnet 每次都選了 0 條，而交報告被接受後程式回「請用一句話結束」。這是模型行為，不是程式錯誤；要不要改規則交使用者決定，沒有自行修改。
  - 每輪只用約 4 分鐘就交報告（上限 120 分鐘）；停止條件一次也沒觸發。
  - 「第一個關鍵發現」三輪都是 0 次呼叫：命中評分的結論第一個證據都來自底稿，這個數字在目前設定下看不出差異。
  - 訂閱額度換算（CLI 回報的 API 等價金額）：三輪 0.46＋0.49＋0.57、對照 0.22，合計約 1.74 美元。
- 經驗沒寫入的改法（2026-11-17；獨立 subagent 只讀判斷，使用者核准「好，就這樣改吧」）：
  - 根因：Skill ⑧ 允許 0 條、寫的時機不清楚；修正稿被接受後程式回「請用一句話結束，不要再呼叫工具」；任務訊息沒提經驗。程式本來就允許 final 階段呼叫 experience（stop.py）。
  - 時機改在報告被接受後：寫入審核要求「照走」路線的 Evidence ID 被最終報告引用，修正稿前寫可能因修稿刪掉引用而不過。
  - 改動（直接改原段落）：
    - `src/seo_agent/skill/SKILL.md` ⑧：標題改「報告被接受後，寫下走過的路線」；條數改「1–3 條；只有這次沒有任何路線拿到被報告引用的 Evidence ID 時才寫 0 條」。
    - `src/seo_agent/report.py` finalize 回覆：改「報告已存檔。若還沒用 experience(action=propose) 寫 ⑧ 路線，現在寫 1–3 條；寫完用一句話結束。」
  - 已知代價（使用者接受）：寫入審核不查路線有沒有用，低價值但格式正確的經驗可能先變使用中，靠 no_value 下架規則清掉。
  - 沒選：只改條數（時機沒變，多半還是不寫）；沒寫經驗就退回修正稿（另開一種退回、逼出硬湊路線）。
  - 測試 184 passed、2 deselected。重跑：`... sim sequence --rounds 3 --no-direct --out reports/sequence/sim-sonnet-20261117-exp`。判讀看第 2 輪讀入經驗是否 >0 且判定「有用到」。
- 重跑結果（2026-11-17 00:40，`reports/sequence/sim-sonnet-20261117-exp`，模擬、非 Hermes）：

  | 輪 | 用時 | Tool 呼叫 | 白做工 | 凍結評分 | 新發現 | 帶入經驗 | 判定 | 寫下經驗 |
  |---|---|---|---|---|---|---|---|---|
  | 1 | 245 秒 | 33 | 0 | 5/14 | — | 0 | — | 1（EXP-001，審核通過） |
  | 2 | 251 秒 | 30 | 1 | 4/14 | 0 | EXP-001 | 沒用到 | 1（EXP-002，通過） |
  | 3 | 288 秒 | 27 | 1 | 4.5/14 | 1（T07） | EXP-001、002 | 都沒用到 | 1（EXP-003，通過） |

  - 寫經驗的問題解了：3 輪各寫 1 條、全數通過寫入審核、下一輪有讀入。
  - 新的斷點：「有用到」只認 research_log 登記了經驗編號（SKILL ⑤〈決定怎麼查時，同時對照經驗筆記〉）。Sonnet 每輪只寫約 4 筆 research_log，從沒填 experience_ids，所以讀入的經驗一律判「沒用到」。
  - 後果：「沒用到」不改狀態，經驗只會越積越多（3 條使用中），no_value 下架規則永遠不會觸發；飛輪的「讀 → 用 → 判」後半段仍沒被測到。分數 5 → 4 → 4.5 看不出趨勢。
  - 訂閱額度換算：0.61＋0.50＋0.51 ≈ 1.62 美元。
- Opus 版 3 輪（2026-11-17 01:20 跑完，`reports/sequence/sim-opus-20261117-exp`，使用者指定「換成用 Opus 跑」；模擬、非 Hermes）：

  | 輪 | 用時 | Tool 呼叫 | 白做工 | 凍結評分 | 新發現 | 帶入經驗 | 登記經驗的 research_log | 判定 | 寫下經驗 |
  |---|---|---|---|---|---|---|---|---|---|
  | 1 | 664 秒 | 67 | 3 | 7/14 | — | 0 | 0 | — | 2 |
  | 2 | 591 秒 | 66 | 1 | 7/14 | 0 | 2 | 6 | 2 條都「有用到＋有新東西」 | 1 |
  | 3 | 475 秒 | 63 | 0 | 5/14 | 0 | 3 | 6 | 3 條都「有用到＋有新東西」 | 2 |

  - 飛輪四步第一次全部走通：寫 → 讀入 → 登記並照路線查 → 程式判定有用到。Sonnet 卡在「登記」是模型不照規則做，規則設計本身可用。
  - 效率有趨勢：用時 664 → 591 → 475 秒、白做工 3 → 1 → 0。
  - 品質沒有趨勢：凍結評分 7 → 7 → 5，第 3 輪少了 T03、T07；新發現 0。凍結評分已知常誤判，要人工逐項核對才能下結論。
  - 「第一個關鍵發現」三輪都是 0 次呼叫（來自底稿），仍看不出差異。
  - 「有新東西」的判定只看路線帶出的證據有沒有被報告引用，門檻低；5 條經驗全部使用中，還沒有任何一條被下架。
  - 訂閱額度換算：2.00＋1.73＋1.69 ≈ 5.42 美元。
- 人工逐項核對（使用者「幫我去審核一下」；`reports/sequence/sim-opus-20261117-exp/manual_review.md`）：人工 7 → 7.5 → 7，評分器 7 → 7 → 5。第 3 輪掉分是評分器誤判（T03 說法不同沒被抓；T07 只下一半判斷給 p）。品質持平，效率變好；6 項三輪都沒找到，經驗沒有帶出新方向。

## 讓表現逐輪變好的改法（2026-11-17，待審查、尚未實作）
- 起因：Opus 模擬 3 輪只變快（664→591→475 秒）不變好（人工 7→7.5→7）。兩個 subagent：xhigh 架構診斷（題單固定＋提早交卷、只深挖、審查只挑錯、經驗只記怎麼查）；medium 上網研究（Voyager、Go-Explore、STORM、ExpeL、ACE、記憶管理、DGM 評估器隔離）。
- 使用者決定：下列 5 個衝突點「這些都可以允許」，改之前先派新的 subagent 審查。
  1. 對帳資料卡的列不違反 #45（對帳的是資料卡列、只記碰過沒，不是全網址對帳表）。
  2. 推翻「經驗只影響怎麼查、不影響想到什麼」，新增「該問」經驗。
  3. 每輪變長（約 30–60 分鐘）可接受。
  4. 可換 1 個網站做驗證。
  5. 固定預算：每輪 Tool 呼叫上限（暫定 150 次），舊版與新版用同一上限比較。
- 改法（放進現有步驟，不另立版本）：
  - ② 底稿不動；資料卡兼當對帳清單（A）。
  - ③ 多角度：Opus 依網站類型自己想 3–5 個角度，各列題（角度不寫死，避免把評分方向塞進去）；並讀入「該問」經驗補題（C）。
  - ④ 探新額度（D2）：一部分動作要花在經驗沒提過的分區或 Tool。
  - ⑤ 收尾前對帳（A）：程式列出資料卡上沒被任何 Tool 碰過的列；每列碰過，或寫理由略過（可整組），看出問題就開新題回 ④。
  - ⑥ 審查多看對帳結果，只問「哪些略過理由站不住」；仍 1 個無 Tool 審查 Agent（B 強化）。
  - ⑧ 經驗兩種：「怎麼查」照舊；「該問」只收靠對帳或審查才找到、已答且被引用的題，寫入審核禁止站名與網址；一條一條加（ACE）。
  - 跑完後跨輪對帳（D1）：上一輪有、這一輪沒有的發現，只在 ⑧ 提示 Opus 寫成通用「該問」，不直接傳給下一輪（避免抄答案）。「該問」讀入後沒帶出被引用的新題就下架。
- 不採用：平行多 subagent、審查換模型、自動改寫 harness、把「可索引性」寫死成一面。
- 驗證：固定 Tool 呼叫上限；主指標人工找到數＋說錯數；次指標碰過列數、途中新增題數、14 項外新發現。順序：(1) A＋多角度＋⑥ 強化跑 1 輪；(2) 加 C＋D1＋D2 從空經驗依序 3 輪；(3) 換網站驗證。
- 方案審查（新 subagent，唯讀）：approved with changes。
  - blocker 2 條：
    - B1：`experience.py` 的 `_STRIP` 擋不住站名與路徑，「該問」要另寫一套格式檢查。
    - B2：D1 和「該問」的收錄條件矛盾（上一輪有、這一輪沒有的發現，這一輪沒有 Evidence ID）；而且若重用 new_findings，會把評分表的結果帶進研究 AI。
  - major 6 條：
    - M1：對帳和停止條件 ②（連 5 次沒新證據）會互相卡住。
    - M2：「碰過一列」要有嚴格定義。
    - M3：D2 探新額度和 A 對帳重複。
    - M4：「該問」的下架規則要和路線經驗一致。
    - M5：固定 150 次的比較不公平，要加「舊版＋同樣預算」對照組。
    - M6：多角度會讓題數膨脹。
  - minor 4 條：審查要加看對帳、不能取代原本的審查；改提示時要擋評分詞；樣本量與成功標準要先定；換站時要有核對真假的方法。待使用者決定修法。

## 整合版方案：接力探索＋累計成績（2026-11-17，取代上一節方案，待第二次審查）
使用者澄清：每一輪是獨立的研究，但要讀前幾輪的路線。舊路線不能原樣重走，可以接著往下查或從中間岔出去；除非確定查完，否則路線都可以繼續。查的順序依提示裡定好的優先順序。成績用累計算。交付越完整越好。

### 一、目標與成績
- 成績：所有輪合起來共找到幾項、說錯幾項（累計）。單輪分數下降不算退步。
- 交付三份：每輪各自的報告（保留）、合併各輪發現的總報告、累計表（每輪新增什麼、累計幾項）。

### 二、路線地圖（新，程式產生）
- 由程式從每輪的 tool_calls、research_log、報告整理出來，Opus 不能直接寫（和 Board 一樣）。
- 每條路線包含：起點疑點、走過的步驟（Tool＋目標）、找到的結論（run_id＋Evidence ID）、狀態。
- 狀態只有兩種：
  - 還有可能：預設狀態。
  - 已查完：要有確定沒東西的證據，沿用「說沒有之前，要用另一種方法確認」。
- 跨輪合併：前幾輪的發現合成一份總清單當地圖。來源只能是報告和紀錄，不讀 evaluation.json 或評分表。
- 分工：網站專屬的內容放地圖；通用的查法放經驗。所以經驗仍然不准出現站名和網址。

### 三、每一步怎麼改
- ② 網站底稿：不動。資料卡每一列加固定編號（R01…），兼當對帳清單。
- ③ 列疑點：
  - 多角度取代原本的 5 面檢查表。Opus 依網站類型自己想 3–5 個角度，角度不寫死。題數上限 15 題。
  - 讀入地圖：「還有可能」的路線，依優先順序變成接續題。
  - 讀入「該問」經驗補題。
- ④ 逐題查：
  - 依 Skill 定好的優先順序查（最可疑的先查，接續題和新題一起排序）。
  - 禁止原樣重走：Tool 和參數跟前幾輪一模一樣的呼叫，程式標成「重走」，不算新證據。至少要多走一步或換個角度。
- ⑤ 收尾前對帳：
  - 程式列出資料卡上「所有輪都沒碰過」的列。每列要碰過，或寫理由略過（可整組），略過理由寫進 research_log。
  - 只在第一次交卷時觸發 1 次。觸發時把連續次數歸零。研究 Tool 已經被擋時，程式自動把剩下的列標成「停止條件擋下」。
  - 「碰過」從嚴：要實際查那個分區或網址才算；結果和底稿一樣、或 Tool 出錯，都不算。
- ⑥ 審查：在原本的挑錯之外，多看對帳的「列、碰過沒、略過理由」，指出站不住的理由。仍然只開 1 個沒有 Tool 的審查 Agent、1 次。
- ⑧ 經驗：
  - 「怎麼查」經驗照舊。
  - 新增「該問」經驗：只收靠對帳或審查才找到、已答、被引用的題。題目從哪來，由程式依時間順序判定。
  - 「該問」另有一套格式檢查：不能出現網址、路徑、網域、資料卡上的路徑片段、關鍵字原文；要寫一句「換網站也成立的條件」。
  - 下架規則和路線經驗一致：連續 2 次沒帶出新題才下架。
- 停止條件三道照舊，另加：每輪研究 Tool 上限 150 次（不含 research_log 和交卷動作，補查也算在內）。
- 結束後：產生總報告和累計表。

### 四、不做的
- D2 探新額度：和對帳重複，只當指標記錄（新分區呼叫比例）。
- 平行多 subagent、審查換模型、自動改寫 harness、把「可索引性」寫死成一面。

### 五、驗證
- 兩組比較，Tool 上限相同：
  - 帶地圖接力 3 輪。
  - 不帶地圖獨立跑 3 輪，最後合併。
- 比較累計曲線。成功標準：帶地圖組的累計找到數，比不帶地圖組多 2 項以上，說錯數不增加。
- 另看：14 項以外的新發現、碰過的列數、重走次數。
- 換網站驗證：規則在 2030.tw 結果出來前先定好。用盲核：把各組發現合在一起，由不知道哪份是哪組的人逐條核對真假。
- 防洩漏：所有新加的提示，都要跑 decompose.leaked_rubric，並另外檢查有沒有評分詞。
- 第二次審查（新 subagent，唯讀）：approved with changes。
  - blocker 2 條：
    - 「禁止原樣重走」和照走經驗、輕試、每輪重建 sitemap、本輪重新取證互相衝突。實測第 2、3 輪有 12、13 次呼叫和前幾輪完全相同。
    - Evidence ID 每輪都從 E-0001 開始編號，跨輪引用會撞號。
  - major 9 條（M-A～M-I）：已查完幾乎關不掉、地圖錯了沒有修正的路、提示長度、地圖和經驗重疊、總報告由誰寫、對照組樣本太少、需求 2.3 要分兩層講、拿掉 5 面要連動改程式、接續與岔出的欄位與排序。
  - 另一個待使用者決定：優先分數要不要用「實際產出率＋沒試過的加分」。

## 定案：4 張紙條（2026-11-17，取代前兩節方案）
- 使用者：「做了可能已經確定你好的版本，你會做好哪些的改動？」→ 收斂成 4 個改動；看 artifact 預覽後說「這個看得懂」，要求把比喻說明放進 artifact，並「記錄在決策記錄，改完之後就直接去改 code」。
- 比喻：三個人輪流打掃同一間大房子，現在每人都從客廳掃，儲藏室沒人進去。
- 4 張紙條：交接筆記（路線地圖）、交差前點名（交卷前對帳）、「這間沒東西」標記（軟結案：連 2 輪沒新結論排最後，不禁止）、總成績單（累計表＋總報告，程式合併）。
- 不做：頁面線索欄、跨輪證據匯入、硬結案、重開與推翻、排序公式、總報告叫模型寫、5 面改多角度、「該問」經驗。
- 依據表修正：刪 Anthropic 多 Agent 文章引用、2505.16067、Mem^p、Golovin；Go-Explore、Yamauchi、ACE、UCB 改標「啟發」；Huang 2023 只支持「核對交給程式」。
- 順序（使用者定）：決策紀錄 → 方案審查（使用者同意加）→ 改程式 → 獨立 subagent 審程式（不過度工程、符合原始需求，有問題就修，最多 3 次）→ Sonnet 依序跑 5 輪（使用者：「這次跑五輪」）。
- 對照組：沿用同一天的舊版 Sonnet 3 輪，不重跑。
- 細節見 `docs/plan-coverage-relay.md`；artifact 預覽可切「現況／提議」，原檔備份在專案外 `artifact-backup/`。
- 方案審查（無記憶唯讀 subagent）：approved_with_minor。補齊 4 項：對帳在送 ⑥ 前、不推進 stage／phase；列＝sitemap＋選單按路徑合併；略過理由只算當輪（碰過跨輪累計）；比較基準改用舊版 Sonnet 自己的 14 項人工核對。另依審查拿掉每輪 Tool 150 次上限（沒需求依據、會干擾比較）。

### 結果：4 張紙條 Sonnet 模擬 5 輪（2026-11-17，模擬，非 Hermes）
- 程式：新增 coverage.py、route_map.py，改 report／research／sequence／sim／thoughts／baseline／SKILL.md；全套 192 passed；獨立唯讀審查 1 次 approved（無必修）。
- 指標改定（使用者）：不看 14 項分數，改看「新的、可信的 SEO 數據」條數；判準見 reports/sequence/sim-sonnet-20261117-relay/data_review.md。
- 結果：前 3 輪累計新數據 新版 27、舊版 25（差 2，在人工拆條誤差內）；新版第 4、5 輪新增 3、0；兩版都沒看到說錯。14 項人工分：舊版 6／5.5／6（reports/sequence/sim-sonnet-20261117-exp/manual_review.md）。
- 觀察：
  - 對帳被整批略過：每輪一句籠統理由略過 38～40 列（共 43 列），5 輪累計只碰過 6 列。
  - 路線地圖幾乎沒用：5 輪只接續 1 次、0 次岔出、0 條被標「別走」。
  - 題數由舊版每輪 4 題降到 1～4 題；用時兩版都約 4 分鐘。
- 結論：沒有達到「明顯多於舊版」，不宣稱有效。整批略過與地圖沒被用的改法要先問使用者，不自行加規則。

## 撤回 4 張紙條（2026-11-17，決策紀錄 #51）

- 原因：路線地圖、交卷前對帳、軟結案沒有效果，原題也沒直接要求（分析：`reports/sequence/feature_benefit_review.md`）。
- 做法：整包存到分支 `experiment/relay-4notes`（ae0e2f1）；新分支 `codex/harness-v3-next` 從 ec9b21c 開始，只帶回 baselines、docs、reports（實驗紀錄與分析），src／tests 維持 ec9b21c。
- 留下：經驗（原題 B 段要求）；累計數字改由 `reports/sequence/history_review/` 腳本計算。
- 驗證：隔離 HOME 跑 `uv run --all-extras pytest -q` → 184 passed、2 deselected，exit 0。
- 下一步方向：Tool 自動測試＋把測到的差異帶進報告，見 `reports/sequence/decision_path_review.md` 第九節決策清單；尚未決定，未實作。
