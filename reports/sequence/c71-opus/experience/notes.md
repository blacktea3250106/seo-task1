## 經驗筆記（使用中）
（每條是上次研究真的走過、有 Evidence ID 的路線；決定怎麼查時參考。照走：照路線查，但一定重新取證；別走（查不到）：用同一 Tool、同一目標輕試 1 次，抓即時資料；別走（會誤導）：不重試。照某條經驗查時，在那次 Tool 呼叫的 why 寫上經驗編號；這次證據推翻某條經驗時，寫在報告的 experience.overturned。）
- [EXP-001｜照走] 情況：競品首頁選單有指定關鍵字的錨文字，但 robots 列出的 sitemap 索引裡找不到對應的大量頁面；資料卡分區顯示某個資料夾的網址數量異常多，而且是靠資料夾探測才找到它的獨立 sitemap。這時要確認這個資料夾是不是關鍵字量產頁群，以及指定關鍵字有哪些變體頁。
  路線：
  1. sitemap_tree：先 build，再對大分區做 sample 和 search 指定關鍵字，因為要知道量產頁群的網址樣式、變體頁數量，以及這些頁在哪個 sitemap 檔
  2. inspect_page：看選單錨文字連到的入口頁和 2 到 3 個關鍵字變體頁的 summary，因為要比對模板結構、canonical 和 JSON-LD
  3. inspect_page：用 link_filter 篩外連品牌和同資料夾的連結，因為要確認 CTA 的 rel、推廣參數和站內互連數
  4. polite_fetch：讀 robots.txt，核對這個 sitemap 有沒有列在 robots，因為要確認是否只有探測才找得到
  （實際 Tool：sitemap_tree、inspect_page、polite_fetch）
  結果：照走
- [EXP-002｜照走] 情況：RDAP 的註冊日期很新，但 Wayback 存檔早好幾年；sitemap 裡還有看起來像舊站短網址代碼或舊分類名的分區。這時懷疑是過期網域再利用，要確認舊站主題，以及新站有沒有沿用舊網址。
  路線：
  1. wayback：用 old_urls 列舊網址，再用 snapshot 讀一個舊首頁，因為要知道舊站主題和當年用過的網址樣式
  2. wayback：用 check_current 看舊網址現在回什麼狀態碼，因為要分出哪些舊網址被接住、哪些已失效
  3. polite_fetch：跟著轉址抓被接住的舊網址最終頁，再用 inspect_page 看內容，因為只看轉址可能只是補斜線
  4. sitemap_tree：search 舊代碼字首，核對 sitemap 裡有幾個同名頁，因為只驗一頁不能推成策略
  （實際 Tool：wayback、polite_fetch、inspect_page、sitemap_tree）
  結果：照走
- [EXP-003｜照走] 情況：量產頁群的頁面上，顯示的「更新」日期和 JSON-LD dateModified 很接近抓取當天，但 og 日期和 sitemap lastmod 停在好幾個月前；網站前面有 CDN 快取。這時要分清楚：這些日期是刻意營造新鮮度，還是快取產生時間的副作用。
  路線：
  1. inspect_page：看量產頁的 jsonld 和 summary，記下顯示日期、JSON-LD 日期和 og 日期，因為三者對不上才需要追查
  2. polite_fetch：重抓同一頁，看 last-modified、age、快取命中標頭，因為日期可能就是快取產生時間
  3. text_match：在另一個同類頁搜尋「更新」和 dateModified，因為只看一頁不能推到整個頁群
  4. inspect_page：再抽 3 頁以上，比較頁首日期是否各不相同，因為各頁快取時間不同時，日期也會跟著不同
  （實際 Tool：inspect_page、text_match、polite_fetch）
  結果：照走
- [EXP-004｜照走] 情況：舊網址樣式和新網址很像，但只差在大小寫或結尾斜線；或舊網址轉址一次就停住。這時不能把永久轉址直接算成「接住舊網址」，要追到最終落點，看是不是新內容、canonical 指向哪裡。
  路線：
  1. wayback：用 snapshot 讀舊首頁，再用 inspect_page 列出舊連結，因為要拿到舊站真實網址和大小寫
  2. wayback：對舊網址做 check_current，因為要分出失效、只補斜線的轉址、轉到別頁的轉址
  3. wayback：對只補斜線的轉址落點再做一次 check_current，因為第一跳可能只是斜線轉址
  4. inspect_page：看最終成功頁的 title 和 canonical，因為要確認是否被新內容接住、指向哪個新網址
  （實際 Tool：wayback、inspect_page）
  結果：照走
- [EXP-005｜照走] 情況：量產頁上有兩組 JSON-LD，日期互相矛盾：一組是錯置的其他頁實體、日期很舊，另一組日期很接近抓取當天。頁首也顯示「更新」日期，網站前面有 CDN 快取。這時要分清楚每個日期各自對應到什麼。
  路線：
  1. inspect_page：用 part=jsonld 讀出原始 JSON-LD，因為摘要只列類型，看不到兩組各自的日期
  2. polite_fetch：用 GET 重抓同一頁，記下 last-modified 和 age 標頭，因為 HEAD 回應可能沒有內容可以比對
  3. text_match：在這份重抓結果的 html 裡搜 dateModified、更新、generator，因為標頭和日期要在同一份證據裡比對才算數
  （實際 Tool：inspect_page、polite_fetch、text_match）
  結果：照走
- [EXP-006｜照走] 情況：網域目前的註冊日期很新，但存檔顯示舊站是另一個主題的機構網站；新站的選單或頁尾連到看起來像舊站文章代號、舊分類名的網址。這時要確認新站是不是把舊網址重建成新主題內容，以及哪些舊網址被放棄。
  路線：
  1. inspect_page：對一個內頁用 link_filter 篩全部連結，列出選單和頁尾網址，因為選單常直接指向被重建的舊網址
  2. sitemap_tree：search 舊文章資料夾，核對 sitemap 裡沿用舊代號的頁，因為要分清楚是個案還是一批
  3. wayback：對失效的舊網址，用補斜線和小寫版本再做 check_current，因為原樣失效可能只是格式不符
  4. polite_fetch：用 follow_redirects=false 抓舊網址，拿到轉址的 Location 標頭，因為存檔檢查可能沒列出目的地
  （實際 Tool：polite_fetch、wayback、inspect_page、sitemap_tree）
  結果：照走
- [EXP-007｜照走] 情況：競品網域目前的註冊日期很新，存檔卻顯示舊站是另一個主題；新站選單連到看起來像舊站文章代號的網址，舊短網址或舊分類名用大寫寫成，不帶斜線時會先轉址。這時要確認舊網址是被重建成新主題內容，還是已經失效；另外，存檔服務可能限流。
  路線：
  1. polite_fetch：用 follow_redirects=false 抓舊大寫網址拿 Location 標頭，因為存檔檢查看不到轉址目的地
  2. inspect_page：跟轉址抓最終頁看 title 和 canonical，因為要確認是不是新主題、指向哪個小寫網址
  3. inspect_page：對內頁用 link_filter 篩選單連結並和存檔舊網址對照，因為存檔被限流時選單仍能證明舊代號被重用
  4. polite_fetch：對失效的舊文章再試帶斜線的版本，因為只試一種格式不能斷定已放棄
  （實際 Tool：wayback、polite_fetch、inspect_page）
  結果：照走
- [EXP-008｜照走] 情況：第一次 build sitemap 時，某個 sitemap 檔回 5xx，報告裡的關鍵字網址數因此可能偏低；重新 build 又會沿用快取，沒有重讀那個檔。這時要確認漏讀的檔裡有沒有指定關鍵字的網址，數字才能當作完整的。
  路線：
  1. sitemap_tree：build 後對指定關鍵字做 search，記下 matches 和 by_sitemap，因為要知道網址數在哪幾個檔
  2. polite_fetch：直接重抓回 5xx 的 sitemap 檔，因為重新 build 可能沿用快取、不會重讀
  3. text_match：在重抓的 sitemap 原檔 html 裡搜關鍵字和量產資料夾名，因為要確認漏讀的檔有沒有相關網址
  （實際 Tool：sitemap_tree、polite_fetch、text_match）
  結果：照走
- [EXP-009｜照走] 情況：網域的舊站是另一個主題的機構網站，新站 sitemap 裡有看起來像舊文章代號的網址，但存檔服務列舊網址清單時一直逾時。這時要用逐頁查存檔的方式，證明這些代號是舊站真的用過的網址，以及新站在這些網址上放了什麼內容。
  路線：
  1. wayback：對單一舊代號網址做 timeline，因為列舊網址清單逾時時，單頁時間線仍能證明舊站用過
  2. wayback：對不帶斜線的舊代號做 check_current，因為要知道舊格式是否永久轉址到新網址
  3. inspect_page：抓補斜線後的頁看 title 和 canonical，因為只有轉址不能證明內容已換主題
  4. wayback：對舊路徑名的大小寫版本做 timeline，因為舊站路徑常是大寫，新站改成小寫
  （實際 Tool：inspect_page、wayback）
  結果：照走
