"""問答建立新規則。"""

from .commands import backfill, cmd_sync
from .config import ACTIONS, CATEGORIES, FIELD_BY_KEY, FIELDS
from .prompts import ask, choose, split_values, yes
from .rules import describe_filter, describe_rule, load_rules, normalize_label, save_rules, to_query


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
