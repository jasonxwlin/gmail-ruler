"""路徑與固定的選項表。"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "gmailctl")              # gmailctl --config 指向這裡
RULES_FILE = os.path.join(CONFIG_DIR, "rules.json")
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, "credentials.json")
BACKFILL_TOKEN_FILE = os.path.join(CONFIG_DIR, "backfill-token.json")
BACKFILL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
# 比對欄位：(gmailctl 欄位, 選單文字, 句子裡的寫法, 輸入提示)
FIELDS = [
    ("from", "寄件者", "寄件者是", "email 或網域，例如 news@shop.com 或 shop.com"),
    ("to", "收件者", "收件者是", "email，例如 me+shop@gmail.com"),
    ("subject", "主旨包含的文字", "主旨包含", "例如：電子報"),
    ("has", "信件任何地方包含的文字", "信件包含", "例如：unsubscribe"),
    ("list", "郵件清單（電子報的 List-ID）", "郵件清單是", "例如：news.shop.com"),
]
FIELD_BY_KEY = {f[0]: f for f in FIELDS}
CATEGORIES = [
    ("personal", "主要"),
    ("social", "社交網路"),
    ("updates", "最新快訊"),
    ("forums", "論壇"),
    ("promotions", "促銷內容"),
]
CATEGORY_TEXT = dict(CATEGORIES)
CATEGORY_LABEL_IDS = {
    "personal": "CATEGORY_PERSONAL",
    "social": "CATEGORY_SOCIAL",
    "updates": "CATEGORY_UPDATES",
    "forums": "CATEGORY_FORUMS",
    "promotions": "CATEGORY_PROMOTIONS",
}
ACTIONS = [
    ("labels", "貼上標籤"),
    ("archive", "略過收件匣（封存）"),
    ("markRead", "標示為已讀"),
    ("star", "加上星號"),
    ("important", "標示為重要"),
    ("notImportant", "一律不標示為重要"),
    ("category", "歸類到某個分頁（促銷內容、社交網路…）"),
    ("delete", "直接刪除（移到垃圾桶）"),
]
ACTION_KEYS = {"labels", "archive", "markRead", "star", "markImportant", "category", "delete"}
