---
name: change-site-enumeration
description: This skill should be used when about to declare "N sites need changing", "the scope is closed", or "this is already fully shared" — before writing a plan that lists change sites, before implementing against a plan's site list, before reviewing a diff for lingering per-section branches, or before an orchestrator reports a scope/size number to the user.
---

<!-- mkdocs-include-start -->

# Change-Site Enumeration

**Owner agents**: Tomori (planning) / Anon (implementation) / Soyo (review)
**Consumers**: orchestrator — before declaring a scope/size number to the user

## 核心判準

適用時機：你準備說出「有 N 處要改」、「範圍是封閉的」、「已經共用化了」這類宣告。

**核心命題**：「有幾處要改」的宣告必須由**解析權威來源**得出——不能由清單轉述（plan 列的清單、
上一輪 review 點名的位置）得出，也不能由 grep 符號名（而非常數名/入口名）得出。三種常見的改動
形狀各自有不同的權威來源，查下表決定用哪一種枚舉方法。

## 依形狀查表選枚舉方法

| 改動形狀 | 枚舉方法 | 為什麼眼睛盤點會漏 |
|---|---|---|
| 使用者可見行為（搜尋／篩選／排序／顯示） | 從**使用者入口**反推：這個功能在站上/app 有幾個進入點？每個進入點綁到哪個 handler？資料來源各是什麼（DOM／索引／API）？入口數 > 1 就逐一確認。**不要**只 grep 相關符號名——那是從實作往外找，使用者的 bug 是從入口往內走。危險地帶：build 步驟（`postbuild`、索引產生腳本）、`_data` 之外的資料管線、第三方搜尋／索引套件——它們常常不讀頁面 HTML，改 template 對它們完全無效。 | 同一個使用者可見功能常有多套獨立實作，符號名不同、彼此不 import；grep 只找到走過的那一套，另一套安靜地不生效，不會有任何錯誤訊息。 |
| 平行程式碼收共用表 | **逐行 diff** 列出候選平行程式碼的**所有**差異 literal（欄位名、type id、yaml key、category 覆寫），列成清單後逐一問「這個能進表嗎？」——能進的全進，不能進的在註解寫明為什麼。判準寫成語意版：「這段邏輯還需要幾個 per-section 分支？」目標 0；不要寫成「reviewer 提的那個欄位收了沒」。**同源提醒**：收完別忘了同步那段解釋「為什麼需要各自的迴圈」的舊註解——理由消失後，留著的舊註解會誤導下一個讀者。 | 只收本輪 review 點名的那一個欄位，等於把同型 drift 留在原地——剩下的差異仍逼著程式碼保留 per-section 分支，下一個 reviewer 或下一個新 section 會再撞一次。 |
| 共用常數改 tuple arity／欄位數 | 用**常數名**（不是型別名、不是欄位名）`grep -rn` 全 repo（含 tests、含子專案之外），逐一標記「這裡是不是在解包」；改完再 grep 一次複查，確認沒有第 N+1 個站點。 | 解包站點不一定長得像解包：中繼變數（先存起來、下一行才拆）、comprehension 裡的 `for t, _ in ...`、參數化 fixture 的清單，都不會出現在「我以為會有的樣子」裡；tuple arity 錯誤是 runtime 才炸，路徑沒被測到時靜態檢查也不一定攔得下來。 |
| 同批下游的守衛／欄位對稱性 | 找出這批下游**全部**成員（同一個 base class 的子類、同一組 dispatch table 的 entry），逐一確認守衛/欄位是否存在；補一個就要補同批的全部。 | 不對稱本身即缺陷——只補被點名的那個，其餘成員在下一次同型輸入時仍會炸，且拋出的錯誤型別可能對不上（該是 `ValueError` 的地方變成 `TypeError`）。 |

## 各 consumer 怎麼套

**Tomori（規劃期）**：寫 plan 前先依上表枚舉落點，把用了哪種枚舉方法、枚舉出的清單寫進對應 step，
不要只寫「改 N 處」的數字結論——結論要附「怎麼查出來的」。

**Anon（實作期）**：**不要沿用 plan 列的清單**——plan 的枚舉可能是錯的（見 worked example 4：計畫
列 3 處解包站點，實作時重新 grep 才發現實際 5 處）。動手前自己依上表重新枚舉一次；若跟 plan 的
清單不一致，回報差異，不要靜默照 plan 做、也不要靜默照自己查的做而不說。

**Soyo（review 期）**：當作判準——問「這段邏輯還剩幾個 per-section 分支？」目標 0；問「這個常數／
入口的所有站點都改了嗎？」不接受「reviewer 上輪點名的那處改了」當作已窮盡的 evidence；diff 裡若
出現「已經共用化」「範圍封閉」這類宣告，要求作者展示枚舉方法，不是照單全收。

**Orchestrator**：對使用者宣告 scope／規模數字（例：「有 N 個檔案要改」「這 15 個都違規」）之前，
先用上表方法覆核一次；不要把 subagent 轉述的數字未經覆核就寫進對使用者的陳述——規模數字常常是
使用者接下來做決策（拆 PR、估工時）的依據，錯了要回頭改。

## 假訊號

**「有些關鍵字搜得到」不代表修正部分生效**——可能代表你根本沒碰到那條路徑，恰好搜到的詞跟你的
修正無關（例：某筆資料的 description 欄位碰巧含相關字串）。

## Worked examples

四個實例（apache/airflow PR #70498、#70190）詳見 `references/worked-examples.md`：

1. #70498 — provider 搜尋的兩套獨立機制（inline 過濾框 vs 全站 Pagefind 索引）
2. #70498 — 同一個搜尋缺口的兩個入口共用（DOM 過濾 + build-time 索引產生），reviewer 只點名一個
3. #70190 — 平行 dict-shaped section 的 drift 被抓兩次（先 class-path 欄位，再 integration 欄位）
4. #70190 — 共用常數改 tuple arity，計畫列 3 處解包站點，實作重新枚舉後發現實際 5 處
