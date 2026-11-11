# gmail-ruler

[gmailctl](https://github.com/mbrt/gmailctl) 的簡易包裝：

- **問答建立規則**：回答幾個固定問題（比對什麼、怎麼處理），自動產生 gmailctl 規則，並用一句中文唸給你確認
- **同步到 Gmail**：之後的新信自動套用（底層就是 `gmailctl apply`）
- **套用到既有信件**：gmailctl 不支援這件事，這裡用 Gmail API 補上，先預覽每條規則會影響幾封信，確認後才執行

```
gmr.py                 # 主程式
gmailctl/              # gmailctl 設定目錄（gmailctl --config gmailctl）
  config.jsonnet       # 讀 rules.json 轉成 gmailctl 格式，一般不用改
  rules.json           # 規則本體，由 gmr.py 管理（含個人寄件者，不進 git，請自行備份）
  credentials.json     # OAuth 用戶端（不進 git）
  token.json           # gmailctl 的授權（不進 git）
  backfill-token.json  # 套用既有信件用的授權（不進 git）
```

## 安裝

```bash
brew install gmailctl
pip3 install -r requirements.txt
```

### 建立 OAuth 用戶端（只要做一次）

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 建一個專案，啟用 **Gmail API**
2. Google Auth Platform → 建立 OAuth 用戶端，類型選 **桌面應用程式**
3. 「目標對象」把自己的 Gmail 加進測試使用者
4. 下載 JSON，存成 `gmailctl/credentials.json`
5. 授權 gmailctl：

   ```bash
   gmailctl --config gmailctl init
   ```

第一次執行「同步」或「套用到既有信件」時，`gmr.py` 會另外打開瀏覽器要求 `gmail.modify` 權限（用來建立標籤、修改舊信）。這份授權存在 `backfill-token.json`，跟 gmailctl 的分開。

## 使用

```bash
python3 gmr.py          # 互動選單
```

或直接下指令：

| 指令 | 作用 |
|---|---|
| `python3 gmr.py new` | 問答建立新規則 |
| `python3 gmr.py list` | 列出規則（中文描述 + Gmail 搜尋語法） |
| `python3 gmr.py remove 2` | 刪除第 2 條規則 |
| `python3 gmr.py diff` | 看本機規則和 Gmail 上篩選器的差異 |
| `python3 gmr.py sync` | 同步到 Gmail（會先顯示差異再請你確認） |
| `python3 gmr.py backfill` | 所有規則套用到既有信件 |
| `python3 gmr.py backfill 1 3` | 只套用第 1、3 條 |

建議加個 alias：`alias gmr="python3 ~/git/personal/gmail-ruler/gmr.py"`

### 問答範例

```
【1】要比對信件的哪個部分？
  1. 寄件者  2. 收件者  3. 主旨包含的文字  4. 信件任何地方包含的文字  5. 郵件清單
請輸入編號：1
寄件者是什麼？多個請用逗號分開：news@shop.com, deals.com
還要加其他條件嗎？ (y/N)：n
有沒有要排除的信？ (y/N)：y
要排除的是信件的哪個部分？ 3 → 訂單

【2】符合的信要怎麼處理？（可多選）：1,2,3
標籤名稱？：購物/電子報

----- 確認 -----
如果寄件者是「news@shop.com」或「deals.com」，而且不是主旨包含「訂單」
  → 貼上標籤「購物/電子報」、略過收件匣、標示為已讀
Gmail 搜尋語法：({from:news@shop.com from:deals.com} -subject:訂單)
```

可以先把搜尋語法貼到 Gmail 搜尋列，預覽會抓到哪些信。

## 用 AI agent 操作

不想自己跑指令，可以讓 AI agent 代勞。這個 repo 的 `AGENTS.md` 寫好了完整流程（建立、檢視、刪除規則、同步、套用到既有信件），`CLAUDE.md` 和 `GEMINI.md` 只是引用它，所以只需要維護一份。

### 怎麼用

1. 先完成上面的[安裝](#安裝)與 OAuth 設定
2. 在這個 repo 目錄下啟動你的 agent：

   | Agent | 指令 | 讀取的檔案 |
   |---|---|---|
   | Claude Code | `claude` | `CLAUDE.md` → `AGENTS.md` |
   | Gemini CLI | `gemini` | `GEMINI.md` → `AGENTS.md` |
   | OpenAI Codex CLI | `codex` | `AGENTS.md` |
   | Cursor、Copilot、Windsurf、Aider 等 | 照各自方式開啟此資料夾 | `AGENTS.md` |

3. 直接用自然語言說要做什麼，例如：
   - 「新增標籤 蝦皮，寄件者 b2ceci@ecimail1.tradevan.com.tw」
   - 「銀行標籤規則加入 mma@sinopac.com」
   - 「列出我現有的規則」
   - 「把規則 3 套用到既有信件」

agent 會一題一題問缺少的資訊，先給你看中文描述和 Gmail 搜尋語法，**你同意後**才會儲存、同步或動到信件。

### 需要你自己做的事

agent 沒辦法替你登入 Google，下面兩件事要你在終端機自己跑一次：

- `gmailctl --config gmailctl init`：授權 gmailctl
- 第一次 `python3 gmr.py sync --yes`：授權修改信件與標籤（會開瀏覽器）。在 agent 的 shell 裡會卡住，請自己跑

做完之後，其餘都可以交給 agent。

### 限制

- agent 必須能在你的電腦上執行指令。ChatGPT、Gemini 網頁版這類沒有 shell 的對話介面用不了
- `AGENTS.md` 是依各 agent 的文件撰寫，目前只在 Claude Code 上實測過。如果 Gemini CLI 沒讀到，在 `~/.gemini/settings.json` 設定 `"contextFileName": ["AGENTS.md", "GEMINI.md"]`
- 不要把 `credentials.json`、`token.json` 貼給任何 agent 或對話

## 注意事項

- **套用到既有信件**是以「單封信」為單位（Gmail 篩選器也是），會搜尋整個信箱，但不含垃圾桶和垃圾郵件。
- 「直接刪除」是移到垃圾桶，30 天內可以救回。選了刪除，其他動作就不會套用。
- 「轉寄」動作不會套用到舊信。
- `config.jsonnet` 刻意**沒有**加 gmailctl 的 `labels` 區塊，所以 gmailctl 不會刪除或改名你 Gmail 裡既有的標籤；規則用到的標籤會在 sync 前由 `gmr.py` 自動建立。
- 第一次 `sync` 時，gmailctl 會把 Gmail 上**不在 rules.json 裡的既有篩選器**列為要刪除。如果你已經有手動建立的篩選器，先跑 `gmailctl --config gmailctl download` 看一下，再決定要不要搬進 rules.json。
- 想手寫更複雜的 gmailctl 規則也可以直接編輯 `rules.json`，格式就是 gmailctl 的 `filter` / `actions`，再加一個 `name` 欄位。
