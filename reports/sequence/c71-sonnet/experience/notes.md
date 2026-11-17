## 經驗筆記（使用中）
（每條是上次研究真的走過、有 Evidence ID 的路線；決定怎麼查時參考。照走：照路線查，但一定重新取證；別走（查不到）：用同一 Tool、同一目標輕試 1 次，抓即時資料；別走（會誤導）：不重試。照某條經驗查時，在那次 Tool 呼叫的 why 寫上經驗編號；這次證據推翻某條經驗時，寫在報告的 experience.overturned。）
- [EXP-001｜照走] 情況：競爭者網域看起來像舊站改作新用途：sitemap 有一個佔一半以上網址的資料夾，內容是大量關鍵字頁；要查它的歷史與變現方式。
  路線：
  1. sitemap_tree：build 後看各分區網址佔比，並 search 指定關鍵字，因為能快速找出關鍵字頁集中在哪個資料夾。
  2. inspect_page：讀該資料夾列表頁與一個關鍵字頁的 link_filter 外部連結，因為可看 rel 屬性與推廣參數。
  3. wayback：用 timeline 看狀態碼變化，再 snapshot 舊首頁，因為能證明網域曾換用途，而註冊日只代表最近一次註冊。
  4. inspect_page：抽一個資料驅動的賽事頁，因為可確認大量頁面是否為模板化。
  （實際 Tool：inspect_page、sitemap_tree、wayback）
  結果：照走
- [EXP-002｜照走] 情況：競爭者網域像舊站改作新用途：首頁是運動或資訊內容，但選單藏一個商業關鍵字資料夾，sitemap 該資料夾網址佔約一半。需要判斷關鍵字頁規模、是否模板化、如何變現，以及網域歷史。
  路線：
  1. sitemap_tree：build 後用 search 搜指定關鍵字並把 limit 開大，因為預設只列少數樣本，要看完整變體數才不會漏。
  2. inspect_page：讀資料夾列表頁與兩個不同品牌頁，比對 H2、FAQ、H1 數、external_nofollow 與外部主機，因為兩頁以上才能推測是否模板化。
  3. wayback：用 timeline 看狀態碼變化，再 snapshot 轉址前最後一個正常存檔的舊首頁並用 inspect_page 讀，因為能看到舊用途。
  4. domain_info：查 RDAP 註冊日、註冊商與 DNS，因為註冊日只代表最近一次註冊，要搭配 wayback 判斷；中間空窗期不能下結論。
  （實際 Tool：wayback、inspect_page、sitemap_tree）
  結果：照走
- [EXP-003｜照走] 情況：競爭者網域首頁是運動或資訊內容，但 sitemap 有一個佔約一半網址的資料夾，內容是大量商業關鍵字（品牌名＋類別）頁；要判斷頁面是否模板化、導流目標是否一致，以及網域是否由舊站改用途。
  路線：
  1. sitemap_tree：build 後 search 指定關鍵字，因為能看出關鍵字頁集中在哪個資料夾，並比對 matches 與 rows。
  2. inspect_page：讀 3 個以上不同品牌頁的 H1 數、H2、外部主機，因為多頁比對才能說模板化。
  3. inspect_page：對品牌頁用 part=links 加 link_filter 篩推廣網域，因為能直接看 href 與 rel。
  4. wayback：查 RDAP 註冊日並 snapshot 轉址前最後正常存檔，因為註冊日只代表最近一次註冊。
  （實際 Tool：sitemap_tree、inspect_page、wayback、text_match）
  結果：照走
- [EXP-004｜照走] 情況：競爭者網域首頁是運動或資訊內容，但 sitemap 有一個佔約一半網址的資料夾，內容是大量商業關鍵字（品牌名加意圖後綴）頁；需要判斷關鍵字頁規模、是否模板化、導流目標是否一致，以及網域是否由舊站改用途。
  路線：
  1. sitemap_tree：build 後 search 指定關鍵字並把 limit 開到最大，因為預設只列少數樣本，要看完整後綴清單。
  2. inspect_page：讀列表頁與多個內容頁的 H1、H2、FAQ、JSON-LD 型別與 og 日期，因為多頁比對才能分辨結構相同或內文也相同。
  3. inspect_page：每個品牌頁各用 part=links 加 link_filter 篩推廣網域，因為要確認連結是否都導向同一個外部網域。
  4. wayback：timeline 後 snapshot 轉址前最後正常存檔，並搭配 domain_info，因為註冊日只代表最近一次註冊。
  （實際 Tool：inspect_page、wayback、sitemap_tree）
  結果：照走
- [EXP-005｜照走] 情況：競爭者網域首頁是運動或資訊內容，sitemap 有一個佔約一半網址的資料夾，內容是大量商業關鍵字（品牌名加意圖詞）頁，另有一個大量日更模板文章資料夾；網域可能是舊站改作新用途。需判斷關鍵字頁規模、是否模板化、導流目標，以及網域歷史。
  路線：
  1. sitemap_tree：build 後 search 指定關鍵字並 sample 大資料夾，因為能看出關鍵字頁集中處、佔比與網址型態。
  2. inspect_page：讀列表頁與兩個品牌頁的 headings 與 JSON-LD，因為逐頁比對才知 H2、FAQ 是否同模板，title 也要逐頁看。
  3. inspect_page：用 part=links 加 link_filter 篩推廣網域與站內連結，因為只有連結清單看得到 rel 與外部主機。
  4. wayback：timeline 後 snapshot 轉址前最後正常存檔並讀，因為能證明舊用途，再對照 JSON-LD 日期與註冊日。
  （實際 Tool：sitemap_tree、inspect_page、wayback）
  結果：照走
