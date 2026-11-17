# Strict Review — Re-review 細節

Loaded on demand by [`skills/strict-review/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md) — 複審（含 delta re-review、mutation／canary／fixture liveness 證據要求）時讀。核心硬規則（未清項目維持 NEEDS_CHANGES／BLOCKED）仍在 SKILL.md。
本檔內文原樣自 SKILL.md 搬出。

When new commits or a new maintainer review arrive on a PR **already
reviewed before**, do a delta re-review against the stored report rather
than reviewing from scratch — the two-step ancestor+date check, the
rebase-range pitfall, and `isResolved` reliability (see below) are in
`references/review-modes.md` and `references/review-judgment.md`.

When the whole review (or a delta re-review) is handed to a single subagent —
minimum delegation clauses, text hand-back instead of a report file, which
claims the orchestrator re-checks, stacked PRs whose upstream already merged —
see `references/review-agent-handoff.md`.

**Mutation test 作為修法驗證證據**：光看「新增的斷言轉綠」不夠——測試可能本來就不會失敗，
或斷言弱到修法被拆掉也不會紅（安慰劑測試）。要求：暫時拆掉修法本體 → 對應測試必須轉紅
（證明測試真的在守這條修法）→ 復原修法 → 測試轉綠。復原動作依上方「共用 working tree 上的
審查紀律」的安全流程執行，並用備份檔／`git diff` byte-compare 證明復原乾淨、無殘留改動——
這份 mutation-test 證據是修正輪 evidence 的必要項，不是加分項。（第一輪新行為測試的 mutation 表另見下方「Pre-PR sweeps」段，有自己的適用範圍。）

**Canary 回報要點名哪個斷言轉紅，不是只看檔案級 exit code**——同一個 bug 常補了不只一支
測試，跑 canary 只記「這個測試檔轉紅」會蓋掉「其中只有一支真的有鑑別力」這件事：兩條
code path 可能在某個測試餵的 input 上收斂到同一個值，這種測試無法區分修法與 bug，看起來
像覆蓋、實際是裝飾。要求：逐測試（或 `-v`/`--tb=line`）跑 canary，記一張 baseline→
post-mutation 的小表；對每一支在 mutation 下仍是綠的測試，追問「為什麼」並講清楚它守的是
別的東西還是什麼都沒守住；跑之前先預測預期的紅/綠分布，一支「本該綠卻紅」或「本該紅卻綠」
本身就是資訊。命中一次後，回覆裡順手給一個兩條 path 真的會分岔的 input，讓下一輪能直接
驗證鑑別力，而不是重新摸索。review 意見一次點出「缺少什麼」與「有沒有被真的 pin 住」兩層
要求時，修完要對每一層各做一次**型態不同**的 mutation（拿掉整段程式碼 vs 把邏輯換成寫死
常數／固定值），不能用同一次 mutation 的結果覆蓋兩層——呼叫端的預設值可能與斷言值巧合相同
（例如寫死 `1` 剛好等於預設 `1`），必須改用非預設值才能讓兩條路徑分岔。

**重構搬動守門邏輯時，canary 要打在新位置，不是這次 diff 動過的行。** 某個 default／
守門判斷若同一輪被搬進另一個函式，canary 打在舊位置只會讓不相關的斷言變紅——看起來像
驗過了，但被證明的性質其實還是沒被測到。判準：canary 的落點由「被證明的性質現在住在
哪一行」決定，不是由「這次 diff 改了哪些行」決定。對同一個守門點打兩種變異（換值、拿掉
保護）能分別證明「接住的值是什麼」與「缺值會不會被接住」兩件不同的事，兩者紅的支數落差
本身就是覆蓋率的證據。

**Fixture liveness：production 改呼叫另一個 callable 時，patch 舊 callable 的 fixture
會靜默死掉，測試仍全綠。** 測試綠只證明斷言成立，不證明斷言仍由測試控制的那條路徑
產生——fixture 死掉之後，那些測試在測真實實作，不是在測宣稱要測的 dispatch。要求：把
受影響 fixture 的 stub 改成無條件 `raise AssertionError`，重跑該 fixture 服務的整批
測試，**紅的支數必須 > 0**；0 支紅代表這個 patch 已經是死碼、測試對它零控制。修好
（讓 patch 指向真正被呼叫的 callable）之後再跑一次同一個 canary，確認這次真的轉紅。
classmethod 與 instance method 是不同的 callable，patch 一個攔不到另一個即使同名。
