## 指令（固定，每份照用）

你是唯讀核對者。不可修改任何檔案、不可跑模型、不可連外網。每份報告分開核對，判準在每份之間一致、從嚴。

### 範圍
- 只看報告的結論段：有 `## 1.`～`## 3.` 的看這三段；沒有這種編號的，看「摘要」與「證據」兩段。寫在「限制／未知」裡、或明說沒查到的不算。
- 證據：有 `evidence.jsonl`＋`raw/` 的，用報告引用的證據編號去找原檔；只有 transcript（`transcript.json` 或 `transcript.jsonl`）的，用 transcript 裡 Tool 實際回傳的內容當證據。

### 要做的事（只有這一件）
1. 列出報告指出的「這個網站的 SEO 技術」：網站為了搜尋排名或流量做的做法，或明顯的 SEO 現象（例如頁面結構、標題與描述、結構化資料、sitemap 安排、站內外連結、導流、網域歷史被拿來做 SEO 等）。單純背景描述、建議、對手以外的泛論不算。同一個做法寫兩次只算 1。
2. 每一項對證據判：
   - 可信：證據存在，而且撐得起報告的說法。標了推論的，所依據的事實有證據即可。
   - 不可信：證據不存在、編號錯、證據撐不起（講太滿、把少數樣本推成全部），或 transcript 找不到對應內容。
3. 數出可信的項數。

### 輸出（每份報告一段，數字必須和清單一致）
- 第一行：`N?｜列出 a 項｜可信 b 項`
- 可信清單：每項一句話＋證據編號（或 transcript 中的位置）。
- 不可信清單：每項一句話＋理由。
- 最後「待確認」：判不準的地方與你最後採用的判法。


### 統一粒度（第六輪追加，所有報告同一套）
可信的每一項，都對到下面技術總表的一個代號。同一個代號在同一份報告裡只算 1 項。總表沒有的，標 `NEW:一句話`。拿不準要對到哪個代號時，選最接近的那個，並寫在「待確認」。

| 代號 | 技術 | 判別說明 |
|---|---|---|
| T01 | /wordcup/ 以關鍵字網址量產娛樂城長尾頁 | /wordcup/ 下一詞一頁（品牌、3a 修飾詞、空白變體），數千網址 |
| T02 | 關鍵字頁共用內容模板 | 多頁同 H2／FAQ 骨架、固定開場句或第一人稱口吻，只換關鍵字 |
| T03 | FAQPage 結構化資料 | 頁面輸出 FAQPage JSON-LD 爭取複合式結果 |
| T04 | JSON-LD／og 混入無關 MLB 實體 | JSON-LD 夾帶 MLB 戰績頁實體，或 og article:section 為 mlb今日戰績 |
| T05 | 顯示日期與 meta／lastmod 不一致（新鮮度訊號） | 頁面顯示或 JSON-LD 日期與 og／sitemap lastmod／網址日期對不上，含動態填近日 |
| T06 | 雙 H1 | 同頁 2 個 H1（站名＋標題）或重複 H1 |
| T07 | nofollow 聯盟導流連結 | 連到 3a1788／wg1888 等註冊頁、帶 st= 參數、nofollow、無 sponsored、註冊 CTA |
| T08 | 全站選單錨文字導向 /wordcup/ | 選單「線上娛樂城推薦」等全站錨文字把各區連到 /wordcup/ |
| T09 | 站內互連與聚合列表 | 相關推薦、側欄品牌連結、麵包屑、分類 hub、列表分頁等內鏈網 |
| T10 | /wordcup/ 獨立 sitemap 未宣告 | /wordcup/sitemap.xml 不在 robots.txt／sitemap_index，靠探測才找到 |
| T11 | sitemap 落後或漏收新頁 | REST 文章數或站上新頁（如 10/31）不在 sitemap，lastmod 停在 8 月 |
| T12 | sitemap 重複列與雜項 | 列數多於不重複網址、svg／kml／image:loc 等雜項入列 |
| T13 | 網域重新註冊、承接舊政府站 | 2026-04-15 新註冊，Wayback 顯示原為 2030 智慧國家政策站 |
| T14 | 舊網址／短碼／舊路徑沿用放新內容 | 有存檔或 301 佐證的舊 URL、短碼、舊資料夾現放運彩／博弈內容 |
| T15 | slug／錨文字與內容不符 | 政策風格 slug 或資料夾名放世足／MLB 內容、選單標籤與目標不符（未證實為舊站網址時歸此） |
| T16 | /taiwanplus/、/mlb/ 程式化 MLB 賽事頁 | 日期＋隊伍網址、API 資料套版的每日 MLB 頁大量產出 |
| T17 | /digi_taiwan/ 世足單場模板頁 | 72–77 個世足單場頁，SportsEvent、第三方 API 資料 |
| T18 | 運彩外殼：首頁與內容頁不放目標詞 | 首頁／內容區正文無「娛樂城」，只在 alt／選單出現，兩層結構 |
| T19 | 批次發佈／lastmod 集中 | lastmod 按月集中、秒級間隔、同日或同秒發佈、賽前集中 |
| T20 | 兩個目標詞的專屬頁布局 | /wordcup/娛樂城、/wordcup/3a娛樂城、列表頁的 title／H1／H2、canonical、index 對準關鍵字 |
| T21 | 模板 meta 與標記缺陷 | 空 meta、base64 og:description、og:title Home 1、generator 版本不一、Organization 空、缺 alt、分類 og:title 取文章 |
| T22 | 示範／重複頁可索引 | home-2、community／community-2、sample-page 等留在 sitemap 或可索引 |
| T23 | 分頁 canonical 指首頁／作者頁 noindex | /page/N 或分頁 canonical 指回首頁、作者頁 noindex |
| T24 | 單薄或擬人作者 | 小編妮妮、阿豪、2030編輯部等無實據作者資訊 |
| T25 | 分類頁 meta 塞博弈／搜尋意圖字眼 | 運彩分類 meta 寫盤口、穩定收益、出金快速、開戶優惠、合法、MLB直播 ptt 等 |
| T26 | meta 自稱「老牌域名權重」 | /topic/ 等頁 meta 自述老牌域名權重 |
| T27 | AI／CMS 未編輯殘留 | 「[外部連結建議」、URL Slug 指示文字、markdown 星號、簡體字等殘留 |
| T28 | 低能見度關鍵字區塊 | 10px／低透明度關鍵字清單 |
| T29 | 不相干 meta 文字 | meta 為西文 WWE、College Baseball、圖例文字等 |
| T30 | 品牌詞高頻重複 | 單頁目標詞出現數十次（3a 75／45 次、大頭家 49 次） |
| T31 | 社群訊號 | 15.8k Subscribers、sameAs 社群連結 |
| T32 | Google 驗證與追蹤設定 | google-site-verification TXT、GT／GA4 tag |
| T33 | 世足／運彩分類與專題聚合頁 | CollectionPage 專題分區、分頁、跨分區列文、多分類掛載 |
| T34 | 薄頁／空正文 | articleBody 空、/pdf/ 薄頁、承諾內容卻無內容 |
| T35 | 無法驗證宣稱與過時即時標示 | 蒙地卡羅模擬、每日即時更新、LIVE／Update 3 mins ago 但為靜態 |
| T36 | 改寫新聞與後台連結外露 | og:image:alt 保留新聞原標題、內文含 wp-admin post.php 連結 |

### 最後一行（必填，程式會讀）
`代號｜R??｜可信代號：T01,T03,…,NEW:…｜可信數 N`
N＝不重複代號數＋NEW 項數。
