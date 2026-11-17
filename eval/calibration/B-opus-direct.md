# 2030.tw 自然搜尋競爭情報報告

- 指定關鍵字：「娛樂城」、「3A娛樂城」（台灣市場）
- 研究時間：2026-11-15 18:32–18:57 UTC（台灣時間 11-16 02:32–02:57）
- 研究方式：獨立從零研究，只用公開資料。curl 會先檢查 robots.txt，同一網站兩次請求至少間隔 1.5 秒（有 1 次例外，見 research-log.md 錯誤 E6），另外用了 WebSearch（美國引擎）、DNS/WHOIS、Wayback CDX API、Open165 開放資料和 Google Search Central 文件。沒有 Ahrefs/Semrush，也沒有 Search Console。
- 請求數：對 2030.tw 網站共 35 次 HTTP（含 www 與 redirect hop），WebFetch 0 次。其他主機 26 次。WebSearch 15 次。逐筆紀錄在 `raw/_requests.tsv`（cb4ae6a7496c）。
- 引用格式：`檔名`（sha256 前 12 碼）。檔案都在 `B-raw/`，`*.headers` 是同一請求的回應標頭。
- 標記：**[事實]** 有原始證據；**[推論]** 附信心等級；**[未知]** 拿不到的資料。

---

## 0. 核心結論

1. **[事實] 2030.tw 有兩套系統。** 第一套是 WordPress 運彩站，3,400 篇文章，sitemap 內 91% 是 MLB 程式化頁。第二套是不在任何 sitemap 裡的 `/wordcup/` 娛樂城區塊，共 2,502 篇，用同一個模板換關鍵字生成，承接「娛樂城」與各品牌查詢。
2. **[事實] 「3A娛樂城」是它最用力經營的品牌查詢群。** 抽樣找到 13 個 3A 變體頁（3a官網、3a登入、3a註冊、3a娛樂城有app嗎、3a娛樂城反水……）。每頁有 4 個 nofollow CTA，都連到 `don0911.3a1788.bet`。
3. **[事實＋推論] Off-page 的核心是過期網域。** 2030.tw 在 2026-04-15 重新註冊。舊站是 2020–2025 年的台灣科技政策類內容站。新站照舊站拼法重建了舊 URL（9 個 /article/ 中有 8 個、11 個舊短網址、舊分類路徑），內容換成運彩。13 天後，另一個過期研討會網域 iftomm2015.tw 由同一家註冊商註冊、用同一組 Cloudflare NS，整站 301 到 2030.tw。
4. **[推論，中高信心] 這套打法成長快但很脆弱。** 它的做法幾乎逐條對應 Google 垃圾內容政策裡的 expired domain abuse、scaled content abuse、doorway abuse 和 keyword stuffing。它的技術面也有明顯漏洞：sitemap 從 8 月起沒再更新，33% 的文章不在 sitemap 裡；娛樂城區沒有 sitemap，分頁 canonical 全部指回第 1 頁；結構化資料互相矛盾。
5. **[未知] 實際台灣 Google 排名與流量不知道。** 在能用的美國搜尋引擎裡，兩個關鍵字（連逐字標題）都查不到 2030.tw，SERP 主要被高權重平台上的寄生頁和品牌自營站佔據。所以「2030.tw 有多強」是從網站結構推出來的，不是排名事實。
6. **建議的優先順序：**
   - 先搶下 3A 品牌查詢群的可信承接頁（官方、防詐、條款類內容）。
   - 馬上把索引與 schema 衛生做好，成本低、見效快。
   - 用少量有方法論、證據可查證的深度頁，對抗它的 2,502 篇模板頁。
   - 建立監測和 Google 政策事件的應對流程。
   - 不要複製它的過期網域和模板量產做法。

---

## 1. 研究範圍、方法與限制

**範圍**：只做技術與內容 SEO，不評估博弈合法性。合規風險只在影響 SEO 時才討論，例如 YMYL 和 Google 垃圾內容政策。

**怎麼在約 60 次請求內決定看什麼**：
1. 先抓「一次能看到全站」的結構檔：robots.txt、sitemap index 和 6 個子 sitemap，8 次請求就拿到 2,331 個 URL 的中繼資料。
2. 用 WordPress 公開 REST API 的 `X-WP-Total` 標頭查總量與缺口，3 次請求。
3. 依假設挑頁：關鍵字承接頁、舊 slug 頁、最新的程式化頁。
4. 從娛樂城 hub 的分頁抽樣：第 1、2、26、52、53 頁，取得 195 個目標關鍵字，約佔 2,502 篇的 7.8%。
5. 做行為測試：不存在的 slug、舊網址的大小寫與 redirect、行動版 UA。

用了 35 次後停止。原因是剩下的關鍵未知（排名、外鏈、流量）多抓頁面也解決不了，詳見 research-log.md 的停止條件。

**主要限制**：
- WebSearch 是美國引擎，不支援 `site:`，「2030」也會和台股代號 2030.TW 混在一起。
- Wayback 快照回 429（被判為 bot），只能用 CDX URL 清單，沒有讀舊頁內容；後續幾次 CDX 查詢回 503。
- PageSpeed Insights 無金鑰的額度用完（429）。
- crt.sh 和 Common Crawl index 的 robots.txt 禁止抓取，所以沒用。

---

## 2. 已知事實（附證據）

### 2.1 網站身分、技術棧與規模

| ID | 事實 | 證據 |
|---|---|---|
| F01 | 首頁 title「2030玩運彩瘋世足｜MLB/NBA比分、中職賽程、世界盃預測分析」，H1「2030玩運彩瘋世足」。generator：`WordPress 7.1.4`、`Site Kit by Google 1.185.0`、WPBakery。主題是 JNews（`/wp-content/themes/jnews/`）。schema 來自 Rank Math（`class="rank-math-schema-pro"`）。有 wpForo 論壇外掛。Google tag `GT-57VMS4XR`。 | `home_desktop.html`（dd1e733c49cd） |
| F02 | 放在 Cloudflare 上，用 APO 快取 HTML（`cf-edge-cache: cache,platform=wordpress`、`cf-apo-via: tcache`，TPE 節點）。DNS 有 `google-site-verification=…` TXT 記錄，NS 是 `tara/zac.ns.cloudflare.com`。 | `home_desktop.html.headers`（b1f5cc789856）、`dns_2030.tw.txt`（e5bddd19b3eb） |
| F03 | robots.txt 只有 `Disallow: /wp-admin/`、`Allow: /wp-admin/admin-ajax.php`、`Sitemap: https://2030.tw/sitemap_index.xml`。 | `robots_2030.tw.txt`（c59d971fff8d） |
| F04 | sitemap index 有 6 個子 sitemap：post 兩份共 2,273 個 URL（1,999＋274）、page 35、category 23、news 34、local 1（`locations.kml`）。沒有 tag sitemap。由 Rank Math 產生。 | `sitemap_index.xml`（c2b1cbd2d158）、`post-sitemap1.xml`（fb5e7fb970e9）、`post-sitemap2.xml`（4a56d2235653）、`page-sitemap.xml`（3426ef9d9961）、`category-sitemap.xml`（73f29e73435a）、`news-sitemap.xml`（9e6911c3c7b2）、`local-sitemap.xml`（0fde761da3c5） |
| F05 | 2,273 篇文章中，2,070 篇（91.1%）是 MLB 程式化頁：賽前 `mlb-live-YYYYMMDD-aaa-vs-bbb` 1,531 篇、賽果 `mlb-scores-…` 539 篇，涵蓋 111 個比賽日（2026-04-24～08-22），單日最多 53 篇。另有 72 篇世足對戰模板頁（`*-vs-*-wc-2026`）。 | 同上 post sitemaps（用 slug 規則統計，見 research-log R2） |
| F06 | WP REST API 顯示文章總數 `x-wp-total: 3400`，2026-08-22 之後發布 594 篇，最新一篇發布於 2026-10-30。但 sitemap 最大 lastmod 是 2026-08-21，sitemap index lastmod 是 2026-08-16，news sitemap 的 34 筆全是 2026-08-16/17。**有 1,127 篇（33%）已發布文章不在 sitemap 裡。** | `wpjson_posts_latest5.json`（ae099df87875）與 `.headers`（25738f0b9d62）、`wpjson_posts_after_20260822.json`（35981250f465）與 `.headers`（014039caaf9c）、`sitemap_index.xml`（c2b1cbd2d158） |
| F07 | 最新的 MLB 頁（10/30 發布）是 `index, follow`，canonical 指向自己，所以不是 noindex 才漏在 sitemap 外。它的 meta description 是圖例文字「🟢 綠色 = 本場優勢方 \| 🟠 橙色 = 劣勢方」。`article:modified_time` 是 2026-11-15T14:05。 | `post_mlb_live_20261031.html`（f1cb03038143）與 `.headers`（7cfe25d5ae10） |
| F08 | 共 1,359 個 tag（`x-wp-total: 1359`），tag 頁設 `follow, noindex`。作者頁 `/author/machnage/` 也是 `follow, noindex`，沒有作者簡介。全站只有一位作者「小編妮妮」。 | `wpjson_tags_1.json.headers`（8b0d73d2834b）、`tag_mlb_bifen.html`（c55cfaee2c8d）、`author_machnage.html`（0c5a6b27705e） |
| F09 | page sitemap 裡有佈景主題 demo 殘留頁 `/home-2/`～`/home-5/`（2026-02-07～10）、WP 預設的 `/sample-page/`，以及論壇 `/community/`、`/community-2/`。論壇頁可索引（無 meta robots），實際只有「Topics 1 / Posts 1 / Members 1」，但首頁寫著「萬名專業球迷在線交流」。page sitemap 裡沒有 about、聯絡、隱私頁。 | `page-sitemap.xml`（3426ef9d9961）、`page_community.html`（5576e5bbec43）、`home_desktop.html`（dd1e733c49cd） |

### 2.2 娛樂城區塊 `/wordcup/`（「娛樂城」與「3A娛樂城」的承接處）

| ID | 事實 | 證據 |
|---|---|---|
| F10 | 所有抽樣的 WordPress 頁（8/8）在全站導覽都有 3 個連到 `/wordcup/` 的連結，錨文字是「線上娛樂城推薦」（menu-item-8097）。 | `home_desktop.html`（dd1e733c49cd）、`post_mlb_live_20261031.html`（f1cb03038143）、`page_legacy_responsible_ai.html`（f76653ad3617）、`tag_mlb_bifen.html`（c55cfaee2c8d）等 |
| F11 | hub 頁 title「線上娛樂城推薦｜2026最新評價排名 - 2030玩運彩瘋世足」。頁面寫「台灣最完整的娛樂城評價與推薦指南，共 2502 篇評測」。分 6 類：熱門娛樂城品牌 1,182、娛樂城評價與推薦 142、優惠與活動 116、遊戲與玩法 160、安全與出金 154、其他 748，合計 2,502。每頁 48 篇，共 53 頁（`?p=N`）。**第 2、26、53 頁的 canonical 全部指向 `https://2030.tw/wordcup/`。** | `page_wordcup.html`（0190322d8ca6）、`wordcup_hub_p2.html`（7116724b35bd）、`wordcup_hub_p26.html`（76faec4ad6d6）、`wordcup_hub_p53.html`（b4467989b59c） |
| F12 | 6 份 sitemap 的 2,331 個 URL 中，沒有任何 `/wordcup/`、「娛樂城」、casino、3a 的 URL。 | post/page/category sitemaps（同 F04） |
| F13 | 從技術面看，`/wordcup/` 不是 WordPress 產生的頁面：(a) 回應標頭沒有 WP 頁面都有的 `cf-edge-cache: …platform=wordpress`、`vary: Cookie` 和 `link: <…/wp-json/>`；(b) 不存在的 slug 回 nginx 預設 404 頁；(c) 頁面內嵌的 Rank Math JSON-LD 是另一篇 MLB 文章的（`@id: https://2030.tw/mlb/mlb-scores-20260712-phi-vs-det/#webpage`，日期 2026-07-12）；(d) generator 是 `WordPress 7.0.1`／Site Kit 1.181.0，現行站是 7.1.4／1.185.0；(e) 頁尾 tag 計數停在舊值（「MLB比分 (1207)」，現行首頁是 3,209）。 | `page_wordcup.html.headers`（55c1bcfdcf34）、`wordcup_3a.html.headers`（e46c62bca731）、`wordcup_nonexistent_test.html`（d465172175d3）與 `.headers`（0173aba26460）、`wordcup_3a.html`（06338ff143b3）、`home_desktop.html`（dd1e733c49cd） |
| F14 | `/wordcup/3a娛樂城` 的 on-page：title「3a娛樂城｜遊戲種類、優惠、出金全攻略」；meta description「2026年3a娛樂城完整攻略，涵蓋百家樂、老虎機、體育投注等熱門遊戲，安全可靠的娛樂選擇。」。有 2 個 H1（站名與「3a娛樂城 - 完整評測與玩家指南」）。H2 依序是平台特色與優勢、遊戲種類、出金速度與安全性、註冊教學、優惠活動與首儲獎勵、客服支援、FAQ（5 題）、總結評價。schema 是 `Article`（作者為 Organization，datePublished 2026-11-10、dateModified 2026-11-15）加 `FAQPage`。可見署名「2030編輯部」。內文用第一人稱宣稱親身經驗，例如「實際玩了幾個月下來」「我自己的經驗是…半小時到一小時」。 | `wordcup_3a.html`（06338ff143b3） |
| F15 | 3a 頁有 4 個 `rel="nofollow noopener"` CTA（「立即註冊領取優惠」×2、「立即註冊開始遊戲」、alt 為「WG娛樂城」的圖片），都連到 `https://don0911.3a1788.bet/?st=wg2030`，另有 1 個 WG 橫幅。WordPress 頁則連到 `bc5730m.wg1888.com/index/Register/?st=2030WG`、`st=2030ADS`、`st=live`，同樣全部 nofollow。 | `wordcup_3a.html`（06338ff143b3）、`post_mlb_live_20261031.html`（f1cb03038143） |
| F16 | `/wordcup/娛樂城`（title「娛樂城評價｜台灣玩家首選平台」）和 `/wordcup/3a官網`（title「3a官網 完整評測｜2026 台灣玩家真實體驗」）的 H2 骨架、FAQ 題目和 meta description 句型，與 3a 頁完全相同，只換了關鍵字（例如「3a官網出金速度與安全性」、「娛樂城最低入金多少?」）。三頁內文的 5-gram Jaccard 相似度只有 0.05～0.07，代表文字不是複製貼上。關鍵字字元佔正文的比例是 7.9%（3a娛樂城）、5.2%（娛樂城）、8.5%（3a官網）。 | `wordcup_yulecheng.html`（574f8a8224e7）、`wordcup_3a_guanwang.html`（902272ea99f1）、`wordcup_3a.html`（06338ff143b3）；計算方式見 research-log R10 |
| F17 | 日期前後矛盾。hub 快取版的頁首日期是「2026年11月4日 星期三」（`age: 1016358`，約 11.8 天前），當時已列出 3a娛樂城，摘要和現行頁開頭逐字相同；現行頁卻標 datePublished 2026-11-10、「2026年11月10日 更新」。即時抓的分頁（11/16）總數仍是「共 2502 篇」。 | `page_wordcup.html`（0190322d8ca6）與 `.headers`（55c1bcfdcf34）、`wordcup_hub_p2.html`（7116724b35bd）、`wordcup_3a.html`（06338ff143b3） |
| F18 | 抽樣 195 個目標 slug：141 個是「品牌名＋娛樂城」（富遊、tu、rg、威樂、鉅城、武財神、大撈家、at99、wg……）。13 個和 3A 有關：`3a娛樂城`、`3a娛樂城反水`、`3a娛樂城優惠活動介紹`、`3a娛樂城有app嗎`、`3a娛樂城百家樂品牌`、`3a娛樂城vip優惠活動`、`3a娛樂城會員平行轉移`、`3a登入`、`3a註冊`、`3a官網`、`3a娛樂城登入`、`3a娛樂城註冊`、`3a娛樂城官網`。另有像搜尋查詢原樣的 slug，例如 `富+寶+娛樂+城`、`fa8+娛樂+城+體驗+金`、`rk 娛樂 城`、`朕天下娛樂城是嗎`。 | `page_wordcup.html`（0190322d8ca6）、`wordcup_hub_p2/p26/p52/p53.html`（7116724b35bd／76faec4ad6d6／2548b18aec8b／b4467989b59c） |
| F19 | 隨便編一個 `/wordcup/` slug 會回 404，所以不是「什麼字都能生頁」的無限產生器，頁面只存在於固定清單裡。 | `wordcup_nonexistent_test.html`（d465172175d3） |
| F20 | 用行動版 UA 抓 3a 頁，HTML 和桌面版完全相同（sha 一致），沒有看到依裝置給不同內容。 | `wordcup_3a_mobile.html`（06338ff143b3） |

### 2.3 網域歷史與舊網址再利用

| ID | 事實 | 證據 |
|---|---|---|
| F21 | WHOIS：`Record created on 2026-04-15 17:19:40 (UTC+8)`，註冊商 `GNAME.COM`，NS 是 `tara/zac.ns.cloudflare.com`。 | `whois_2030.tw.txt`（0907dd08133c） |
| F22 | Wayback CDX 顯示，首頁從 2020-03 起有存檔，2020-08～2025-11 多為 200，2026-01-05 變成 301，之後沒有存檔。舊站是 Nuxt.js（CDX 前 300 列中有 `/_nuxt/` 資源 248 筆），圖檔有 `FORMOSAT-1~7`、`space-tech-01~14`、`responsible-ai-01~15`、`logo-smart-taiwan@3x`、`where-is-chip-01~10`。舊 `/article/` 共 168 個不同 URL（首次存檔 2021–2025），系列名稱有 digi-plus、the-taiwan-edge、taiwan's-competitive-edge、responsible-ai、space-tech、smart-nation、science-technology-diplomacy 等。 | `wayback_cdx_home_monthly.txt`（32c7d687474a）、`wayback_cdx_domain_prefix_to2025.txt`（6562047aaa16）、`wayback_cdx_article_prefix_to2025.txt`（577461414ac1） |
| F23 | 新站 page sitemap 裡的 9 個 `/article/` 頁，有 8 個與舊站 URL 逐字相同（小寫化），例如 `responsible-ai-008-audrey-tang`、`space-tech-002-jong-shinn-wu`、`cultivation-of-innovative-talents-035-moe`。第 9 個的 slug 夾著 Facebook 點擊參數殘留：`smart-recreation-016-jang-hwa-leu`**`afbclidiwar1xngy0u8-…`**。 | `page-sitemap.xml`（3426ef9d9961）＋`wayback_cdx_article_prefix_to2025.txt`（577461414ac1） |
| F24 | 新站有 16 個 7 碼短 slug 頁（`/2kapb2a/`、`/2lond3x/`…），其中 11 個與 Wayback 存檔的舊短網址相同（小寫化）；那些舊短網址在 2022 年都是 301，例如 `/2kAPB2a`、`/2lOnD3x`。實測舊網址 `https://2030.tw/2kAPB2a` → 301 到 `/2kAPB2a/` → 200，內容是 WP page 837「2026 NBA分析：總冠軍預測前瞻全攻略」，canonical 為 `/2kapb2a/`。舊大小寫網址 `/article/Cultivation-of-Innovative-Talents-035-MOE` 也會 301 到加斜線的版本。 | `wayback_cdx_domain_prefix_to2025.txt`（6562047aaa16）、`legacy_shortlink_2kAPB2a.html.headers`（52c57e621f86）、`legacy_shortlink_2kAPB2a_slash.html`（93d43e995767）與 `.headers`（11d15af468f8）、`legacy_article_mixedcase.html.headers`（441773ed092e） |
| F25 | 已證實的舊路徑 `/5G_Taiwan`、`/AI_Taiwan`、`/AI`（Wayback 有存檔），現在分別變成新分類 `/5g_taiwan/`（導覽錨文字「MLB分析」）、`/ai_taiwan/`（「中華職棒分析」）、`/ai/`（「NBA直播」）。其他分類如 `/taiwanplus/`、`/digi_taiwan/`、`/pretech/`、`/b5g/`、`/inclusion/`、`/topic/`，命名風格和舊站一致（舊站有 `icon_inclusion` 圖檔），但 CDX 輸出被截斷，沒能逐一驗證。如果把這些都算作舊式命名路徑，sitemap 裡有 84.6% 的文章放在這類路徑下，主要是 `/taiwanplus/` 的 1,819 篇。 | `wayback_cdx_domain_prefix_to2025.txt`（6562047aaa16）、`home_desktop.html`（dd1e733c49cd）、post sitemaps |
| F26 | 舊網址頁現在的內容：`/article/responsible-ai-008-audrey-tang/` 是「2026世足資格賽全攻略：完整解析各區晉級賽制、同分規則與最新戰況」（WP page 422，2026-04-17 發布）；`/iftomm2015cd/pdf/os11-017-pdf/` 的 title 是「MLB分析」（post 3326，**2026-04-28T17:45:03+08:00** 發布）。 | `page_legacy_responsible_ai.html`（f76653ad3617）、`post_legacy_os11_017_pdf.html`（656c5b9f8085） |
| F27 | Wayback 在 2025 年以前沒有任何 `2030.tw/iftomm2015cd/` 的存檔。 | `wayback_cdx_iftomm_prefix_to2025.txt`（e3b0c44298fc，空回應） |
| F28 | iftomm2015.tw：WHOIS `Record created on 2026-04-28 17:16:53 (UTC+8)`，註冊商 `GNAME.COM`，NS `tara/zac.ns.cloudflare.com`（和 2030.tw 相同）。實測 `/`、`/iftomm2015cd/pdf/OS11-017.pdf`、`/files/Call%20for%20Paper.pdf` 都 301 到 `https://2030.tw/`，路徑沒有保留。 | `dns_whois_iftomm2015.tw.txt`（d503f8cf80ad）、`iftomm2015tw_home.html.headers`（c098faecb904）、`iftomm2015tw_os11_017_pdf.html.headers`（87c39c534a72） |

### 2.4 外部環境

| ID | 事實 | 證據 |
|---|---|---|
| F29 | Open165（g0v 整理的警政署 165 開放資料）頁面寫：「內政部警政署已收到 21 次民眾檢舉以「3A娛樂城」為名的網站，最近 1 次落在 2025/12/17 那週」。列出的網域包含「seo188.3a1788.bet 2025/06/05 ~ 2025/06/11 共通報 1 次」，和 2030.tw 的 CTA 是同一個註冊網域 `3a1788.bet`，只是子網域不同。 | `g0v165_name_3A.html`（b8a8ea50cd99） |
| F30 | WebSearch 查「3A娛樂城」、「娛樂城」、品牌名「2030玩運彩瘋世足」、2030.tw 頁面的逐字標題、「娛樂城推薦 2026 排行」，回傳結果都沒有 2030.tw。前兩個查詢主要回傳 GitLab、Docker Hub、NewsPicks、Scrapbox、`kdi.umn.edu`、`scalar.usc.edu`、`learninglab.si.edu`、Substack、CMoney 筆記、stockfeel、udn 部落格、vocus 等第三方平台頁。「娛樂城推薦 2026 排行」則回傳品牌自營站與聯盟站（live-show.com.tw、lh888.com.tw、bc99.org、havespring.com 等），還有 `fisherprice.com.tw/娛樂城推薦`。 | `websearch_log.md`（bb870ce2ff00）WS-01、02、05、09、10、15 |
| F31 | Google 垃圾內容政策頁（Last updated 2026-08-28）的 Expired domain abuse 條目舉例：「Affiliate content on a site previously used by a government agency」、「Casino-related content on a former elementary school site」。Scaled content abuse 條目寫：「Using generative AI tools or other similar tools to generate many pages without adding value for users」。另有 Doorway abuse、Keyword stuffing、Thin affiliation，以及 site reputation abuse 對第三方內容的定義。 | `google_spam_policies_en.html`（14794e28d278） |

---

## 3. 推論（附信心與限制）

| ID | 推論 | 依據 | 信心 | 限制／反例 |
|---|---|---|---|---|
| I01 | 2030.tw 是博弈導流站，有兩條漏斗：一條用運彩和 MLB 程式化頁吸流量，靠 WG 橫幅變現；另一條用 `/wordcup/` 承接「娛樂城」與品牌導航查詢，靠 3A CTA 變現。 | F05、F10、F11、F15、F18 | 高 | 看不到合約、轉換和營收。 |
| I02 | `/wordcup/` 是另一個系統（非 WordPress），用 reverse proxy 掛在子目錄下，外框是約 2026-07 擷取的 WP 頁面。 | F13 | 高（是獨立系統）；中（擷取時間） | 無法看到伺服器設定。 |
| I03 | `/wordcup/` 很可能和 WP 部分由同一個操作者經營，所以比較符合「第一方的 scaled content」，不像出租子目錄（site reputation abuse）。 | WG 追蹤碼 `st=2030WG` 在兩套系統一致；3A 連結帶 `st=wg2030`（F15） | 中 | 子目錄出租時，也可能由出租方統一放追蹤碼。 |
| I04 | 2030.tw 是過期網域再利用，而且有系統地重建「可能帶外鏈」的舊 URL，用來繼承舊站的 link equity。 | F21–F26；fbclid 殘留表示 URL 清單來自外部連結或分享紀錄，不是從 sitemap 抄來的（F23） | 高（重建舊 URL）；中（目的是繼承外鏈） | 沒有外鏈資料（U03）。Google 可能已不計這些舊連結。 |
| I05 | 舊站很可能是和台灣政府科技政策（DIGI+／行政院科技會報類）有關的雙語內容站。 | F22 的系列名稱與圖檔；WS-13 只找到 DIGI+ 相關報導 | 低–中 | Wayback 快照 429，沒讀到舊頁的標題與內容，營運者未證實。 |
| I06 | iftomm2015.tw 和 2030.tw 由同一操作者控制，用全站 301 把舊研討會網域的權重導進來。 | F26–F28：同註冊商、同 CF NS 配對；註冊後 28 分鐘就建了 `/iftomm2015cd/` 頁 | 中 | GNAME 和 CF NS 配對很常見，可能是巧合。全站導到首頁、不保留路徑的 301，通常傳不了多少價值。 |
| I07 | `/wordcup/` 的內容是用生成工具依關鍵字清單批量產出：同一個 H2/FAQ 模板換關鍵字，再加上「老玩家／小編／阿豪體驗官」等人設口吻。關鍵字清單來自搜尋查詢資料。 | F16、F18（像查詢原樣、含空白的 slug，以及把「官網」當成品牌名來評測） | 中–高 | 只看了 3 篇正文、195 個 slug，沒對 2,502 篇做全面檢測，也沒做 AI 偵測。 |
| I08 | 系統會刷新日期欄位（datePublished、dateModified、頁面上的「更新」）來製造新鮮度。 | F07、F17 | 中 | 強反例只有 3a 頁一個；也可能是系統批次重新發布。 |
| I09 | 3A 是它最核心的變現品牌：所有賭場頁 CTA 都指向 3A，3A 變體頁成群；`don0911` 很可能是代理商代碼，因為 Open165 也出現同格式的 `seo188.3a1788.bet`。 | F15、F18、F29 | 中 | 看不到代理後台；`3a1788.bet` 和 3A 品牌的正式關係未知。 |
| I10 | 對「3A娛樂城」相關長尾與導航查詢，它的結構競爭力比「娛樂城」head term 強：前者有精準 URL 群加內鏈，後者要和大量寄生頁、品牌站正面競爭。 | F11、F14、F18、F30 | 低–中 | 沒有排名資料（U01），只是從結構推論。 |
| I11 | 這套策略不耐久。被 Google 的垃圾內容系統或人工處置認定後，整站（包括運彩區）可能一起失去能見度。 | F31 對照 I04、I07、F16 的關鍵字密度 | 中 | 政策文字很明確，但執行時點和範圍無法預測。 |
| I12 | 技術漏洞會限制它的收錄規模：sitemap 停更、賭場區沒 sitemap、分頁 canonical 指回第 1 頁，深層頁只能靠「相關推薦」內鏈被發現，收錄可能不完整。 | F06、F11、F12 | 中 | 沒有 GSC／索引資料；它也可能另外在 GSC 提交了 sitemap（U04）。 |

---

## 4. 未知資訊

| ID | 未知 | 為什麼重要 | 本次替代訊號 | 替代訊號的限制 | 建議取得方式 |
|---|---|---|---|---|---|
| U01 | 台灣 Google 上「娛樂城」、「3A娛樂城」和 3A 長尾的實際排名 | 決定 2030.tw 實際上是不是主要威脅 | WebSearch 全部查不到 2030.tw（F30） | 美國引擎、索引範圍不同、不支援 `site:`，不能外推到 Google 台灣 | 用台灣 IP 開無痕手動查 20–30 個查詢，或用指定台灣地區的 rank tracker |
| U02 | 流量與流量結構 | 判斷哪條漏斗有效 | 無（PSI 429，見 `psi_wordcup_mobile.json` 8eeb60dae6c1） | — | Similarweb、CrUX API（需要金鑰） |
| U03 | 完整外鏈與 referring domains（舊 URL 的外鏈品質） | 判斷 Off-page 實力與風險 | Wayback 舊 URL 清單、fbclid 指紋、1 個 301 網域 | 只能推論「應該有外鏈」 | Ahrefs／Majestic／Semrush：看 Best by links、Redirects 報告 |
| U04 | `/wordcup/` 有多少頁被 Google 收錄 | 判斷 2,502 頁是否真的進了索引 | 無 | — | 用 Google `site:2030.tw/wordcup` 手動抽查 20 個 URL |
| U05 | 還有沒有其他過期網域 301 到 2030.tw | 判斷導入網絡的規模 | 只找到 1 個（F28） | 沒有反查工具；crt.sh 被 robots 禁止 | 外鏈工具的 redirect 報告、付費的 reverse NS/IP 資料集 |
| U06 | 舊站真實身分（是否政府相關） | 影響 expired domain abuse 的嚴重度 | URL 與圖檔命名（F22） | Wayback 快照 429 | 改天讀取 Wayback 快照 |
| U07 | `/wordcup/` 的營運者是第一方還是租用方 | 決定適用哪條政策（scaled vs site reputation abuse） | 追蹤碼一致（I03） | 間接證據 | 長期觀察 CTA 和代碼是否同步變動 |
| U08 | 3A 和 WG 的關係、`3a1788.bet` 是不是 3A 官方網域 | 影響品牌 SERP 策略 | 子網域命名、Open165（F29） | Open165 是民眾通報，不等於判定 | 若我方是品牌方，可內部確認 |
| U09 | Core Web Vitals | 頁面體驗 | HTML 大小（首頁未壓縮 238KB）、CF APO 快取 | 沒有 lab 也沒有 field 數據 | 用有金鑰的 PSI，或 CrUX |
| U10 | 我方網站的定位與現況 | 行動要怎麼排序 | — | 本報告用兩種情境處理 | 請使用者提供網址、GSC 資料 |

---

## 5. On-page 策略分析

### 5.1 架構

```
舊站外鏈（2020–2025，推論）
  └─> 照舊拼法重建的 URL：/article/…（8）、/2kapb2a/…（11+）、舊分類（/5g_taiwan/ 等）
iftomm2015.tw ──301（全站→首頁）──> 2030.tw/
        │
WordPress 運彩區：3,400 篇（sitemap 內 91% 為 MLB 程式化頁），每頁有 WG 代理橫幅
        │  全站導覽「線上娛樂城推薦」×3（每個 WP 頁都有）
        ▼
/wordcup/ hub「線上娛樂城推薦｜2026最新評價排名」：共 2,502 篇
        │  每頁 48 篇 × 53 頁（canonical 指回 hub）＋文末「相關推薦」「熱門娛樂城推薦」內鏈
        ▼
/wordcup/{品牌或查詢}：換關鍵字的模板頁 ── 4 個 nofollow CTA ──> don0911.3a1788.bet
```

### 5.2 怎麼承接「娛樂城」（head term）
- 至少有 3 個頁面競爭同一意圖：hub（title「線上娛樂城推薦」）、`/wordcup/娛樂城`（title「娛樂城評價｜台灣玩家首選平台」）、`/wordcup/娛樂城推薦`（F11、F16、F18）。這是**自我 cannibalization**。exact-match 頁 `/wordcup/娛樂城` 套的是品牌評測模板，還會出現「娛樂城最低入金多少?」這種不合理的 FAQ，對 head term 的資訊意圖（怎麼選、風險、比較）回答很弱。
- 它的優勢是導覽位置：每個 WP 頁都有 3 個連到 hub 的連結，所以舊網域留下的權重主要流向 hub（F10）。
- **對我方的意義**：要拿 head term，靠的是一頁真正回答「如何比較與選擇、風險、條款」的 hub，而不是更多換字頁。它在這裡沒有內容護城河。

### 5.3 怎麼承接「3A娛樂城」（品牌，含導航與交易意圖）
- 用一個 URL 對一個意圖的方式，覆蓋 3A 的導航查詢（官網、登入、註冊、app）、交易查詢（優惠、vip、反水、平行轉移）和資訊查詢（百家樂品牌）（F18）。每頁 title 都把關鍵字放最前面，加上年份「2026」，H2 涵蓋玩家決策的六個面向，最後放 FAQPage（F14）。
- 品牌導航查詢的使用者想找的是官方入口。它用「完整評測」頁攔截，再用 CTA 把人導到代理連結（F15），這是典型的品牌字聯盟攔截。
- 它的模板**完全沒提到品牌的負面或信任議題**，可是公開資料顯示這是真實存在的需求：Open165 有 21 次以「3A娛樂城」為名的檢舉，其中一筆是 `3a1788.bet` 的子網域（F29）。這是可以切入的缺口。

### 5.4 內容品質與 E-E-A-T 訊號
- **Experience 是假的**：第一人稱的「實測、玩了幾個月」沒有任何可驗證的細節（截圖、日期、金額、條款），而且至少換了 3 種人設（F14、F16、F18；I07）。
- **Expertise／Authoritativeness 很弱**：
  - 只有一位作者，作者頁 noindex、沒有簡介（F08）。
  - 賭場頁的可見署名「2030編輯部」，和外框 schema 裡的 Person「小編妮妮」對不起來（F13、F14）。
  - 沒有 about、聯絡或隱私頁，page sitemap 裡完全沒有（F09）。
- **Trust 有反效果**：論壇空殼卻宣稱萬名球迷（F09）；日期刷新（I08）；在 YMYL 主題下只寫正面內容。
- **Keyword stuffing 跡象**：關鍵字字元佔正文 5–8.5%（F16），依 Google 的 keyword stuffing 定義屬於「重複到不自然」（F31）。

### 5.5 運彩區：MLB 程式化頁
- 每天依賽程自動產生賽前與賽果頁。title 樣式是「【MLB直播】YYYY/MM/DD A VS B | 先發投手+打線+MLB今日賽程」，內容是戰績、投手數據、打線，加 quickchart.io 圖表（F05、F07）。用途是吃每天大量的「MLB直播／比分／賽程」長尾，並在每頁放 WG 橫幅（F15）。
- 缺點：
  - meta description 是圖例文字（F07）。
  - 頁面內容幾乎只有資料表。
  - MLB 休賽季就沒有新內容（最新一篇 2026-10-30，F06）。
  - 33% 的頁面不在 sitemap 裡（F06）。

### 5.6 技術 SEO 小結

| 面向 | 它做得好 | 它的漏洞 |
|---|---|---|
| 可索引性 | 主要頁 `index,follow`、canonical 指向自己；tag 和作者頁 noindex，避免了 1,359 個 tag 頁膨脹（F07、F08） | demo 頁、sample-page、空論壇都可索引（F09） |
| 發現與 sitemap | 有 news sitemap 和 Rank Math sitemap（F04） | 8 月起停更，33% 漏收（F06）；賭場區沒有 sitemap（F12）；hub 分頁 canonical 指回第 1 頁（F11） |
| 結構化資料 | 有 Article、FAQPage、BreadcrumbList（WP 頁） | 賭場頁同時有另一篇 MLB 文章的 NewsArticle／WebPage 和自己的 Article，實體互相矛盾（F13）；首頁 og:title「Home 1」；第二個 Organization 的 name 是空的，sameAs 指向 `http://plus.google.com`（`home_desktop.html`）；FAQPage 依 Google 2023-08 公告大概拿不到 rich result（本次未重新查證） |
| 標題結構 | 關鍵字放前面，有年份 | 賭場頁和舊網址頁都有 2 個 H1（F14、F26） |
| 效能與快取 | Cloudflare APO 在 TPE 節點命中快取（F02） | hub 快取了 11.8 天沒更新（F17）；首頁 HTML 未壓縮 238KB |
| Redirect | 舊大小寫網址會 301 加斜線，再回 200 給 canonical 小寫版（F24） | `http://www` 要多跳一次 `https://www` 才到 apex（`redirect_http_www.html.headers` 9e3031abd8a5） |
| 行動版 | 桌機和行動版 HTML 相同（F20） | — |

### 5.7 值得學、不該學
- **可以學（合規作法）**：
  - 一個意圖一個 URL 的品牌查詢地圖。
  - 把玩家決策面向做成 H2：出金、優惠條款、註冊、客服。
  - 全站導覽把權重送進 money hub。
  - 運彩內容和娛樂城主題之間做主題橋接。
- **不要學**：過期網域重建舊 URL、換字模板量產、假的第一人稱經驗、刷新日期、關鍵字堆疊、空殼 UGC。這些都對應 F31 的政策條目，風險在第 7 節。

---

## 6. Off-page 策略分析

1. **過期網域本身（2030.tw）**：舊站有約 5 年歷史（F22）。2026-04-15 重新註冊（F21）後，除了 demo 頁，page sitemap 的 lastmod 從 2026-04-16 開始；重建舊 URL 的頁面發布在 04-17～04-21，也就是註冊後 2–6 天（F23–F26）。舊站的外鏈因此直接落在新的運彩頁上，例如舊短網址 `/2kAPB2a` 現在是 NBA 分析頁（F24）。重建的對象有選擇性：只重建了 8 個 `/article/`，而舊站有 168 個；另外有 fbclid 殘留（F23）。這表示它是依「哪些舊 URL 有連結或分享」來挑選的（I04，中信心）。
2. **導入其他過期網域**：iftomm2015.tw（2015 年台灣主辦的 IFToMM 研討會網域）在 2026-04-28 註冊，全站 301 到 2030.tw 首頁（F28）。28 分鐘後，2030.tw 建了 `/iftomm2015cd/pdf/os11-017-pdf/` 頁（F26）。這種「研討會、學術網域導進博弈相關站」的做法，正是 Google 政策裡「過期網域被拿來放不相關商業內容」的典型（F31）。其他導入網域是否存在：未知（U05）。
3. **品牌與社群訊號很弱**：
   - schema 的 sameAs 只有一個 Facebook 專頁 `https://www.facebook.com/www.2030.tw`，以及佔位用的 `http://twitter.com` 和已關閉的 `http://plus.google.com`（`home_desktop.html` dd1e733c49cd）。
   - 品牌名查詢在 WebSearch 查不到它（F30）；「2030.tw」還會和股票代號混在一起（WS-04）。
4. **聯盟與代理關係**：
   - 推論是 WG 和 3A 的代理（F15、I09）。所有外連都加 nofollow，這是符合 Google 對付費或聯盟連結的作法，也表示它不靠外連交換做 SEO。
   - 3A 側的網域在公開防詐資料中有通報紀錄（F29）。這對它本身（YMYL 信任）和連到它的網站都是聲譽風險。
5. **外部 SERP 生態**：在可用的搜尋引擎中，兩個關鍵字的結果被高權重平台上的寄生頁佔據（`.edu` 子路徑、GitLab、Docker Hub、Substack、媒體站的專欄或筆記），還有疑似過期品牌網域（`fisherprice.com.tw/娛樂城推薦`）（F30）。2030.tw 走「自有過期網域」路線，其他競爭者走「寄生在別人網域」路線，兩者都屬於高風險的 Off-page 手法。這代表 SERP 波動會很大，而且 Google 的政策更新本身就是一個競爭變數。

---

## 7. 政策與 YMYL 風險（作為 SEO 因素）

| 觀察到的手法 | 對應 Google 政策（F31） | 對 2030.tw 的風險 | 對我方的意義 |
|---|---|---|---|
| 過期網域照舊拼法重建 URL，放運彩與博弈導流內容（F21–F26） | Expired domain abuse，例子包括「前政府機關網站放聯盟內容」、「前小學網站放賭場內容」 | 可能整站被降權或人工處置（I11） | 不要買過期網域來做；它若被處置，會空出排名，要事先準備好承接頁 |
| 2,502 篇換關鍵字模板頁（F16、F18） | Scaled content abuse（生成工具大量產頁）、Doorway abuse（大量相似頁導向同一終點） | 演算法或人工處置 | 用少量高價值頁競爭；不要用量去拼 |
| 關鍵字佔正文 5–8.5%（F16） | Keyword stuffing | 頁面品質判定變差 | 自然的語意涵蓋 |
| 代理 CTA 頁沒有原創測試或比較資料（F14、F15） | Thin affiliation | 品質判定變差 | 聯盟頁要有獨家數據與方法論 |
| 在 YMYL（金錢、博弈）主題下用假經驗、刷日期、空殼社群（F09、F14、F17） | 品質評分中的 E-E-A-T／Trust（一般知識，本次未抓原文） | 信任訊號弱 | 用可驗證的身分、方法和更新紀錄建立 Trust |
| 出租子目錄的可能性（I03 排除了一部分） | Site reputation abuse（第三方內容） | 若是租用，也屬違規 | 監測它的 CTA 和代碼是否變更 |

**合規提醒**：所有建議都假設我方的營運與推廣符合所在司法管轄區的法規和平台政策。法規評估不在本報告範圍內。

---

## 8. 優先行動

**排序依據**：(1) 對兩個指定關鍵字的**影響力**；(2) **成本**（人力、時間）；(3) **可行性**（不需要不確定的外部配合）；(4) **不確定性**（缺乏排名資料時，優先做「不管排名如何都有價值」的事）。排序大致等於「預期效益除以成本，再依不確定性打折」。我方身分未知（U10），所以分兩種情境：**A＝我方是 3A 品牌官方或授權方**；**B＝我方是第三方內容或評測站**。

| 順序 | 行動 | 針對的證據 | 影響力 | 成本 | 可行性 | 不確定性 | 為何排在這裡 | 驗收指標 |
|---|---|---|---|---|---|---|---|---|
| 1 | **拿下「3A 品牌查詢群」**。A：建立官方、可爬取的頁面組：官方網址與防詐驗證、登入、註冊、APP、客服、優惠條款；加上 Organization schema 與 sameAs，品牌拼法統一為「3A」。B：做 1 篇高品質的「3A娛樂城評價／安全性／出金」頁，附可驗證的測試紀錄、條款表、Open165 查詢方法，正面回應它的模板刻意迴避的信任意圖。 | F14、F15、F18、F29、I10 | 高：這是它最集中的投入，而且導航查詢理論上最該由真正的實體拿下 | 低–中 | 高 | 中（不知道現在的 SERP） | 對「3A娛樂城」的影響最直接，證據也最強，而且對手的內容在信任意圖上完全空白 | TW 地區 3A 變體查詢的排名與點擊（GSC）；品牌 SERP 前 10 名中我方的頁數 |
| 2 | **索引與 schema 衛生（快贏）**：sitemap 即時更新、依類型拆分、lastmod 正確；送 GSC，Bing 送 IndexNow；分頁 canonical 指向自己；單一 H1；單一 Organization 實體；Article 用真實日期與真實作者；BreadcrumbList；清掉 demo 頁。 | F06、F11、F12、F13、F09 | 中 | 低 | 高 | 低 | 不管排名如何都值得做；也是第 1、3 項的新頁能被快速收錄的前提；對手在這方面明顯落後 | GSC 索引涵蓋率；新頁從發布到被收錄的天數 |
| 3 | **「娛樂城」head term：做 1 個有方法論的 hub，加 20–50 篇深度頁**（不要做 2,000 篇換字頁）。公開評比準則與權重；附實測紀錄（時間戳、入出金時效、條款或流水表）；有具名作者與簡介、更新紀錄、風險與負責任博弈段落；用 hub 下的錨點承接變體查詢，不要每個查詢各開一頁。 | F11、F16、F18、I07、F31 | 高（長期） | 高 | 中 | 高（SERP 充滿垃圾頁，品質不一定很快贏） | 是 head term 唯一可持續的槓桿，但成本與不確定性最高，所以排第 3，並和第 1、2 項同時開始 | hub 的曝光與排名趨勢；長尾查詢的點擊數 |
| 4 | **競品監測與政策事件應對**：每週記錄它的 hub 總數（目前 2,502）、sitemap lastmod、3A 變體頁數、CTA 目的地、新的 301 導入網域；對照 Google spam update 日期。可選擇送一份 spam report（expired domain abuse 加 scaled content），成本低，但效果不確定。 | F06、F17、F28、I11 | 中（看時機） | 低 | 高 | 高 | 它的策略脆弱，一旦被處置會空出排名。監測成本低，能讓第 1、3 項在空窗期最快接手 | 監測表；事件發生後我方承接頁的排名變化 |
| 5 | **可持續的 Off-page**：A：統一官方社群與檔案、做新聞或贊助曝光（付費連結加 `rel="sponsored"`）。B：做會吸引自然連結的資料型資產，例如運彩賠率或賽事數據工具、條款比較表，搭配 digital PR。明確**不做**過期網域、寄生頁和 PBN。 | F30、第 6 節第 1–2 點 | 高（長期） | 高 | 中 | 高 | 外鏈缺口是未知（U03），要先量測再投入；長期必要，但短期見效慢 | referring domains 品質與成長（取得工具之後） |
| 6 | **運彩內容當上游流量（選擇性）**：若商業模式允許，就季節性地做有原創分析的賽事內容（例如目前 NBA 賽季），用情境式內鏈接到娛樂城 hub。不要做純資料模板。 | F05、F07 | 低–中（對指定兩個關鍵字是間接的） | 中 | 中 | 高 | 對手這條漏斗真實存在，但和指定關鍵字的關係是間接的，所以放最後 | 運彩頁導到 hub 的內鏈點擊 |

**刻意不建議的事**：
- 買過期網域。
- 寄生在 `.edu` 或媒體站。
- 量產換字頁。
- 假冒的第一人稱實測。
- 刷新日期。
- 為了拿 rich result 塞 FAQPage。
- 模仿官方或冒用品牌（情境 B 尤其要避免，以免被誤認為官方入口）。

---

## 9. 下一步最值得研究什麼（依資訊價值排序）

1. **台灣 Google 的實際 SERP（U01）**：「娛樂城」、「3A娛樂城」加上 F18 的 13 個 3A 變體。用台灣 IP 開無痕查詢，或用 rank tracker（地區設台灣）。理由：這決定本報告的威脅評估是否成立，成本最低、資訊價值最高。
2. **`/wordcup/` 的索引狀態（U04）**：用 `site:` 抽查 20 個 URL，並查 hub 的快取版。理由：可以驗證 I12，知道 2,502 頁是真威脅還是紙老虎。
3. **外鏈與導入網域（U03、U05）**：用 Ahrefs、Majestic 看指向舊 `/article/` 與舊短網址的 referring domains，以及有哪些網域 301 到 2030.tw。理由：可以量化 I04、I06，並判斷舊權重還剩多少。
4. **完整的關鍵字清單**：以 ≥1.5 秒間隔抓完 53 個 hub 分頁（53 次請求），取得全部 2,502 個 slug，分類後再用 GSC 或 Keyword Planner 驗證搜量。理由：這等於免費拿到它的關鍵字研究結果，可以用來排我方的內容缺口。
5. **時間序列監測（每週）**：總篇數、日期、sitemap 狀態、CTA 目的地。理由：驗證 I08，並及早偵測 Google 的處置。
6. **改天讀取 Wayback 快照（U06）**：確認舊站身分，判斷 expired domain abuse 的嚴重程度。
7. **我方基準資料（U10）**：需要使用者提供網址和 GSC 匯出，才能把第 8 節的排序換成量化的 ROI。

---

## 附錄 A：證據檔案（`B-raw/`，sha256 前 12 碼）

| 檔案 | sha256-12 | 內容 |
|---|---|---|
| `_requests.tsv` | cb4ae6a7496c | 逐筆請求紀錄（60 列，其中 1 列 robots SKIP） |
| `robots_2030.tw.txt` | c59d971fff8d | robots.txt |
| `home_desktop.html`／`.headers` | dd1e733c49cd／b1f5cc789856 | 首頁 |
| `sitemap_index.xml`／`.headers` | c2b1cbd2d158／667542217b0e | sitemap index |
| `post-sitemap1.xml`、`post-sitemap2.xml` | fb5e7fb970e9、4a56d2235653 | 文章 sitemap |
| `page-sitemap.xml`、`category-sitemap.xml`、`news-sitemap.xml`、`local-sitemap.xml` | 3426ef9d9961、73f29e73435a、9e6911c3c7b2、0fde761da3c5 | 其他 sitemap |
| `page_wordcup.html`／`.headers` | 0190322d8ca6／55c1bcfdcf34 | 娛樂城 hub（11/04 快取） |
| `wordcup_hub_p2/p26/p52/p53.html` | 7116724b35bd／76faec4ad6d6／2548b18aec8b／b4467989b59c | hub 分頁抽樣 |
| `wordcup_3a.html`／`.headers` | 06338ff143b3／e46c62bca731 | 3a娛樂城頁 |
| `wordcup_3a_mobile.html` | 06338ff143b3 | 行動版 UA（與桌面相同） |
| `wordcup_yulecheng.html`／`.headers` | 574f8a8224e7／5c929fff51e0 | 娛樂城頁 |
| `wordcup_3a_guanwang.html` | 902272ea99f1 | 3a官網頁 |
| `wordcup_nonexistent_test.html`／`.headers` | d465172175d3／0173aba26460 | 404 測試 |
| `post_mlb_live_20261031.html`／`.headers` | f1cb03038143／7cfe25d5ae10 | 最新 MLB 頁 |
| `page_legacy_responsible_ai.html` | f76653ad3617 | 舊 slug 頁 |
| `post_legacy_os11_017_pdf.html` | 656c5b9f8085 | 舊 iftomm 路徑頁 |
| `legacy_shortlink_2kAPB2a.html.headers`、`legacy_shortlink_2kAPB2a_slash.html`／`.headers`、`legacy_article_mixedcase.html.headers` | 52c57e621f86、93d43e995767／11d15af468f8、441773ed092e | 舊網址 redirect 實測 |
| `wpjson_posts_latest5.json`／`.headers`、`wpjson_posts_after_20260822.json`／`.headers`、`wpjson_tags_1.json`／`.headers` | ae099df87875／25738f0b9d62、35981250f465／014039caaf9c、f5921df0f268／8b0d73d2834b | REST API 計數 |
| `tag_mlb_bifen.html`、`author_machnage.html`、`page_community.html` | c55cfaee2c8d、0c5a6b27705e、5576e5bbec43 | tag、作者、論壇 |
| `redirect_http_www.html.headers` | 9e3031abd8a5 | http→https 的 www redirect |
| `whois_2030.tw.txt`、`dns_2030.tw.txt` | 0907dd08133c、e5bddd19b3eb | WHOIS 與 DNS |
| `wayback_cdx_home_monthly.txt`、`wayback_cdx_domain_prefix_to2025.txt`、`wayback_cdx_article_prefix_to2025.txt`、`wayback_cdx_iftomm_prefix_to2025.txt` | 32c7d687474a、6562047aaa16、577461414ac1、e3b0c44298fc | Wayback CDX |
| `wayback_home_20251108.html`、`wayback_cdx_domain_nonasset_to2025.txt` | e859c18f0c0c、e084d5279217 | Wayback 快照 429 頁、CDX 503 頁（未能取得） |
| `dns_whois_iftomm2015.tw.txt`、`iftomm2015tw_home.html.headers`、`iftomm2015tw_os11_017_pdf.html.headers` | d503f8cf80ad、c098faecb904、87c39c534a72 | iftomm2015.tw |
| `g0v165_name_3A.html` | b8a8ea50cd99 | Open165 頁 |
| `google_spam_policies_en.html` | 14794e28d278 | Google 垃圾內容政策 |
| `websearch_log.md` | bb870ce2ff00 | WebSearch 15 次查詢的回應摘錄 |
| `psi_wordcup_mobile.json` | 8eeb60dae6c1 | PSI 額度錯誤 |

## 附錄 B：請求統計（逐筆見 `_requests.tsv`）

- **2030.tw 網站**：2030.tw 主機 31 次，www.2030.tw 2 次，另有 2 個 redirect hop（http://www → https://www → https://2030.tw/robots.txt），合計 **35 次 HTTP**。WebFetch 0 次。對 2030.tw 沒有使用 PSI 或其他代抓服務（PSI 因額度錯誤，沒有對目標發出請求）。
- **其他主機**：web.archive.org 11、iftomm2015.tw 4、index.commoncrawl.org 2（robots 與 collinfo）、crt.sh 1（只抓 robots，查詢因 robots 跳過）、urlscan.io 2、165.g0v.tw 2、www.googleapis.com 2、developers.google.com 2，合計 26。
- **WebSearch**：15 次（WS-01～WS-15）。DNS/WHOIS 查詢不屬於 HTTP，沒有計入。
