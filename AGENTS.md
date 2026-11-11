# Gmail 規則管理（gmail-ruler）

這個 repo 用 `gmr.py`（gmailctl 的包裝）管理 Gmail 篩選規則。當使用者想整理、分類、自動刪除 Gmail 信件，或要新增、檢視、刪除、同步規則時，照這份文件做。

全程用繁體中文（台灣用語）回覆，每一步一句話加上問題，不要解釋 gmailctl 的內部運作。

## 檔案

- `gmr.py`：所有操作都透過它
- `gmailctl/rules.json`：規則本體（由 gmr.py 寫入，**不要手動改 `config.jsonnet`**）
- `gmailctl/credentials.json`、`token.json`、`backfill-token.json`：OAuth 憑證，不要讀出內容或 commit

所有指令都在 repo 根目錄執行。

## 跟使用者互動的方式

需要使用者選擇時：如果你的 agent 有結構化提問工具（例如選項選單），就用它；沒有的話，用編號清單列出選項，請使用者回編號。需要使用者自己在終端機執行的指令，直接把指令寫出來請他執行，不要代跑。

## 非互動指令（只用這些，不要用 `python3 gmr.py` 或 `new` 這種需要鍵盤輸入的模式）

| 指令 | 作用 |
|---|---|
| `python3 gmr.py preview '<json>'` | 驗證規則，印出中文描述和 Gmail 搜尋語法，不儲存 |
| `python3 gmr.py add '<json>'` | 驗證並新增規則，印出規則編號 |
| `python3 gmr.py list --json` | 列出所有規則（含 number、description、query） |
| `python3 gmr.py remove N --yes` | 刪除第 N 條規則 |
| `python3 gmr.py diff` | 本機規則和 Gmail 篩選器的差異 |
| `python3 gmr.py sync --yes` | 同步到 Gmail（gmailctl apply） |
| `python3 gmr.py backfill N [N...] --dry-run` | 預覽套用到既有信件會影響幾封 |
| `python3 gmr.py backfill N [N...] --yes` | 實際套用到既有信件 |

JSON 含中文或引號時，用 heredoc 從 stdin 傳入：

```bash
python3 gmr.py preview - <<'EOF'
{"name": "...", "filter": {...}, "actions": {...}}
EOF
```

**沒有「修改規則」指令。** 要改一條規則（例如多加一個寄件者）：用完整的新內容 `add`，再 `remove` 舊的。刪除後編號會往前遞補，要重新 `list --json` 確認編號。

## 第一次使用前的檢查

靜默檢查一次：`which gmailctl`、`ls gmailctl/`。

- 沒有 gmailctl → `brew install gmailctl`
- 缺 Python 套件（gmr.py 會提示）→ `pip3 install -r requirements.txt`
- 沒有 `gmailctl/credentials.json` → 請使用者照 README 建立 Google Cloud OAuth 桌面用戶端，下載 JSON 存到那個路徑
- 沒有 `gmailctl/token.json` → 請使用者**自己在終端機**執行 `gmailctl --config gmailctl init`（需要瀏覽器授權）
- 沒有 `gmailctl/backfill-token.json` → 第一次 `sync`／`backfill` 會開瀏覽器等授權，在 agent 的 shell 裡會卡住不動。請使用者**自己在終端機**執行 `python3 gmr.py sync --yes`（或 `backfill --dry-run`）完成授權，之後 agent 就能正常跑

只建立、檢視、刪除本機規則不需要任何授權，缺憑證時這些仍可以先做。

## 開場

如果使用者的訊息已經說清楚要做什麼（例如「把蝦皮的信都標成購物」），直接進對應流程。否則問：

> 要做什麼？ 建立新規則 / 檢視現有規則 / 刪除規則 / 把規則套用到既有信件

## 流程一：建立新規則

使用者可能一次講完。先從他的話抽出能確定的部分，**只問還缺的題目**。順序固定：

**Q1 比對哪個部分**（單選）：寄件者 / 主旨包含的文字 / 信件任何地方包含的文字 / 收件者或郵件清單

**Q2 值是什麼**：可以多個，逗號分開。寄件者可以是完整 email 或網域（`shop.com`）。

**Q3 其他條件**：不用了 / 再加一個條件 / 要排除某些信
- 再加條件 → 回到 Q1、Q2，然後問「全部都要符合」還是「符合任一個就好」
- 排除 → 問要排除哪個部分和值，包成 `not`

**Q4 怎麼處理**（可多選）：貼上標籤 / 略過收件匣（封存） / 標示為已讀 / 直接刪除（移到垃圾桶）
- 使用者也可以說：加星號、標示為重要、不標示為重要、歸類到促銷／社交／快訊／論壇／主要
- 選了刪除：只保留 `delete`，並提醒之後符合的新信都會直接進垃圾桶

**Q5 標籤名稱**（只有貼標籤才問）：巢狀用 `/`，例如 `購物/電子報`。先 `list --json` 看已用過的標籤當選項。

**Q6 規則名稱**：自己根據條件取簡短名稱，不用問。

建立前先 `list --json`：如果已有規則涵蓋同樣的寄件者和動作，先告訴使用者，不要重複建立。

### 規則 JSON 格式

```json
{"name": "購物電子報", "filter": { ... }, "actions": { ... }}
```

`filter` 是單一 key 的物件，可以巢狀：
- 欄位：`{"from": "x"}`、`{"to": "x"}`、`{"subject": "x"}`、`{"has": "x"}`、`{"list": "x"}`
- 多個值 → `{"or": [{"from": "a"}, {"from": "b"}]}`
- 組合 → `{"and": [...]}` / `{"or": [...]}`（至少兩個元素）
- 排除 → `{"not": {...}}`

`actions`（不需要的就不要放）：
- `"labels": ["購物/電子報"]`
- `"archive": true`、`"markRead": true`、`"star": true`
- `"markImportant": true` 或 `false`
- `"category": "personal" | "social" | "updates" | "forums" | "promotions"`
- `"delete": true`（只能單獨使用）

### 確認與儲存

1. 跑 `preview`，把**中文描述**和**搜尋語法**給使用者看，建議把搜尋語法貼到 Gmail 搜尋列預覽
2. 問「要儲存嗎？」，確認後跑 `add`
3. 問要不要同步到 Gmail（流程四）
4. 問要不要套用到既有信件（流程五，用 add 回傳的規則編號）

preview 回報錯誤時，依錯誤訊息修正 JSON，不要把錯誤訊息直接丟給使用者。

## 流程二：檢視規則

跑 `list --json`，用編號列出每條的 `name` 和 `description`。不用列 JSON 或搜尋語法，除非使用者問。

## 流程三：刪除規則

`list --json` → 讓使用者選要刪哪一條 → 再確認一次 → `remove N --yes`。提醒刪除規則不會動到信件，並問要不要同步，讓 Gmail 上的篩選器也移除。

## 流程四：同步到 Gmail

1. 跑 `diff`，用白話摘要會新增、修改、刪除哪些篩選器
2. **如果 diff 要刪除使用者不是用這個工具建立的篩選器**（第一次同步常見），特別指出，建議先 `gmailctl --config gmailctl download -o <暫存檔>` 看 Gmail 現有內容，把它們用 `add` 併進本機規則，diff 變乾淨再同步
3. 使用者明確同意後跑 `sync --yes`，再跑一次 `diff` 確認沒有差異

## 流程五：套用到既有信件

1. **一定先跑** `backfill N --dry-run`，告訴使用者每條規則會影響幾封
2. 包含 `delete` 的規則要講清楚「X 封會被移到垃圾桶，30 天內可以救回」
3. 使用者在這次對話裡明確同意後，才跑 `backfill N --yes`
4. 回報處理了幾封

## 原則

- 會修改信件或 Gmail 設定的步驟（`sync --yes`、`backfill --yes`、`remove --yes`、任何刪信）都要先讓使用者看到會發生什麼並明確同意。上一次的同意不適用於下一次。
- 使用者拒絕或中斷某個動作後，不要重試，等他下一句指示。
- 條件很寬（例如只比對 `has: "news"`）又要刪除時，提醒可能誤刪，建議先 dry-run 或改成貼標籤觀察幾天。
- 刪信一律用「移到垃圾桶」，不要永久刪除。
