## 經驗筆記（使用中）
（每條是上次研究真的走過、有 Evidence ID 的路線；決定怎麼查時參考。照走：照路線查，但一定重新取證；別走（查不到）：用同一 Tool、同一目標輕試 1 次，抓即時資料；別走（會誤導）：不重試。照某條經驗查時，在那次 Tool 呼叫的 why 寫上經驗編號；這次證據推翻某條經驗時，寫在報告的 experience.overturned。）
- [EXP-001｜照走] 情況：競品網站的 sitemap 有上千個以關鍵字命名的商業頁面（例如博弈、貸款類），主體卻是體育或新聞內容；網域註冊日很新，但 Wayback 有更早的存檔。要判斷它的關鍵字頁怎麼做，以及網域是否承接舊站。
  路線：
  1. sitemap_tree：先 build 再看分區與 sample，因為能知道哪個資料夾佔大宗、網址 slug 是否直接用關鍵字與長尾變體
  2. inspect_page：讀指定關鍵字的專屬頁（title、H1/H2、FAQ、JSON-LD），因為能核對結構是否為模板並看 schema 是否錯置
  3. inspect_page：用 link_filter 篩外部網域看 rel 與追蹤參數，因為摘要只列主機，不一定看得到 rel 或 st 參數
  4. wayback：snapshot 抓註冊日前的首頁再 inspect_page，因為 RDAP 註冊日只代表最近一次註冊，需用舊內容確認前身
  （實際 Tool：sitemap_tree、wayback、inspect_page）
  結果：照走
