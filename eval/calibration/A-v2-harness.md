# 2030.tw SEO 分析與 Benchmark（site_live）

> **資料與決策性質**
> - 網站頁面：2026-11-15（UTC）實際抓取的公開資料（live），遵守 robots.txt，每個請求間隔 ≥1 秒，只允許目標主機。
> - 研究流程：真實 Hermes 迴圈＋本機**規則式替身策略**（**非 LLM 推理**）。下面的彙整和建議由開發者 Agent 依原始證據撰寫；每個數字都對得到 `sha:` 原始檔。
> - 沒有市場資料：沒有 OpenSEO 認證（B-SEO），所以 SERP 排名、流量、外鏈一律列為**未知**。「搜尋觀察」只是一次 US 地區網頁搜尋工具的快照，不是台灣 Google 排名。
> - 本分析只看技術 SEO 與內容訊號，**不評估博弈相關的合法性**，也不構成法律意見。

## 1. 資料來源與重現

| 項目 | 位置 |
|---|---|
| T1 研究 run（site_live，最終程式） | `SL-2030-r3`（目標站）、`SL-stockfeel-r2`、`SL-casino3a-r2`（benchmark） |
| 對照用 run（不作為結論依據） | `SL-2030-r1`（challenge 誤判修正前）、`SL-2030-r2`、`SL-stockfeel-r1`、`SL-casino3a-r1`（以中間版本程式產生，見 §6） |
| 檢核表結果 | `reports/site-live/benchmark/benchmark.json`（原始檔放在 `benchmark/raw/`） |
| 搜尋觀察 | `reports/site-live/serp-observation.json`（整理）＋`reports/site-live/serp-raw/`（WebSearch 原始回應：sha:07b3219a57e5、sha:d32a964c2cd1） |
| 檢驗 | `reports/site-live/verify.json`（hash、origin、Report Gate、重算一致性、引用對照） |
| 日誌 | `reports/logs/site-live-*.log`、`reports/logs/site-benchmark.log`、`reports/logs/site-live-verify.log` |

```bash
# 2030.tw 在 config/run_policy.json 的核准主機內；其他站須操作者加 --approve-target-host 明示核准
.venv/bin/seo-agent research --target https://2030.tw --keyword 娛樂城 --keyword 3A娛樂城 --mode site_live --out /tmp/seo-site-live
.venv/bin/seo-agent research --target https://www.stockfeel.com.tw --keyword 娛樂城 --keyword 3A娛樂城 --mode site_live --approve-target-host --out /tmp/seo-site-live
.venv/bin/python tools/site_benchmark.py --config reports/site-live/benchmark-config.json --out /tmp/seo-bench
.venv/bin/python tools/site_live_verify.py --runs SL-2030-r3 SL-stockfeel-r2 SL-casino3a-r2 \
  --benchmark reports/site-live/benchmark --report reports/site-live/analysis-2030.md \
  --context-runs SL-2030-r1 SL-2030-r2 SL-stockfeel-r1 SL-casino3a-r1 --out /tmp/verify.json
```

三個 run 的終態都是 **partial**（`tool_failures_or_partial_data`），屬於如實標記，不是通過：
- discover_site 只讀了部分 sitemap；crawl_sample 受抽樣上限限制。
- search_market／inspect_backlinks 因為 B-SEO 回報 error 或 refused，沒有送出任何市場請求（`market_provider_calls=0`、`usd.spent=0`）。
- Report Gate 已接受報告。`verify.json` 也用 trace 中提交的完整 claims 重跑 gate，仍然 accepted。

真實網站內容會變動，重跑得到的 hash 和數字可能不同。要核對本報告，請用最後一條命令，它會驗證已保存的證據，不需要連網。

## 2. 2030.tw 現況（事實）

1. **站點定位是運彩／賽事內容站。** 首頁標題為「2030玩運彩瘋世足｜MLB/NBA比分、中職賽程、世界盃預測分析」（sha:dd1e733c49cd）。
2. **規模與模板。** 這次 run 讀了 sitemap_index 底下 6 份子 sitemap 中的 2 份（sha:c2b1cbd2d158），正規化去重後共 2264 個不重複 URL（原始 `<loc>` 為 1999＋274＝2273，sha:fb5e7fb970e9、sha:4a56d2235653）。主要模板如下（sha:3b021c03201a）：
   - `/taiwanplus/{slug}`：1819 個（MLB 直播頁）
   - `/mlb/{slug}`：302 個（比分頁）
   - `/digi_taiwan/{slug}`：76 個（世界盃賽事頁）
   - `/2026-worldcup/{slug}`：13 個
   - 未讀的 category／news／local／page sitemap 不在統計內。
3. **「娛樂城」只有一個專屬頁 `/wordcup/`**（sha:0190322d8ca6），各項訊號如下：
   - 標題：「線上娛樂城推薦｜2026最新評價排名」。
   - H1：「2026 線上娛樂城推薦」。meta description 含關鍵字。HTML 中「娛樂城」出現 138 次。
   - 頁面上有 2 個 H1，另一個是全站共用的站名 H1。H2 只有 2 個（「立即加入…」和作者框）。
   - canonical 指向自身，可索引，有 NewsArticle 結構化資料。
4. **「3A娛樂城」在所有抽樣頁都出現 0 次**，共 11 頁，包含 `/wordcup/`。
   - `/wordcup/` 有一個「立即註冊」按鈕，外連到 3a1788.bet 子網域（rel=nofollow），但錨文字和本文都沒有「3A娛樂城」（sha:0190322d8ca6）。
5. **全站共用區塊含「娛樂城」。** 每一篇賽事頁的 HTML 都有 17–19 次「娛樂城」（例：sha:b41e73a25aef、sha:e32875a1bd2a），來自共用的橫幅與導覽（例如「WG娛樂城」banner 的 alt）。這些頁的標題和 H1 都沒有這個詞。
6. **技術 SEO 基本面完整。** 11 頁中，以下 8 項全部通過：title、meta description、單一 canonical、可索引、JSON-LD（無解析錯誤）、內部連結、H1、`lang=zh-TW`。
   - **唯一弱項是圖片 alt**：只有 18% 的頁面缺 alt 比例 ≤10%。缺 alt 比例依模板不同：`/digi_taiwan/` 454/874（約 52%），`/taiwanplus/` 26/70（約 37%），`/mlb/` 10/54（約 19%），`/article/` 3/25；首頁與 `/wordcup/` 為 0。`/digi_taiwan/` 的缺漏主要是 api-sports 的球隊 logo（例：sha:b41e73a25aef）。
7. **page-sitemap 有殘留頁**（sha:3426ef9d9961，共 35 個 URL）：
   - WordPress 預設或測試頁：`/sample-page/`、`/home-2/`～`/home-5/`、`/community/`、`/community-2/`。
   - 16 個隨機短碼頁（如 `/2kapb2a/`）。
   - 9 篇與現有主題無關的舊 `/article/` 文章頁（如數位轉型、負責任 AI 訪談），外加 `/article/` 索引頁本身。
8. **搜尋觀察中沒有 2030.tw。** 兩個關鍵字的觀察結果裡都沒有出現 2030.tw（serp-observation.json）。這只是單次 US 地區的快照，**不能推論它在台灣 Google 的排名**。

## 3. Benchmark

### 3a. 搜尋觀察（2026-11-15 17:24 UTC，WebSearch，US 地區）

- 兩個關鍵字的結果以**寄生頁面**為主：大學與公共平台的使用者頁、GitLab、Docker Hub、Newspicks、Scrapbox、Gumroad 個人頁。
- 唯一同時出現在兩個查詢中的自有網域內容是 **stockfeel.com.tw 的「娛樂城排行榜」文章**。
- WebSearch 工具自己產生的摘要稱：3A 相關結果至少出現三個網域（3a娛樂城.icu、casino3a.org、3acasino.org）、三個地址與不同電話（sha:d32a964c2cd1）。這是**工具摘要，未逐頁驗證**；本分析只用它來挑 benchmark 候選，不當作事實結論。

### 3b. 同一檢核表的比較（Google Search Central 指南對應，見 benchmark.json 的 `guides`）

| 檢核（通過率） | 2030.tw（11 頁） | stockfeel（8 頁） | casino3a.org（1 頁） |
|---|---|---|---|
| title／H1／canonical／可索引／內部連結 | 全部 1.0 | 全部 1.0 | 全部 1.0 |
| meta description | 1.0 | 0.25 | 1.0 |
| JSON-LD（靜態 HTML） | 1.0 | 0.0（JS 動態插入，Google 渲染後可能看得到，未驗證） | 1.0（Product） |
| `<html lang>` | 1.0 | 0.0 | 1.0 |
| 圖片 alt（缺漏 ≤10%） | 0.18 | 0.0 | 0.0 |
| 關鍵字頁（title 或 H1 含詞）：娛樂城／3A娛樂城 | 1／0 | 1／0 | 1／1 |

逐頁比較「娛樂城」關鍵字頁：

| | 2030.tw `/wordcup/` | stockfeel 排行文 | casino3a.org 首頁 |
|---|---|---|---|
| 證據 | sha:0190322d8ca6 | sha:a6188f59a644 | sha:ffe1e3aa5ad2 |
| 標題含詞 | 是 | 是 | 是（另含 3A娛樂城） |
| H2 結構 | 2（無實質小節） | 5（每個 H2 一個平台：「娛樂城人氣排行：…」） | 0 |
| 本文字數 | 3991 | 5276 | 6402 |
| URL 是否描述主題 | 否（`/wordcup/`） | 是（中文 slug：娛樂城人氣-線上娛樂城-排行） | 首頁 |
| 外部連結 | 6（皆 nofollow） | 27 | 288（多數為 Lazada 等無關網域） |

## 4. 推論（附限制）

- **I1：2030.tw 的 on-page 技術面已不輸 benchmark。** 檢核表中，2030.tw 在 meta、lang、JSON-LD 三項都優於 stockfeel，和 casino3a.org 相當。
  - 據此推論：**如果**2030.tw 在這兩個關鍵字上的能見度確實較低，原因較可能是主題相關性與站外權威，而不是技術缺陷。
  - 限制：
    - 沒有台灣 SERP 排名與外鏈資料（B-SEO），所以「能見度較低」本身沒有成立，站外因素也無法驗證。
    - 頁型不同：stockfeel 的 8 頁中有 6 頁是分類頁，另有首頁與 1 篇文章。它的 meta 與 lang 通過率主要是被分類頁拉低，那篇排行文本身的 meta 是通過的。
    - 2030.tw 只抽樣 11 頁，不代表全站。
- **I2：`/wordcup/` 和 stockfeel 排行文相比，內容結構偏薄。** stockfeel 以 5 個 H2 逐一介紹平台；`/wordcup/` 只有 2 個 H2，而且都不是內容小節。
  - 限制：H2 數只是結構代理指標，不等於內容品質，本工具不判斷內容是否有幫助。
- **I3：「3A娛樂城」目前在 2030.tw 沒有任何對應頁。** 頁面上有導向 3A 子網域的 CTA，卻沒有可被索引的「3A娛樂城」文字內容。若要經營這個詞，目前缺少承接頁。
  - 限制：只觀察到抽樣頁與 page-sitemap；category／news sitemap 未讀。
- **I4：page-sitemap 的殘留頁可能稀釋站點主題訊號，也可能浪費爬取資源。**
  - 限制：沒有 Search Console 資料，無法確認這些頁是否已被索引，也無法確認它們造成的影響。
- **I5：這兩個關鍵字的搜尋結果被寄生頁面占據。** 這代表競爭環境偏向「借用高權威網域」，所以只靠 on-page 優化，效果可能有限。
  - 限制：只有單次 US 地區快照。

## 5. 建議行動（推論，依優先級）

| 優先 | 行動 | 依據 | 對應 Google 指南 |
|---|---|---|---|
| P1 | 擴充 `/wordcup/` 的內容結構：每個平台或評估面向各一個 H2，並補上評估方法、更新日期、作者資訊；移除重複的站名 H1 或改為非 H1 | I2、事實 3 | SEO 入門指南（標題與結構）、helpful content |
| P1 | 決定是否經營「3A娛樂城」。若要經營，建立專屬承接頁（標題與 H1 含詞），並從 `/wordcup/` 內部連結到該頁 | I3、事實 4 | SEO 入門指南（內部連結、描述性錨文字） |
| P2 | 將 `/wordcup/` 改為能描述主題的 URL，舊網址 301 到新網址，並更新 canonical 與 sitemap | 事實 3 | URL 結構、consolidate duplicate URLs |
| P2 | 清理 page-sitemap：`/sample-page/`、`/home-2..5/`、短碼頁與無關舊文改為 noindex，或移除後回應 404／410，並從 sitemap 拿掉 | I4、事實 7 | sitemaps、block-indexing |
| P3 | 為球隊 logo 等圖片補上 alt（例如「{隊名} 隊徽」） | 事實 6 | Google 圖片最佳做法 |
| 未知 | 排名、流量、外鏈落差 | B-SEO | 需要 OpenSEO 或 Search Console 資料才能評估 |

## 6. 檢驗過程中發現並修正的問題（照實記錄）

1. **驗證頁誤判。** 修正前的 run（`SL-2030-r1`）把所有真實頁面都標為 challenge_page，原因是登入表單的 `g-recaptcha` 命中 `captcha` 標記。
   - 修正：標記命中且本文少於 1000 字，才算驗證頁。
   - 失敗紀錄：`reports/logs/site-live-tests-before-fix.log`，舊解析器下 1 項測試失敗。
2. **例外頁名稱是空字串。** URL 結尾有 `/` 時，例外頁名稱會變成空字串。已修正，並在 `tests/test_site_live.py` 加了測試。
3. **規則式行動句型寫死。** 抽樣沒有例外時，策略仍會叫人「處理例外頁」。已改為只在 site_live 時依實際觀察產生文字；fixture 模式不變，避免影響 B0。
4. **benchmark 工具修正**：
   - 同一篇文章的短網址會 301 到同一頁，原本被算成兩頁。已改為同一個最終 URL 只算一次。
   - canonical 的百分比編碼與 Unicode 寫法被判為不同網址。已改為解碼後再比較。
   - 靜態 HTML 沒有 JSON-LD 的頁面，改為標記 `injected_by_js`。
5. **casino3a.org 描述更正。** 初稿寫它「已非 3A 娛樂城」，經原始檔核對後更正：它是單頁站，標題含 3A娛樂城，外連多為 Lazada 網域。
6. **獨立審查（changes_required）後的修正**：
   - F1：目標站的 `SL-2030-r2` 是在 fixture_policy 修完前跑的，a1 仍是舊句型。已用最終程式重跑三站（`SL-2030-r3`、`SL-stockfeel-r2`、`SL-casino3a-r2`），舊 run 降為對照組。r3 的 a1 已改為「抽樣未發現…例外；下一步先擴大…」。
   - F2：「地址、電話」原本沒有原始紀錄。已把 WebSearch 原始回應存進 `serp-raw/`（附 sha），改寫為工具摘要、未驗證。
   - F6：site_live 不再自動放行 CLI target。不在 policy 中的主機，必須加 `--approve-target-host` 才會抓取；未核准時 run 為 blocked（`reports/logs/site-live-unapproved-refused.log`）。
   - 其餘修正：數字精確化（F3）、I1 限制條件（F4）、檢驗器改用唯讀 SQLite（F11）、egress 報告加上 data_mode（F8）、新增主機核准與 NetGuard 拒絕的離線測試（F7）。

