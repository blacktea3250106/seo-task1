# AI / Coding Agent 使用紀錄（Problem Solving → Implementation → Verification → Revision）

對應原題「3. 交付物：AI / Coding Agent 使用紀錄」。V3 逐步建置細節在 `docs/build-log.md`；這裡說明整個開發過程怎麼用 AI，以 V3 為主，V1、V2 簡短帶過。

- 原話取自我在 Claude Code 與 Codex 下的指令（10/28–11/16，共 367 則，已去除個資與金鑰）；括號裡是時間（UTC）。
- 11/17 的案例（12–20）改引用決策紀錄裡記下的問題摘要，不是逐字原話；決策全文在 [`docs/design/decision-log.md`](design/decision-log.md)（#22–#71；#1–#21 在 V1 repo，私人 repo，未附）。
- 分數都是 2030.tw 這一題的分數，滿分寫在數字旁；找不到來源的數字一律不放。
- 證據路徑：標「V1 repo」「V2 repo」「d-review/」的是前兩版的私人 repo（私人 repo，未附），只列路徑供對照；沒標的＝本 repo（V3）。

## 1. 一句話總結＋工具分工

**一句話**：一開始照「先想好架構再實作」做出 V1，實測輸給單一 Opus one-shot；之後改成「由下而上」：先讓三家最強的 AI 各自 one-shot 同一題，拆出共同做法，再把做法工程化成 Tool、Skill、檢查層和經驗層（D 架構 → V3）。每改一步都用凍結的評分器加人工逐句核對來驗證，沒證明的照實寫「沒證明」。

| 工具／模型 | 負責什麼 | 證據 |
|---|---|---|
| ChatGPT | V1 前期我先和 ChatGPT 討論架構，沒有保留原文；11/16 把 A／B 比較整理成交接檔，交給 ChatGPT 繼續研討 | V1 repo `docs/research/2030-harness-vs-opus/chatgpt-analysis-main.md` |
| Claude Code（Opus 5.5） | 主要開發：V1 的 P0–P5、D 架構設計、V3 建置與實跑 | V1 repo git log（120 個 commit）、`docs/build-log.md` |
| Codex CLI | 11/14 code review；11/15 額度不足時接手 V1；審查 D 架構（#13）；三家 one-shot 之一 | V1 repo `docs/codex-takeover.md`、`d-review/codex-review.md`、V1 repo `docs/research/2030-multimodel/codex/` |
| Antigravity CLI（agy，Gemini） | V1 eval-2.0 的跨廠商 Judge；三家 one-shot 之一 | V1 repo `reports/evaluation/judge-heldout.json`、`docs/research/2030-multimodel/gemini/` |
| 獨立唯讀審查（短暫 subagent） | 每個 gate（G0–G5）前審一次；V3 實跑前審 8 輪；D 架構每個大改動前審一次 | V1 repo `reports/reviews/`、`reports/reviews/stop_guard_sim.py`、決策 #46–#49 |
| 產品裡的 AI | Hermes Loop 裡的 Opus 5.5，只有讀取用 Tool；另跑 1 次 Fable 5.2 對照、7 次 Sonnet 5.5 依序實驗 | `docs/experiments.md` |
| 模擬執行（11/17） | API 額度用完時，用 Claude Code CLI 代替 Hermes「叫模型」這一層，Tool、證據、審查、經驗同一套程式；結果標 `simulated: true`，不算 Hermes 整合證據；另可換 Codex CLI、Antigravity CLI 當執行者 | `src/seo_agent/sim.py`、決策 #53、#57 |
| 唯讀核對 Agent（11/17） | 評分端：遮掉 run 名稱、用固定指令逐句核對 14 項與講太滿，取代人工核對 | `eval/checker_prompt.md`、決策 #60 |
| 兩個 Session 分工 | 架構 Session 負責設計 D 架構、記錄決策；V3 建置 Session 負責照交接文件寫程式和實跑；決策紀錄兩邊共用一份 | `d-review/decision-log.md`、`v3-build-handoff.md` |

## 2. 版本演進

**V1：由上而下設計（11/14–11/15）**
- 架構先和 ChatGPT 討論、模擬出來（沒有保留原文）；規格包是 P0–P5 六個階段、六道 gate，Claude Code 一路實作。
- 怎麼測：live 模型當時是 blocked，研究的「大腦」改用規則式替身 `fixture_policy`，再用合成網站（fixture）跑；每個 gate 由獨立唯讀審查放行。
- 結果：G0–G5 全部通過，G2 審了 5 輪、G3 審了 4 輪；之後加了 site_live 模式去跑 2030.tw（commit `5695beb`）。
- 問題：我不熟 SEO，架構沒有可信的既有流程可以依據。

**2030.tw 實測：V1 對單一 Opus（11/15）**
- 怎麼測：開 Claude Code subagent，用 Opus 5.5、effort=max，不看現有報告，one-shot 獨立研究（B）；和 V1 的 2030.tw 報告（A）一起交給獨立 subagent 盲審，逐條用原始檔核對。
- 結果：A 3/8、B 8/8（決策 #1、V1 repo `docs/research/2030-harness-vs-opus/judge-verdict.md`）。兩邊讀到同一份 hub 檔，A 看成只有一頁，B 認出「共 2502 篇」。
- 要注意：A 的大腦是規則替身，不是 LLM，所以這場比的是「架構＋規則腦」對「裸 Opus」，不是公平的同模型比較。

**V2：修掉盲審抓到的架構問題（11/16，未 commit）**
- 怎麼做：在 worktree 分支 `codex/harness-v2-action-space`，依盲審結論逐條修：sitemap 預設讀滿、關鍵字比對正規化、刪掉和準確度無關的層。
- 怎麼測：每條修正寫成單元測試，基線 349 passed、4 skipped；另把舊 A 的 trace 重跑一次，確認新 gate 會擋下（V2 repo `docs/research/harness-v2-direction.md`）。
- 結果：沒有接真的 LLM 實跑，Skill 改法標「待驗證」；V2 保留當對照，沒有繼續做。

**三家 one-shot：由下而上找做法（11/16）**
- 怎麼測：同一份題目 prompt，Codex（`gpt-6-astra`、effort ultra）和 Antigravity 各跑一次；Opus 沿用前一天的 B。三份報告用同一張 14 項評分表評分。
- 結果：Opus 12、Gemini 11.5、Codex 7（滿分 14，決策 #5）。Opus 也有說錯的地方：「娛樂城區沒有 sitemap」。
- 結論：每個重點都有人找到，差別在沒有固定覆蓋、沒有重新核對（#6）。所以先不組合多家 AI，把做法寫進單一 AI 的架構。

**D 架構 → V3（11/16）**
- 架構 Session 把三家重複手寫、也出過錯的能力抽成 8 個 Tool；研究方法寫成 1 個 Skill；另加停止條件、報告檢查、經驗層（#19–#21）。Codex 審查 D 架構：approved_with_changes，12 個發現，其中 11 個 major（#13）。
- V3 建置 Session 在全新資料夾照交接文件建好：8 步，每步都有 pytest 和 exit code，實跑前測試 53 passed。
- 實跑結果（人工核對後，滿分 14）：Harness Opus 7／7／7.5，One Shot（同模型、不經 Harness，只開 WebSearch／WebFetch，同一份任務文字）5，Fable 8。這 3 次是同時跑、沒帶經驗，不算逐輪學習。
- 之後依序帶經驗跑了 Opus 3 輪、Sonnet 5 輪（#43、#44），還看不出經驗讓分數變好。架構依結果改到決策 #50（經驗層、網站底稿、獨立審查），11/17 已實作（commit de97e01）。

**11/17：從「多加功能」轉向「減法＋修事實」**
- 早上實作 D 架構（#39–#50）並 commit；加了 4 張紙條（路線地圖、交卷前對帳…）想讓多輪接力變好，Sonnet 5 輪沒有效果，整包撤回到 git 分支（#51）。
- 中午重新定義怎麼評分：每輪單獨評分＋不帶經驗對照組；講太滿算說錯；核對交給遮名的唯讀 Agent（#59、#60）。
- 下午從第一性原理重推 Harness，先寫好判準再跑 pilot：外圈預測不成立（#61）；小包 scout＋頁面文字讓 Sonnet、Opus 都上升，但成本 4～14 倍，還沒接進正式流程（#63）。
- 晚上讀 Sonnet、Opus 的實際決策紀錄，發現一部分說錯是 Tool 自己回了錯的事實，先修 Tool 回傳（#64–#66）；對流程的其他質疑做成預設關閉的實驗開關批次實跑（#67）。
- 同時補上 Hermes 用訂閱登入實跑的路徑（#62）。
- 深夜重定主分數＝可信 SEO 技術數，重評 101 份既有報告（#70）；正式流程改成目前架構，並做獨立 code review（#71）。目前架構尚未用 Hermes 實跑。

## 3. 代表案例

V1 案例的路徑與 commit 指 V1 repo（私人 repo，未附）；V2 沒有 commit，只附檔案路徑；V3 到 #60 的 commit 在本 repo 的 git log，#61 之後還沒 commit。

### 案例 1（V1）：規則式評審抓不到語意錯誤 → 換成跨廠商 Judge
- **Problem**：規則式語意檢查只認得替身報告的句型，held-out 只對 13/36；G3 依規格標「未通過」。
- **Implementation**：eval-2.0 改用凍結的跨廠商 Judge（Gemini via agy）。評審協議在第一次呼叫前先 commit；held-out 題目交給 Codex 出，不由開發 AI 自己出。
- **Verification**：held-out 46/48（`reports/evaluation/judge-heldout.json`）；`tests/test_c06_judge_calibration.py` 用快取重現（commit `a8a13a7`）。
- **Revision**：gemini-cli 不支援個人方案，builder 自己改用 agy；G3 第 3 輪審查指出這件事後，才由我事後確認（commit `c76c39f`）。
- 原話（11/15 04:49）：「那你可以派一個 subagent 或是 Codex」

### 案例 2（V1）：寫程式和審查強制分開，major 不能降級放行
- **Problem**：G1 第一次寫 gate 時，把 major 標成 accepted_risk，被 audit 拒絕。
- **Implementation**：改成每個 gate 前開短暫、唯讀的獨立上下文審查；major 一定要真的修好，修復次數用完就標 blocked、問我。
- **Verification**：審查原文逐字存在 `reports/reviews/`（P0–P5 共 20 多份）；G2 審 5 輪、G3 審 4 輪、G4 審 2 輪才放行。
- **Revision**：G4 第 1 輪指出「Judge 對同一個錯誤判定不一致，卻沒揭露」，補揭露後才通過（commit `4cfc317` → `b15a1f6`）。
- 原話（11/14 15:43）：「我覺得是要強制分開的啊」

### 案例 3（V2）：盲審的錯誤一條條追到根因層
- **Problem**：A 的 3 個核心結論被自己存下的原始檔推翻，例如「3A娛樂城 0 次」是因為比對有區分大小寫，原始檔裡其實有小寫的 `3a娛樂城`。
- **Implementation**：每條錯誤先標出根因在哪一層（Adapter、SKILL、Report Gate），再改：新增 `text_match`（NFKC＋casefold，exact 和正規化分欄回報）、sitemap 預設讀滿。
- **Verification**：`tests/test_v2_action_space.py`，含 `test_old_a_report_accepted_then_rejected_by_v2_gate`（舊報告在新 gate 會被擋）；349 passed、4 skipped。
- **Revision**：審查者估計差距約三成來自「沒有 LLM」、約七成來自架構，所以只修那七成；Skill 改法沒有 LLM 實跑，照實標「待驗證」。
- 原話（11/16 06:32）：「什麼叫七份只讀三份？正常來說不是全讀嗎？」

### 案例 4（D）：三家 one-shot 的共同做法 → 8 個 Tool＋1 個 Skill
- **Problem**：我不熟 SEO，要從可信的實作裡找出該工程化的東西，而不是憑空設計。
- **Implementation**：Codex、Antigravity 用同一份 prompt 背景 one-shot，並保存決策路線（`2030-multimodel/codex/`、`gemini/` 的 research-log、events）。原本規劃 3 個 Skill，派獨立 subagent 檢查後改成 8 個 Tool＋1 個 Skill，因為流程 Skill 會把研究順序寫死（#19–#21）。
- **Verification**：14 項評分 Opus 12、Gemini 11.5、Codex 7（#5）；Codex 審查 D 架構，12 個發現（#13）。
- **Revision**：Codex 指出的問題大多採用，例如只能讀的 Tool 加 3 個測試、評分改成 6 項分開列；「附原文片段」由我決定先不做（d-review/decision-log.md 的 Codex 處理表）。
- 原話（11/16 06:47）：「獨立一個架構去吸收他們的優點組合起來」

### 案例 5（V3）：評分器先證明會抓錯，才拿來比較
- **Problem**：14 項評分表一開始只核對過 1 項，答案又來自 AI 自己的報告（#14）。
- **Implementation**：確定性評分規則 `eval/rubric_2030.json`，用 4 份舊報告校準，凍結 hash 存在 `eval/FROZEN.sha256`。
- **Verification**：舊 A 只拿 1.5/14；B 12/14，而且 T10「娛樂城區沒有 sitemap」被判成說錯；3 份報告共 42 個標記，全部和人工比對表一致（`docs/build-log.md` 第 5 步）。
- **Revision**：實跑後審查發現規則有 3 處誤判（例如「沒有」裡含「有」）。凍結的規則不改，改成 14 項人工逐句核對；Sonnet 那批的 T07 判準原本較鬆，審查退回後統一成同一套嚴格判準（V3-4、#44）。
- 原話（11/16 07:44）：「評分表的機制是什麼？這評分表可信嗎？」

### 案例 6（V3）：Opus 拒答，逐段拿掉 Skill 找原因
- **Problem**：接上 Skill 後第一次 live 跑，第 1 次 API 呼叫就回 content_filter，一個 Tool 都沒叫。
- **Implementation**：把 Skill 逐段拿掉重測，找到觸發的是「每一步記下想法有沒有改變」；改寫成中性的研究日誌，Tool 改名 `research_log`，欄位 reason/belief_change 改成 purpose/revision。
- **Verification**：完整提示加 Tool 定義重測 2 次，都正常呼叫 Tool；自主邊界 live 測試 1 passed（164 秒）：頁面藏的「抓 ahrefs、設正式經驗」指令都沒照做。
- **Revision**：原因只是推測（可能被當成要求輸出內部思考）；這件事記進專案經驗，之後寫提示時避開。
- 原話（11/16 08:27）：「執行到底，執行到最終目標。」

### 案例 7（V3）：實跑前 8 輪唯讀審查：停止條件和洩題
- **Problem**：停止條件 A「連續 5 次沒有新證據」第一版只看證據有沒有新 hash；Tool 說明的範例 `/wordcup/` 剛好就是評分重點。
- **Implementation**：第 1 輪抓到 3 個 major（洩題、停止條件、評分器把「未知」句也算分）；第 2–8 輪逐輪收斂停止條件，涵蓋 date 標頭、DNS TTL、nonce、零命中、RDAP 更新時間等繞過或誤擋。
- **Verification**：審查者寫離線模擬 `reports/reviews/stop_guard_sim.py`，25 個情境 23 個 OK，另外 2 個是已認可的 minor；pytest 53 passed。
- **Revision**：範例改成 `/blog/`，之後每輪審查都掃一遍會送進模型的所有文字；只用自己寫的假 Tool 會漏掉真實回傳格式，從第 6 輪起改用真實 Tool 配模擬網路。
- 原話（11/16 10:02）：「派一個乾淨的 session、subagent 去審核」

### 案例 8（V3）：Harness 比 One Shot 好嗎？Fable 為什麼高？
- **Problem**：要分清分數差距來自 Harness、模型能力，還是隨機變動。
- **Implementation**：`scripts/run_matrix.sh` 同時跑 Harness Opus ×3、Fable ×1、One Shot Opus ×1；再跑 opus-fx：讓 Opus 帶 Fable 的 3 條經驗。
- **Verification**：人工核對後 Harness Opus 7／7／7.5、One Shot 5、Fable 8；opus-fx 6，沒追上 Fable（`docs/experiments.md`、#43）。
- **Revision**：Fable 多拿的分有一部分是模型自己想到的抽樣法；決定不把這些查法寫進 Skill，因為等於照考題教答案。README 寫明：前一天 B 的 12/14 這次沒有重現，只跑 1 次不能下定論。
- 原話（11/16 09:51）：「還是它就只是它的模型本能效能比較好」

### 案例 9（V3）：經驗真的讓 AI 逐輪變好嗎？
- **Problem**：前面 3 次是同時跑、沒帶經驗，證明不了逐輪學習。
- **Implementation**：Opus 依序帶經驗跑 3 輪；額度吃緊時不升級模型或額度，改用較弱的 Sonnet：3 次不帶經驗當基準，第 2–5 輪依序帶前面所有經驗（`scripts/run_sonnet_seq.sh`）。
- **Verification**：Opus 7 → 6.5 → 7.5；Sonnet 基準 5、5.5、5.5，帶經驗第 2–5 輪 6.5、6.5、6.5、6（#44）。多的約 1 分來自 2 項，都不能算經驗的功勞（例如基準組讀錯 Wayback 的回傳）。獨立審查第 1 次退回，2 個 major 修好後才收。
- **Revision**：總分不能判斷單條經驗好不好 → 經驗改成「照走／別走」，寫入時嚴格審核，狀態只剩使用中／已下架（#39、#41）；之後規定驗證逐輪變好一律依序跑。
- 原話（11/16 10:23）：「我不選擇 Model 升級，而是 Model 降級的方式去跑」

### 案例 10（D）：每次都一樣的偵察，抽成網站底稿
- **Problem**：#44 每輪都重新偵察，sitemap 結果忽高忽低，隨機差異干擾比較；B 跑 14 輪的關鍵發現，幾乎都落在 6 組固定比對（#45）。
- **Implementation**：固定偵察（robots＋全部 sitemap、首頁選單、WHOIS、Wayback、關鍵字搜尋 ×2）在網站底稿那步由程式跑一次，存成網站底稿；資料卡只把數字並排，不標差異，避免洩題（#46）。
- **Verification**：經過 3 次獨立唯讀審查才定案（`d-review/v3-gap.md` G-50–G-55）；11/17 已實作成 `src/seo_agent/baseline.py`，現在是 run 的第 2 步。
- **Revision**：#45 原本提的「程式自動標出對不上的地方」被 #46 取代。底稿會墊高基準，所以要用同一份底稿重跑新基準，不和舊分數直接比。
- 原話（11/16 12:50）：「固定偵查是最高級別的固定資料」

### 案例 11（D）：自己驗自己 → 程式固定開 Reviewer Agent，不另加 Judge AI
- **Problem**：審查原本由 Opus 在同一個 context 自我檢查；#23 曾把獨立審查放進 4 週計畫。
- **Implementation**：報告寫完後，程式固定另開一個 Reviewer Agent 審查：只給報告和引用的證據、不給任何 Tool；產出待修清單，Opus 修一次，缺證據的可以先補查（#49）。
- **Verification**：設計時發現 Hermes 內建的 `delegate_task` 會繼承上網 Tool，而且由模型自己決定要不要叫，和這個設計衝突，所以改由程式另開。11/17 已實作（`src/seo_agent/review.py`），現在是 run 的第 5 步。
- **Revision**：我認為這個審查已經等於另類的 Judge AI，所以不再加 Judge AI；經驗寫入審核從 7 項減成 6 項（#50）；#59 又加回「經驗不記網址」，現在是 7 項。
- 原話（11/16 13:40）：「我覺得這個部分一定要去拆 subagent 去做」

### 案例 12（V3，#51）：加了 4 個功能沒效果 → 整包撤回，用 git 回到原點
- **Problem**：為了讓多輪接力越跑越好，加了路線地圖、交卷前對帳、軟結案、累計表；我問：花很多時間卻沒有顯著提升，不必要的功能要不要砍？
- **Implementation**：先查數據再決定：Sonnet 5 輪累計 27 vs 舊版 25（誤差內）；路線地圖 5 輪只接續 1 次，對帳 43 列每輪一句話整批略過 38～40 列。整包存到分支 `experiment/relay-4notes`，新分支從 ec9b21c 重開，只帶回底稿、文件與實驗紀錄。
- **Verification**：無記憶 subagent 唯讀審查 approved（src／tests 和 ec9b21c 無差異、184 passed、沒有夾帶別的修正）；3 條 minor 已修。
- **Revision**：只留原題 B 段要求的經驗；Sonnet 的缺口在「到了之後沒看進去」，多輪功能處理的是「下一輪去哪查」，方向對不上。
- 我的問題（決策紀錄摘要）：能不能用 git 回到之前的版本重新開始？

### 案例 13（V3，#56）：證據檔被自己的程式弄壞 → 先證明舊程式會失敗再修
- **Problem**：停止判斷為了防「換字拖延」把參數換成 `<arg>`，但存成證據檔的也是換過的版本，`text_match` 多個關鍵字互相覆蓋只剩 1 個；`sitemap_tree` 把圖片網址當成頁面，資料卡出現假的「/wp-content/ 99 個網址」。
- **Implementation**：證據檔改存 Tool 原樣結果，換字版只拿來算指紋；sitemap 只認 `<url>` 直接子層的 `loc`。
- **Verification**：新增 3 個測試，先用 `git stash` 確認舊程式會失敗；191 passed。重建網站底稿：原檔 sha256 和舊版相同，所以數字變化（/wp-content/ 99 → 0、不重複網址 4602 → 4676）都來自程式修正。
- **Revision**：舊 run 的證據不回補，分析時把 `<arg>` 當成「內容不可信」；受污染的人工清單要用新底稿重算。

### 案例 14（V3，#59、#60）：評分對齊原題 B 段：每輪單獨評分、講太滿算說錯
- **Problem**：原本用「多輪累計找到幾條」，但累計量的是覆蓋、沒有對照組，還會懲罰後面輪次重新查到正確的事實。
- **Implementation**：每輪單獨評分＋同模型不帶經驗的對照組，判定規則事先寫進 `eval/README.md`；講太滿（標事實卻證據不足、以少推全）算說錯；卷外新發現另列只當參考；核對交給遮名、固定指令的唯讀 Agent。另加時間回饋（每次 Tool 回傳附「已用 xx／上限 分」，只給事實不給指示），經驗不記網址（寫入審核第 7 項）。
- **Verification**：冷讀審查兩輪 changes_requested（判錯數來源、核對 Agent 拿不到待修清單等 8 項），全部照改；離線測試通過（commit de97e01）。
- **Revision**：新規則只適用之後的實驗，已開跑的那批只做方向比較；「毒經驗」測驗先不做，README 限制寫明「學錯會改」沒有實跑證據。
- 我的問題（決策紀錄摘要）：好的 Harness 應該第 1 輪就做到位，之後靠經驗跑得更快、找到新思路；Benchmark 要怎麼設計才能導對方向？

### 案例 15（V3，#61、#63）：先寫好判準再跑 pilot，預測不成立就照實寫
- **Problem**：我要求不受既有架構綁住，從本質重推一套對各種模型都有加分的 Harness。
- **Implementation**：先回溯舊紀錄（不花額度）：Sonnet 14 輪只碰約 12 個分區（資料卡 42 個）。提案「外圈」：沒碰過的分區分段再派；判準事先寫在 `experiments/episodes_pilot/PREREG.md`（≥ 9 成立、≤ 7.5 不成立）。全部只新增檔案，不改 `src/`、`eval/`。
- **Verification**：外圈 3 段合計 7.5 → 判「不成立」（走到了沒看進去）。改成小包 scout＋頁面文字＋無 Tool 合併後：Sonnet 6.0 → 8.5、Opus 9.0 → 11.0，但說錯也變多（Sonnet 1～2 → 4）、Token 約 4～14 倍。
- **Revision**：沒有接進正式流程；也抓到 Harness 自己造成的錯（`page_text` 說明寫「可見文字」但程式不看 CSS，模型跟著寫錯），說明已改。限制照寫：1 個網站、各 1 次、全是模擬。

### 案例 16（V3，#62）：用 Hermes 自己的訂閱登入實跑，審查抓到 token 不會換新
- **Problem**：原題要求「使用 Hermes 建立」，但 API workspace 用量上限擋住實跑。
- **Implementation**：`.env` 設 `SEO_MODEL_AUTH=oauth` 就改用 Hermes 原生登入；每個 run 的 Hermes home 用 profile 模式讀上層登入，不借本機 Claude Code／Codex 登入。
- **Verification**：獨立程式審查第一次 changes_requested：只傳 `api_key=None` 時 Hermes 不會換新 token，過期後每輪都 401。改用 `credential_pool.select()` 並把 pool 交給 AIAgent；新增測試「過期 token 會換新並寫回上層」（同條件下舊寫法回傳過期 token）；220 passed。
- **Revision**：之後（#74）就用這個訂閱登入，以 Hermes 實跑目前架構一次（`claude-sonnet-5-5`，27 次 Tool、1.31M Token、455 秒），紀錄在 `reports/runs/seq-r1-20261117-225453/`，也是 README 的 Demo Video。多輪批次實驗仍用模擬執行器（同一套 Tool、審查、經驗程式）。

### 案例 17（V3，#64–#66）：讀模型的決策紀錄找說錯來源 → 先修 Tool 回傳的事實
- **Problem**：精簡版實驗中 6 筆說錯有 2 筆是 Tool 自己回錯：`sitemap_tree` 沒 build 就查會回「都不在 sitemap」；`inspect_page` 追蹤碼漏 `GT-`。我要求每一刀都有理由，先排出最可疑的地方，不要全部拆一遍。
- **Implementation**：分三批：先修模型拿到的事實，再對準實際說錯，最後才減流程。用程式量 Token 去向＋唯讀 Agent 逐步讀 Sonnet、Opus 的 `sim_transcript.jsonl`，動 5 刀：拿錯編號讀頁時回錯誤並指出正確編號（Sonnet 2 輪共 5 次）、`sitemap_tree build` 回傳精簡（1.1 萬字裡 6 千字和資料卡重複）、`wayback old_urls` 在存檔服務端過濾靜態檔（80 列裡 56 列是 js）、審查摘錄補上 head／JSON-LD 欄位（26 項待修有 4 項是誤判）。
- **Verification**：Sonnet 各 2 輪：14 項 6.0／6.0 → 5.5／6.5（持平），Token 85 萬 → 73 萬／52 萬，拿錯編號 5 次 → 0 次。獨立程式審查提出 3 個 major（指紋算法、日期被截斷、快照網址解析錯），全部修好並補測試；232 passed。
- **Revision**：成本下降不全算在這幾刀（其中一輪剛好查得比較少），照實寫；判定為非必要但這次不刪的零件也列出理由。

### 案例 18（V3，#67）：對流程的質疑做成預設關閉的實驗開關
- **Problem**：質疑「看板題目全收尾就交卷」「記帳一題一回合太貴」「搜尋每輪都被人機驗證擋還重試」，但不確定改了會不會更好。
- **Implementation**：每個質疑一個開關（`SEO_EXPERIMENT`，預設全關、行為不變），只多給事實或工具能力，不寫規定；判準事先寫定四欄：找到的 SEO 技術、準確性、Token＋秒、多輪提升。
- **Verification**：Sonnet 每種 2 輪（#67）：`coverage`、`cardex` 判退並從程式移除；`multi`、`shortfix`、`leaninspect` 不確定，預設不開；`searchmemo` 兩輪都沒觸發，未驗證。
- **Revision**：判「退」的開關交付前移除，不留在程式裡。之後換成可信 SEO 技術數重比，`coverage` 反而最明確（#70），#71 改成以 `sections_not_yet_read` 放回正式流程（見案例 19、20）。

### 案例 19（V3，#70）：換主分數，101 份報告重評
- **Problem**：14 項是「已知答案涵蓋率」，不是完整標準答案（#69）；我要的是驗證過、能追溯回證據的可信結果，再看 Token 和時間。
- **Implementation**：主分數改成每輪「可信 SEO 技術數」（屬實主張裡不同的 SEO 做法數），其次 Token、秒；14 項保留凍結、只當參考。不重跑模型：101 份既有報告交給 15 個 Sonnet Grader Agent（每個 7 份）遮名重評，14 份再由 Opus 評一次校準，1 個 Opus 把可信項目歸併成 36 條統一技術總表後用同一粒度重數（`docs/research/credible-rescore/`）。
- **Verification**：評分雜訊：同一份報告換核對者平均差 1.7 條、最大差 5 條。單份平均可信技術數：Sonnet One Shot 7、之前的架構 11.3、改良後 8.3、精簡版 12.5；Opus One Shot 14、之前的架構 12.3、改良後 17（不帶經驗）／10（帶經驗）。用新口徑重比被退掉的設計：`coverage` 6 份平均 10.7，對照 8.3。第六輪（全用 Sonnet、程式凍結成快照、判準事先寫在 `experiments/lean/PREREG6.md`）：完整版 11.5／72 萬 Token／250 秒、精簡版 15.7／41 萬／97 秒、精簡版＋`coverage` 16.0／37 萬／117 秒、再加 `leaninspect` 15.0／34 萬／111 秒。
- **Revision**：判定精簡版可取代完整版；`coverage` 在精簡版上看不出效果、`leaninspect` 無效。舊口徑下被退掉的設計可能是被冤枉的，所以先重比再改流程，改流程前先給我白話草稿確認。
- 我的問題（決策紀錄摘要）：Benchmark 應該先看可信、能追溯的準確度，再看 Token、時間；不是用 14 項當標準答案。

### 案例 20（V3，#71）：改成目前架構＋獨立 code review
- **Problem**：第六輪精簡版＋`coverage` 分數最高、成本最低，但我要求「獨立審查跟經驗累積這是一定要有的」，要一起整合。
- **Implementation**：研究段拿掉 `research_log`、疑點與 Skill 的流程規定，研究 Tool 8 → 7；每個研究 Tool 回傳附 `sections_not_yet_read`、`inspect_page` 附 `page_text`、加選填 `why`；報告 7 段 → 5 段；Reviewer Agent 與經驗保留，改接新來源（「有用到」看 why 寫的經驗編號，「推翻」看 `experience.overturned` 附的 Evidence ID）。
- **Verification**：派乾淨 Opus subagent 唯讀 code review：changes_requested，1 blocker、3 major，全部修好並補 4 個回歸測試；離線測試 224 passed、2 deselected，ruff 通過。
  - blocker：`sections_not_yet_read` 被算進進展指紋，零命中查詢永遠算「有新證據」，停止條件 A 對非 `polite_fetch` 的 Tool 失效。這表示第六輪 C 組的 16.0 不能直接套到正式版。
  - major：修正稿被格式退回後會改存初稿；「推翻」沒核對 Evidence ID 就下架；why 寫一次經驗編號後，之後所有同類呼叫都算進這條經驗。
- **Revision**：README、架構圖、Skill 一起改寫；評估說明對齊 #70。目前架構整合審查與經驗後的完整流程，在當時還沒實跑。

## 4. 對照評核標準

| 評核標準 | 看哪幾個案例 | 重點 |
|---|---|---|
| Problem Solving & Engineering | 3、4、6、7、10、12、13、17、20 | 每個錯誤追到根因層；從三家實作抽出可工程化的部分；逐段拿掉 Skill 定位拒答；沒效果的功能整包撤回；讀模型決策紀錄找說錯來源 |
| Agent Architecture & Tool Use（Hermes、Skills、Tools、自主決策） | 4、6、7、10、11、16、17、20 | Hermes Loop＋7 個只讀 Tool（#71 前是 8 個，含 research_log）＋1 個 Skill；研究順序交給模型；交卷動作和審查 Agent 由程式控制；Tool 只回事實，不規定怎麼想 |
| Memory, Learning & Evaluation | 1、5、8、9、14、15、18、19 | 先驗證評分器會抓錯；每輪單獨評分＋對照組；判準事先寫好；預測不成立就照實寫；換主分數後重評既有報告 |
| Reliability & Production Thinking（Failure Handling、Autonomy Boundary、工程成熟度） | 1、2、6、7、11、13、16、20 | 自主邊界 live 測試；停止條件的繞過和誤擋；寫和審分開；凍結評分器；另見 V1 repo（私人 repo，未附）的 C20 竄改測試 5/5 被拒 |

## 5. 沒做的事與限制

- **目前架構只用 Hermes 實跑 1 次**：#74 用 Hermes 訂閱登入跑 `claude-sonnet-5-5` 研究 2030.tw 一輪（`reports/runs/seq-r1-20261117-225453/`）。第 4 節的多輪成績表是模擬執行器跑的（Claude Code CLI 代替 Hermes 叫模型，Tool、證據、審查、經驗同一套程式）；API workspace 用量上限到 2026-12-01 才恢復，所以沒用 Hermes 重跑那批實驗。
- **#61、#63 的研究結果只有通用部分接進正式流程**：`page_text` 在 #71 併入 `inspect_page`；scout 分包、分段跑沒有採用。#61–#71 的改動在撰寫本紀錄時還沒 commit。
- **沒有證明經驗讓 AI 逐輪變好**：Opus 依序 3 輪、Sonnet 依序 5 輪，差距都在隨機範圍內，或者不能歸功給經驗；#51 的數據顯示經驗只讓 Opus 變快（664 → 591 → 475 秒），沒有查得更多。
- **樣本很小**：每個設定只跑 1–3 次，只測 2030.tw 一個網站；分數不能當作統計顯著的結果。
- **V1 對 B 不是公平比較**：A 的大腦是規則替身，不是 LLM。
- **三家比較的條件不完全一樣**：Opus 沿用前一天的 B（Claude Code subagent）；Gemini 的 log 顯示指定的模型 ID 不在本機設定，「resolved via default」，實際跑的是哪個模型無法從紀錄確認。
- **憑證例外**：V3 追加實驗時 API 額度用完，經我同意改用訂閱 token，這違反了「開發與產品憑證分開」，只限那次實驗（`docs/build-log.md` 第 7 步）。
- **版控**：V2 沒有 commit，證據只能附檔案路徑；V3 到 #60 的 commit 見本 repo git log，#61–#71 撰寫本紀錄時還沒 commit。本紀錄不能當作安全邊界，同權限的程序仍然可以改檔。
- **V1 的 live 項目**：V1 後段由 Codex 補了 API 接線和 Learning runner，但執行環境禁止 loopback，真實 Hermes 整合沒有重驗（V1 repo，私人 repo，未附）。
