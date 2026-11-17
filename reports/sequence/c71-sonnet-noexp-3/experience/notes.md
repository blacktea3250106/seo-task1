## 經驗筆記（使用中）
（每條是上次研究真的走過、有 Evidence ID 的路線；決定怎麼查時參考。照走：照路線查，但一定重新取證；別走（查不到）：用同一 Tool、同一目標輕試 1 次，抓即時資料；別走（會誤導）：不重試。照某條經驗查時，在那次 Tool 呼叫的 why 寫上經驗編號；這次證據推翻某條經驗時，寫在報告的 experience.overturned。）
- [EXP-001｜照走] 情況：競品站 sitemap 很大，且有某個資料夾下的子 sitemap 不在 robots 列出，只能靠資料夾探測找到；目標關鍵字（品牌＋長尾詞）疑似被大量生成頁面覆蓋。需要判斷覆蓋規模、頁面是否模板化，以及網域是否有舊站歷史。
  路線：
  1. sitemap_tree：build 讀全站 sitemap，因為 robots 沒列的資料夾 sitemap 只有資料夾探測能找到，並得到各分區網址數
  2. inspect_page：讀分區列表頁與關鍵字落地頁（part=all），因為能一次看到 title、H1/H2、JSON-LD、外鏈與 nofollow
  3. sitemap_tree：search 關鍵字子字串並列出範例，因為能量出變體網址數；範例只代表網址型態，內容要另外抽樣
  4. wayback：snapshot 讀舊年存檔再 inspect_page，因為註冊日晚於存檔時可核對舊站內容與現站 slug 殘留
  （實際 Tool：sitemap_tree、inspect_page、wayback）
  結果：照走
