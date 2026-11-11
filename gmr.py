#!/usr/bin/env python3
"""
gmr — gmailctl 的簡易包裝

用固定的問答建立 Gmail 篩選規則（存成 gmailctl 格式），同步到 Gmail，
並且可以把規則套用到信箱裡既有的信件（gmailctl 本身不支援這件事）。

用法：
  python3 gmr.py            互動選單
  python3 gmr.py new        問答建立新規則
  python3 gmr.py list       列出規則
  python3 gmr.py remove N   刪除第 N 條規則
  python3 gmr.py diff       看本機規則和 Gmail 篩選器的差異
  python3 gmr.py sync       同步到 Gmail（gmailctl apply）
  python3 gmr.py backfill [N ...]  把規則套用到既有信件（預設全部規則）

非互動指令（給腳本或 Claude 呼叫）：
  python3 gmr.py preview '<rule json>'   驗證規則，印出中文描述與搜尋語法（不儲存）
  python3 gmr.py add '<rule json>'       驗證並新增規則
  python3 gmr.py list --json             以 JSON 輸出所有規則
  python3 gmr.py remove N --yes          不經確認直接刪除第 N 條
  python3 gmr.py backfill [N ...] --dry-run   只預覽會影響幾封信
  python3 gmr.py backfill [N ...] --yes       不經確認直接套用
  python3 gmr.py sync --yes              不經確認直接 gmailctl apply
"""

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
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


# ---------------------------------------------------------------------------
# 互動輸入
# ---------------------------------------------------------------------------

def ask(prompt, default=None, required=True):
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            ans = input(f"{prompt}{suffix}：").strip()
        except EOFError:
            print()
            sys.exit(1)
        if not ans and default is not None:
            return default
        if ans or not required:
            return ans
        print("  這一題必填喔。")


def yes(prompt, default=True):
    d = "Y/n" if default else "y/N"
    while True:
        ans = ask(f"{prompt} ({d})", required=False).lower()
        if not ans:
            return default
        if ans in ("y", "yes", "是", "好"):
            return True
        if ans in ("n", "no", "否", "不"):
            return False


def choose(prompt, options, multi=False):
    """options: [(key, text)]。multi=True 時可輸入 1,3 多選。回傳 key 或 key 的 list。"""
    print(prompt)
    for i, (_, text) in enumerate(options, 1):
        print(f"  {i}. {text}")
    hint = "（可多選，用逗號分開，例如 1,3）" if multi else ""
    while True:
        raw = ask(f"請輸入編號{hint}")
        try:
            nums = [int(x) for x in raw.replace("，", ",").split(",") if x.strip()]
        except ValueError:
            nums = []
        if nums and all(1 <= n <= len(options) for n in nums) and (multi or len(nums) == 1):
            keys = list(dict.fromkeys(options[n - 1][0] for n in nums))
            return keys if multi else keys[0]
        print("  編號不正確，請再輸入一次。")


def split_values(raw):
    """「a, b、c」→ ['a', 'b', 'c']"""
    for sep in ("，", "、", ";", "；"):
        raw = raw.replace(sep, ",")
    return [v.strip() for v in raw.split(",") if v.strip()]


# ---------------------------------------------------------------------------
# 規則檔
# ---------------------------------------------------------------------------

def load_rules():
    if not os.path.exists(RULES_FILE):
        return []
    with open(RULES_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_rules(rules):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = RULES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, RULES_FILE)


# ---------------------------------------------------------------------------
# 規則 → 中文句子
# ---------------------------------------------------------------------------

def describe_filter(node, top=True):
    if "and" in node:
        s = "，而且".join(describe_filter(n, False) for n in node["and"])
        return s if top else f"（{s}）"
    if "or" in node:
        parts = [describe_filter(n, False) for n in node["or"]]
        # 同一個欄位的 or：寄件者是 a 或 b
        keys = {next(iter(n)) for n in node["or"]}
        if len(keys) == 1 and next(iter(keys)) in FIELD_BY_KEY:
            key = next(iter(keys))
            vals = "或".join(f"「{n[key]}」" for n in node["or"])
            return f"{FIELD_BY_KEY[key][2]}{vals}"
        s = "，或".join(parts)
        return s if top else f"（{s}）"
    if "not" in node:
        return f"不是{describe_filter(node['not'], False)}"
    key = next(iter(node))
    if key in FIELD_BY_KEY:
        return f"{FIELD_BY_KEY[key][2]}「{node[key]}」"
    return f"{key}: {node[key]}"


def describe_actions(actions):
    parts = []
    if actions.get("delete"):
        parts.append("移到垃圾桶")
    for label in actions.get("labels", []):
        parts.append(f"貼上標籤「{label}」")
    if actions.get("archive"):
        parts.append("略過收件匣")
    if actions.get("markRead"):
        parts.append("標示為已讀")
    if actions.get("star"):
        parts.append("加上星號")
    if actions.get("markImportant") is True:
        parts.append("標示為重要")
    if actions.get("markImportant") is False:
        parts.append("不標示為重要")
    if actions.get("category"):
        parts.append(f"歸類到「{CATEGORY_TEXT.get(actions['category'], actions['category'])}」")
    return "、".join(parts) or "（沒有動作）"


def describe_rule(rule):
    return f"如果{describe_filter(rule['filter'])} → {describe_actions(rule['actions'])}"


# ---------------------------------------------------------------------------
# 規則 → Gmail 搜尋語法（給 backfill 用，語意和 gmailctl 編譯出來的篩選器一致）
# ---------------------------------------------------------------------------

def _term(value):
    value = value.replace('"', "")
    return f'"{value}"' if any(c.isspace() for c in value) else value


def to_query(node):
    if "and" in node:
        return "(" + " ".join(to_query(n) for n in node["and"]) + ")"
    if "or" in node:
        return "{" + " ".join(to_query(n) for n in node["or"]) + "}"
    if "not" in node:
        return "-" + to_query(node["not"])
    if "query" in node:
        return f"({node['query']})"
    key = next(iter(node))
    if key == "has":
        return _term(node[key])
    return f"{key}:{_term(node[key])}"


# ---------------------------------------------------------------------------
# 問答：建立規則
# ---------------------------------------------------------------------------

def ask_condition(title):
    field = choose(title, [(f[0], f[1]) for f in FIELDS])
    _, name, _, hint = FIELD_BY_KEY[field]
    values = []
    while not values:
        values = split_values(ask(f"{name}是什麼？多個請用逗號分開（{hint}）"))
    nodes = [{field: v} for v in values]
    return nodes[0] if len(nodes) == 1 else {"or": nodes}


def ask_filter():
    conditions = [ask_condition("\n【1】要比對信件的哪個部分？")]
    while yes("還要加其他條件嗎？", default=False):
        conditions.append(ask_condition("\n要比對信件的哪個部分？"))

    if len(conditions) == 1:
        flt = conditions[0]
    else:
        mode = choose("\n這些條件要怎麼組合？", [
            ("and", "全部條件都要符合"),
            ("or", "符合任何一個條件就好"),
        ])
        flt = {mode: conditions}

    if yes("\n有沒有要排除的信？（例如某個寄件者不要套用）", default=False):
        exclude = ask_condition("要排除的是信件的哪個部分？")
        if "and" in flt:
            flt["and"].append({"not": exclude})
        else:
            flt = {"and": [flt, {"not": exclude}]}
    return flt


def ask_actions():
    picked = choose("\n【2】符合的信要怎麼處理？", ACTIONS, multi=True)
    actions = {}
    if "delete" in picked:
        if len(picked) > 1:
            print("  選了「直接刪除」，其他動作就沒有意義了，只保留刪除。")
        print("  ⚠ 之後符合的新信都會直接進垃圾桶，請確認條件夠精準。")
        return {"delete": True}

    if "labels" in picked:
        labels = []
        while not labels:
            labels = split_values(ask("標籤名稱？多個用逗號分開，巢狀用「/」，例如 購物/電子報"))
        actions["labels"] = [normalize_label(l) for l in labels]
    if "archive" in picked:
        actions["archive"] = True
    if "markRead" in picked:
        actions["markRead"] = True
    if "star" in picked:
        actions["star"] = True
    if "important" in picked and "notImportant" in picked:
        print("  「標示為重要」和「不標示為重要」互相衝突，兩個都不套用。")
    elif "important" in picked:
        actions["markImportant"] = True
    elif "notImportant" in picked:
        actions["markImportant"] = False
    if "category" in picked:
        actions["category"] = choose("要歸類到哪個分頁？", CATEGORIES)
    return actions


def normalize_label(name):
    parts = [p.strip() for p in name.split("/") if p.strip()]
    return "/".join(parts)


def cmd_new():
    print("=== 建立新規則 ===")
    flt = ask_filter()
    actions = ask_actions()
    while not actions:
        print("  至少要有一個動作，請重新選擇。")
        actions = ask_actions()
    rule = {"filter": flt, "actions": actions}
    desc = describe_filter(rule["filter"])
    default_name = desc if len(desc) <= 40 else desc[:39] + "…"
    rule = {"name": ask("\n【3】幫這條規則取個名字", default=default_name), **rule}

    print("\n----- 確認 -----")
    print(describe_rule(rule))
    print(f"Gmail 搜尋語法：{to_query(rule['filter'])}")
    print("（可以先把搜尋語法貼到 Gmail 搜尋列，看看會抓到哪些信）")
    if not yes("要儲存這條規則嗎？"):
        print("已取消。")
        return

    rules = load_rules()
    rules.append(rule)
    save_rules(rules)
    print(f"已儲存為第 {len(rules)} 條規則。")

    if yes("\n要現在同步到 Gmail，讓之後的新信自動套用嗎？"):
        cmd_sync()
    if yes("要把這條規則套用到信箱裡既有的信嗎？"):
        backfill([len(rules)])


# ---------------------------------------------------------------------------
# 列出 / 刪除
# ---------------------------------------------------------------------------

def cmd_list(as_json=False):
    rules = load_rules()
    if as_json:
        out = [dict(r, number=i, description=describe_rule(r), query=to_query(r["filter"]))
               for i, r in enumerate(rules, 1)]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    if not rules:
        print("還沒有任何規則，用 `python3 gmr.py new` 新增。")
        return
    for i, r in enumerate(rules, 1):
        print(f"{i}. {r.get('name', '')}")
        print(f"   {describe_rule(r)}")
        print(f"   搜尋語法：{to_query(r['filter'])}")


def cmd_remove(args, assume_yes=False):
    rules = load_rules()
    if not rules:
        print("沒有規則可以刪除。")
        return
    if args:
        n = int(args[0])
    else:
        cmd_list()
        n = int(ask("要刪除第幾條？"))
    if not 1 <= n <= len(rules):
        print("沒有這一條。")
        return
    rule = rules[n - 1]
    print(describe_rule(rule))
    if assume_yes or yes("確定刪除這條規則？（只會移除規則，不會動到信件）", default=False):
        rules.pop(n - 1)
        save_rules(rules)
        print("已刪除。記得執行 sync 讓 Gmail 上的篩選器也一起移除。")


# ---------------------------------------------------------------------------
# 同步到 Gmail（gmailctl）
# ---------------------------------------------------------------------------

def gmailctl(*args):
    exe = shutil.which("gmailctl")
    if not exe:
        print("找不到 gmailctl，請先安裝：brew install gmailctl")
        sys.exit(1)
    return subprocess.call([exe, "--config", CONFIG_DIR, *args])


def cmd_diff():
    gmailctl("diff")


def cmd_sync(assume_yes=False):
    if not os.path.exists(os.path.join(CONFIG_DIR, "token.json")):
        print("gmailctl 還沒授權，請先執行：gmailctl --config gmailctl init")
        return
    labels = sorted({l for r in load_rules() for l in r["actions"].get("labels", [])})
    if labels:
        # gmailctl 只會引用既有標籤，所以先把缺的標籤建好
        service = gmail_service()
        ensure_labels(service, labels)
    gmailctl("apply", *(["--yes"] if assume_yes else []))


# ---------------------------------------------------------------------------
# 套用到既有信件（Gmail API）
# ---------------------------------------------------------------------------

def gmail_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("缺少套件，請先執行：pip3 install -r requirements.txt")
        sys.exit(1)

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"找不到 {CREDENTIALS_FILE}，請照 README 建立 OAuth 用戶端並下載 credentials.json。")
        sys.exit(1)

    creds = None
    if os.path.exists(BACKFILL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(BACKFILL_TOKEN_FILE, BACKFILL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("第一次使用需要授權修改 Gmail 信件（會打開瀏覽器）。")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, BACKFILL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(BACKFILL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        os.chmod(BACKFILL_TOKEN_FILE, 0o600)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def ensure_labels(service, names):
    """確保標籤存在（含巢狀標籤的上層），回傳 {名稱: label id}。"""
    existing = service.users().labels().list(userId="me").execute().get("labels", [])
    by_name = {l["name"]: l["id"] for l in existing}
    for name in names:
        parts = name.split("/")
        for i in range(1, len(parts) + 1):
            path = "/".join(parts[:i])
            if path not in by_name:
                created = service.users().labels().create(userId="me", body={
                    "name": path,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                }).execute()
                by_name[path] = created["id"]
                print(f"  建立標籤「{path}」")
    return {n: by_name[n] for n in names}


def actions_to_modify(service, actions):
    """把 gmailctl 動作轉成 Gmail API 的 add/remove label id。"""
    add, remove = [], []
    if actions.get("delete"):
        return ["TRASH"], []
    if actions.get("labels"):
        add += list(ensure_labels(service, actions["labels"]).values())
    if actions.get("archive"):
        remove.append("INBOX")
    if actions.get("markRead"):
        remove.append("UNREAD")
    if actions.get("star"):
        add.append("STARRED")
    if actions.get("markImportant") is True:
        add.append("IMPORTANT")
    if actions.get("markImportant") is False:
        remove.append("IMPORTANT")
    if actions.get("category"):
        target = CATEGORY_LABEL_IDS[actions["category"]]
        add.append(target)
        remove += [c for c in CATEGORY_LABEL_IDS.values() if c != target]
    return add, remove


def search_ids(service, query):
    ids, token = [], None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=500, pageToken=token).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            return ids


def backfill(numbers=None, assume_yes=False, dry_run=False):
    rules = load_rules()
    if not rules:
        print("還沒有任何規則。")
        return
    numbers = numbers or list(range(1, len(rules) + 1))
    service = gmail_service()

    plan = []
    print("\n=== 套用到既有信件：預覽 ===")
    for n in numbers:
        rule = rules[n - 1]
        query = to_query(rule["filter"])
        ids = search_ids(service, query)
        plan.append((n, rule, ids))
        print(f"{n}. {describe_rule(rule)}")
        print(f"   搜尋語法：{query} → 符合 {len(ids)} 封")
        if rule["actions"].get("forward"):
            print("   （轉寄動作不會套用到舊信）")

    total = sum(len(ids) for _, _, ids in plan)
    if total == 0:
        print("沒有符合的既有信件。")
        return
    if dry_run:
        print(f"\n（預覽模式）共 {total} 封會受影響，沒有做任何修改。")
        return
    deleting = sum(len(ids) for _, r, ids in plan if r["actions"].get("delete"))
    if deleting:
        print(f"\n⚠ 其中 {deleting} 封會被移到垃圾桶（30 天內可以救回）。")
    if not assume_yes and not yes(f"\n確定要處理這 {total} 封信嗎？", default=False):
        print("已取消。")
        return

    for n, rule, ids in plan:
        if not ids:
            continue
        add, remove = actions_to_modify(service, rule["actions"])
        if not add and not remove:
            continue
        for i in range(0, len(ids), 1000):  # batchModify 一次最多 1000 封
            body = {"ids": ids[i:i + 1000]}
            if add:
                body["addLabelIds"] = add
            if remove:
                body["removeLabelIds"] = remove
            service.users().messages().batchModify(userId="me", body=body).execute()
        print(f"  第 {n} 條規則：已處理 {len(ids)} 封")
    print("完成。")


def cmd_backfill(args, assume_yes=False, dry_run=False):
    rules = load_rules()
    nums = []
    for a in args:
        n = int(a)
        if not 1 <= n <= len(rules):
            print(f"沒有第 {n} 條規則。")
            return
        nums.append(n)
    backfill(nums or None, assume_yes=assume_yes, dry_run=dry_run)


# ---------------------------------------------------------------------------
# 非互動：驗證 / 預覽 / 新增
# ---------------------------------------------------------------------------

ACTION_KEYS = {"labels", "archive", "markRead", "star", "markImportant", "category", "delete"}


def validate_filter(node, path="filter"):
    if not isinstance(node, dict) or len(node) != 1:
        raise ValueError(f"{path} 必須是只有一個 key 的物件")
    key, val = next(iter(node.items()))
    if key in ("and", "or"):
        if not isinstance(val, list) or len(val) < 2:
            raise ValueError(f"{path}.{key} 至少要有兩個條件")
        for i, n in enumerate(val):
            validate_filter(n, f"{path}.{key}[{i}]")
    elif key == "not":
        validate_filter(val, f"{path}.not")
    elif key in FIELD_BY_KEY:
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{path}.{key} 必須是非空字串")
    else:
        raise ValueError(f"{path} 不支援的欄位 {key}（可用：{', '.join(FIELD_BY_KEY)}、and、or、not）")


def validate_rule(rule):
    if not isinstance(rule, dict):
        raise ValueError("規則必須是 JSON 物件")
    if not str(rule.get("name", "")).strip():
        raise ValueError("缺少 name")
    validate_filter(rule.get("filter"))
    actions = rule.get("actions")
    if not isinstance(actions, dict) or not actions:
        raise ValueError("actions 至少要有一個動作")
    unknown = set(actions) - ACTION_KEYS
    if unknown:
        raise ValueError(f"不支援的動作：{', '.join(sorted(unknown))}")
    if actions.get("delete") and len(actions) > 1:
        raise ValueError("delete 不能和其他動作一起使用")
    if "labels" in actions:
        labels = actions["labels"]
        if not isinstance(labels, list) or not labels or not all(isinstance(l, str) and l.strip() for l in labels):
            raise ValueError("labels 必須是非空的字串陣列")
        actions["labels"] = [normalize_label(l) for l in labels]
    if "category" in actions and actions["category"] not in CATEGORY_TEXT:
        raise ValueError(f"category 必須是 {', '.join(CATEGORY_TEXT)} 其中之一")
    if "markImportant" in actions and not isinstance(actions["markImportant"], bool):
        raise ValueError("markImportant 必須是 true 或 false")
    for k in ("archive", "markRead", "star", "delete"):
        if k in actions and actions[k] is not True:
            raise ValueError(f"{k} 只能是 true（不需要就不要放）")
    return {"name": rule["name"].strip(), "filter": rule["filter"], "actions": actions}


def parse_rule_arg(args):
    if not args:
        raise ValueError("請提供規則 JSON")
    raw = args[0]
    if raw == "-":
        raw = sys.stdin.read()
    try:
        return validate_rule(json.loads(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 格式錯誤：{e}")


def cmd_preview(args):
    rule = parse_rule_arg(args)
    print(describe_rule(rule))
    print(f"搜尋語法：{to_query(rule['filter'])}")


def cmd_add(args):
    rule = parse_rule_arg(args)
    rules = load_rules()
    rules.append(rule)
    save_rules(rules)
    print(f"已新增第 {len(rules)} 條規則：{describe_rule(rule)}")
    print(f"搜尋語法：{to_query(rule['filter'])}")


# ---------------------------------------------------------------------------
# 主選單
# ---------------------------------------------------------------------------

def menu():
    while True:
        print()
        choice = choose("=== Gmail 規則小幫手 ===", [
            ("new", "建立新規則"),
            ("list", "檢視現有規則"),
            ("remove", "刪除規則"),
            ("sync", "同步規則到 Gmail（之後的新信自動套用）"),
            ("backfill", "把規則套用到既有信件"),
            ("quit", "離開"),
        ])
        print()
        if choice == "quit":
            return
        if choice == "backfill":
            cmd_list()
            raw = ask("要套用哪幾條？直接按 Enter 代表全部", required=False)
            nums = [int(x) for x in split_values(raw)] if raw else []
            cmd_backfill([str(n) for n in nums])
        elif choice == "remove":
            cmd_remove([])
        else:
            COMMANDS[choice]()


COMMANDS = {
    "new": cmd_new,
    "list": cmd_list,
    "diff": cmd_diff,
    "sync": cmd_sync,
}


def main(argv):
    if not argv:
        return menu()
    cmd = argv[0]
    flags = {a for a in argv[1:] if a.startswith("--")}
    args = [a for a in argv[1:] if not a.startswith("--")]
    assume_yes = "--yes" in flags
    try:
        if cmd == "new":
            return cmd_new()
        if cmd == "list":
            return cmd_list(as_json="--json" in flags)
        if cmd == "diff":
            return cmd_diff()
        if cmd == "sync":
            return cmd_sync(assume_yes=assume_yes)
        if cmd == "remove":
            return cmd_remove(args, assume_yes=assume_yes)
        if cmd == "backfill":
            return cmd_backfill(args, assume_yes=assume_yes, dry_run="--dry-run" in flags)
        if cmd == "preview":
            return cmd_preview(args)
        if cmd == "add":
            return cmd_add(args)
    except ValueError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(2)
    print(__doc__)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print("\n已中斷。")
