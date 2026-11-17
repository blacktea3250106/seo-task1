## 經驗筆記（使用中）
（每條是上次研究真的走過、有 Evidence ID 的路線；決定怎麼查時參考。照走：照路線查，但一定重新取證；別走（查不到）：用同一 Tool、同一目標輕試 1 次，抓即時資料；別走（會誤導）：不重試。照某條經驗查時，在那次 Tool 呼叫的 why 寫上經驗編號；這次證據推翻某條經驗時，寫在報告的 experience.overturned。）
- [EXP-001｜照走] 情況：競爭者網站的 sitemap 有一個佔比很大的單一資料夾，網址是關鍵字當 slug（例如博弈、貸款這類高競爭詞）。要判斷它如何針對指定關鍵字做頁面，並確認 sitemap 的占比能不能代表全站。網域可能曾換過主人或換過主題。
  路線：
  1. sitemap_tree：用 search 搜指定關鍵字，再用 sample 看最大分區的網址型態，因為 slug 就是對方的關鍵字佈局。
  2. polite_fetch：抓指定關鍵字的專頁和該分區列表頁，因為要看 title、H1、H2、FAQ 與分類結構才能判斷模板化程度。
  3. sitemap_tree：對首頁最新文章網址再搜一次並用 by_month 看 lastmod 截止月份，因為 sitemap 可能漏掉新文，占比不能當全站比例。
  4. wayback：用 timeline 看歷史存檔，再用 snapshot 抓換手前最後的首頁快照，因為註冊日比存檔晚時要確認網域是否換過主題。
  （實際 Tool：sitemap_tree、polite_fetch、wayback、inspect_page）
  結果：照走
