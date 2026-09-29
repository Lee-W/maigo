# Strict Review — Frontend Device Checks

Loaded on demand by `skills/strict-review/SKILL.md` when a diff touches UI / CSS / client-side
interaction code. 前端改動常有一整類問題**只在真裝置或非 Chrome 瀏覽器出現**，靜態檢查與
桌機 Chrome 都驗不到。Read this file when reviewing such a diff, or before declaring a
frontend change "done".

---

## 1. 「桌機縮視窗重現不了」是指紋：去枚舉 device-only 行為

**規則**：回報是「實機壞掉，但桌機把視窗縮成手機寬度不會發生」時，這句話本身就是根因的
類別——問題不在寬度、不在 media query、不在顏色規則，而在**只有真裝置才有的瀏覽器行為**。
繼續在桌機縮視窗上猜是空轉。

**已知的 device-only 行為**（先從這張表比對）：

- **`100vh` ≠ 可視高度**：手機把 `100vh` 解析成網址列收起時的大視窗，元素可以比螢幕還高。
  若它同時是 `overflow-y: auto` 的捲動容器，內容塞得進 max-height → 捲軸永不啟動 → 底部
  內容落在畫面外且捲不到。改用 `dvh`。
- **`backdrop-filter` ＋ transform 過的祖先**：iOS 可能取樣到錯的圖層，模糊板畫出「元素背後
  的頁面」而非元素自己的表面（淺色模式尤其明顯）。滑入式面板尤其中招——改用不透明填色。
- **`resize` 會被網址列伸縮觸發**：手機一捲動就發 resize。「resize → 關閉選單」會讓選單
  一捲動就自己關掉。只在**寬度**真的改變時才反應。
- **外部 SVG sprite 的 `<use>`**：見下一節。

**怎麼套用**：

- 先用硬證據排除版本歪斜：把線上實際送出的 asset 與本機 build 逐 byte／逐規則比對，確認
  手機與桌機拿到同一份檔案——不然會把「沒部署到」誤診成「程式碼有 bug」。
- 這類推論**無法在桌機證實**：修完要如實說「這需要實機驗證」，不要宣稱已修好。

## 2. 跨文件的 SVG `<use>` 在 WebKit 可能不渲染

**經驗性觀察（非通則）**：曾在某些情境下觀察到 `<use href="/path/icons.svg#name">`（跨文件
參照）在 WebKit 系瀏覽器不渲染，icon 靜默變空白——不報錯、無 console 訊息，元素仍在、仍可點；
同一份在桌機 Chrome／Firefox 正常，所以桌機模擬測不出。iOS 上所有瀏覽器底層都是 WebKit，
換瀏覽器不會繞過。實際是否發生取決於情境（例如跨來源載入、瀏覽器版本），**遇到前先在
目標裝置實測，不要直接把它當已證實的通則**。

**症狀辨識**：手機上 icon 空白、桌機正常、元素查得到也點得到。**只有 icon、沒有可見文字**的
控制項（label 被藏起來給螢幕閱讀器）最先「消失」。

**怎麼套用**：

- 症狀符合時，以 inline sprite 為保險（隱藏的 `<svg>` 容器放 `<symbol>`），`<use href="#name">` 用同
  文件參照。
- 隱藏容器用 `position:absolute; width:0; height:0; overflow:hidden`，不要用
  `display:none`——symbol 仍須可被參照。
- sprite 若是產生檔，讓 build 同時吐出獨立檔與 inline partial，並加測試擋兩者飄移。

## 3. 前端改動要在 Firefox 與手機觸控實測才算完成

**規則**：互動元件、彈窗、動畫類的 UI 改動，完成前要實際在 Firefox 與手機觸控環境驗收，
並檢查動畫流暢度。只靠 Chrome 桌機加靜態 HTML／CSS 檢查就宣稱「好了」，會漏掉一整類問題。

**理由**：靜態 grep 只能證明標記或設定有進 output，不能證明互動體驗正常。典型漏網：
瀏覽器間對 `matchMedia("(hover:hover)")` 的行為不同，導致互動在某瀏覽器整個失效；按鈕
`line-height:0` 讓觸控命中區趨近零高度；縮放動畫期間套 `backdrop-filter: blur` 讓每個影格
重算合成而卡頓。

**怎麼套用**：

- **Firefox**：互動／hover／`matchMedia` 類邏輯一定要在 Firefox 跑一遍。
- **手機觸控**：用實機，或 devtools 的 device toolbar（先切手機模式**再重整**，因為
  `matchMedia` 多在載入時評估一次）；確認命中區夠大、彈窗位置合理。
- **動畫**：避免在 transform／scale 動畫期間套 `backdrop-filter` 等高成本合成；卡頓感優先
  懷疑這類。
- Review 時看到宣稱「前端改動完成」卻沒有列出 Firefox／觸控驗收，要求補上或明說未驗。
