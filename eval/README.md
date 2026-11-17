# 評分方法（run 結束後）

- **主分數＝可信 SEO 技術數**（決策 #70）：由 Grader Agent 照固定指令 [`inst71.md`](../docs/research/credible-rescore/inst71.md) 核對。
- 本檔下方的 **14 項凍結評分只當參考**，也是經驗下架的判錯依據。
- 兩者都在 run 結束後才跑，研究程式與 Tool 說明都讀不到。

## 主分數：Grader Agent 怎麼算
- **Grader Agent**：run 結束後新開、沒有記憶、唯讀的核對 Agent；報告資料夾先遮名再交出（盲評）。
- 固定指令：[`inst71.md`](../docs/research/credible-rescore/inst71.md)；第六輪實驗用的指令另存在 [`reports/sequence/r6/grader_prompt.md`](../reports/sequence/r6/grader_prompt.md)。
- 做法：列出報告指出的 SEO 技術 → 每一項對證據判可信／不可信 → 數出可信項數。講太滿、引錯編號、沒有證據的都不算。
- 統一粒度：不同核對者的條目用統一技術總表歸併後再數（[`docs/research/credible-rescore/`](../docs/research/credible-rescore/)，`rescore.py`）。
- 評分雜訊：同一份報告換一個核對者，平均差 1.7 條，最大差 5 條（決策 #70）。
- 不是一條命令就算得出來：要手動派 Grader Agent；結果只出報表，不影響經驗。

## 事先寫好的判定規則（跑實驗前定好，跑完不改）
- 每輪單獨評分，不用累計。主分數：可信 SEO 技術數；其次 Token、秒數。14 項、說錯數、新發現數等過程數字只當參考。
- 主實驗：Run 1 從空經驗開始，依序帶經驗跑。對照組：同模型、不帶經驗，每次用新的 `--out` 資料夾跑 1 輪；runner、模型、effort 都要和主實驗相同。
  - Hermes：`uv run python -m seo_agent.sequence --rounds 1 --no-direct --out reports/sequence/<對照-n>`
  - sim 執行器：`uv run python -m seo_agent.sim sequence --rounds 1 --no-direct --model <同一模型> [--effort <同一 effort>] --out reports/sequence/<對照-n>`
- One Shot：同模型、不經 Harness，只開 WebSearch／WebFetch，同一份任務文字。
- 「帶經驗比較好」：帶經驗組 Run 2 起的每一輪，可信 SEO 技術數都要高過對照組的最高分。
- 「比較快」只在品質沒掉時才算：可信 SEO 技術數不低於對照組最低分，而且 Tool 呼叫次數與 Token 都低於對照組的最低值。
- 要比較的各輪必須用同一版指令一起核對；指令改了就全部重核。
- 差距在評分雜訊（約 ±1.7 條）內的，只代表方向，不代表證明。
- `untrusted_run` 的輪次不列入比較，表上標明原因（`uv run python -m seo_agent.evaluation --table <sequence 資料夾>` 產生 rounds.md）。
- 第 5 步 Reviewer Agent 待修清單每項的結局（補查後修正／降成推論／沒處理）由程式保守判定；判不出的標「需人工判定」（沿用程式欄名），寫在 `review_outcomes.md`，由核對 Agent 判定並寫明依據。
- 同一個網站上的進步可能含洩漏；換第二個網站檢查列在 README 的 4 週計畫。

## 參考：14 項凍結評分（凍結 grader）
- `eval/rubric_2030.json`：14 個事先整理的已知 SEO 事實（只拿來評分，不給研究 AI 看）。每項用固定文字規則比對報告：同一行內每組都命中才算。
  - 完整 1 分、部分 0.5 分、沒有 0 分；命中「說錯」規則記 x（0 分並列出原句）。
- 6 項分開列、不合總分：完整度（14 項分數）、正確度（說錯項目＋檢查層未解決問題）、誠實度（絕對句有範圍且 2 份證據、推論有限制、未知數）、可追溯（主張的證據編號都在證據庫且檔案存在）、建議有根據（行動指到存在的主張）、新發現（不屬於 14 項的主張，列給人看）。
- 用途：經驗寫入審核與下架判定讀這份的判錯（`wrong_count`）；其餘只當參考。
- 為什麼用確定性規則：同一份報告永遠同分、可重跑、不花額度；語意判斷交給 Grader Agent。
- 命令：
  - 舊報告：`uv run python -m seo_agent.grader eval/calibration/B-opus-direct.md`
  - run 資料夾：`uv run python -m seo_agent.grader reports/runs/<run_id>`（加 `--json` 輸出全部）

### 先驗證會抓錯（`uv run pytest tests/test_grader.py -q`）
4 份校準報告：其中 3 份共 42 個標記和人工比對表完全一致；第 4 份（舊 A）當低分基準。

| 報告 | 分數 | 和人工比對表 |
|---|---|---|
| 舊 A（V2 Harness） | 1.5/14 | 低分基準（前次盲審 3/8） |
| B（One Shot，Opus） | 12/14，T10 說錯 | 14 個標記全對；抓到「娛樂城區沒有 sitemap」 |
| Codex | 7/14 | 14 個標記全對 |
| Gemini | 11.5/14 | 14 個標記全對 |

人工比對表來源：（私人 repo，未附）。

### 只算「主張」
- 寫在「未知／限制／自我檢討／下一步／檢查未通過」段落裡的句子，或標成 [未知] 的行，不算找到重點（例：「未確認 iftomm2015.tw 是否 301」不給分）。
- run 的報告：結論會另存成 `strategy` 清單給凍結 grader 讀（`report.py`）；舊報告與 One Shot 的 Markdown 報告用標題排除上述段落。兩種來源格式不同，比較時要看命中原句。

### 公平性
- One Shot 與對照組用空經驗；主實驗依序帶經驗。
- 評分項目只在 eval/，研究程式與 Tool 說明不讀也不提（實跑前審查發現 sitemap_tree 說明用了 /wordcup/ 當例子，已改成 /blog/）。

## 歷史口徑（決策 #59、#60，已被 #70 取代）
- #59：主指標＝14 項（凍結評分＋獨立核對）與說錯數；「帶經驗比較好」要求 14 項高過對照組最高分、說錯數不多於對照組最少的那輪。
- #60：14 項核對交給遮名、固定指令 [`eval/checker_prompt.md`](checker_prompt.md) 的唯讀 Agent；講太滿（證據撐不起、以少推全，或沒證據又沒標推論）算進說錯數；卷外新發現另列只當參考。
- 這兩版的分數只出現在 [`docs/experiments.md`](../docs/experiments.md) 的歷史實驗，不和可信 SEO 技術數直接比。

## 限制（要誠實看）
- 14 項規則是用這 4 份報告調出來的（校準集＝調整集），對新報告的不同說法可能漏抓或誤判。
- 凍結 grader 只看字面，不判斷證據真假；真假靠報告的證據編號＋檢查層，以及 Grader Agent。
- 14 項的真值：T01、T06、T10 於 2026-11-16 實網重查（`scripts/live_tools_check.py`）；其餘沿用前次三家的原始檔，未逐項重抓。14 項不是完整標準答案。
- 網站會變：之後重跑，部分重點可能已不存在。
- 「學錯會改」只有寫入審核 7 項與下架判定的機制，還沒有實跑證據（「毒經驗」測驗未做，#60）。
